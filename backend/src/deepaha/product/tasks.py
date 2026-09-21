from datetime import timedelta
from urllib.parse import urlsplit
from sqlalchemy import select
from .models import Task, Account, Meta, SourceProfile, Audit, Opportunity, Identity, CatalogTarget, now, uid
from .adapter import safe_url, text
from .auth import aware
from .errors import Problem
from .scout_models import TaskSourceContext

class TasksMixin:
    def _task_view(self,t):
        return {k:(getattr(t,k).isoformat() if k.endswith('_at') and getattr(t,k) else getattr(t,k)) for k in
          ['id','source_id','notice_url','status','kind','instruction','runtime_id','session_id','stage','error_code','budget_seconds','attempts','revision_id','created_at','updated_at']}
    def create_task(self,source_id,url,*,actor,request_key,instruction='',kind='INVESTIGATE',budget_seconds=1200,connection_ref='default'):
        if not 60<=budget_seconds<=1800:raise Problem('调查预算应为60至1800秒')
        if kind not in ('INVESTIGATE','RECHECK','SUPPLEMENT'):raise Problem('调查类型不正确')
        if not request_key or len(request_key)>128:raise Problem('请求标识不正确')
        url=safe_url(url)
        if not url:raise Problem('请输入公开网页地址')
        with self.db.tx() as s:
            a=self._account(s,actor,'operator');source=self._source(s,source_id)
            old=s.scalar(select(Task).where(Task.request_key==request_key))
            from .dispatch_policy import ensure_dispatch,policy_dict
            from .models import DispatchPolicy,TaskDispatch
            from sqlalchemy import func
            import re
            if not re.fullmatch(r'[a-zA-Z0-9_-]{1,48}',connection_ref):raise Problem('执行连接标识不正确')
            if old:
                if ensure_dispatch(s,old).connection_ref!=connection_ref:raise Problem('请求连接冲突',409)
                if old.creator_id!=a.id or old.notice_url!=url or old.source_id!=source_id or old.instruction!=instruction or old.kind!=kind or old.budget_seconds!=budget_seconds:raise Problem('请求标识冲突',409)
                return self._task_view(old)
            if not source['active'] or not source['enabled']:raise Problem('该来源已暂停新任务',409)
            if urlsplit(url).hostname not in source['allowed_hosts']:raise Problem('网址不属于该来源的允许范围',400)
            policy=policy_dict(s.get(DispatchPolicy,connection_ref),connection_ref)
            queued=s.scalar(select(func.count()).select_from(Task).outerjoin(TaskDispatch,Task.id==TaskDispatch.task_id).where(Task.status.in_(['QUEUED','RUNNING','RECOVERY_QUEUED']),func.coalesce(TaskDispatch.connection_ref,'default')==connection_ref))
            if queued>=policy['queue_limit']:raise Problem('该执行连接的任务队列已满，请先处理现有任务',409,'QUEUE_FULL')
            t=Task(source_id=source_id,creator_id=a.id,notice_url=url,request_key=request_key,instruction=text(instruction,10000),kind=kind,budget_seconds=budget_seconds)
            s.add(t);s.flush();t.workspace='/workspace/deepaha/'+t.id
            ensure_dispatch(s,t,connection_ref)
            s.add(TaskSourceContext(task_id=t.id,payload={k:source.get(k) for k in
                ('id','name','url','allowed_hosts','brief','policy_version','intelligence')}))
            self._audit(s,actor,'CREATE_INVESTIGATION',t.id,'已授权一次Direct WMA调查')
            return self._task_view(t)

    def create_targeted_recheck(self,public_id,*,actor,request_key,budget_seconds=1200):
        """Create a Direct WMA recheck scoped to one actionable target.

        The task describes the already-known target and affected fields; it does
        not ask WMA to re-investigate unrelated sibling units.
        """
        with self.db.tx(False) as s:
            self._account(s,actor,'operator')
            target=s.scalar(
                select(CatalogTarget)
                .where(CatalogTarget.public_id==public_id,CatalogTarget.status.in_(['CURRENT','UPDATE_PENDING']))
                .order_by(CatalogTarget.created_at.desc(),CatalogTarget.id.desc())
            )
            if not target:raise Problem('具体机会不存在或已撤回',404)
            opp=s.get(Opportunity,target.opportunity_id)
            ident=s.scalar(select(Identity).where(Identity.opportunity_id==opp.opportunity_id).order_by(Identity.id))
            if not ident:raise Problem('具体机会缺少来源身份，不能发起定向复查',409)
            source=self._source(s,ident.source_id)
            body=target.content if isinstance(target.content,dict) else {}
            currentness=body.get('currentness') if isinstance(body.get('currentness'),dict) else {}
            affected=list(currentness.get('affected_fields') or [])
            summary=currentness.get('summary') or '复查此具体机会的当前官方内容。'
            target_title=body.get('title') or opp.canonical_title
            code=body.get('code') or ''
            url=body.get('official_url') or source['url']
        field_text='、'.join(affected) if affected else '当前内容与证据'
        instruction=(
            f'仅复查具体机会 {public_id}（{target_title}' + (f'，编号{code}' if code else '') + '）。'
            f'重点核对：{field_text}。当前变化说明：{summary}'
            '只追查与此具体机会直接相关的官方公告、附件、更正、延期、撤回或附件替换；'
            '不要扩大到其他兄弟岗位/赛道，也不要把本轮未看到解释为撤回。'
        )
        return self.create_task(ident.source_id,url,actor=actor,request_key=request_key,
                                instruction=instruction,kind='RECHECK',budget_seconds=budget_seconds)
    def task_detail(self,id,*,actor):
        with self.db.tx(False) as s:
            self._account(s,actor,'operator');t=s.get(Task,id)
            if not t:raise Problem('任务不存在',404)
            context=s.get(TaskSourceContext,id)
            from .models import TaskDispatch
            from .experience import task_guidance
            d=s.get(TaskDispatch,id)
            return {**self._task_view(t),'source_context':context.payload if context else None,'next_action':task_guidance(t),
                'dispatch':{'connection_ref':d.connection_ref,'policy':d.policy_snapshot,'prompt_started':d.prompt_started,'remote_pending':d.remote_pending,'lease_expires_at':aware(d.lease_expires_at).isoformat() if d.lease_expires_at else None} if d else None}
    def tasks(self,*,actor,offset=0,limit=30):
        with self.db.tx(False) as s:
            self._account(s,actor,'operator')
            rows=list(s.scalars(select(Task).order_by(Task.created_at.desc(),Task.id).offset(offset).limit(min(limit,50))))
            return [self._task_view(t) for t in rows]
    def cancel_task(self,id,*,actor):
        with self.db.tx() as s:
            self._account(s,actor,'operator');t=s.get(Task,id)
            if not t:raise Problem('任务不存在',404)
            if t.status=='READY':raise Problem('结果已接收，不能按任务取消撤回内容',409)
            t.status='CANCELLED';t.updated_at=now()
            self._audit(s,actor,'CANCEL_LOCAL_CONTINUATION',id,'停止本地后续处理；远端已发出的调查不保证停止')
            return self._task_view(t)
    def recover_task(self,id,*,actor):
        with self.db.tx() as s:
            self._account(s,actor,'operator');t=s.get(Task,id)
            if not t:raise Problem('任务不存在',404)
            if t.status=='RECOVERY_QUEUED':return self._task_view(t)
            if t.status=='RUNNING' and now()-aware(t.updated_at)>timedelta(seconds=t.budget_seconds+180):t.status='NEEDS_RECOVERY'
            if t.status not in ('NEEDS_RECOVERY','FAILED'):raise Problem('当前任务不能恢复',409)
            if not t.session_id and not all(n in t.files for n in ('report.md','opportunities.json','evidence.json')):raise Problem('没有可恢复的远端会话或完整已保存结果；请检查记录后另建调查',409)
            t.status='RECOVERY_QUEUED';t.updated_at=now()
            self._audit(s,actor,'RECOVER_RESULT_FILES',id,'仅回收已有文件与整理；不会再次发送调查提示词')
            return self._task_view(t)
    def history(self,*,actor,offset=0,limit=30):
        with self.db.tx(False) as s:
            self._account(s,actor,'operator')
            return [{'id':r.id,'actor':r.actor,'action':r.action,'target':r.target,'summary':r.summary,'created_at':r.created_at.isoformat()} for r in s.scalars(select(Audit).order_by(Audit.created_at.desc(),Audit.id).offset(offset).limit(min(limit,50)))]
    def runtime_status(self,*,actor):
        import importlib.util
        import os
        import json
        from sqlalchemy import text as sqltext
        out={'version':'3.8.0-rc1','database':'UNKNOWN','storage':'UNKNOWN','worker':None,'wma':'NOT_CONFIGURED','sdk_available':False}
        with self.db.tx(False) as s:
            self._account(s,actor,'operator')
            s.execute(sqltext('SELECT 1'));out['database']='READ_OK'
            r=s.get(Meta,'worker_heartbeat')
            from .worker_health import status
            out['worker_health']=status(s)
            if r:
                try:out['worker']=json.loads(r.value)
                except ValueError:pass
        try:
            # Readability only; write verification is a separate explicit operation.
            out['storage']='READABLE' if os.access(self.object_root,os.R_OK) else 'UNKNOWN'
        except OSError:pass
        out['sdk_available']=importlib.util.find_spec('cloud_agent_sdk') is not None
        out['wma']='CONFIGURED_NOT_CHECKED' if os.getenv('DEEPAHA_WMA_API_KEY') and os.getenv('DEEPAHA_WMA_AGENT_ID') else 'NOT_CONFIGURED'
        out['agent_id']=os.getenv('DEEPAHA_WMA_AGENT_ID','')
        out['source_app']=os.getenv('DEEPAHA_WMA_SOURCE_APP','deepaha-dail')
        return out
    def check_storage(self,*,actor):
        with self.db.tx(False) as s:self._account(s,actor,'operator')
        content=b'deepaha-storage-check'
        manifest=self.store.save({'probe.txt':content})
        if self.store.one(manifest,'probe.txt')!=content:raise Problem('存储读取校验失败',503)
        with self.db.tx() as s:self._audit(s,actor,'STORAGE_CHECK','object-store','写入与回读一致')
        return {'storage':'WRITE_READ_OK'}
