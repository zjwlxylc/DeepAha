import asyncio
import pytest
from .test_contract import svc
from deepaha.product.errors import Problem


def test_live_runner_requires_explicit_cost_confirmation_before_registry_access(svc,tmp_path):
    import deepaha.product.live_validation as live
    class ForbiddenRegistry:
        def factory(self,*args):raise AssertionError('credentials must not be loaded')
    with pytest.raises(Problem) as e:
        asyncio.run(live.validate_live(svc,ForbiddenRegistry(),actor='operator',connection_ref='default',source_id=svc.test_source,url='https://research.example.org/notices/101',parallel=2,max_prompts=0,budget_seconds=60,confirmed=False,evidence_dir=tmp_path/'live'))
    assert e.value.code=='LIVE_AUTHORIZATION_REQUIRED'
    assert not (tmp_path/'live').exists()


def test_peak_counts_overlap_not_total_requests():
    from deepaha.product.live_validation import request_peak
    assert request_peak([{'prompt_started':1,'prompt_finished':4},{'prompt_started':2,'prompt_finished':3}])==2
    assert request_peak([{'prompt_started':1,'prompt_finished':2},{'prompt_started':2,'prompt_finished':3}])==1


def test_live_factory_failure_is_durable_and_does_not_grant(svc,tmp_path):
    import json
    from deepaha.product.live_validation import validate_live
    class Reader:
        async def inspect_release(self):return {'published_model':'other-model'}
        async def aclose(self):pass
    class Registry:
        created=0
        def fingerprint(self,*args):return 'binding-1'
        def factory(self,*args):
            def create():
                self.created+=1
                if self.created==2:raise RuntimeError('synthetic factory failure')
                return Reader()
            return create
    result=asyncio.run(validate_live(svc,Registry(),actor='operator',connection_ref='default',source_id=svc.test_source,
        url='https://research.example.org/notices/101',parallel=1,max_prompts=1,budget_seconds=60,confirmed=True,evidence_dir=tmp_path/'live'))
    assert result['status']=='FAIL' and result['grant_created'] is False
    report=json.loads((tmp_path/'live/report.json').read_text())
    assert report['status']=='FAIL' and report['records'][0]['state']=='FAILED'
    assert not (tmp_path/'live/grant-receipt.json').exists()


def test_live_probe_reservation_blocks_workers_and_another_probe(svc,tmp_path):
    from deepaha.product.models import Meta
    from deepaha.product.dispatch_policy import claim
    from deepaha.product.live_validation import validate_live
    svc.create_task(svc.test_source,'https://research.example.org/1',actor='operator',request_key='probe-guard')
    with svc.db.tx() as s:s.add(Meta(key='wma_live_probe',value='{"run_id":"pending","status":"RUNNING"}'))
    assert claim(svc,'default',None,'worker') is None
    class ForbiddenRegistry:
        def factory(self,*args):raise AssertionError('a second probe must not reach credentials')
    with pytest.raises(Problem) as err:
        asyncio.run(validate_live(svc,ForbiddenRegistry(),actor='operator',connection_ref='default',source_id=svc.test_source,
            url='https://research.example.org/notices/101',parallel=1,max_prompts=1,budget_seconds=60,confirmed=True,evidence_dir=tmp_path/'live'))
    assert err.value.code=='LIVE_PROBE_BUSY'


def test_live_probe_refuses_existing_remote_reservation(svc,tmp_path):
    from deepaha.product.models import TaskDispatch
    from deepaha.product.live_validation import validate_live
    t=svc.create_task(svc.test_source,'https://research.example.org/1',actor='operator',request_key='remote-guard')
    with svc.db.tx() as s:s.get(TaskDispatch,t['id']).remote_pending=True
    class ForbiddenRegistry:
        def factory(self,*args):raise AssertionError('must not start probe alongside existing remote request')
    with pytest.raises(Problem) as err:
        asyncio.run(validate_live(svc,ForbiddenRegistry(),actor='operator',connection_ref='default',source_id=svc.test_source,
            url='https://research.example.org/notices/101',parallel=1,max_prompts=1,budget_seconds=60,confirmed=True,evidence_dir=tmp_path/'live'))
    assert err.value.code=='LIVE_PROBE_BUSY'


def test_uncertain_live_probe_reserves_until_host_confirmation(svc,tmp_path):
    from deepaha.product.models import Meta
    from deepaha.product.live_validation import validate_live,resolve_probe
    class Interrupted:
        async def inspect_release(self):return {'published_model':'other-model'}
        async def create(self,key,checkpoint):checkpoint('synthetic-runtime','synthetic-session')
        async def upload(self,*args):pass
        async def prompt(self,*args,**kwargs):raise TimeoutError('synthetic timeout')
        async def aclose(self):pass
    class Registry:
        def factory(self,*args):return Interrupted
        def fingerprint(self,*args):return 'binding-1'
    result=asyncio.run(validate_live(svc,Registry(),actor='operator',connection_ref='default',source_id=svc.test_source,
        url='https://research.example.org/notices/101',parallel=1,max_prompts=1,budget_seconds=60,confirmed=True,evidence_dir=tmp_path/'live'))
    assert result['status']=='FAIL'
    with svc.db.tx(False) as s:assert s.get(Meta,'wma_live_probe') is not None
    with pytest.raises(Problem):resolve_probe(svc,actor='operator',confirmed=False,reason='not yet verified')
    assert resolve_probe(svc,actor='operator',confirmed=True,reason='Synthetic test only: verified no remote session remains')['remote_stop_called'] is False
    with svc.db.tx(False) as s:assert s.get(Meta,'wma_live_probe') is None
