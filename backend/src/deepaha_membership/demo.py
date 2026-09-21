"""Loopback-only demonstration with synthetic data, NEVER a production auth system."""
from pathlib import Path
from types import SimpleNamespace
import argparse,hashlib,hmac,secrets,time,threading
from fastapi import FastAPI,Request,Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from .db import Store
from .commerce import Commerce
from .api import mount
from .errors import DomainError,require

class DemoCore:
    def __init__(self):self.sources={};self.tasks={};self.lock=threading.Lock()
    def register(self,a,l):
        with self.lock:
            self.sources.setdefault(l['id'],{'id':'demo-src-'+l['id'],'enabled':False,'policy_version':1})
            return dict(self.sources[l['id']])
    def enable(self,a,l):
        with self.lock:self.sources[l['id']]['enabled']=True;return dict(self.sources[l['id']])
    def enqueue(self,a,l,key,connection):
        require(connection=='default','演示仅使用default连接')
        with self.lock:
            require(self.sources.get(l['id'],{}).get('enabled'),'请先明确启用该演示来源',409)
            self.tasks.setdefault(key,dict(id='demo-task-'+key,status='QUEUED'))
            return dict(self.tasks[key])
    def task(self,a,id):
        with self.lock:
            value=next((t for t in self.tasks.values() if t['id']==id),None)
            require(value,'演示进程重启后任务模拟状态丢失；请创建新演示目录',409)
            return dict(value)
    def catalog_for_source(self,lead,**kw):
        # Synthetic demonstration has no reviewed publication from these sources.
        return dict(items=[],total=0,read_version=1,has_more=False)
    def catalog(self,**kw):
        all_items=[dict(id='demo-op-1',title='演示数据｜校招品牌策划实习机会',type='校招',region='宁波',summary='合成演示，不是真实招募',version='demo-v1',status='CURRENT'),dict(id='demo-op-2',title='演示数据｜青年广告创意项目',type='竞赛',region='杭州',summary='合成演示，不是真实报名',version='demo-v1',status='CURRENT')]
        items=[x for x in all_items if all(not kw.get(k) or kw[k] in (str(x) if k=='q' else x.get('type' if k=='kind' else k,'')) for k in ('q','kind','region'))]
        offset=kw.get('offset',0);limit=kw.get('limit',50)
        return dict(items=items[offset:offset+limit],total=len(items),read_version=1,has_more=offset+limit<len(items))

class DemoProduct:
    def __init__(self,engine,credentials):
        self.db=SimpleNamespace(engine=engine);self.sessions={};self.failures={};self.lock=threading.Lock()
        self.passwords={}
        for name,pw in credentials.items():
            salt=secrets.token_bytes(16);self.passwords[name]=(salt,self.hash(pw,salt))
    @staticmethod
    def hash(pw,salt):return hashlib.scrypt(pw.encode(),salt=salt,n=16384,r=8,p=1)
    def login(self,name,password,ip):
        with self.lock:
            recent=[t for t in self.failures.get(ip,[]) if t>time.time()-60]
            require(len(recent)<10,'登录尝试过多，请稍后重试',429)
            stored=self.passwords.get(name)
            valid=stored and hmac.compare_digest(stored[1],self.hash(password,stored[0]))
            if not valid:self.failures[ip]=recent+[time.time()];raise DomainError('账号或密码不正确',401)
            token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
            roles=['operator'] if name=='maintainer' else (['reviewer'] if name=='reviewer' else [])
            self.sessions[token]=dict(username=name,roles=roles,csrf=csrf,expires=time.time()+43200)
            return {**self.sessions[token],'token':token}
    def authenticate(self,token,csrf=None):
        with self.lock:data=self.sessions.get(token)
        require(data and data['expires']>time.time(),'请先登录',401,'AUTH_REQUIRED')
        if csrf is not None:require(hmac.compare_digest(csrf,data['csrf']),'写操作校验失败，请重新登录',403,'CSRF_FAILED')
        return {k:data[k] for k in ('username','roles','csrf')}

class Login(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    username:str=Field(min_length=1,max_length=80)
    password:str=Field(min_length=1,max_length=256)

def create_demo(path,credentials):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    engine=create_engine('sqlite:///'+str(path),connect_args={'check_same_thread':False})
    s=Store(engine);s.initialize();Commerce(s).seed()
    p=DemoProduct(engine,credentials);core=DemoCore()
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    app.state.demo_product=p;app.state.demo_core=core
    @app.middleware('http')
    async def guard(req,call_next):
        if req.method not in ('GET','HEAD','OPTIONS'):
            origin=req.headers.get('origin')
            if origin and origin!=str(req.base_url).rstrip('/'):
                return JSONResponse({'message':'请求来源不受信任'},403)
            total=0;body=bytearray()
            async for chunk in req.stream():
                total+=len(chunk)
                if total>65536:return JSONResponse({'message':'请求过大'},413)
                body.extend(chunk)
            req._body=bytes(body)
        r=await call_next(req)
        r.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        r.headers['X-Content-Type-Options']='nosniff';r.headers['X-Frame-Options']='DENY';r.headers['Referrer-Policy']='no-referrer'
        if req.url.path.startswith('/api/'):r.headers['Cache-Control']='no-store'
        return r
    @app.exception_handler(SQLAlchemyError)
    async def db_error(req,e):return JSONResponse({'message':'数据服务暂不可用'},503)
    @app.post('/api/auth/login')
    def login(d:Login,req:Request,res:Response):
        v=p.login(d.username,d.password,req.client.host if req.client else '')
        res.set_cookie('deepaha_session',v['token'],httponly=True,samesite='strict',max_age=43200)
        res.set_cookie('deepaha_csrf',v['csrf'],httponly=False,samesite='strict',max_age=43200)
        return {k:v[k] for k in ('username','roles','csrf')}
    @app.get('/api/auth/me')
    def me(req:Request):return p.authenticate(req.cookies.get('deepaha_session'))
    @app.post('/api/auth/logout')
    def logout(req:Request,res:Response):
        token=req.cookies.get('deepaha_session');p.authenticate(token,req.headers.get('x-csrf-token',''))
        with p.lock:p.sessions.pop(token,None)
        res.delete_cookie('deepaha_session');res.delete_cookie('deepaha_csrf');return {'logged_out':True}
    @app.post('/api/membership/demo/jobs/{id}/complete')
    def complete(id:str,req:Request):
        u=p.authenticate(req.cookies.get('deepaha_session'),req.headers.get('x-csrf-token',''))
        require('operator' in u['roles'],'仅维护员可操作演示任务',403)
        with core.lock:
            value=next((t for t in core.tasks.values() if t['id']==id),None);require(value,'演示任务不存在',404);value['status']='READY'
        return {'simulated':True,'status':'READY'}
    mount(app,p,core=core,dns=lambda url:[],demo=True)
    return app

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',default='.demo');parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args();path=Path(args.data);path.mkdir(parents=True,exist_ok=True)
    names=('alice','bob','reviewer','maintainer');credentials={n:secrets.token_urlsafe(12) for n in names}
    out='仅用于本机演示；每次启动密码和会话重置。\n'+''.join(n+' : '+pw+'\n' for n,pw in credentials.items())
    secret_file=path/'LOCAL_DEMO_ACCOUNTS.txt';secret_file.write_text(out,encoding='utf-8');secret_file.chmod(0o600)
    print(out,flush=True);print(f'打开 http://127.0.0.1:{args.port}/membership  （无真实支付或采集）',flush=True)
    import uvicorn
    uvicorn.run(create_demo(path/'demo.db',credentials),host='127.0.0.1',port=args.port)

if __name__=='__main__':main()
