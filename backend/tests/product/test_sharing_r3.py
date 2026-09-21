import io,json,hashlib
import pytest
from PIL import Image
from .test_api import client,login
from .test_contract import svc,packet


def config(client):
    login(client,'operator')
    r=client.get('/api/manage/sharing');assert r.status_code==200,r.text
    return {k:v for k,v in r.json().items() if k not in ('diagnostics',)}


def test_og_rendered_before_javascript_no_host_poison(client):
    r=client.get('/')
    assert 'property="og:title"' in r.text
    assert 'https://deepaha.com/' in r.text
    assert 'og:image:width' in r.text and 'og:image:alt' in r.text
    assert r.headers['cache-control']=='no-store'
    assert 'testserver' not in r.text
    p=client.get('/app/profile')
    assert 'noindex' in p.text and 'property="og:title"' not in p.text
    assert 'https://res.wx.qq.com' not in p.headers['content-security-policy']


def test_public_share_landing_clickable_and_sdk_limited(client):
    r=client.get('/share')
    assert r.status_code==200 and 'og:title' in r.text
    assert 'href="/app/overview"' in r.text
    assert '/product/share-page.js' in r.text
    assert 'https://res.wx.qq.com' in r.headers['content-security-policy']
    assert client.get('/api/share/wechat-signature',params={'url':'https://deepaha.com/share'}).json()['enabled'] is False


def test_operator_controls_version_and_escaping(client):
    d=config(client);d['title']='找机会 " /><script>bad()</script>';d['description']='公开说明 & "安全"'
    r=client.put('/api/manage/sharing',json=d);assert r.status_code==200,r.text
    assert client.put('/api/manage/sharing',json=d).status_code==409
    h=client.get('/share').text
    assert '<script>bad()' not in h and '&lt;script&gt;' in h
    login(client,'reviewer')
    assert client.get('/api/manage/sharing').status_code==403
    assert client.put('/api/manage/sharing',json=d).status_code==403


@pytest.mark.parametrize('origin',['http://deepaha.com','https://localhost','https://127.0.0.1','https://[::1]','https://deepaha.com.evil/a','https://u:p@deepaha.com','https://deepaha.com?evil=1','https://foo.local'])
def test_bad_origins_rejected(client,origin):
    d=config(client);d['origin']=origin
    assert client.put('/api/manage/sharing',json=d).status_code==400


def test_cover_decoded_reencoded_hashed_and_permission(client):
    data=io.BytesIO();Image.new('RGB',(1500,900),(10,68,179)).save(data,'PNG')
    login(client,'reader')
    assert client.post('/api/manage/sharing/cover?kind=wide',content=data.getvalue()).status_code==403
    login(client,'operator')
    r=client.post('/api/manage/sharing/cover?kind=wide',content=data.getvalue(),headers={'content-type':'image/png'})
    assert r.status_code==200,r.text
    id=r.json()['asset'];body=client.get('/share-assets/'+id).content
    assert Image.open(io.BytesIO(body)).size==(1200,630)
    assert hashlib.sha256(body).hexdigest()+'.jpg'==id
    assert 'immutable' in client.get('/share-assets/'+id).headers['cache-control']
    d=config(client);d['cover']=id
    assert client.put('/api/manage/sharing',json=d).status_code==200
    assert '/share-assets/'+id in client.get('/share').text
    assert client.post('/api/manage/sharing/cover?kind=wide',content=b'<svg onload=evil/>').status_code==400
    assert client.post('/api/manage/sharing/cover?kind=anything',content=data.getvalue()).status_code==422


def test_only_current_public_fact_metadata_and_withdrawal(client,svc):
    a=svc.ingest(svc.test_source,packet('测试科研申请'),actor='operator')
    svc.decide(a['id'],'APPROVE',a['preview_hash'],'','share-r3-test',actor='reviewer')
    item=svc.catalog()['items'][0];id=item['id']
    r=client.get('/share/opportunity/'+id);assert r.status_code==200,r.text
    assert '测试科研申请' in r.text
    assert 'href="/app/opportunity/'+id+'"' in r.text
    assert client.get('/app/opportunity/'+id).status_code==200
    assert client.get('/share/opportunity/not-real').status_code==404
    svc.withdraw(id,'公告已失效',actor='reviewer')
    r=client.get('/share/opportunity/'+id)
    assert r.status_code in (404,410) and '测试科研申请' not in r.text


def test_nonpublic_catalog_does_not_leak_share(client,svc):
    a=svc.ingest(svc.test_source,packet('不可公开名称'),actor='operator');svc.decide(a['id'],'APPROVE',a['preview_hash'],'','r3-private',actor='reviewer')
    id=svc.catalog()['items'][0]['id']
    client.app.state.settings.public_catalog=False
    r=client.get('/share/opportunity/'+id)
    assert r.status_code==404 and '不可公开名称' not in r.text


def test_signature_url_cannot_sign_external_or_private(client):
    for u in ['https://evil.org/share','https://deepaha.com/app/profile','https://deepaha.com/share/../manage','https://deepaha.com/share?secret=private','https://deepaha.com:8443/share']:
        r=client.get('/api/share/wechat-signature',params={'url':u})
        assert r.status_code==400,(u,r.text)


def test_wechat_verification_file_exact_and_no_arbitrary_path(client):
    d=config(client);d.update(verification_name='MP_verify_testR3.txt',verification_text='safeDomainVerification123')
    r=client.put('/api/manage/sharing',json=d);assert r.status_code==200,r.text
    r=client.get('/MP_verify_testR3.txt');assert r.text=='safeDomainVerification123'
    assert client.get('/MP_verify_other.txt').status_code==404
    d['version']=r=client.get('/api/manage/sharing').json()['version'];d['verification_name']='../.env'
    assert client.put('/api/manage/sharing',json=d).status_code==400


def test_private_catalog_keeps_normal_app_shell_but_no_og(client,svc):
    a=svc.ingest(svc.test_source,packet('只供登录用户查看'),actor='operator');svc.decide(a['id'],'APPROVE',a['preview_hash'],'','r3-private-shell',actor='reviewer')
    id=svc.catalog()['items'][0]['id'];client.app.state.settings.public_catalog=False
    login(client,'reader');r=client.get('/app/opportunity/'+id)
    assert r.status_code==200 and 'id="app"' in r.text
    assert 'og:title' not in r.text and '只供登录用户查看' not in r.text
    assert client.get('/share/opportunity/'+id).status_code==404
