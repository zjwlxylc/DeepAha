import asyncio
from .test_contract import svc,packet
import pytest


def test_no_credentials_no_claim(svc):
    from deepaha.product.worker import run_once
    t=svc.create_task(svc.test_source,'https://research.example.org/notices/101',actor='operator',request_key='job1')
    out=asyncio.run(run_once(svc,client_factory=None))
    assert out['state']=='NOT_CONFIGURED'
    assert svc.task_detail(t['id'],actor='operator')['status']=='QUEUED'


def test_recovery_does_not_prompt_again(svc):
    from deepaha.product.worker import run_once
    from deepaha.product.models import Task
    from deepaha.product.storage import unpack
    class Fake:
        prompts=0
        async def resume(self,ref):pass
        async def download(self,path,max_bytes):return unpack(packet())[path.split('/result/',1)[-1]]
        async def aclose(self):pass
        async def prompt(self,*args,**kwargs):Fake.prompts+=1;raise AssertionError('must not reprompt')
    t=svc.create_task(svc.test_source,'https://research.example.org/notices/101',actor='operator',request_key='job2')
    with svc.db.tx() as s:
        r=s.get(Task,t['id']);r.status='NEEDS_RECOVERY';r.stage='PROMPT_STARTED';r.runtime_id='runtime1';r.session_id='session1';r.workspace='/workspace/deepaha/job2'
    svc.recover_task(t['id'],actor='operator')
    out=asyncio.run(run_once(svc,client_factory=lambda:Fake()))
    assert Fake.prompts==0
    assert svc.task_detail(t['id'],actor='operator')['status']=='READY'


def test_source_pause_stops_new_dispatch(svc):
    from deepaha.product.errors import Problem
    svc.source_status(svc.test_source,False,'维护',actor='operator')
    with pytest.raises(Problem):svc.create_task(svc.test_source,'https://research.example.org/notices/101',actor='operator',request_key='job3')
