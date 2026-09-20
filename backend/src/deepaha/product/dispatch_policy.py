"""Database-enforced WMA admission. Provider capability grants cannot come from HTTP clients.

The shared Database.tx write lock covers claims/quotas, never remote IO. Leases fence
stale workers. Ambiguous prompt acceptance keeps a remote reservation until files
are recovered or an operator explicitly confirms remote termination.
"""
from datetime import timedelta
import json
import re
from sqlalchemy import select,func
from .models import (DispatchPolicy,DispatchValidation,TaskDispatch,Task,Account,Meta,now)
from .auth import aware
from .errors import Problem
from .adapter import hash_json
from .scout_models import TaskSourceContext

POLICY_KEYS=('mode','max_concurrent','queue_limit','task_budget_seconds','new_dispatch_enabled','domain_limit')
LEASE_SECONDS=120


def serial_model(model):
    # Both spellings occur in the project. This is a project rule, not a vendor quota.
    value=(model or '').strip().lower()
    return not value or 'agens' in value or 'agnes' in value


def effective_parallel(mode,requested,model,validated):
    if mode!='PARALLEL' or serial_model(model):return 1
    return max(1,min(requested,validated or 1,4))


def defaults(ref='default'):
    return {'connection_ref':ref,'version':0,'mode':'SERIAL','max_concurrent':1,'queue_limit':20,
            'task_budget_seconds':1200,'new_dispatch_enabled':True,'domain_limit':1,
            'observed_fingerprint':'','published_model':''}


def policy_dict(row,ref='default'):
    if row is None:return defaults(ref)
    return {k:getattr(row,k) for k in (*POLICY_KEYS,'connection_ref','version','observed_fingerprint','published_model')}


def valid_capacity(s,ref,fingerprint):
    if not fingerprint:return 1
    return s.scalar(select(func.max(DispatchValidation.parallel)).where(
        DispatchValidation.connection_ref==ref,DispatchValidation.binding_fingerprint==fingerprint,
        DispatchValidation.origin=='LIVE',DispatchValidation.passed.is_(True))) or 1


def ensure_dispatch(s,t,ref='default'):
    row=s.get(TaskDispatch,t.id)
    if row:return row
    p=policy_dict(s.get(DispatchPolicy,ref),ref)
    row=TaskDispatch(task_id=t.id,connection_ref=ref,binding_fingerprint=p['observed_fingerprint'],policy_snapshot=p,
        model_name=p['published_model'],prompt_started=t.stage in ('PROMPT_STARTED','COLLECTING','PROJECTING','DONE'),
        remote_pending=t.status in ('RUNNING','NEEDS_RECOVERY','CANCELLED') and t.stage in ('PROMPT_STARTED','COLLECTING','PROJECTING'))
    s.add(row);s.flush();return row


class DispatchPolicyMixin:
    def observe_binding(self,ref,fingerprint,release,*,actor='WORKER'):
        # Only called by server-side inspect_release; no API accepts release/verified input.
        permitted=('published_model','release_id','release_version','configuration_sha256','prompt_sha256','skills_sha256')
        safe={k:release[k] for k in permitted if k in release and isinstance(release[k],(str,int))}
        with self.db.tx() as s:
            row=s.get(DispatchPolicy,ref)
            if not row:row=DispatchPolicy(connection_ref=ref);s.add(row)
            changed=row.observed_fingerprint!=fingerprint
            row.observed_fingerprint=fingerprint;row.published_model=str(safe.get('published_model',''))
            row.release_evidence=safe;row.inspected_at=now()
            if changed:self._audit(s,actor,'WMA_BINDING_OBSERVED',ref,'执行绑定已更新；旧并发验证不再适用')

    def execution_policies(self,*,actor,binding_refs=None):
        with self.db.tx(False) as s:
            self._account(s,actor,'operator')
            refs=list(dict.fromkeys((binding_refs or ['default'])+list(s.scalars(select(DispatchPolicy.connection_ref)))))
            items=[]
            for ref in refs:
                row=s.get(DispatchPolicy,ref);p=policy_dict(row,ref)
                validated=valid_capacity(s,ref,p['observed_fingerprint'])
                p.update(effective_concurrent=effective_parallel(p['mode'],p['max_concurrent'],p['published_model'],validated),
                    validated_concurrent=validated,validation_status='LIVE_VALIDATED' if validated>1 else 'NOT_VALIDATED',
                    serial_required=serial_model(p['published_model']),binding_fingerprint=p.pop('observed_fingerprint'),
                    inspected_at=aware(row.inspected_at).isoformat() if row and row.inspected_at else None)
                active=s.scalars(select(TaskDispatch).where(TaskDispatch.connection_ref==ref))
                p['running']=[{'task_id':x.task_id,'remote_pending':x.remote_pending,
                    'lease_expires_at':aware(x.lease_expires_at).isoformat() if x.lease_expires_at else None,
                    'model':x.model_name} for x in active if x.remote_pending or (x.lease_owner and x.lease_expires_at and aware(x.lease_expires_at)>now())]
                items.append(p)
            probe=s.get(Meta,'wma_live_probe')
            return {'items':items,'live_probe':json.loads(probe.value) if probe else None}

    def set_execution_policy(self,ref,*,actor,expected_version,**values):
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,48}',ref) or set(values)!=set(POLICY_KEYS):raise Problem('执行策略字段不正确')
        if values['mode'] not in ('SERIAL','PARALLEL') or type(values['max_concurrent']) is not int or not 1<=values['max_concurrent']<=4:raise Problem('并发配置不正确')
        if not 1<=values['queue_limit']<=1000 or not 60<=values['task_budget_seconds']<=1800 or not 1<=values['domain_limit']<=4:raise Problem('预算或队列上限不正确')
        with self.db.tx() as s:
            self._account(s,actor,'operator');row=s.get(DispatchPolicy,ref)
            if (row.version if row else 0)!=expected_version:raise Problem('执行策略已变化，请刷新',409,'POLICY_CHANGED')
            p=policy_dict(row,ref);limit=valid_capacity(s,ref,p['observed_fingerprint'])
            if values['mode']=='PARALLEL' and (serial_model(p['published_model']) or limit<values['max_concurrent']):
                raise Problem('该发布绑定尚未通过对应并发实测，或按项目策略必须串行',409,'VALIDATION_REQUIRED')
            if not row:row=DispatchPolicy(connection_ref=ref,version=0);s.add(row)
            for k,v in values.items():setattr(row,k,v)
            row.version+=1
            self._audit(s,actor,'WMA_POLICY_UPDATE',ref,f'版本{row.version}；{row.mode}；新调度={row.new_dispatch_enabled}')
        return self.execution_policies(actor=actor,binding_refs=[ref])['items'][0]

    def confirm_remote_terminal(self,id,reason,*,actor):
        if not isinstance(reason,str) or not reason.strip() or len(reason)>500:raise Problem('请填写在WMA侧确认结束的依据')
        with self.db.tx() as s:
            self._account(s,actor,'operator');t=s.get(Task,id)
            if not t:raise Problem('任务不存在',404)
            d=ensure_dispatch(s,t)
            if d.lease_owner and d.lease_expires_at and aware(d.lease_expires_at)>now():raise Problem('本地工作进程仍持有租约，不能解除占用',409)
            if t.status not in ('NEEDS_RECOVERY','FAILED','CANCELLED'):raise Problem('此任务无需人工解除远端占用',409)
            d.remote_pending=False
            self._audit(s,actor,'REMOTE_TERMINAL_CONFIRMED',id,reason.strip())
            return {'confirmed':True,'remote_stop_called':False}


def claim(product,ref,fingerprint,owner):
    from urllib.parse import urlsplit
    with product.db.tx() as s:
        if s.get(Meta,'wma_live_probe'):return None
        current=policy_dict(s.get(DispatchPolicy,ref),ref)
        # Turn crashed claims into recovery candidates, NEVER back into QUEUED.
        for t,d in s.execute(select(Task,TaskDispatch).join(TaskDispatch,Task.id==TaskDispatch.task_id).where(Task.status=='RUNNING')):
            if d.lease_expires_at and aware(d.lease_expires_at)<=now():
                t.status='NEEDS_RECOVERY';t.error_code='WORKER_LEASE_EXPIRED';d.lease_owner=None
                product._audit(s,'WORKER','LEASE_EXPIRED',t.id,'需恢复文件；未重发调查')
        active=list(s.scalars(select(TaskDispatch)))
        occupied=[d for d in active if d.remote_pending or (d.lease_owner and d.lease_expires_at and aware(d.lease_expires_at)>now())]
        for t in s.scalars(select(Task).where(Task.status.in_(['QUEUED','RECOVERY_QUEUED'])).order_by(Task.created_at,Task.id)):
            d=ensure_dispatch(s,t)
            if d.connection_ref!=ref:continue
            recovery=t.status=='RECOVERY_QUEUED'
            if d.lease_owner and d.lease_expires_at and aware(d.lease_expires_at)>now():continue
            if not recovery and not current['new_dispatch_enabled']:continue
            source=product._source(s,t.source_id);a=s.get(Account,t.creator_id)
            if not a or not a.active or 'operator' not in a.roles:continue
            if not recovery and (not source['active'] or not source['enabled']):continue
            frozen=s.get(TaskSourceContext,t.id)
            if not recovery and frozen and frozen.payload.get('policy_version')!=source['policy_version']:
                t.status='FAILED';t.stage='POLICY_CHANGED';t.error_code='SOURCE_POLICY_CHANGED';t.updated_at=now();continue
            if not recovery and d.prompt_started:
                t.status='NEEDS_RECOVERY';t.error_code='PROMPT_ALREADY_STARTED';continue
            if d.binding_fingerprint and fingerprint and d.binding_fingerprint!=fingerprint:
                t.status='FAILED' if not recovery else 'NEEDS_RECOVERY';t.error_code='BINDING_CHANGED';t.updated_at=now();continue
            # A direct compatibility caller with no checked fingerprint is always serial.
            model=current['published_model'] if fingerprint else ''
            valid=valid_capacity(s,ref,fingerprint)
            snap=d.policy_snapshot or current
            cap=min(effective_parallel(current['mode'],current['max_concurrent'],model,valid),
                    effective_parallel(snap.get('mode','SERIAL'),snap.get('max_concurrent',1),model,valid))
            other=[x for x in occupied if x.task_id!=t.id]
            same=[x for x in other if x.connection_ref==ref]
            if same:cap=min(cap,*(x.policy_snapshot.get('max_concurrent',1) for x in same))
            # Recovery does not consume another remote prompt slot, but only one
            # local recovery may own this task and no new prompt is ever sent.
            if not recovery:
                if len(same)>=cap:continue
                if serial_model(model) and model and any(serial_model(x.model_name) and x.model_name for x in other):continue
                host=urlsplit(t.notice_url).hostname
                hosts=0
                for x in other:
                    ot=s.get(Task,x.task_id)
                    if ot and urlsplit(ot.notice_url).hostname==host:hosts+=1
                if hosts>=min(current['domain_limit'],snap.get('domain_limit',1)):continue
            d.binding_fingerprint=d.binding_fingerprint or fingerprint or ''
            d.model_name=model or d.model_name;d.lease_owner=owner;d.lease_expires_at=now()+timedelta(seconds=LEASE_SECONDS)
            t.status='RUNNING';t.attempts+=1;t.updated_at=now()
            if frozen:source={**source,**frozen.payload}
            return {'id':t.id,'source_id':t.source_id,'actor':a.username,'url':t.notice_url,'instruction':t.instruction,'kind':t.kind,
                'budget':min(t.budget_seconds,snap.get('task_budget_seconds',1200)),'recovery':recovery,
                'runtime_id':t.runtime_id,'session_id':t.session_id,'workspace':t.workspace,'files':dict(t.files),'source':source}
    return None


def pulse_lease(product,id,owner):
    with product.db.tx() as s:
        d=s.get(TaskDispatch,id)
        if not d or d.lease_owner!=owner or not d.lease_expires_at or aware(d.lease_expires_at)<=now():raise Problem('任务租约已失效',409,'LEASE_LOST')
        d.lease_expires_at=now()+timedelta(seconds=LEASE_SECONDS)


def finish_lease(product,id,owner):
    with product.db.tx() as s:
        d=s.get(TaskDispatch,id);t=s.get(Task,id)
        if not d or d.lease_owner!=owner:return
        d.lease_owner=None;d.lease_expires_at=None
        if t.status=='RUNNING':t.status='NEEDS_RECOVERY';t.error_code='WORKER_INTERRUPTED'
        if t.status=='READY':d.remote_pending=False


def assert_worker_lease(s,task_id,owner):
    t=s.get(Task,task_id);d=s.get(TaskDispatch,task_id)
    if not t or not d or d.lease_owner!=owner or not d.lease_expires_at or aware(d.lease_expires_at)<=now():
        raise Problem('任务租约已失效',409,'LEASE_LOST')
    if t.status=='CANCELLED':raise Problem('本地后续处理已停止',409,'LOCAL_CANCELLED')
    if t.status!='RUNNING':raise Problem('任务不再由当前进程处理',409,'LEASE_LOST')
    return t
