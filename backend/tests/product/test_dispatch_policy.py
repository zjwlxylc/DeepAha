"""Synthetic WMA transport for scheduling mechanics; NEVER provider capability evidence."""
import asyncio
from datetime import timedelta
import pytest
from sqlalchemy import select
from .test_contract import svc,packet
from .test_api import client,login
from deepaha.product.errors import Problem
from deepaha.product.models import Task,now


def task(p,key='dispatch-one'):
    return p.create_task(p.test_source,'https://research.example.org/notices/101',actor='operator',request_key=key)


def test_policy_is_serial_unverified_and_browser_cannot_grant(client):
    login(client,'operator')
    r=client.get('/api/manage/execution-policies');assert r.status_code==200
    assert r.json()['items'][0]['effective_concurrent']==1
    bad=client.put('/api/manage/execution-policies/default',json={'expected_version':0,'mode':'PARALLEL','max_concurrent':4,'verified':True})
    assert bad.status_code==422
    body={'expected_version':0,'mode':'PARALLEL','max_concurrent':2,'queue_limit':20,'task_budget_seconds':1200,'new_dispatch_enabled':True,'domain_limit':1}
    assert client.put('/api/manage/execution-policies/default',json=body).status_code==409


def test_policy_agens_and_unknown_force_serial(svc):
    assert hasattr(svc,'observe_binding'), 'server must inspect and bind the actual release'
    from deepaha.product.dispatch_policy import effective_parallel
    for model in ['AGENS','agnes-2.5-flash','AGENS-3','']:
        assert effective_parallel('PARALLEL',4,model,4)==1
    assert effective_parallel('PARALLEL',4,'other-model',0)==1
    assert effective_parallel('PARALLEL',4,'other-model',2)==2


class FakeClient:
    prompts=0;active=0;peak=0
    def __init__(self,fail=None):self.fail=fail
    async def create(self,id,checkpoint):
        checkpoint('runtime_'+id,'session_'+id)
        if self.fail=='create':raise RuntimeError('synthetic interruption')
    def binding_evidence(self):return {'published_model':'other-model','source':'CONTROL_PLANE'}
    async def upload(self,path,data):
        if self.fail=='upload':raise RuntimeError('synthetic interruption')
    async def prompt(self,prompt,timeout_seconds):
        type(self).prompts+=1;type(self).active+=1;type(self).peak=max(type(self).peak,type(self).active)
        try:
            await asyncio.sleep(.06)
            if self.fail=='prompt':raise TimeoutError('unknown remote acceptance')
            return 'done'
        finally:type(self).active-=1
    async def download(self,path,max_bytes):
        if self.fail=='download':raise RuntimeError('synthetic interruption')
        from deepaha.product.storage import unpack
        return unpack(packet())[path.split('/result/',1)[-1]]
    async def resume(self,ref):pass
    async def aclose(self):pass


def test_two_workers_one_task_prompt_once_and_durable_claim(svc):
    assert hasattr(svc,'execution_policies'), 'durable scheduler not installed'
    from deepaha.product.worker import run_once
    from deepaha.product.models import TaskDispatch
    t=task(svc);FakeClient.prompts=0
    async def race():return await asyncio.gather(run_once(svc,FakeClient),run_once(svc,FakeClient))
    result=asyncio.run(race())
    assert FakeClient.prompts==1 and sum(x['state']=='READY' for x in result)==1
    with svc.db.tx(False) as s:
        d=s.get(TaskDispatch,t['id']);assert d.prompt_started and not d.remote_pending and d.lease_owner is None


@pytest.mark.parametrize('phase',['create','upload','prompt','download'])
def test_interruption_never_automatically_reprompts(svc,phase):
    assert hasattr(svc,'execution_policies')
    from deepaha.product.worker import run_once
    from deepaha.product.models import TaskDispatch
    t=task(svc);FakeClient.prompts=0
    asyncio.run(run_once(svc,lambda:FakeClient(phase)))
    count=FakeClient.prompts
    assert svc.task_detail(t['id'],actor='operator')['status']=='NEEDS_RECOVERY'
    asyncio.run(run_once(svc,FakeClient));assert FakeClient.prompts==count
    svc.recover_task(t['id'],actor='operator')
    asyncio.run(run_once(svc,FakeClient));assert FakeClient.prompts==count
    assert svc.task_detail(t['id'],actor='operator')['status']=='READY'


def test_parallel_cap_with_simulated_trusted_grant_and_changed_binding(svc):
    assert hasattr(svc,'observe_binding')
    from deepaha.product.models import DispatchPolicy,DispatchValidation,TaskDispatch
    from deepaha.product.worker import run_once
    # TEST FIXTURE ONLY: simulates a previously measured LIVE record, does not run a provider.
    with svc.db.tx() as s:
        s.add(DispatchPolicy(connection_ref='default',version=1,mode='PARALLEL',max_concurrent=2,domain_limit=2,
            observed_fingerprint='fp1',published_model='other-model',release_evidence={}))
        s.add(DispatchValidation(connection_ref='default',binding_fingerprint='fp1',parallel=2,origin='LIVE',passed=True,report_sha256='a'*64))
    for n in range(4):task(svc,'par-'+str(n))
    FakeClient.prompts=FakeClient.peak=0
    async def race():return await asyncio.gather(*(run_once(svc,FakeClient,binding_fingerprint='fp1',connection_ref='default') for _ in range(4)))
    result=asyncio.run(race());assert FakeClient.peak==2 and FakeClient.prompts==2
    assert sum(x['state']=='READY' for x in result)==2
    asyncio.run(run_once(svc,FakeClient,binding_fingerprint='fp2'))
    assert FakeClient.prompts==2
    assert svc.search_tasks(actor='operator',status='FAILED')['total']==2


def test_expired_lease_fences_old_worker_and_preserves_uncertain_remote_slot(svc):
    assert hasattr(svc,'execution_policies')
    from deepaha.product.models import TaskDispatch
    from deepaha.product.worker import _patch,run_once
    t=task(svc)
    with svc.db.tx() as s:
        row=s.get(Task,t['id']);row.status='RUNNING';row.stage='PROMPT_STARTED'
        d=s.get(TaskDispatch,t['id']);d.lease_owner='lost';d.lease_expires_at=now()-timedelta(seconds=5);d.prompt_started=True;d.remote_pending=True
    with pytest.raises(Problem) as e:_patch(svc,t['id'],lease_owner='lost',stage='DONE')
    assert e.value.code=='LEASE_LOST'
    task(svc,'next-blocked');FakeClient.prompts=0
    result=asyncio.run(run_once(svc,FakeClient))
    assert FakeClient.prompts==0
    assert svc.task_detail(t['id'],actor='operator')['status']=='NEEDS_RECOVERY'


def test_pause_recovery_and_queue_limit(client,svc):
    login(client,'operator')
    r=client.get('/api/manage/execution-policies');assert r.status_code==200
    p=r.json()['items'][0]
    update={'expected_version':p['version'],'mode':'SERIAL','max_concurrent':1,'queue_limit':1,'task_budget_seconds':600,'new_dispatch_enabled':False,'domain_limit':1}
    assert client.put('/api/manage/execution-policies/default',json=update).status_code==200
    task(svc)
    with pytest.raises(Problem) as ex:task(svc,'over-capacity')
    assert ex.value.code=='QUEUE_FULL'
    from deepaha.product.worker import run_once
    FakeClient.prompts=0;asyncio.run(run_once(svc,FakeClient))
    assert FakeClient.prompts==0


def test_source_revoked_during_upload_never_sends_prompt(svc):
    from deepaha.product.worker import run_once
    class Revoking(FakeClient):
        async def upload(self,path,data):
            if path.endswith('task.json'):svc.source_status(svc.test_source,False,'撤销采集',actor='operator')
    task(svc);Revoking.prompts=0
    result=asyncio.run(run_once(svc,Revoking))
    assert Revoking.prompts==0 and result['code']=='SOURCE_POLICY_CHANGED'


def test_ingest_fences_cancelled_or_expired_worker_before_revision(svc):
    from deepaha.product.dispatch_policy import claim
    from deepaha.product.models import TaskDispatch,Revision
    t=task(svc);claim(svc,'default',None,'owner')
    svc.cancel_task(t['id'],actor='operator')
    with pytest.raises(Problem) as ex:
        svc.ingest(svc.test_source,packet(),actor='operator',task_id=t['id'],worker_lease='owner')
    assert ex.value.code in ('LOCAL_CANCELLED','LEASE_LOST')
    with svc.db.tx(False) as s:assert not list(s.scalars(select(Revision)))


def test_inspected_binding_change_does_not_claim_or_prompt(svc):
    from deepaha.product.worker import run_once
    class Changed(FakeClient):
        async def inspect_release(self):return {'configuration_sha256':'new'}
    task(svc);Changed.prompts=0
    result=asyncio.run(run_once(svc,Changed,binding_fingerprint='old',expected_release={'configuration_sha256':'old'}))
    assert result['state']=='BINDING_CHANGED' and Changed.prompts==0


def test_projection_runs_off_event_loop_so_lease_heartbeat_can_progress(svc,monkeypatch):
    import threading
    from deepaha.product.worker import run_once
    t=task(svc);original=svc.ingest;loop_thread=threading.get_ident();threads=[]
    def inspect_thread(*args,**kw):
        threads.append(threading.get_ident());return original(*args,**kw)
    monkeypatch.setattr(svc,'ingest',inspect_thread)
    result=asyncio.run(run_once(svc,FakeClient))
    assert result['state']=='READY' and threads and threads[0]!=loop_thread
