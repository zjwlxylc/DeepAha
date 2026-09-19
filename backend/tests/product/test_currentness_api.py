from fastapi.testclient import TestClient
from .test_contract import svc
from .test_currentness import currentness_packet, approve, targets, day


def _login(client,name):
    r=client.post('/api/auth/login',json={'username':name,'password':'long-password-123'})
    assert r.status_code==200,r.text
    client.headers['X-CSRF-Token']=r.json()['csrf']


def _client(svc):
    from deepaha.product.api import create_app
    from deepaha.product.config import Settings
    app=create_app(Settings(database_url=svc.database_url,data_dir=svc.object_root.parent,
                            public_catalog=True,allowed_hosts=['testserver']),product=svc)
    return TestClient(app)


def test_history_compare_and_targeted_recheck_api(svc):
    approve(svc,currentness_packet(a_deadline=day(40)),'api-sg3-v1')
    tid=targets(svc)['A01']['id']
    preview=svc.ingest(svc.test_source,currentness_packet(a_deadline=day(70)),actor='operator')
    svc.decide(preview['id'],'APPROVE',preview['preview_hash'],'','api-sg3-v2',actor='reviewer')
    with _client(svc) as client:
        history=client.get(f'/api/catalog/{tid}/history')
        assert history.status_code==200,history.text
        versions=history.json()['versions']
        assert len(versions)>=2
        compare=client.get(f'/api/catalog/{tid}/compare',params={
            'from_id':versions[1]['catalog_target_id'],'to_id':versions[0]['catalog_target_id']})
        assert compare.status_code==200,compare.text
        assert compare.json()['changes']['deadline']=={'before':day(40),'after':day(70)}
        _login(client,'operator')
        task=client.post(f'/api/manage/catalog/{tid}/recheck',json={'request_key':'api-target-recheck','budget_seconds':1200})
        assert task.status_code==200,task.text
        assert task.json()['kind']=='RECHECK'


def test_manual_target_withdrawal_does_not_withdraw_sibling(svc):
    approve(svc,currentness_packet(),'api-target-withdraw-initial')
    before=targets(svc)
    with _client(svc) as client:
        _login(client,'reviewer')
        r=client.post(f"/api/catalog/{before['A01']['id']}/withdraw",json={'reason':'该岗位已明确撤回'})
        assert r.status_code==200,r.text
        assert r.json()['scope']=='TARGET'
    after=targets(svc)
    assert 'A01' not in after
    assert after['A02']['id']==before['A02']['id']
