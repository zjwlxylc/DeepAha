from .test_contract import svc,packet
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client(svc):
    from deepaha.product.api import create_app
    from deepaha.product.config import Settings
    app=create_app(Settings(database_url=svc.database_url,data_dir=svc.object_root.parent,public_catalog=True,allowed_hosts=['testserver']),product=svc)
    with TestClient(app) as c:yield c

def login(client,name):
    r=client.post('/api/auth/login',json={'username':name,'password':'long-password-123'})
    assert r.status_code==200,r.text
    client.headers['X-CSRF-Token']=r.json()['csrf']

def test_public_cannot_read_private_or_write(client):
    assert client.get('/api/catalog').status_code==200
    assert client.get('/api/review').status_code==401
    assert client.get('/api/manage/sources').status_code==401

def test_authenticated_real_upload_approve_catalog(client,svc):
    login(client,'operator')
    r=client.post('/api/intake/'+svc.test_source,content=packet(),headers={'Content-Type':'application/zip'})
    assert r.status_code==200,r.text
    value=r.json()
    login(client,'reader')
    assert client.post('/api/review/'+value['id']+'/decision',json={'decision':'APPROVE','preview_hash':value['preview_hash'],'note':'','request_key':'testrequest'}).status_code==403
    login(client,'reviewer')
    r=client.post('/api/review/'+value['id']+'/decision',json={'decision':'APPROVE','preview_hash':value['preview_hash'],'note':'','request_key':'testrequest'})
    assert r.status_code==200,r.text
    assert client.get('/api/catalog').json()['total']==1
    assert client.post('/api/legacy/human-test/runs',json={}).status_code==410

def test_csrf_origin_and_extra_input_rejected(client):
    login(client,'reader')
    r=client.put('/api/me/profile',json={'major':'广告学'},headers={'X-CSRF-Token':'wrong'})
    assert r.status_code==403
    r=client.put('/api/me/profile',json={'major':'广告学'},headers={'Origin':'https://evil.example'})
    assert r.status_code==403
    r=client.put('/api/me/profile',json={'major':'广告学','roles':['operator']})
    assert r.status_code in (400,422)

def test_no_secrets_in_manage_status(client):
    login(client,'operator')
    data=client.get('/api/manage/status').json()
    assert 'api_key' not in data and 'password' not in data

def test_product_html_no_fixture_script(client):
    r=client.get('/review/overview')
    assert r.status_code==200
    assert 'fixtures.js' not in r.text and 'model.js' not in r.text
    assert 'Content-Security-Policy' in r.headers

def test_sg5_value_endpoint_and_profile_controls(client,svc):
    from .test_personal_value import opportunity_packet
    login(client,'operator')
    blob=opportunity_packet('宁波青年科研实践',typ='RESEARCH_PROGRAM',region='宁波',summary='AI科研实践',unit_name='AI研究方向')
    r=client.post('/api/intake/'+svc.test_source,content=blob,headers={'Content-Type':'application/zip'})
    assert r.status_code==200,r.text
    preview=r.json()
    login(client,'reviewer')
    r=client.post('/api/review/'+preview['id']+'/decision',json={'decision':'APPROVE','preview_hash':preview['preview_hash'],'note':'','request_key':'sg5-api'})
    assert r.status_code==200,r.text
    target=client.get('/api/catalog?kind=RESEARCH_PROGRAM').json()['items'][0]['id']
    login(client,'reader')
    r=client.put('/api/me/profile',json={'cities':['宁波'],'interests':['科研'],'career_directions':['AI产品运营'],'personalization_enabled':True,'region_preference_mode':'PREFERRED'})
    assert r.status_code==200,r.text
    value=client.get('/api/me/value/'+target)
    assert value.status_code==200,value.text
    data=value.json()
    assert data['target_id']==target and data['why_for_you'] and data['llm_used'] is False
    star=client.get('/api/me/opportunities?limit=5').json()
    assert star['basis']=='LOCAL_VALUE_PRIORITY_V1' and star['featured']
