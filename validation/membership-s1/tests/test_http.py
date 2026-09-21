import importlib
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client(tmp_path):
    try:M=importlib.import_module('deepaha_membership.demo')
    except ImportError:pytest.fail('http/demo implementation missing')
    app=M.create_demo(tmp_path/'http.db',{'alice':'Alice-password-2026','bob':'Bob-password-2026','maintainer':'Admin-password-2026','reviewer':'Review-password-2026'})
    with TestClient(app) as c:yield c

def login(c,name='alice',password='Alice-password-2026'):
    r=c.post('/api/auth/login',json=dict(username=name,password=password));assert r.status_code==200
    c.headers['x-csrf-token']=r.json()['csrf']
    return r.json()

def publish(c):
    login(c,'maintainer','Admin-password-2026')
    r=c.post('/api/membership/manage/plans/basic/status',json={'status':'PUBLISHED','version':1});assert r.status_code==200

def test_assets_and_draft_catalog(client):
    assert client.get('/membership').status_code==200
    assert client.get('/membership/app.js').status_code==200
    r=client.get('/api/membership/plans');assert r.status_code==200 and r.json()==[]
    assert client.get('/api/membership/me').status_code==401

def test_login_and_protected_request_requires_csrf(client):
    login(client);client.headers.pop('x-csrf-token')
    r=client.post('/api/membership/submissions',json=dict(name='公开网站',url='https://example.org/',kind='SOURCE',note='',consent=True,key='submit-http-key'))
    assert r.status_code==403

def test_cross_origin_rejected(client):
    login(client)
    r=client.post('/api/membership/submissions',headers={'Origin':'https://attacker.example'},json=dict(name='公开网站',url='https://example.org/',kind='SOURCE',note='',consent=True,key='submit-http-key'))
    assert r.status_code==403

def test_price_visibility_and_real_order_flow(client):
    publish(client);login(client)
    r=client.post('/api/membership/orders',json=dict(code='basic',version=1,key='order-http-key',note=''))
    assert r.status_code==200
    o=r.json();assert client.get('/api/membership/me').json()['entitlements']['tier']=='FREE'
    login(client,'maintainer','Admin-password-2026')
    r=client.post(f"/api/membership/manage/orders/{o['id']}/confirm",json=dict(version=1,method='TRIAL',amount_cents=0,reference='',reason='本地试用开通测试',key='confirm-http-key'))
    assert r.status_code==200
    login(client)
    assert client.get('/api/membership/me').json()['entitlements']['tier']=='BASIC'
    r=client.post('/api/membership/watches/topics',json=dict(name='校招',q='校招',kind='',region='',key='watch-http-key'))
    assert r.status_code==200

def test_normal_user_cannot_change_price_or_read_another_order(client):
    publish(client);login(client)
    o=client.post('/api/membership/orders',json=dict(code='basic',version=1,key='order-http-key',note='')).json()
    assert client.get('/api/membership/manage/orders').status_code==403
    assert client.post('/api/membership/manage/plans/basic/status',json=dict(status='ARCHIVED',version=1)).status_code==403
    login(client,'bob','Bob-password-2026')
    assert client.get('/api/membership/orders/'+o['id']).status_code==404

def test_reviewer_can_review_but_not_price_admin(client):
    login(client)
    s=client.post('/api/membership/submissions',json=dict(name='公开网站',url='https://example.org/',kind='SOURCE',note='个人备注不应外泄',consent=True,key='submit-http-key')).json()
    login(client,'reviewer','Review-password-2026')
    assert client.get('/api/membership/review/leads').status_code==200
    assert client.get('/api/membership/manage/plans').status_code==403
    r=client.post('/api/membership/review/leads/'+s['lead']['id']+'/decision',json=dict(version=1,decision='APPROVE',note='公开栏目核验通过',public_brief='仅收集栏目公开的招聘机会并提交审核',approved_url='https://example.org/',tier='COMMUNITY_SIGNAL',key='review-http-key'))
    assert r.status_code==200 and r.json()['state']=='APPROVED'

def test_input_strictness_and_bad_url_are_4xx(client):
    login(client)
    for u in ['http://127.0.0.1','https://example.org/?token=secret','javascript:alert(1)']:
        r=client.post('/api/membership/submissions',json=dict(name='公开网站',url=u,kind='SOURCE',note='',consent=True,key='submit-http-key'))
        assert 400<=r.status_code<500
    r=client.post('/api/membership/submissions',json=dict(name='公开网站',url='https://example.org/',kind='SOURCE',note='',consent=True,key='submit-http-key',username='maintainer'))
    assert r.status_code==422

def test_logout_invalidates_session(client):
    login(client);assert client.post('/api/auth/logout').status_code==200
    assert client.get('/api/membership/me').status_code==401

def test_notice_owner_only_and_no_cookie_javascript(client):
    login(client)
    client.post('/api/membership/submissions',json=dict(name='公开网站',url='https://example.org/',kind='SOURCE',note='',consent=True,key='submit-http-key'))
    ns=client.get('/api/membership/notices').json();assert ns
    login(client,'bob','Bob-password-2026')
    assert client.post('/api/membership/notices/'+ns[0]['id']+'/read',json={}).status_code==404

def test_api_no_store_and_csp(client):
    r=client.get('/api/membership/plans');assert r.headers['cache-control']=='no-store'
    assert "object-src 'none'" in r.headers['content-security-policy']
