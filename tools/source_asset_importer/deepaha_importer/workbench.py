"""Loopback-only browser workbench. File transfer, local review, no production writes."""
from __future__ import annotations
import copy
import hmac
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import replace
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs,urlsplit,unquote
from .config import default_data_dir
from .contract import parse_json
from .errors import ImporterError
from .research.ingest import safe_member,Limits
from .research.workspace import Workspace,pretty
from .research.library import ResearchLibraryPull,FOLDERS
from .codex_process import CodexLibraryConfig,load_library_config,save_library_config

WEB=Path(__file__).with_name('web')

class Application:
    def __init__(self,data_dir):
        self.data_dir=Path(data_dir);self.workspace=Workspace(self.data_dir/'research_workbench')
        self.token=secrets.token_urlsafe(32);self.lock=threading.RLock();self.uploads={};self.jobs={};self.catalogs={}
        self.temp=tempfile.TemporaryDirectory(prefix='deepaha-upload-');self.upload_root=Path(self.temp.name)
        self.upload_total=0;self.slots=threading.BoundedSemaphore(2)
    def close(self):
        for j in list(self.jobs.values()):j['cancel'].set()
        self.temp.cleanup()
    def job(self,operation):
        if not self.slots.acquire(blocking=False):raise ImporterError('BUSY','已有操作正在进行，请完成或取消后再试。',429)
        jid=uuid.uuid4().hex;cancel=threading.Event();job={'id':jid,'status':'RUNNING','cancel':cancel,'progress':'准备开始','started_at_monotonic':time.monotonic()}
        with self.lock:self.jobs[jid]=job
        def run():
            try:
                result=operation(cancel,job)
                with self.lock:job.update(status='DONE',result=result,progress='已完成')
            except ImporterError as e:
                with self.lock:job.update(status='CANCELLED' if e.code=='LIBRARY_CANCELLED' else 'ERROR',error={'code':e.code,'message':e.message},progress='已取消' if e.code=='LIBRARY_CANCELLED' else '需要处理')
            except Exception:
                with self.lock:job.update(status='ERROR',error={'code':'LOCAL_OPERATION_FAILED','message':'本地操作未完成，原件与已有审核记录保留。请检查文件和目录权限。'},progress='需要处理')
            finally:self.slots.release()
        threading.Thread(target=run,daemon=True).start();return {'job_id':jid}
    def add_upload(self,name,raw):
        name=safe_member(name)
        with self.lock:
            if self.upload_total+len(raw)>Limits().expanded_bytes or len(self.uploads)>=10000:raise ImporterError('UPLOAD_LIMIT','本次选择已超过500MiB或10000个文件，请重新打开工作台分批处理。')
            uid=uuid.uuid4().hex;p=self.upload_root/uid/name;p.parent.mkdir(parents=True,mode=0o700)
            p.write_bytes(raw);self.uploads[uid]={'id':uid,'path':str(p),'name':name,'size_bytes':len(raw)};self.upload_total+=len(raw)
        return {k:v for k,v in self.uploads[uid].items() if k!='path'}
    def selected_paths(self,ids):
        if not isinstance(ids,list) or not 1<=len(ids)<=10000 or any(not isinstance(x,str) for x in ids):raise ImporterError('UPLOAD_REQUIRED','请先选择一个或多个研究文件。')
        with self.lock:
            if any(x not in self.uploads for x in ids):raise ImporterError('UPLOAD_NOT_FOUND','所选文件不在本次会话中，请重新选择。')
            return [Path(self.uploads[x]['path']) for x in dict.fromkeys(ids)]
    def session_summary(self,sid):
        s=self.workspace.get(sid);a=s['analysis'];out={k:v for k,v in s.items() if k not in {'analysis','originals'}}
        keep=('id','namespace','candidate_key','name','institution','seed_urls','roles','opportunity_types','recommendation',
              'recon_status','issue_codes','blocking','review_needed','repeat_versions','score')
        out['analysis']={k:a[k] for k in ('summary','namespace_summary','limits','warnings','timeline_issues')}
        out['analysis']['sources']=[{k:g[k] for k in keep} for g in a['sources']]
        out['originals']=[{k:r[k] for k in ('path','size_bytes','sha256')} for r in s['originals']]
        return out
    def library_config(self,value=None):
        path=self.data_dir/'codex-library.settings.json'
        if value is None:return load_library_config(path)
        if not isinstance(value,dict) or set(value)-set(CodexLibraryConfig.__dataclass_fields__):raise ImporterError('CODEX_CONFIG_INVALID','获取设置字段无效。')
        config=CodexLibraryConfig(**value);config.validate();save_library_config(config,path)
        with self.lock:self.catalogs.clear()
        return config

class WorkbenchServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,app,port):self.app=app;super().__init__(('127.0.0.1',port),Handler)

class Handler(BaseHTTPRequestHandler):
    server_version='DeepAhaWorkbench/0.3.1'
    def setup(self):super().setup();self.connection.settimeout(30)
    def log_message(self,*args):pass # Do not log session headers or filenames.
    @property
    def app(self):return self.server.app
    @property
    def origin(self):return f'http://127.0.0.1:{self.server.server_port}'
    def authorize(self,api=True):
        if self.headers.get('Host')!=f'127.0.0.1:{self.server.server_port}':raise ImporterError('LOCAL_HOST_REQUIRED','工作台仅允许本机回环地址。',403)
        if self.headers.get('Origin') not in (None,self.origin):raise ImporterError('ORIGIN_REJECTED','拒绝来自其他网站的工作台请求。',403)
        if self.headers.get('Sec-Fetch-Site')=='cross-site':raise ImporterError('ORIGIN_REJECTED','拒绝跨站请求。',403)
        supplied=self.headers.get('X-DeepAha-Session','')
        if api and not hmac.compare_digest(supplied,self.app.token):raise ImporterError('LOCAL_SESSION_REQUIRED','本地会话已失效，请使用启动窗口给出的地址重新打开。',403)
    def send(self,status,body,content_type='application/json; charset=utf-8',extra=None):
        raw=pretty(body) if not isinstance(body,bytes) else body
        self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        for key,value in (extra or {}).items():self.send_header(key,value)
        self.end_headers();self.wfile.write(raw)
    def body(self,limit):
        if self.headers.get('Transfer-Encoding'):raise ImporterError('BODY_FORMAT','不接受分块传输。')
        if len(self.headers.get_all('Content-Length',[]))!=1:raise ImporterError('BODY_FORMAT','需要唯一的请求长度。')
        try:size=int(self.headers['Content-Length'])
        except (ValueError,TypeError):raise ImporterError('BODY_FORMAT','请求长度无效。')
        if not 0<=size<=limit:raise ImporterError('BODY_LIMIT','文件或请求超过允许大小。',413)
        raw=self.rfile.read(size)
        if len(raw)!=size:raise ImporterError('BODY_INCOMPLETE','文件传输不完整，请重新选择。')
        return raw
    def handle_error(self,exc):
        try:
            if isinstance(exc,ImporterError):self.send(exc.status,exc.as_dict())
            else:self.send(400,{'error':{'code':'REQUEST_FAILED','message':'请求未完成，请核对文件格式和当前审核版本。'}})
        except (BrokenPipeError,ConnectionResetError):pass
    def do_GET(self):
        try:self._get()
        except Exception as e:self.handle_error(e)
    def _get(self):
        parsed=urlsplit(self.path);path=parsed.path;q=parse_qs(parsed.query)
        self.authorize(path.startswith('/api/'))
        static={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','application/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
        if path in static:
            name,mime=static[path];return self.send(200,(WEB/name).read_bytes(),mime)
        if path=='/api/sessions':return self.send(200,self.app.workspace.list())
        if path=='/api/session':return self.send(200,self.app.session_summary(q.get('id',[''])[0]))
        if path=='/api/source':
            s=self.app.workspace.get(q.get('id',[''])[0]);source=q.get('source',[''])[0];a=s['analysis']
            g=next((g for g in a['sources'] if g['id']==source),None)
            if not g:raise ImporterError('SOURCE_NOT_FOUND','未找到所选审核对象。',404)
            names={g['id']:g['name'] for g in a['sources']}
            return self.send(200,{'source':g,'issues':[x for x in a['issues'] if x.get('source_id')==source],
                'relations':[x|{'left_name':names[x['left']],'right_name':names[x['right']]} for x in a['relations'] if source in (x['left'],x['right'])],
                'attachments':[r for r in a['attachment_reconciliation'] if r['namespace']==g['namespace'] and r['evidence_key'] in {e['key'] for e in g['evidence_versions']}],
                'decision':s['decisions'].get(source),'revision':s['revision']})
        if path=='/api/job':
            with self.app.lock:job=self.app.jobs.get(q.get('id',[''])[0])
            if not job:raise ImporterError('JOB_NOT_FOUND','未找到操作记录。',404)
            return self.send(200,{k:v for k,v in job.items() if k not in {'cancel','started_at_monotonic'}}|{'elapsed_seconds':round(time.monotonic()-job['started_at_monotonic'],1)})
        if path=='/api/library/diagnostic':
            with self.app.lock:
                job=self.app.jobs.get(q.get('job_id',[''])[0])
                diagnostic=copy.deepcopy(job.get('diagnostic')) if job else None
            if not diagnostic:raise ImporterError('DIAGNOSTIC_NOT_READY','本次尚无已完成的连接诊断，请完成检查或取消后再下载。',404)
            return self.send(200,diagnostic,extra={'Content-Disposition':'attachment; filename="DeepAha_Library_Diagnostic.json"'})
        if path=='/api/config':
            from dataclasses import asdict
            return self.send(200,{'codex':asdict(self.app.library_config()),'library_folders':FOLDERS})
        if path=='/api/download':
            name=q.get('file',[''])[0]
            if Path(name).name!=name or not name.startswith('DeepAha_Research_') or not name.endswith('.zip'):raise ImporterError('DOWNLOAD_NOT_FOUND','导出文件不存在。',404)
            p=self.app.workspace.exports/name
            if not p.is_file() or p.is_symlink():raise ImporterError('DOWNLOAD_NOT_FOUND','导出文件不存在。',404)
            from .research.ingest import _read_file
            raw=_read_file(p,650*1024*1024)
            return self.send(200,raw,'application/zip',{'Content-Disposition':f'attachment; filename="{name}"'})
        raise ImporterError('NOT_FOUND','没有这个页面或操作。',404)
    def do_POST(self):
        try:self._post()
        except Exception as e:self.handle_error(e)
    def _post(self):
        path=urlsplit(self.path).path;self.authorize()
        if path=='/api/upload':
            name=unquote(self.headers.get('X-File-Name',''));safe_member(name)
            return self.send(200,self.app.add_upload(name,self.body(Limits().input_bytes)))
        data=parse_json(self.body(2*1024*1024),2*1024*1024)
        if not isinstance(data,dict):raise ImporterError('REQUEST_FORMAT','请求必须为对象。')
        if path=='/api/analyze':
            paths=self.app.selected_paths(data.get('uploads'));ns=data.get('namespace','AUTO')
            return self.send(202,self.app.job(lambda cancel,job:{'session_id':self.app.workspace.create(paths,ns)['id']}))
        if path in ('/api/decision','/api/undo'):
            fn=self.app.workspace.decide if path.endswith('decision') else self.app.workspace.undo
            args=[data.get('session_id'),data.get('source_id')]
            if path.endswith('decision'):args+=[data.get('decision')]
            args+=[data.get('reason'),data.get('actor'),data.get('revision')]
            extra={'acknowledge_issues':data.get('acknowledge_issues',False),'primary_seed':data.get('primary_seed') or None} if path.endswith('decision') else {}
            s=fn(*args,**extra);return self.send(200,{'id':s['id'],'revision':s['revision']})
        if path=='/api/export':return self.send(202,self.app.job(lambda cancel,job:self.app.workspace.export(data.get('session_id'),data.get('revision'))))
        if path=='/api/feedback':
            p=self.app.selected_paths([data.get('upload_id')])[0]
            from .research.ingest import _read_file
            s=self.app.workspace.add_feedback(data.get('session_id'),_read_file(p,8*1024*1024),data.get('revision'))
            return self.send(200,{'id':s['id'],'revision':s['revision'],'verification':s['feedback'][-1]['verification']})
        if path=='/api/config':self.app.library_config(data.get('codex'));return self.send(200,{'status':'SAVED_LOCALLY'})
        if path=='/api/library/list':
            folder=data.get('folder_path');bridge=ResearchLibraryPull(self.app.library_config(),self.app.data_dir)
            def progress(text):
                with self.app.lock:current_job['progress']=text
            current_job={}
            def listing(cancel,job):
                nonlocal current_job
                current_job=job
                try:
                    cat=bridge.connect_and_list(folder,cancel=cancel,progress=progress);cid=uuid.uuid4().hex
                    cat['supports_ephemeral']=bridge.process.supports_ephemeral
                    with self.app.lock:self.app.catalogs[cid]=cat
                    return cat|{'catalog_id':cid}
                finally:
                    with self.app.lock:job['diagnostic']=bridge.last_diagnostic
            return self.send(202,self.app.job(listing))
        if path=='/api/library/fetch':
            with self.app.lock:cat=self.app.catalogs.get(data.get('catalog_id'))
            if not cat:raise ImporterError('CATALOG_EXPIRED','请重新读取资料库文件列表。')
            indexes=data.get('indexes')
            if not isinstance(indexes,list) or not 1<=len(indexes)<=20 or any(type(i)is not int or not 0<=i<len(cat['files']) for i in indexes):raise ImporterError('LIBRARY_SELECTION','每次请选择1至20个清单中的文件。')
            bridge=ResearchLibraryPull(self.app.library_config(),self.app.data_dir)
            bridge.process.supports_ephemeral=cat.get('supports_ephemeral',True)
            def fetching(cancel,job):
                results=[];failures=[];started=time.monotonic();diagnostics=[]
                with self.app.lock:job['diagnostic']={'schema_version':'deepaha.library-diagnostic-batch.v1','operations':diagnostics,'database_submission':'NOT_ATTEMPTED'}
                for k,i in enumerate(dict.fromkeys(indexes)):
                    if cancel.is_set():break
                    remaining=600-(time.monotonic()-started)
                    if remaining<30:
                        failures.append({'name':'剩余文件','code':'BATCH_TIMEOUT','message':'本批已达到10分钟上限；剩余文件未取回，可稍后单独选择。'});break
                    bridge.process.config=replace(bridge.process.config,timeout_seconds=min(bridge.process.config.timeout_seconds,int(remaining)))
                    with self.app.lock:job['progress']=f'正在取回第{k+1}/{len(indexes)}个原件'
                    entry=cat['files'][i]
                    try:
                        result=bridge.fetch_diagnosed(cat['folder_path'],cat['folder_ref'],entry,cancel=cancel)
                        results.append(self.app.add_upload(entry['name'],Path(result['file_path']).read_bytes()))
                    except ImporterError as e:failures.append({'name':entry['name'],'code':e.code,'message':e.message})
                    finally:
                        if bridge.last_diagnostic:diagnostics.append(bridge.last_diagnostic)
                return {'uploads':results,'failures':failures,'cancelled':cancel.is_set(),'database_submission':'NOT_ATTEMPTED'}
            return self.send(202,self.app.job(fetching))
        if path=='/api/cancel':
            with self.app.lock:job=self.app.jobs.get(data.get('job_id'))
            if job:job['cancel'].set()
            return self.send(200,{'status':'CANCEL_REQUESTED'})
        if path=='/api/legacy':
            subprocess.Popen([sys.executable,'-m','deepaha_importer','gui'],cwd=WEB.parent.parent,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,shell=False)
            return self.send(200,{'status':'LAUNCH_REQUESTED','message':'已请求打开原单批兼容窗口；需要Python Tk组件。该窗口仍严格验证旧执行契约。'})
        raise ImporterError('NOT_FOUND','没有这个操作；工作台不提供生产提交接口。',404)

def create_server(data_dir=None,port=0):return WorkbenchServer(Application(data_dir or default_data_dir()),port)
def main(data_dir=None,port=0,open_browser=True):
    server=create_server(data_dir,port);address=f'http://127.0.0.1:{server.server_port}/#'+server.app.token
    print('DeepAha 来源资产工作台 v0.3.1\n只在本机运行；未连接生产数据库。\n'+address,flush=True)
    if open_browser:webbrowser.open(address)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();server.app.close()
