"""Current public/read, overall-review and operations APIs. Same-origin UI."""
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
from typing import Literal
from urllib.parse import quote
from fastapi import FastAPI,Request,Response,Query,HTTPException
from fastapi.responses import JSONResponse,FileResponse,RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from deepaha.artifacts.object_store import ObjectIntegrityError
from .service import Product
from .config import Settings,ConnectionConfig
from .errors import Problem
from .storage import MAX_ARCHIVE
from .scout_package import MAX_UPLOAD
from .scout_api import mount_scout
from .scout_models import SCOUT_TABLE_NAMES
from .upgrade import ACTIONABLE_TABLE_NAMES,ACTION_LOOP_TABLE_NAMES,LAB_TABLE_NAMES
from .models import Meta
from .granularity import resolve_units, resolve_actionable_targets

class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class Login(Strict):
    username:str=Field(min_length=3,max_length=80)
    password:str=Field(min_length=1,max_length=256)
class Decide(Strict):
    decision:Literal['APPROVE','REJECT']
    preview_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    note:str=Field(default='',max_length=3000)
    request_key:str=Field(min_length=1,max_length=128)
class SourceInput(Strict):
    name:str=Field(min_length=1,max_length=300)
    url:str=Field(max_length=3000)
    brief:str=Field(default='',max_length=20000)
    allowed_hosts:list[str]=Field(default_factory=list,max_length=30)
class SourceState(Strict):
    enabled:bool
    reason:str=Field(min_length=1,max_length=1000)
    expected_version:int|None=None
class TaskInput(Strict):
    source_id:str
    url:str=Field(max_length=3000)
    request_key:str=Field(min_length=1,max_length=128)
    instruction:str=Field(default='',max_length=10000)
    kind:Literal['INVESTIGATE','RECHECK','SUPPLEMENT']='INVESTIGATE'
    budget_seconds:int=Field(default=1200,ge=60,le=1800)
class ActionInput(Strict):
    status:Literal['SAVED','PREPARING','APPLIED','WAITING','COMPLETED','DISMISSED']
    note:str=Field(default='',max_length=2000)
class Withdrawal(Strict):
    reason:str=Field(min_length=1,max_length=3000)
    expected_publication:str|None=None
class ConnectionInput(Strict):
    agent_id:str=Field(min_length=1,max_length=128)
    source_app:str=Field(min_length=1,max_length=128)
    api_key:str=Field(default='',max_length=4096)
    enabled:bool=False
class ReminderInput(Strict):days_before:int=Field(default=1,ge=1,le=30)
class ScheduleInput(Strict):hours:int=Field(ge=0,le=720)
class RecheckInput(Strict):
    request_key:str=Field(min_length=1,max_length=128)
    budget_seconds:int=Field(default=1200,ge=60,le=1800)
class LabGoldInput(Strict):
    target_id:str=Field(min_length=1,max_length=48)
    split:Literal['CALIBRATION','VALIDATION','LOCKED_ACCEPTANCE']='CALIBRATION'
    truth_origin:Literal['ENGINEERING_FIXTURE','OPERATOR_ANNOTATED','INDEPENDENT_HUMAN_GOLD']='OPERATOR_ANNOTATED'
    annotation:dict=Field(default_factory=dict)
    attestation_ref:str|None=Field(default=None,max_length=160)
    lock:bool=False
class LabRunInput(Strict):
    kind:Literal['CATALOG_SAFETY','GOLD_BENCHMARK']='CATALOG_SAFETY'
    max_targets:int=Field(default=50,ge=1,le=200)
    label:str=Field(default='',max_length=200)
class LabPairTruthInput(Strict):
    twin_key:str=Field(min_length=1,max_length=64)
    expected_eligibility:Literal['ELIGIBLE','LIKELY_ELIGIBLE','UNCERTAIN','INELIGIBLE']|None=None
    expected_recommendation:Literal['FEATURE','EXPLORE','HOLD']|None=None
    truth_origin:Literal['ENGINEERING_FIXTURE','OPERATOR_ANNOTATED','INDEPENDENT_HUMAN_GOLD']='OPERATOR_ANNOTATED'
    attestation_ref:str|None=Field(default=None,max_length=160)
    note:str=Field(default='',max_length=1000)

async def bounded_body(req,max_bytes):
    raw=bytearray()
    async for chunk in req.stream():
        raw.extend(chunk)
        if len(raw)>max_bytes:raise Problem('请求内容过大',413)
    return bytes(raw)


def create_app(settings=None,product=None):
    settings=settings or Settings.from_env()
    p=product or Product(settings.database_url,settings.data_dir/'objects')
    p.feedback_environment='PRODUCTION' if settings.mode=='production' else 'STAGING'
    connection=ConnectionConfig(settings.data_dir,settings.mode)
    root=Path(__file__).resolve().parents[4]
    static=root/'web'/'public'/'product'
    @asynccontextmanager
    async def lifespan(app):
        # Initialization is an explicit CLI action. GET/startup never creates users,
        # publishes demo data, runs a migration, or starts a paid investigation.
        if not inspect(p.db.engine).has_table('product_meta'):
            raise RuntimeError('Database not initialized. Run: python -m deepaha.product.cli init')
        tables=set(inspect(p.db.engine).get_table_names())
        if not SCOUT_TABLE_NAMES.issubset(tables):
            raise RuntimeError('来源资产数据结构尚未升级。停服务后运行：python -m deepaha.product.cli upgrade')
        if not ACTIONABLE_TABLE_NAMES.issubset(tables):
            raise RuntimeError('SG1行动目标数据结构尚未升级。停服务后运行：python -m deepaha.product.cli upgrade-sg1')
        if not ACTION_LOOP_TABLE_NAMES.issubset(tables):
            raise RuntimeError('SG6行动闭环数据结构尚未升级。停服务后运行：python -m deepaha.product.cli upgrade-sg6')
        if not LAB_TABLE_NAMES.issubset(tables):
            raise RuntimeError('SG7机会实验室数据结构尚未升级。停服务后运行：python -m deepaha.product.cli upgrade-sg7')
        with p.db.tx(False) as s:
            av=s.get(Meta,'actionable_schema_version')
            if not av or av.value!='2':
                raise RuntimeError('SG1行动目标数据结构版本不正确。运行：python -m deepaha.product.cli upgrade-sg1')
            lv=s.get(Meta,'action_loop_schema_version')
            if not lv or lv.value!='1':
                raise RuntimeError('SG6行动闭环数据结构版本不正确。运行：python -m deepaha.product.cli upgrade-sg6')
            lab=s.get(Meta,'opportunity_lab_schema_version')
            if not lab or lab.value!='2':
                raise RuntimeError('SG7.1机会实验室数据结构版本不正确。运行：python -m deepaha.product.cli upgrade-sg7')
        yield
        p.db.engine.dispose()
    app=FastAPI(title='DeepAha 机会星图',version='3.8.0-rc1',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
    app.state.product=p;app.state.settings=settings
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=settings.allowed_hosts)
    @app.exception_handler(json.JSONDecodeError)
    async def invalid_json(req,e):return JSONResponse({'error':'INVALID_JSON','message':'请求内容不是有效JSON'},status_code=400)
    @app.exception_handler(Problem)
    async def problem_handler(req,e):return JSONResponse({'error':e.code,'message':e.message},status_code=e.status)
    @app.exception_handler(ObjectIntegrityError)
    async def integrity_handler(req,e):return JSONResponse({'error':'OBJECT_INTEGRITY','message':'原件完整性检查失败，已停止读取'},status_code=409)
    @app.exception_handler(SQLAlchemyError)
    async def database_handler(req,e):return JSONResponse({'error':'DATABASE_UNAVAILABLE','message':'数据服务暂不可用，请稍后重试'},status_code=503)
    @app.middleware('http')
    async def protect(req,call_next):
        length=req.headers.get('content-length','0')
        upload=req.url.path=='/api/manage/scout/previews'
        ceiling=MAX_UPLOAD if upload else MAX_ARCHIVE+1024
        try:too_large=int(length)>ceiling or int(length)<0
        except ValueError:too_large=True
        if too_large:return JSONResponse({'message':'请求内容过大','error':'BODY_LIMIT'},413)
        # Bound chunked requests too, before JSON/form parsers allocate memory.
        if req.method in ('POST','PUT','PATCH'):
            if upload:
                try:user(req,'operator',True)
                except Problem as exc:return JSONResponse({'message':exc.message,'error':exc.code},exc.status)
            cap=MAX_UPLOAD if upload else (MAX_ARCHIVE if req.url.path.startswith('/api/intake/') else 2_100_000)
            try:body=await bounded_body(req,cap)
            except Problem as e:return JSONResponse({'message':e.message,'error':e.code},e.status)
            req._body=body
        if req.method not in ('GET','HEAD','OPTIONS'):
            origin=req.headers.get('origin')
            allowed=settings.origins or [str(req.base_url).rstrip('/')]
            if origin and origin not in allowed:return JSONResponse({'message':'请求来源不受信任','error':'ORIGIN_FAILED'},403)
        res=await call_next(req)
        res.headers['X-Content-Type-Options']='nosniff'
        res.headers['Referrer-Policy']='strict-origin-when-cross-origin'
        res.headers['X-Frame-Options']='DENY'
        res.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
        res.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        if req.url.path.startswith('/api/'):res.headers['Cache-Control']='no-store'
        return res
    def user(req,role=None,write=False):
        u=p.authenticate(req.cookies.get('deepaha_session'),req.headers.get('x-csrf-token','') if write else None)
        if role and role not in u['roles']:raise Problem('没有执行此操作的权限',403,'FORBIDDEN')
        return u['username']
    def reader(req):
        if not settings.public_catalog:user(req)
    def auth_cookies(res,data):
        res.set_cookie('deepaha_session',data['token'],max_age=43200,httponly=True,secure=settings.secure_cookie,samesite='lax',path='/')
        res.set_cookie('deepaha_csrf',data['csrf'],max_age=43200,httponly=False,secure=settings.secure_cookie,samesite='lax',path='/')
    @app.get('/api/site')
    def site():return {'name':'机会星图','public_catalog':settings.public_catalog,'registration':settings.allow_registration}
    @app.get('/health/live')
    def live():return {'live':True,'version':'3.8.0-rc1'}
    @app.get('/health/ready')
    def ready():
        from sqlalchemy import text
        with p.db.tx(False) as s:s.execute(text('SELECT 1'))
        return {'database_read':'ok'}
    @app.post('/api/auth/login')
    def login(data:Login,req:Request,res:Response):
        value=p.login(data.username,data.password,req.client.host if req.client else 'unknown')
        auth_cookies(res,value)
        return {k:value[k] for k in ['username','roles','csrf']}
    @app.post('/api/auth/register')
    def register(data:Login,req:Request,res:Response):
        if not settings.allow_registration:raise Problem('当前未开放自助注册',403)
        p.create_account(data.username,data.password,['user'])
        value=p.login(data.username,data.password,req.client.host if req.client else 'unknown');auth_cookies(res,value)
        return {k:value[k] for k in ['username','roles','csrf']}
    @app.get('/api/auth/me')
    def me(req:Request):
        a=p.authenticate(req.cookies.get('deepaha_session'))
        return {**a,'csrf':req.cookies.get('deepaha_csrf','')}
    @app.post('/api/auth/logout')
    def logout(req:Request,res:Response):
        user(req,write=True);p.logout(req.cookies['deepaha_session'])
        res.delete_cookie('deepaha_session',path='/');res.delete_cookie('deepaha_csrf',path='/')
        return {'logged_out':True}
    @app.get('/api/catalog')
    def catalog(req:Request,q:str=Query('',max_length=300),kind:str=Query('',max_length=100),region:str=Query('',max_length=100),offset:int=Query(0,ge=0,le=1_000_000),limit:int=Query(20,ge=1,le=50),read_version:int|None=None):
        reader(req);return p.catalog(q,kind,region,offset,limit,read_version)
    def bounded_field(f):
        return {**f,'value':f['value'][:6000],'value_total':len(f['value'])}
    def bounded_unit(x):
        return {**x,'field_total':len(x['fields']),'fields':[bounded_field(f) for f in x['fields'][:50]]}
    @app.get('/api/announcements/{id}')
    def announcement(id:str,req:Request):
        reader(req);c=p.announcement(id)
        c['field_total']=len(c.get('fields',[]));c['child_total']=len(c.get('children',[]))
        c['fields']=[bounded_field(f) for f in c.get('fields',[])[:50]]
        c['children']=[bounded_unit(x) for x in c.get('children',[])[:20]]
        return c

    @app.get('/api/catalog/{id}/text')
    def full_field_text(id:str,req:Request,field:str,offset:int=Query(0,ge=0),version:str|None=None):
        reader(req);c=p.detail(id)
        if version and c['version']!=version:raise Problem('内容版本已更新，请刷新',409,'CONTENT_CHANGED')
        all_fields=c.get('fields',[])+c.get('ancestor_fields',[])+c.get('common_fields',[])+[f for u in c.get('children',[]) for f in u.get('fields',[])]
        f=next((f for f in all_fields if f['id']==field),None)
        if not f:raise Problem('条目不存在',404)
        return {'text':f['value'][offset:offset+6000],'total':len(f['value']),'version':c['version']}
    @app.get('/api/catalog/{id}')
    def detail(id:str,req:Request):
        reader(req);c=p.detail(id)
        # All content is reachable through paged endpoints; first view is bounded.
        c['field_total']=len(c.get('fields',[]));c['ancestor_field_total']=len(c.get('ancestor_fields',[]));c['common_field_total']=len(c.get('common_fields',[]));c['child_total']=len(c.get('children',[]))
        c['fields']=[bounded_field(f) for f in c.get('fields',[])[:50]]
        c['ancestor_fields']=[bounded_field(f) for f in c.get('ancestor_fields',[])[:50]]
        c['common_fields']=[bounded_field(f) for f in c.get('common_fields',[])[:50]]
        c['children']=[bounded_unit(x) for x in c.get('children',[])[:20]]
        return c
    @app.get('/api/catalog/{id}/content')
    def content(id:str,req:Request,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=50),unit:str|None=None,scope:Literal['own','ancestor','common']='own',version:str|None=None):
        reader(req);c=p.detail(id)
        if version and c['version']!=version:raise Problem('内容版本已更新，请刷新',409,'CONTENT_CHANGED')
        fields={'own':c.get('fields',[]),'ancestor':c.get('ancestor_fields',[]),'common':c.get('common_fields',[])}[scope]
        if unit:
            child=next((x for x in c.get('children',[]) if x['id']==unit),None)
            if not child:raise Problem('子项不存在',404)
            fields=child['fields']
        return {'items':[bounded_field(f) for f in fields[offset:offset+limit]],'total':len(fields),'version':c['version'],'scope':scope}
    @app.get('/api/catalog/{id}/units')
    def units(id:str,req:Request,offset:int=Query(0,ge=0),limit:int=Query(20,ge=1,le=50),version:str|None=None):
        reader(req);c=p.detail(id)
        if version and c['version']!=version:raise Problem('内容版本已更新，请刷新',409,'CONTENT_CHANGED')
        return {'items':[bounded_unit(x) for x in c.get('children',[])[offset:offset+limit]],'total':len(c.get('children',[])),'version':c['version']}
    @app.get('/api/catalog/{id}/calendar')
    def calendar(id:str,req:Request):
        reader(req);return Response(p.calendar(id),media_type='text/calendar',headers={'Content-Disposition':'attachment; filename="deepaha-opportunity.ics"'})
    @app.get('/api/catalog/{id}/history')
    def target_history(id:str,req:Request,limit:int=Query(20,ge=1,le=100)):
        reader(req);return p.target_history(id,limit=limit)
    @app.get('/api/catalog/{id}/compare')
    def target_compare(id:str,req:Request,from_id:str=Query(min_length=1,max_length=64),to_id:str=Query(min_length=1,max_length=64)):
        reader(req);return p.compare_target_versions(id,from_id,to_id)
    @app.get('/api/review')
    def inbox(req:Request,status:str='PENDING',q:str=Query('',max_length=300),offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=50)):
        return p.inbox(actor=user(req,'reviewer'),status=status,q=q,offset=offset,limit=limit)
    @app.get('/api/review/catalog/summary')
    def review_catalog_summary(req:Request):
        return p.catalog_management_summary(actor=user(req,'reviewer'))
    @app.get('/api/review/catalog/groups')
    def review_catalog_groups(req:Request,q:str=Query('',max_length=300),kind:str=Query('',max_length=100),status:str=Query('',max_length=40),time_state:str=Query('',max_length=40),offset:int=Query(0,ge=0),limit:int=Query(20,ge=1,le=50)):
        return p.catalog_management_groups(actor=user(req,'reviewer'),q=q,kind=kind,status=status,time_state=time_state,offset=offset,limit=limit)
    @app.get('/api/review/catalog/groups/{root_id}/targets')
    def review_catalog_group_targets(root_id:str,req:Request,q:str=Query('',max_length=300),status:str=Query('',max_length=40),time_state:str=Query('',max_length=40),offset:int=Query(0,ge=0),limit:int=Query(20,ge=1,le=50)):
        return p.catalog_management_group_targets(root_id,actor=user(req,'reviewer'),q=q,status=status,time_state=time_state,offset=offset,limit=limit)
    @app.get('/api/review/catalog/targets')
    def review_catalog_targets(req:Request,q:str=Query('',max_length=300),kind:str=Query('',max_length=100),status:str=Query('',max_length=40),time_state:str=Query('',max_length=40),offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=50)):
        return p.catalog_management_targets(actor=user(req,'reviewer'),q=q,kind=kind,status=status,time_state=time_state,offset=offset,limit=limit)
    def reviewed_item(id,req,item,version=None):
        r=p.preview(id,actor=user(req))
        if version and version!=r['preview_hash']:raise Problem('预览版本已变化，请刷新',409,'STALE_PREVIEW')
        if not 0<=item<len(r['opportunities']):raise Problem('机会分项不存在',404)
        return r,r['opportunities'][item]
    @app.get('/api/review/{id}')
    def preview(id:str,req:Request,item:int=Query(0,ge=0)):
        r=p.preview(id,actor=user(req));opps=r['opportunities']
        r['scope']={'opportunities':len(opps),'children':sum(len(o['children']) for o in opps),
            'action_targets':sum(len(resolve_actionable_targets(resolve_units(o),o)) for o in opps),'fields':r['field_count'],
            'excluded':sum(f['excluded'] for o in opps for f in o['fields']+[f for c in o['children'] for f in c['fields']])}
        r['opportunity_total']=len(opps);r['item_index']=item
        if opps:
            if item>=len(opps):raise Problem('机会分项不存在',404)
            o=opps[item]
            r['opportunities']=[{**o,'field_total':len(o['fields']),'child_total':len(o['children']),
                'fields':[bounded_field(f) for f in o['fields'][:50]],'children':[bounded_unit(c) for c in o['children'][:20]]}]
        return r
    @app.get('/api/review/{id}/content')
    def review_content(id:str,req:Request,item:int=Query(0,ge=0),unit:str|None=None,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=50),version:str|None=None):
        r,o=reviewed_item(id,req,item,version);fs=o['fields']
        if unit:
            child=next((c for c in o['children'] if c['id']==unit),None)
            if not child:raise Problem('子项不存在',404)
            fs=child['fields']
        return {'items':[bounded_field(f) for f in fs[offset:offset+limit]],'total':len(fs),'version':r['preview_hash']}
    @app.get('/api/review/{id}/units')
    def review_units(id:str,req:Request,item:int=Query(0,ge=0),offset:int=Query(0,ge=0),limit:int=Query(20,ge=1,le=50),version:str|None=None):
        r,o=reviewed_item(id,req,item,version)
        return {'items':[bounded_unit(c) for c in o['children'][offset:offset+limit]],'total':len(o['children']),'version':r['preview_hash']}
    @app.get('/api/review/{id}/text')
    def review_text(id:str,req:Request,field:str,item:int=Query(0,ge=0),offset:int=Query(0,ge=0),version:str|None=None):
        r,o=reviewed_item(id,req,item,version)
        f=next((f for f in o['fields']+[f for c in o['children'] for f in c['fields']] if f['id']==field),None)
        if not f:raise Problem('条目不存在',404)
        return {'text':f['value'][offset:offset+6000],'total':len(f['value']),'version':r['preview_hash']}
    @app.post('/api/review/{id}/decision')
    def decide(id:str,data:Decide,req:Request):return p.decide(id,**data.model_dump(),actor=user(req,'reviewer',True))
    @app.get('/api/review/{id}/file')
    def original(id:str,req:Request,name:str=Query(max_length=2048)):
        b=p.raw_file(id,name,actor=user(req))
        return Response(b,media_type='application/octet-stream',headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(Path(name).name)})
    @app.post('/api/intake/{source_id}')
    async def intake(source_id:str,req:Request):
        actor=user(req,'operator',True)
        return await asyncio.to_thread(p.ingest,source_id,await req.body(),actor=actor)
    @app.post('/api/catalog/{id}/withdraw')
    def withdraw(id:str,data:Withdrawal,req:Request):return p.withdraw(id,**data.model_dump(),actor=user(req,'reviewer',True))
    @app.get('/api/manage/status')
    def status(req:Request):return {**p.runtime_status(actor=user(req,'operator')),'connection':connection.public()}
    @app.put('/api/manage/connection')
    def save_connection(data:ConnectionInput,req:Request):
        actor=user(req,'operator',True)
        with p.db.tx() as s:
            connection.save(**data.model_dump())
            p._audit(s,actor,'UPDATE_WMA_CONNECTION','wma','更新连接；密钥不写入操作记录')
        return connection.public()
    @app.post('/api/manage/check-connection')
    async def check_connection(req:Request):
        actor=user(req,'operator',True);f=connection.factory()
        if not f:raise Problem('请先保存并启用连接',409)
        client=None
        try:
            client=f();out=await client.inspect_release()
            with p.db.tx() as s:p._audit(s,actor,'CHECK_WMA_CONNECTION','wma','已读取发布Agent绑定；未发送调查')
            # Release metadata only. Never return an SDK object or request headers.
            return {'connected':True,'binding':out}
        except Exception as e:
            if isinstance(e,Problem):raise
            raise Problem('连接检查未通过，请核对密钥、Agent与SDK版本',503,getattr(e,'code','WMA_CONNECTION_FAILED')) from None
        finally:
            if client:await client.aclose()
    @app.post('/api/manage/check-storage')
    def check_storage(req:Request):return p.check_storage(actor=user(req,'operator',True))
    @app.get('/api/manage/sources')
    def sources(req:Request,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=50)):return p.list_sources(actor=user(req,'operator'),offset=offset,limit=limit)
    @app.post('/api/manage/sources')
    def add_source(data:SourceInput,req:Request):return p.add_source(**data.model_dump(),actor=user(req,'operator',True))
    @app.put('/api/manage/sources/{id}/status')
    def source_state(id:str,data:SourceState,req:Request):return p.source_status(id,**data.model_dump(),actor=user(req,'operator',True))
    @app.put('/api/manage/sources/{id}/schedule')
    def source_schedule(id:str,data:ScheduleInput,req:Request):return p.schedule_source(id,data.hours,actor=user(req,'operator',True))
    @app.post('/api/manage/source-assets')
    async def import_source_asset(req:Request):
        actor=user(req,'operator',True)
        try:asset=json.loads(await req.body())
        except ValueError:raise Problem('请上传有效JSON文件')
        return await asyncio.to_thread(p.import_sources,asset,actor=actor)
    @app.post('/api/manage/catalog/{id}/recheck')
    def targeted_recheck(id:str,data:RecheckInput,req:Request):
        return p.create_targeted_recheck(id,**data.model_dump(),actor=user(req,'operator',True))
    @app.get('/api/manage/tasks')
    def tasks(req:Request,offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=50)):return p.tasks(actor=user(req,'operator'),offset=offset,limit=limit)
    @app.post('/api/manage/tasks')
    def create_task(data:TaskInput,req:Request):return p.create_task(**data.model_dump(),actor=user(req,'operator',True))
    @app.get('/api/manage/tasks/{id}')
    def task(id:str,req:Request):return p.task_detail(id,actor=user(req,'operator'))
    @app.post('/api/manage/tasks/{id}/recover')
    def recover(id:str,req:Request):return p.recover_task(id,actor=user(req,'operator',True))
    @app.post('/api/manage/tasks/{id}/cancel')
    def cancel(id:str,req:Request):return p.cancel_task(id,actor=user(req,'operator',True))
    @app.get('/api/manage/legacy')
    def legacy_history(req:Request,offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=50)):
        user(req,'operator')
        from .legacy import inventory,list_runs
        return {**inventory(p.db.engine),'items':list_runs(p.db.engine,offset,limit)}
    @app.get('/api/manage/history')
    def history(req:Request,offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=50)):return p.history(actor=user(req,'operator'),offset=offset,limit=limit)
    @app.get('/api/manage/feedback-candidates')
    def feedback_candidates(req:Request,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100)):
        return p.feedback_candidates(actor=user(req,'operator'),offset=offset,limit=limit)
    @app.get('/api/manage/lab/summary')
    def lab_summary(req:Request):return p.lab_summary(actor=user(req,'operator'))
    @app.get('/api/manage/lab/twins')
    def lab_twins(req:Request,offset:int=0,limit:int=30):return p.lab_twins(actor=user(req,'operator'),offset=offset,limit=limit)
    @app.post('/api/manage/lab/twins/seed')
    def lab_seed_twins(req:Request):return p.lab_seed_twins(actor=user(req,'operator',True))
    @app.get('/api/manage/lab/candidates')
    def lab_candidates(req:Request,q:str='',limit:int=30):return p.lab_catalog_candidates(actor=user(req,'operator'),q=q,limit=limit)
    @app.get('/api/manage/lab/gold')
    def lab_gold(req:Request,offset:int=0,limit:int=30):return p.lab_gold_cases(actor=user(req,'operator'),offset=offset,limit=limit)
    @app.post('/api/manage/lab/gold')
    def lab_gold_add(data:LabGoldInput,req:Request):return p.lab_add_gold_case(data.target_id,actor=user(req,'operator',True),split=data.split,truth_origin=data.truth_origin,annotation=data.annotation,attestation_ref=data.attestation_ref,lock=data.lock)
    @app.get('/api/manage/lab/gold/{case_id}/pair-truths')
    def lab_pair_truths(case_id:str,req:Request):return p.lab_pair_truths(case_id,actor=user(req,'operator'))
    @app.post('/api/manage/lab/gold/{case_id}/pair-truths')
    def lab_pair_truth_set(case_id:str,data:LabPairTruthInput,req:Request):return p.lab_set_pair_truth(case_id,data.twin_key,data.expected_eligibility,actor=user(req,'operator',True),expected_recommendation=data.expected_recommendation,truth_origin=data.truth_origin,attestation_ref=data.attestation_ref,note=data.note)
    @app.post('/api/manage/lab/gold/{case_id}/lock')
    def lab_gold_lock(case_id:str,req:Request):return p.lab_lock_gold_case(case_id,actor=user(req,'operator',True))
    @app.delete('/api/manage/lab/gold/{case_id}')
    def lab_gold_retire(case_id:str,req:Request):return p.lab_retire_gold_case(case_id,actor=user(req,'operator',True))
    @app.get('/api/manage/lab/runs')
    def lab_runs(req:Request,limit:int=20):return p.lab_runs(actor=user(req,'operator'),limit=limit)
    @app.post('/api/manage/lab/runs')
    def lab_run(data:LabRunInput,req:Request):return p.lab_run_benchmark(actor=user(req,'operator',True),kind=data.kind,max_targets=data.max_targets,label=data.label)
    @app.get('/api/manage/lab/runs/{run_id}')
    def lab_run_detail(run_id:str,req:Request):return p.lab_run(run_id,actor=user(req,'operator'))
    @app.get('/api/manage/lab/founding-metrics')
    def lab_founding_metrics(req:Request):return p.lab_founding_metrics(actor=user(req,'operator'))
    @app.get('/api/me/lab')
    def my_lab(req:Request):return p.lab_me(actor=user(req))
    @app.post('/api/me/lab/join')
    def my_lab_join(req:Request):return p.lab_join(actor=user(req,write=True))
    @app.post('/api/me/lab/leave')
    def my_lab_leave(req:Request):return p.lab_leave(actor=user(req,write=True))

    @app.get('/api/me/profile')
    def profile(req:Request):return p.get_profile(actor=user(req))
    @app.put('/api/me/profile')
    async def update_profile(req:Request):return p.set_profile(await req.json(),actor=user(req,write=True))
    @app.get('/api/me/opportunities')
    def recommendations(req:Request,limit:int=Query(20,ge=1,le=50)):return p.recommendations(actor=user(req),limit=limit)
    @app.get('/api/me/actions')
    def actions(req:Request,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=50)):return p.my_actions(actor=user(req),offset=offset,limit=limit)
    @app.get('/api/me/actions/{id}/history')
    def action_history(id:str,req:Request):return p.action_history(id,actor=user(req))
    @app.get('/api/me/weekly-digest')
    def weekly_digest(req:Request):return p.weekly_digest(actor=user(req))
    @app.put('/api/me/actions/{id}')
    def set_action(id:str,data:ActionInput,req:Request):return p.set_action(id,**data.model_dump(),actor=user(req,write=True))
    @app.delete('/api/me/actions/{id}')
    def remove_action(id:str,req:Request):return p.remove_action(id,actor=user(req,write=True))
    @app.post('/api/me/feedback/{id}')
    async def feedback(id:str,req:Request):return p.feedback(id,await req.json(),actor=user(req,write=True))
    @app.get('/api/me/fit/{id}')
    def fit(id:str,req:Request):return p.fit(id,actor=user(req))
    @app.get('/api/me/value/{id}')
    def value(id:str,req:Request):return p.value(id,actor=user(req))
    @app.post('/api/me/reminders/{id}')
    def reminder(id:str,data:ReminderInput,req:Request):return p.set_reminder(id,**data.model_dump(),actor=user(req,write=True))
    @app.get('/api/me/notifications')
    def notifications(req:Request,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=50)):return p.notifications(actor=user(req),offset=offset,limit=limit)
    @app.post('/api/me/notifications/{id}/read')
    def mark(id:str,req:Request):return p.mark_read(id,actor=user(req,write=True))
    @app.get('/api/me/export')
    def export(req:Request):return JSONResponse(p.export_personal(actor=user(req)),headers={'Content-Disposition':'attachment; filename="deepaha-personal-data.json"'})
    @app.delete('/api/me/data')
    def erase(req:Request):return p.erase_personal(actor=user(req,write=True))
    @app.api_route('/api/legacy/{path:path}',methods=['GET','POST','PUT','PATCH','DELETE'],include_in_schema=False)
    def retired(path:str):raise Problem('旧采集与逐字段审核入口已退役',410,'ROUTE_RETIRED')
    # Exact historic families fail closed rather than silently falling through to SPA.
    @app.api_route('/api/v1/local-human-test/{path:path}',methods=['GET','POST','PUT','PATCH','DELETE'],include_in_schema=False)
    @app.api_route('/api/v1/review/{path:path}',methods=['POST','PUT','PATCH','DELETE'],include_in_schema=False)
    @app.api_route('/api/v1/investigations/{path:path}',methods=['POST','PUT','PATCH','DELETE'],include_in_schema=False)
    def old_api(path:str):raise Problem('旧操作入口已退役，请使用整体审核与系统管理',410,'ROUTE_RETIRED')
    mount_scout(app,p,user)
    @app.get('/api/{path:path}')
    def api_missing(path:str):raise Problem('接口不存在',404)
    if static.exists():app.mount('/product',StaticFiles(directory=static),name='product-assets')
    @app.get('/{path:path}')
    def page(path:str):
        if path.startswith(('review/human-test','review/assurance')):return RedirectResponse('/manage/history',status_code=307)
        return FileResponse(static/'index.html')
    return app
