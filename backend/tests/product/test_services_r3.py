"""R3 integration against the actual R2 Product, database and HTTP application."""
from datetime import datetime, timedelta, timezone
import json
import pytest
from .test_api import client, login
from .test_contract import svc, packet

P='/api/membership'

def published(client, code='basic'):
    login(client,'operator')
    r=client.post(P+'/manage/plans/'+code+'/status',json={'version':1,'status':'PUBLISHED'})
    assert r.status_code==200,r.text
    return r.json()

def trial(client, code='basic'):
    plan=published(client,code)
    login(client,'reader')
    r=client.post(P+'/orders',json={'key':'r3-order-'+code,'code':code,'version':plan['version'],'note':'关注公开网站的科研机会'})
    assert r.status_code==200,r.text
    order=r.json()
    if code=='custom':
        login(client,'operator')
        q=client.post(P+'/manage/orders/'+order['id']+'/quote',json={'key':'r3-quote-0001','version':order['version'],'amount_cents':20000,'months':2,'site_limit':3,'topic_limit':10,'scope':'跟踪指定公开网站中的科研项目机会，保留公开原文和附件依据'})
        assert q.status_code==200,q.text
        login(client,'reader')
        q=client.post(P+'/orders/'+order['id']+'/accept',json={'key':'r3-accept-0001','version':q.json()['version']})
        assert q.status_code==200,q.text
        order=q.json()
    login(client,'operator')
    r=client.post(P+'/manage/orders/'+order['id']+'/confirm',json={'key':'r3-trial-'+code,'version':order['version'],'method':'TRIAL','amount_cents':0,'reference':'','reason':'集成验收试用，不代表真实收款'})
    assert r.status_code==200,r.text
    login(client,'reader')
    return order


def test_member_routes_share_real_auth_roles_and_csrf(client):
    r=client.get(P+'/plans')
    assert r.status_code==200,r.text
    assert r.json()==[]  # No silently published prices.
    assert client.get(P+'/me').status_code==401
    login(client,'reviewer')
    assert client.get(P+'/manage/plans').status_code==403
    assert client.get(P+'/review/leads').status_code==200
    login(client,'operator')
    assert len(client.get(P+'/manage/plans').json())==3
    assert client.post(P+'/manage/plans/basic/status',json={'status':'PUBLISHED','version':1},headers={'X-CSRF-Token':'bad'}).status_code==403


def test_real_trial_changes_entitlements_not_role_or_free_catalog(client):
    trial(client)
    me=client.get(P+'/me').json()
    assert me['entitlements']['tier']=='BASIC'
    assert me['roles']==['user']
    assert client.get('/api/catalog').status_code==200
    assert client.get('/api/review').status_code==403
    assert client.get(P+'/manage/orders').status_code==403


def test_messages_merge_badges_batch_read_and_do_not_leak(client,svc):
    trial(client)
    msgs=client.get('/api/me/notification-list').json()
    assert any(n['id'].startswith('mbr:') for n in msgs['items']),msgs
    assert client.get('/api/me/summary').json()['unread_count']==msgs['unread_count']
    ids=[n['id'] for n in msgs['items']]
    login(client,'reviewer')
    assert client.post('/api/me/notifications/read',json={'ids':ids}).status_code==404
    login(client,'reader')
    assert client.post('/api/me/notifications/read',json={'ids':ids}).status_code==200
    assert client.get('/api/me/summary').json()['unread_count']==0


def test_export_and_erase_cover_member_private_data_preserve_contract(client,svc):
    trial(client)
    r=client.post(P+'/watches/topics',json={'key':'r3-topic-0001','name':'私人主题','q':'科研','kind':'','region':''})
    assert r.status_code==200,r.text
    r=client.post(P+'/submissions',json={'key':'r3-source-0001','name':'研究网站','url':'https://research.example.org/jobs','note':'不应保留的私人描述','consent':True,'kind':'SOURCE'})
    assert r.status_code==200,r.text
    export=client.get('/api/me/export').json()
    assert export['membership']['watches'] and export['membership']['submissions']
    assert '不应保留的私人描述' in json.dumps(export,ensure_ascii=False)
    assert client.delete('/api/me/data').status_code==200
    export=client.get('/api/me/export').json()['membership']
    assert not export['watches'] and not export['submissions'] and not export['notices']
    assert export['orders'] and export['grants']
    assert client.get(P+'/me').json()['entitlements']['tier']=='BASIC'
    # Replays may not resurrect erased private data.
    assert '不应保留的私人描述' not in json.dumps(export,ensure_ascii=False)


def test_free_site_enters_review_without_publishing(client,svc):
    login(client,'reader')
    payload={'key':'r3-source-0002','name':'研究中心','url':'https://research.example.org/jobs','note':'建议补充该网站','consent':True,'kind':'SOURCE'}
    a=client.post(P+'/submissions',json=payload)
    assert a.status_code==200,a.text
    assert client.post(P+'/submissions',json=payload).json()==a.json()
    assert svc.catalog()['total']==0
    login(client,'reviewer')
    q=client.get(P+'/review/leads').json()
    assert len(q)==1
    r=client.post(P+'/review/leads/'+q[0]['id']+'/decision',json={'key':'r3-review-0002','version':q[0]['version'],'decision':'APPROVE','note':'可用公开机会栏目','public_brief':'调查公开的科研项目，保留原文和附件。','approved_url':payload['url'],'tier':'COMMUNITY_SIGNAL'})
    assert r.status_code==200,r.text
    assert svc.catalog()['total']==0
    assert client.post(P+'/manage/leads/'+q[0]['id']+'/adopt').status_code==403


def test_runtime_settings_explicit_versioned_authorization(client):
    login(client,'reader')
    assert client.get(P+'/manage/runtime').status_code==403
    login(client,'operator')
    r=client.get(P+'/manage/runtime')
    assert r.status_code==200,r.text
    data=r.json(); assert not data['enabled'] and not data['allow_site_enqueue']
    config={'version':data['version'],'enabled':True,'allow_site_enqueue':False,'max_jobs':2,'connection':'default'}
    r=client.put(P+'/manage/runtime',json=config)
    assert r.status_code==200,r.text
    assert r.json()['actor']=='operator'
    assert client.put(P+'/manage/runtime',json=config).status_code==409
