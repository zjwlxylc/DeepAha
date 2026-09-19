from fastapi.testclient import TestClient
from sqlalchemy import text
from .test_contract import svc,packet
from .test_api import login


def approve(svc):
    p=svc.ingest(svc.test_source,packet(),actor='operator')
    r=svc.decide(p['id'],'APPROVE',p['preview_hash'],'','sg6-api-approve',actor='reviewer')
    return r['catalog_target_ids'][0]


def test_sg6_api_action_history_digest_and_feedback_candidates(svc):
    from deepaha.product.api import create_app
    from deepaha.product.config import Settings
    target=approve(svc)
    app=create_app(Settings(database_url=svc.database_url,data_dir=svc.object_root.parent,public_catalog=True,allowed_hosts=['testserver']),product=svc)
    with TestClient(app) as client:
        login(client,'reader')
        r=client.put('/api/me/profile',json={
            'notification_enabled':True,'notification_deadline_enabled':True,
            'notification_change_enabled':True,'notification_weekly_enabled':True,
            'deadline_reminder_days':[7,1]
        })
        assert r.status_code==200,r.text
        assert client.put('/api/me/actions/'+target,json={'status':'PREPARING','note':'准备证明材料'}).status_code==200
        h=client.get('/api/me/actions/'+target+'/history')
        assert h.status_code==200 and h.json()['current_status']=='PREPARING' and h.json()['events']
        d=client.get('/api/me/weekly-digest')
        assert d.status_code==200 and d.json()['action_summary']['PREPARING']==1
        fb=client.post('/api/me/feedback/'+target,json={'useful':True,'outcome':'INTERVIEW','action_reason':'WORTH_APPLYING'})
        assert fb.status_code==200 and fb.json()['evaluation_candidate']=='CANDIDATE'
        assert client.get('/api/me/actions/'+target+'/history').json()['current_status']=='WAITING'
        login(client,'operator')
        candidates=client.get('/api/manage/feedback-candidates')
        assert candidates.status_code==200 and candidates.json()['total']==1
        assert 'reader' not in candidates.text
