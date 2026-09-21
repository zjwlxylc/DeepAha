import asyncio
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from .test_contract import svc
from deepaha.product import cli, worker, membership
from deepaha.product.models import Meta, now


def test_normal_cli_enters_real_dispatch_path(svc, tmp_path, monkeypatch):
    from deepaha_membership.db import Store
    monkeypatch.setattr(cli.Settings, 'from_env', lambda: SimpleNamespace(data_dir=tmp_path, database_url='mock', mode='local'))
    monkeypatch.setattr(cli, 'Product', lambda *args: svc)
    monkeypatch.setattr(Store, 'assert_ready', lambda self: None)
    monkeypatch.setattr(worker, 'schedule_weekly_digests', lambda p: None)
    monkeypatch.setattr(membership, 'scheduled_tick', lambda *args: None)
    monkeypatch.setattr(cli.ConnectionConfig, 'factory', lambda self: None)
    cycle = AsyncMock(return_value={'state':'NOT_CONFIGURED'})
    monkeypatch.setattr(worker, 'run_cycle', cycle)
    assert cli.main(['worker', '--once']) == 0
    cycle.assert_awaited_once()
    cycle.side_effect=NameError('synthetic failure')
    with pytest.raises(SystemExit) as stopped:cli.main(['worker','--once'])
    assert stopped.value.code==1
    health=svc.runtime_status(actor='operator')['worker_health']
    assert health['dispatch']=='ERROR' and health['consecutive_errors']==1


def test_health_errors_staleness_and_recovery(svc):
    from deepaha.product.worker_health import record, status
    record(svc, 'STARTING')
    for _ in range(3):record(svc, 'ERROR', error='NameError')
    with svc.db.tx(False) as s:
        health=status(s)
    assert health['process']=='RESPONDING'
    assert health['dispatch']=='ERROR' and health['consecutive_errors']==3
    record(svc, 'OK')
    with svc.db.tx(False) as s:assert status(s)['dispatch']=='OK'
    with svc.db.tx() as s:
        row=s.get(Meta,'worker_health');data=json.loads(row.value)
        data['at']=(now()-timedelta(minutes=3)).isoformat();row.value=json.dumps(data)
    with svc.db.tx(False) as s:
        assert status(s)['process']=='STALE'
        assert status(s)['dispatch']=='STALE'


def test_binding_inspection_failure_is_not_healthy(svc):
    class Client:
        async def inspect_release(self):raise RuntimeError('private credential must not escape')
        async def aclose(self):pass
    registry=SimpleNamespace(public=lambda:[{'id':'default'}],factory=lambda ref:Client)
    result=asyncio.run(worker.run_cycle(svc,registry))
    assert result['dispatch_errors']==['BINDING_INSPECTION_FAILED']


def test_live_process_with_stopped_dispatch_is_unhealthy(svc):
    from deepaha.product.worker_health import record, status
    record(svc,'WORKING')
    with svc.db.tx() as s:
        row=s.get(Meta,'worker_health');value=json.loads(row.value)
        value['cycle_started_at']=(now()-timedelta(minutes=3)).isoformat()
        row.value=json.dumps(value)
    with svc.db.tx(False) as s:
        assert status(s)['process']=='RESPONDING'
        assert status(s)['dispatch']=='STALLED'
    worker.heartbeat(svc,'existing-task')
    with svc.db.tx(False) as s:assert status(s)['dispatch']=='WORKING'


def test_log_has_location_without_exception_secret(capsys):
    from deepaha.product.worker_health import log_error
    try:raise RuntimeError('SECRET_TEST_PASSWORD')
    except RuntimeError as error:log_error(error)
    output=capsys.readouterr().out
    assert 'SECRET_TEST_PASSWORD' not in output
    value=json.loads(output)
    assert value['code']=='RuntimeError' and value['frames'][-1]['line']>0


def test_normal_cli_runs_cycle_and_claim_without_real_wma(svc,tmp_path,monkeypatch):
    from deepaha_membership.db import Store
    from .test_dispatch_policy import FakeClient, task
    from deepaha.product.models import Task
    class Client(FakeClient):
        async def inspect_release(self):return {'published_model':'other-model','release_id':'test-release'}
    registry=SimpleNamespace(public=lambda:[{'id':'default'}],factory=lambda ref:Client,
                             fingerprint=lambda *args:'a'*64)
    monkeypatch.setattr(cli.Settings,'from_env',lambda:SimpleNamespace(data_dir=tmp_path,database_url='mock',mode='local'))
    monkeypatch.setattr(cli,'Product',lambda *args:svc)
    monkeypatch.setattr(Store,'assert_ready',lambda self:None)
    monkeypatch.setattr(worker,'schedule_weekly_digests',lambda p:None)
    monkeypatch.setattr(membership,'scheduled_tick',lambda *args:None)
    monkeypatch.setattr(cli.ConnectionConfig,'factory',lambda self:None)
    monkeypatch.setattr(cli,'BindingRegistry',lambda *args:registry)
    queued=task(svc,'normal-cli-real-claim')
    assert cli.main(['worker','--once'])==0
    with svc.db.tx(False) as s:
        row=s.get(Task,queued['id'])
        assert row.attempts==1 and row.runtime_id and row.session_id
        assert row.status=='READY'
