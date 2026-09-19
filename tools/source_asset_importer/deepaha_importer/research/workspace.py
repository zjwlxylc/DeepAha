"""Local-only review sessions. SQLite transactions protect decisions and revisions.

No imports of production repositories, network clients, or WMA runners. Original
byte blobs are content-addressed; exports re-read them and verify every digest.
"""
from __future__ import annotations
import collections
from contextlib import contextmanager
import copy
import io
import json
import os
import re
import sqlite3
import tempfile
import uuid
import zipfile
from datetime import datetime,timezone
from pathlib import Path
from ..contract import canonical_json,digest
from ..errors import ImporterError
from .ingest import load_inputs,_read_file,safe_member
from .audit import analyze
from .feedback import inspect_feedback

def now():return datetime.now(timezone.utc).isoformat()
def _dumps(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def pretty(value):return (json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8')

class Workspace:
    def __init__(self,root):
        self.root=Path(root).expanduser();self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        if self.root.is_symlink():raise ImporterError('UNSAFE_WORKSPACE','审核工作区不能为链接。')
        if any(p.is_symlink() for p in self.root.parents) or any((self.root/name).is_symlink() for name in ('blobs','exports','review.sqlite3')):
            raise ImporterError('UNSAFE_WORKSPACE','审核工作区路径或内部存储不能经过链接。')
        self.blobs=self.root/'blobs';self.blobs.mkdir(exist_ok=True,mode=0o700)
        self.exports=self.root/'exports';self.exports.mkdir(exist_ok=True,mode=0o700)
        self.db=self.root/'review.sqlite3'
        with self.connect() as con:
            con.execute('PRAGMA journal_mode=WAL')
            con.execute('CREATE TABLE IF NOT EXISTS review_sessions(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL)')
    @contextmanager
    def connect(self):
        con=sqlite3.connect(self.db,timeout=10);con.row_factory=sqlite3.Row
        try:
            with con:yield con
        finally:con.close()
    def _id(self,sid):
        if not isinstance(sid,str) or not re.fullmatch('[a-f0-9]{32}',sid):raise ImporterError('BAD_SESSION','审核会话标识无效。')
    def _store_blob(self,blob):
        h=digest(blob);p=self.blobs/h
        try:
            with p.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
        except FileExistsError:
            if digest(_read_file(p,100*1024*1024))!=h:raise ImporterError('LOCAL_BLOB_CHANGED','已有原件字节损坏。')
        return h
    def create(self,paths,namespace='AUTO'):
        inputs=load_inputs(paths,namespace=namespace)
        if not inputs.handoffs:raise ImporterError('NO_HANDOFF','所选文件未包含支持的Handoff。State、Review或源码包不能代替来源研究包。')
        audit=analyze(inputs);sid=uuid.uuid4().hex; originals=[]
        for i,b in enumerate(inputs.originals):
            h=self._store_blob(b.data); originals.append(b.metadata()|{'blob_sha256':h,'archive_path':f'originals/{i+1:04d}/{Path(b.name).name}',
                                                                      'namespace_hint':b.namespace_hint})
        value={'id':sid,'revision':0,'created_at':now(),'analysis':audit,'originals':originals,'decisions':{},'events':[],
               'feedback':[],'export_history':[],'database_submission':'NOT_ATTEMPTED'}
        with self.connect() as con:con.execute('INSERT INTO review_sessions VALUES(?,?,?,?)',(sid,0,value['created_at'],_dumps(value)))
        return value
    def get(self,sid):
        self._id(sid)
        with self.connect() as con:row=con.execute('SELECT payload FROM review_sessions WHERE id=?',(sid,)).fetchone()
        if not row:raise ImporterError('SESSION_NOT_FOUND','未找到本地审核会话。',404)
        return json.loads(row['payload'])
    def list(self):
        with self.connect() as con:rows=con.execute('SELECT id,revision,created_at FROM review_sessions ORDER BY created_at DESC LIMIT 100').fetchall()
        return [dict(row) for row in rows]
    def _mutate(self,sid,revision,callback):
        self._id(sid)
        if type(revision) is not int:raise ImporterError('BAD_REVISION','审核版本必须为整数。')
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE');row=con.execute('SELECT revision,payload FROM review_sessions WHERE id=?',(sid,)).fetchone()
            if not row:raise ImporterError('SESSION_NOT_FOUND','未找到审核会话。',404)
            if row['revision']!=revision:raise ImporterError('REVIEW_CHANGED','审核已在另一窗口更新。请刷新后再保存，避免覆盖别人意见。',409)
            value=json.loads(row['payload']);callback(value);value['revision']+=1
            con.execute('UPDATE review_sessions SET revision=?,payload=? WHERE id=?',(value['revision'],_dumps(value),sid))
        return value
    def _decision_args(self,decision,reason,actor):
        if decision not in {'PROPOSE_STAGING','DEFER','REJECT'}:raise ImporterError('BAD_DECISION','只允许候选交接建议、暂缓或不采用。')
        if not isinstance(reason,str) or not 1<=len(reason.strip())<=4000 or not isinstance(actor,str) or not 1<=len(actor.strip())<=120:
            raise ImporterError('DECISION_REASON','请填写操作者和处理原因。')
    def decide(self,sid,source_id,decision,reason,actor,revision,acknowledge_issues=False,primary_seed=None):
        self._decision_args(decision,reason,actor)
        def apply(value):
            group=next((s for s in value['analysis']['sources'] if s['id']==source_id),None)
            if not group:raise ImporterError('SOURCE_NOT_FOUND','所选审核对象已不存在。')
            if decision=='PROPOSE_STAGING':
                if group['blocking']:raise ImporterError('SOURCE_BLOCKED','存在身份或入口阻断问题，先暂缓；补齐原件后重新审核。')
                if group['review_needed'] and acknowledge_issues is not True:raise ImporterError('ACK_REQUIRED','请先核对疑点并确认知晓；这仍只是候选交接建议。')
                if len(group['seed_urls'])>1 and primary_seed not in group['seed_urls']:raise ImporterError('PRIMARY_SEED_REQUIRED','请明确选择一个主入口，其他入口仍保留。')
            if primary_seed is not None and primary_seed not in group['seed_urls']:raise ImporterError('INVALID_PRIMARY_SEED','主入口必须来自本次解析出的入口，不允许暗中替换。')
            previous=copy.deepcopy(value['decisions'].get(source_id))
            current={'decision':decision,'reason':reason.strip(),'actor':actor.strip(),'decided_at':now(),
                     'acknowledged_issues':bool(acknowledge_issues),'primary_seed':primary_seed or (group['seed_urls'][0] if len(group['seed_urls'])==1 else None),
                     'authority':'LOCAL_REVIEW_ONLY_NOT_SYSTEM_APPROVAL'}
            value['decisions'][source_id]=current
            value['events'].append({'event_id':uuid.uuid4().hex,'type':'DECISION','source_id':source_id,'before':previous,'after':current,
                                    'at':now(),'revision':value['revision']+1})
        return self._mutate(sid,revision,apply)
    def undo(self,sid,source_id,reason,actor,revision):
        self._decision_args('DEFER',reason,actor)
        def apply(value):
            if source_id not in value['decisions']:raise ImporterError('NO_DECISION','该对象还没有可撤销的决定。')
            previous=value['decisions'].pop(source_id)
            value['events'].append({'event_id':uuid.uuid4().hex,'type':'UNDO','source_id':source_id,'before':previous,'after':None,
                                    'actor':actor.strip(),'reason':reason.strip(),'at':now(),'revision':value['revision']+1})
        return self._mutate(sid,revision,apply)
    def add_feedback(self,sid,raw,revision):
        def apply(value):
            inspected=inspect_feedback(raw,[x['bundle_id'] for x in value['export_history']])
            if any(x['sha256']==inspected['sha256'] for x in value['feedback']):raise ImporterError('FEEDBACK_ALREADY_LOADED','这个反馈文件已读取，不重复累计。')
            self._store_blob(raw);value['feedback'].append(inspected)
            value['events'].append({'event_id':uuid.uuid4().hex,'type':'FEEDBACK_FILE_LOADED_NOT_AUTHENTICATED','sha256':digest(raw),'at':now(),'revision':value['revision']+1})
        return self._mutate(sid,revision,apply)
    def export(self,sid,revision):
        # Serialize against decisions so no changed review can be mislabeled current.
        self._id(sid)
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE');row=con.execute('SELECT revision,payload FROM review_sessions WHERE id=?',(sid,)).fetchone()
            if not row:raise ImporterError('SESSION_NOT_FOUND','未找到审核会话。')
            if row['revision']!=revision:raise ImporterError('REVIEW_CHANGED','导出前审核已更新，请刷新。',409)
            value=json.loads(row['payload']);entries={};a=value['analysis']
            for item in value['originals']:
                name=safe_member(item['archive_path']);raw=_read_file(self.blobs/item['blob_sha256'],100*1024*1024)
                if digest(raw)!=item['sha256'] or len(raw)!=item['size_bytes']:raise ImporterError('LOCAL_BLOB_CHANGED','本地原件字节已变化，停止导出。')
                entries[name]=raw
            inventory=[{'path':name,'sha256':digest(raw),'size_bytes':len(raw)} for name,raw in sorted(entries.items())]
            bundle_id=digest(canonical_json({'originals':inventory,'analysis_sha256':digest(canonical_json(a)),
                                            'decisions':value['decisions'],'revision':revision,'events':value['events']}))
            previous=next((x for x in value['export_history'] if x['bundle_id']==bundle_id),None)
            if previous:
                existing=self.exports/previous['filename']
                raw=_read_file(existing,650*1024*1024)
                if digest(raw)!=previous['sha256'] or len(raw)!=previous['size_bytes']:
                    raise ImporterError('LOCAL_EXPORT_CHANGED','此前导出已变化，停止复用；不会覆盖旧包。')
                return {k:v for k,v in previous.items() if k!='exported_at'}
            exported_at=now()
            proposed=[]
            for g in a['sources']:
                d=value['decisions'].get(g['id'])
                if d and d['decision']=='PROPOSE_STAGING':proposed.append({'review_source_id':g['id'],'namespace':g['namespace'],
                    'candidate_key':g['candidate_key'],'name':g['name'],'primary_seed':d['primary_seed'],'all_seed_candidates':g['seed_urls'],
                    'decision_ref':g['id'],'system_source_id':None,'collection_enabled':None,'authority_validation':'NOT_INDEPENDENTLY_VERIFIED'})
            complete=len(value['decisions'])==len(a['sources'])
            handoff={'schema_version':'deepaha.research-handoff.v1','bundle_id':bundle_id,'review_session':sid,'review_revision':revision,
                'submission_status':'NOT_SUBMITTED','delivery_mode':'MANUAL_EXPORT_ONLY','created_at':exported_at,
                'analyzed_at':a['analyzed_at'],'exported_at':exported_at,
                'last_reviewed_at':max((x['at'] for x in value['events']),default=None),'generator_version':'0.3.1',
                'readiness':'REVIEWED_CANDIDATES_ONLY' if complete else 'UNFINISHED_REVIEW_NOT_FOR_APPROVAL',
                'source_versions':a['summary']['source_versions'],'candidate_groups':a['summary']['candidate_groups'],
                'staging_proposals':proposed,'counts':{'pending':len(a['sources'])-len(value['decisions']),
                     **dict(collections.Counter(x['decision'] for x in value['decisions'].values()))},
                'review_file':'Audit.json','decisions_file':'Decisions.json','original_inventory':inventory,
                'integration_status':'REQUIRES_DEEPAHA_STAGING_ADAPTER_NOT_LEGACY_IMPORT_PROFILE_V1',
                'notes':['相同候选的历史观察不是垃圾记录，全部保留。','本包不批准Source，不启动WMA，不发布事实。','不把旧版本晚到或研究者评分当作系统状态。']}
            entries.update({'ResearchHandoff.json':pretty(handoff),'Audit.json':pretty(a),
                            'Decisions.json':pretty({'revision':revision,'decisions':value['decisions'],'events':value['events']}),
                            'FeedbackDeclarations.json':pretty(value['feedback'])})
            entries['README.md']=('# 研究资产交接包\n\n本包由本地审核工作台生成，**尚未导入DeepAha**。\n\n'
                                  '先阅读 ResearchHandoff.json 的 readiness 与 counts，再核查 Decisions.json。Audit.json 保留所有候选版本、证据、Brief和关系。\n'
                                  'originals 是原始输入，不得用投影替代。Manifest.json 校验各文件SHA-256。反馈文件自报未认证，不代表来源已批准。\n'
                                  '主系统需要接收 deepaha.research-handoff.v1 的专用候选暂存适配器，不能直接调用旧 v1执行接口。\n').encode()
            entries['Manifest.json']=pretty({'schema_version':'deepaha.research-bundle-manifest.v1','bundle_id':bundle_id,
                'files':[{'path':name,'sha256':digest(raw),'size_bytes':len(raw)} for name,raw in sorted(entries.items())],
                'self_excluded':True,'scope':'解压成员字节校验；不证明官方来源或研究事实准确。'})
            target=self.exports/f'DeepAha_Research_{bundle_id[:16]}_r{revision}.zip'
            fd,tmp=tempfile.mkstemp(prefix='.export-',dir=self.exports);os.close(fd)
            try:
                with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_DEFLATED) as z:
                    for name,raw in sorted(entries.items()):
                        info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,raw)
                with open(tmp,'rb') as f:sha=digest(f.read())
                if target.exists():
                    if digest(target.read_bytes())!=sha:raise ImporterError('EXPORT_COLLISION','已存在导出文件与本次结果不同。')
                    os.unlink(tmp)
                else:os.replace(tmp,target)
            finally:
                if os.path.exists(tmp):os.unlink(tmp)
            result={'filename':target.name,'path':str(target),'bundle_id':bundle_id,'sha256':sha,'size_bytes':target.stat().st_size,
                    'review_revision':revision,'status':'EXPORTED_NOT_SUBMITTED','readiness':handoff['readiness']}
            if not any(x['bundle_id']==bundle_id for x in value['export_history']):
                value['export_history'].append(result|{'exported_at':exported_at})
                con.execute('UPDATE review_sessions SET payload=? WHERE id=?',(_dumps(value),sid))
        return result
