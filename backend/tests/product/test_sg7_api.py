from fastapi.testclient import TestClient
import pytest

from .test_api import login
from .test_contract import svc
from .test_personal_value import approve, opportunity_packet

@pytest.fixture
def client(svc):
    from deepaha.product.api import create_app
    from deepaha.product.config import Settings
    app=create_app(Settings(database_url=svc.database_url,data_dir=svc.object_root.parent,public_catalog=True,allowed_hosts=['testserver']),product=svc)
    with TestClient(app) as c:yield c


def test_sg7_operator_and_user_permissions_are_separated(client,svc):
    login(client,'reader')
    assert client.get('/api/manage/lab/summary').status_code==403
    assert client.post('/api/manage/lab/twins/seed').status_code==403
    assert client.get('/api/me/lab').status_code==200
    assert client.post('/api/me/lab/join').status_code==200
    assert client.get('/api/me/lab').json()['status']=='ACTIVE'

    login(client,'reviewer')
    assert client.get('/api/manage/lab/summary').status_code==403
    assert client.post('/api/me/lab/join').status_code==200

    login(client,'operator')
    assert client.get('/api/manage/lab/summary').status_code==200
    assert client.post('/api/manage/lab/twins/seed').status_code==200
    summary=client.get('/api/manage/lab/summary').json()
    assert summary['synthetic_twins']==100
    assert summary['production_authority']=='UNCHANGED'


def test_sg7_api_can_lock_case_pair_truth_and_run_without_wma(client,svc):
    target=approve(svc,opportunity_packet('SG7 API机会',typ='PUBLIC_INSTITUTION_JOB',unit_name='API岗位'),'sg7-api-case')
    login(client,'operator')
    client.post('/api/manage/lab/twins/seed')
    r=client.post('/api/manage/lab/gold',json={'target_id':target,'split':'CALIBRATION','truth_origin':'OPERATOR_ANNOTATED','annotation':{'note':'api'},'attestation_ref':None,'lock':True})
    assert r.status_code==200,r.text
    case=r.json()
    pair=client.post(f"/api/manage/lab/gold/{case['id']}/pair-truths",json={'twin_key':'TWIN-001','expected_eligibility':'UNCERTAIN','expected_recommendation':'EXPLORE','truth_origin':'OPERATOR_ANNOTATED','attestation_ref':None,'note':'人工测试配对'})
    assert pair.status_code==200,pair.text
    run=client.post('/api/manage/lab/runs',json={'kind':'GOLD_BENCHMARK','max_targets':1,'label':'api run'})
    assert run.status_code==200,run.text
    data=run.json()
    assert data['manifest']['production_mutation_allowed'] is False
    assert data['metrics']['llm_used'] is False
