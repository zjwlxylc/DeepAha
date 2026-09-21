"""Same-origin API and additive UI. Schema creation is an explicit CLI action."""
from pathlib import Path
from typing import Literal
from fastapi import Request
from fastapi.responses import JSONResponse,FileResponse
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select,update
from .auth import Actor
from .db import Store,notices,audit,row,rows
from .commerce import Commerce
from .contributions import Contributions
from .tracking import Tracking
from .integration import ProductPort
from .errors import DomainError,require

class Strict(BaseModel):model_config=ConfigDict(extra='forbid',strict=True)
class Key(Strict):key:str=Field(min_length=8,max_length=128)
class VersionKey(Key):version:int=Field(ge=1)
class OrderIn(VersionKey):
    code:str=Field(min_length=2,max_length=48)
    note:str=Field(default='',max_length=3000)
class CustomRequest(OrderIn):
    site_name:str=Field(min_length=1,max_length=200)
    site_url:str=Field(max_length=2048)
    consent:bool
class PlanIn(Strict):data:dict
class NewPlan(PlanIn):code:str=Field(min_length=2,max_length=48)
class PlanEdit(PlanIn):version:int=Field(ge=1)
class Status(Strict):
    version:int=Field(ge=1)
    status:Literal['DRAFT','PUBLISHED','ARCHIVED']
class ServiceIn(PlanIn):version:int|None=None
class Quote(VersionKey):
    amount_cents:int=Field(ge=1,le=10000000)
    months:int=Field(ge=1,le=36)
    site_limit:int=Field(ge=1,le=20)
    topic_limit:int=Field(ge=0,le=50)
    scope:str=Field(min_length=10,max_length=3000)
class Confirm(VersionKey):
    method:Literal['TRIAL','MANUAL']
    amount_cents:int=Field(ge=0,le=10000000)
    reference:str=Field(default='',max_length=128)
    reason:str=Field(min_length=5,max_length=1000)
class Reason(Key):reason:str=Field(min_length=5,max_length=1000)
class Submission(Key):
    name:str=Field(min_length=1,max_length=200)
    url:str=Field(min_length=1,max_length=2048)
    kind:Literal['SOURCE','CUSTOM']='SOURCE'
    note:str=Field(default='',max_length=2000)
    consent:bool
class Decision(VersionKey):
    decision:Literal['APPROVE','NEEDS_INFO','REJECT']
    note:str=Field(min_length=2,max_length=1000)
    public_brief:str=Field(default='',max_length=3000)
    approved_url:str=Field(default='',max_length=2048)
    tier:Literal['OFFICIAL_PRIMARY','OFFICIAL_AGGREGATOR','TRUSTED_SECONDARY','COMMUNITY_SIGNAL']='COMMUNITY_SIGNAL'
class Supplement(VersionKey):note:str=Field(min_length=5,max_length=2000)
class Topic(Key):
    name:str=Field(min_length=1,max_length=100)
    q:str=Field(default='',max_length=200)
    kind:str=Field(default='',max_length=100)
    region:str=Field(default='',max_length=100)
class Site(Key):submission_id:str=Field(min_length=1,max_length=128)
class Toggle(VersionKey):enabled:bool
class Prepare(Key):connection:str=Field(default='default',pattern=r'^[a-zA-Z0-9_-]{1,48}$')


def mount(app,product,settings=None,*,core=None,dns=None,demo=False):
    s=Store(product.db.engine);c=Commerce(s);f=Contributions(s)
    port=core or ProductPort(product,settings)
    t=Tracking(s,c,port,**({'dns':dns} if dns else {}))
    app.state.membership_store=s;app.state.membership_tracking=t
    def actor(req,write=False,role=None):
        u=product.authenticate(req.cookies.get('deepaha_session'),req.headers.get('x-csrf-token','') if write else None)
        a=Actor(u['username'],frozenset(u['roles']))
        if role:a.need(role)
        return a
    def call(fn,*args,**kwargs):
        s.assert_ready()
        try:return fn(*args,**kwargs)
        except ValueError:raise DomainError('输入不正确：请核对公开网址、字段类型和长度',400,'INVALID_INPUT') from None
    @app.exception_handler(DomainError)
    async def error(req,e):return JSONResponse({'error':e.code,'message':e.message},status_code=e.status)
    prefix='/api/membership'
    @app.get(prefix+'/info')
    def info():return {'version':'0.1.0','demo':demo,'payment':'MANUAL_ONLY','auto_renew':False,'baseline_integration_verified':True,'host_iteration':'services-r3'}
    @app.get(prefix+'/plans')
    def plans():return call(c.list_plans)
    @app.get(prefix+'/me')
    def me(req:Request):
        a=actor(req);return {'username':a.name,'roles':sorted(a.roles),'entitlements':call(c.entitlements,a),'grants':call(c.list_grants,a)}
    @app.post(prefix+'/custom-requests')
    def custom_request(d:CustomRequest,req:Request):
        from .requests import create_custom_request
        return call(create_custom_request,s,c,f,actor(req,True),**d.model_dump())
    @app.get(prefix+'/orders')
    def orders(req:Request):return call(c.list_orders,actor(req))
    @app.get(prefix+'/orders/{id}')
    def order(id:str,req:Request):return call(c.get_order,actor(req),id)
    @app.post(prefix+'/orders')
    def create_order(d:OrderIn,req:Request):return call(c.create_order,actor(req,True),**d.model_dump())
    @app.post(prefix+'/orders/{id}/accept')
    def accept(id:str,d:VersionKey,req:Request):return call(c.accept_quote,actor(req,True),id,**d.model_dump())
    @app.post(prefix+'/orders/{id}/cancel')
    def cancel(id:str,d:VersionKey,req:Request):return call(c.cancel,actor(req,True),id,**d.model_dump())
    @app.get(prefix+'/manage/plans')
    def all_plans(req:Request):actor(req,role='operator');return call(c.list_plans,admin=True)
    @app.post(prefix+'/manage/plans')
    def new_plan(d:NewPlan,req:Request):return call(c.create_plan,actor(req,True,'operator'),d.code,d.data)
    @app.put(prefix+'/manage/plans/{code}')
    def edit_plan(code:str,d:PlanEdit,req:Request):return call(c.revise_plan,actor(req,True,'operator'),code,d.version,d.data)
    @app.post(prefix+'/manage/plans/{code}/status')
    def plan_status(code:str,d:Status,req:Request):return call(c.set_status,actor(req,True,'operator'),code,d.status,d.version)
    @app.get(prefix+'/manage/services')
    def services(req:Request):actor(req,role='operator');return call(c.list_services)
    @app.post(prefix+'/manage/services')
    def save_service(d:ServiceIn,req:Request):return call(c.save_service,actor(req,True,'operator'),d.data,d.version)
    @app.get(prefix+'/manage/orders')
    def all_orders(req:Request):return call(c.list_orders,actor(req,role='operator'),manage=True)
    @app.get(prefix+'/manage/grants')
    def all_grants(req:Request):return call(c.list_grants,actor(req,role='operator'),manage=True)
    @app.post(prefix+'/manage/orders/{id}/quote')
    def quote(id:str,d:Quote,req:Request):return call(c.quote,actor(req,True,'operator'),id,**d.model_dump())
    @app.post(prefix+'/manage/orders/{id}/confirm')
    def confirm(id:str,d:Confirm,req:Request):return call(c.confirm,actor(req,True,'operator'),id,**d.model_dump())
    @app.post(prefix+'/manage/grants/{id}/revoke')
    def revoke(id:str,d:Reason,req:Request):return call(c.revoke,actor(req,True,'operator'),id,**d.model_dump())
    @app.get(prefix+'/submissions')
    def submissions(req:Request):return call(f.mine,actor(req))
    @app.post(prefix+'/submissions')
    def submit(d:Submission,req:Request):return call(f.submit,actor(req,True),**d.model_dump())
    @app.post(prefix+'/submissions/{id}/supplement')
    def supplement(id:str,d:Supplement,req:Request):return call(f.supplement,actor(req,True),id,**d.model_dump())
    @app.get(prefix+'/review/leads')
    def lead_queue(req:Request,state:str=''):return call(f.queue,actor(req,role='reviewer'),state)
    @app.post(prefix+'/review/leads/{id}/decision')
    def decision(id:str,d:Decision,req:Request):return call(f.decide,actor(req,True,'reviewer'),id,**d.model_dump())
    @app.post(prefix+'/manage/leads/{id}/adopt')
    def adopt(id:str,req:Request):return call(t.adopt,actor(req,True,'operator'),id)
    @app.post(prefix+'/manage/leads/{id}/enable')
    def enable(id:str,req:Request):return call(t.enable_source,actor(req,True,'operator'),id)
    @app.get(prefix+'/watches')
    def watches(req:Request):return call(t.mine,actor(req))
    @app.post(prefix+'/watches/topics')
    def topic(d:Topic,req:Request):return call(t.create_topic,actor(req,True),**d.model_dump())
    @app.post(prefix+'/watches/sites')
    def site(d:Site,req:Request):return call(t.create_site,actor(req,True),**d.model_dump())
    @app.post(prefix+'/watches/{id}/toggle')
    def toggle(id:str,d:Toggle,req:Request):return call(t.toggle,actor(req,True),id,**d.model_dump())
    @app.get(prefix+'/jobs')
    def jobs(req:Request):return call(t.list_jobs,actor(req))
    @app.get(prefix+'/manage/watches')
    def all_watches(req:Request):return call(t.mine,actor(req,role='operator'),manage=True)
    @app.post(prefix+'/manage/scan-topics')
    def scan_topics(req:Request):return call(t.scan_topics,actor(req,True,'operator'))
    @app.post(prefix+'/manage/scan-site-publications')
    def scan_site_publications(req:Request):return call(t.scan_site_publications,actor(req,True,'operator'))
    @app.post(prefix+'/manage/watches/{id}/prepare')
    def prepare(id:str,d:Prepare,req:Request):return call(t.prepare,actor(req,True,'operator'),id,**d.model_dump())
    @app.get(prefix+'/manage/jobs')
    def all_jobs(req:Request):return call(t.list_jobs,actor(req,role='operator'),manage=True)
    @app.post(prefix+'/manage/jobs/{id}/dispatch')
    def dispatch(id:str,req:Request):return call(t.dispatch,actor(req,True,'operator'),id)
    @app.post(prefix+'/manage/jobs/{id}/refresh')
    def refresh(id:str,req:Request):return call(t.refresh,actor(req,True,'operator'),id)
    @app.get(prefix+'/notices')
    def notices_list(req:Request):
        a=actor(req);s.assert_ready()
        with s.read() as conn:return rows(conn,select(notices).where(notices.c.owner==a.name).order_by(notices.c.created_at.desc()).limit(200))
    @app.post(prefix+'/notices/{id}/read')
    def mark_read(id:str,req:Request):
        a=actor(req,True);s.assert_ready()
        with s.write() as conn:
            require(row(conn,select(notices.c.id).where(notices.c.id==id,notices.c.owner==a.name)),'消息不存在',404)
            conn.execute(update(notices).where(notices.c.id==id).values(read_at=s.time()))
        return {'read':True}
    @app.get(prefix+'/manage/audit')
    def audits(req:Request):
        actor(req,role='operator');s.assert_ready()
        with s.read() as conn:return rows(conn,select(audit).order_by(audit.c.created_at.desc()).limit(200))
    static=Path(__file__).with_name('static')
    @app.get('/membership',include_in_schema=False)
    @app.get('/membership/',include_in_schema=False)
    def shell():
        from fastapi.responses import RedirectResponse
        if demo:return FileResponse(static/'index.html',headers={'Cache-Control':'no-store'})
        return RedirectResponse('/services',status_code=307)
    @app.get('/membership/{asset}',include_in_schema=False)
    def asset(asset:str):
        require(asset in ('app.js','style.css'),'文件不存在',404)
        return FileResponse(static/asset,headers={'Cache-Control':'no-cache'})
    return t
