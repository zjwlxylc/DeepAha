"""Experience contract tests use real HTTP/service transactions and synthetic accounts."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from sqlalchemy import select
from .test_contract import svc, packet
from .test_api import client, login
from deepaha.product.errors import Problem
from deepaha.product.models import Account, Source, SourceProfile, Task, now, uid


def published(p):
    r=p.ingest(p.test_source,packet(),actor='operator')
    p.decide(r['id'],'APPROVE',r['preview_hash'],'','experience-approve',actor='reviewer')
    return p.catalog()['items'][0]['id']


def test_versioned_profile_patch_preserves_omitted_and_explicit_clear(client,svc):
    svc.set_profile({'major':'广告学','certificates':['CET6'],'cities':['宁波'],'birth_date':'2000-02-29','notification_enabled':False},actor='reader')
    login(client,'reader')
    r=client.get('/api/me/profile-state');assert r.status_code==200
    state=r.json();assert state['profile']['major']=='广告学'
    data={'expected_version':state['version'],'changes':{'team_size':4,'birth_date':''}}
    r=client.patch('/api/me/profile',json=data);assert r.status_code==200,r.text
    assert r.json()['version']==state['version']+1
    saved=client.get('/api/me/profile').json()
    assert saved['major']=='广告学' and saved['certificates']==['CET6'] and saved['cities']==['宁波']
    assert saved['team_size']==4 and saved['birth_date']=='' and saved['notification_enabled'] is False
    assert client.patch('/api/me/profile',json=data).status_code==409
    assert client.patch('/api/me/profile',json={'expected_version':r.json()['version'],'changes':{'roles':['operator']}}).status_code==400
    assert client.patch('/api/me/profile',json={'expected_version':r.json()['version'],'changes':{'birth_date':'2001-02-29'}}).status_code==400
    assert client.get('/api/me/profile').json()==saved


def test_profile_two_clients_and_erase_cannot_resurrect_old_version(svc):
    assert hasattr(svc,'profile_state'), 'versioned profile state is required'
    version=svc.profile_state(actor='reader')['version']
    def update(city):
        try:return svc.patch_profile({'cities':[city]},version,actor='reader')['version']
        except Problem as e:return e.code
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(update,['宁波','杭州']))
    assert results.count('PROFILE_CHANGED')==1
    old=svc.profile_state(actor='reader')['version']
    svc.erase_personal(actor='reader')
    with pytest.raises(Problem) as ex:svc.patch_profile({'major':'old'},old,actor='reader')
    assert ex.value.code=='PROFILE_CHANGED'


def seed_sources(p):
    with p.db.tx() as s:
        for n in range(120):
            id=uid();s.add(Source(source_id=id,public_id='src_'+id.replace('-',''),canonical_url=f'https://src{n}.example.org/',authority_name=f'来源{n:03d}'))
            s.flush();s.add(SourceProfile(source_id=id,allowed_hosts=[f'src{n}.example.org'],scheduling_enabled=n>=50))


def test_source_search_full_population_stable_paging_and_permissions(client,svc):
    seed_sources(svc);login(client,'operator')
    r=client.get('/api/manage/source-search?q=来源119&enabled=true');assert r.status_code==200
    assert r.json()['total']==1 and r.json()['items'][0]['name']=='来源119'
    seen=[]
    for off in [0,30,60,90,120]:
        p=client.get(f'/api/manage/source-search?offset={off}&limit=30').json()
        assert p['total']==121
        seen.extend(x['id'] for x in p['items'])
    assert len(seen)==len(set(seen))==121
    assert client.get('/api/manage/source-search?q=%25').json()['total']==0
    assert client.get('/api/manage/source-search?limit=999').status_code==422
    target=r.json()['items'][0]
    svc.source_status(target['id'],False,'pause after select',actor='operator')
    bad=client.post('/api/manage/tasks',json={'source_id':target['id'],'url':target['url'],'request_key':'paused-selected'})
    assert bad.status_code==409
    assert isinstance(client.get('/api/manage/sources').json(),list)
    login(client,'reviewer');assert client.get('/api/manage/source-search').status_code==403


def test_task_search_counts_guidance_and_source_detail(client,svc):
    t=svc.create_task(svc.test_source,'https://research.example.org/notice',actor='operator',request_key='search-task',instruction='寻找独特的火星项目')
    login(client,'operator')
    r=client.get('/api/manage/task-search?q=火星');assert r.status_code==200
    assert r.json()['total']==1 and r.json()['items'][0]['id']==t['id']
    assert r.json()['counts']['QUEUED']==1
    assert r.json()['items'][0]['next_action']['kind']=='WAIT'
    assert client.get('/api/manage/task-search?status=READY').json()['total']==0
    src=client.get('/api/manage/sources/'+svc.test_source);assert src.status_code==200
    assert src.json()['task_counts']['QUEUED']==1
    with svc.db.tx() as s:
        row=s.get(Task,t['id']);row.status='NEEDS_RECOVERY';row.session_id='session_test';row.runtime_id='runtime_test'
    item=client.get('/api/manage/task-search?status=NEEDS_RECOVERY').json()['items'][0]
    assert item['next_action']['kind']=='RECOVER_FILES'
    assert client.post('/api/manage/tasks/'+t['id']+'/recover').status_code==200


def test_preparation_items_persist_isolate_conflict_export_erase(client,svc):
    target=published(svc);login(client,'reader')
    base='/api/me/actions/'+target+'/items'
    r=client.post(base,json={'text':'准备作品集','request_key':'prepare-one'});assert r.status_code==200,r.text
    item=r.json();assert item['origin']=='USER' and item['done'] is False and item['publication_id']
    assert client.post(base,json={'text':'准备作品集','request_key':'prepare-one'}).json()['id']==item['id']
    assert client.post(base,json={'text':'other','request_key':'prepare-one'}).status_code==409
    assert client.get(base).json()['items'][0]['text']=='准备作品集'
    url=base+'/'+item['id'];update={'expected_version':item['version'],'done':True}
    assert client.patch(url,json=update).status_code==200
    assert client.patch(url,json=update).status_code==409
    assert svc.detail(target)['eligibility']=='UNCERTAIN'
    svc.create_account('another-reader','long-password-123',['user']);login(client,'another-reader')
    assert client.get(base).json()['items']==[]
    assert client.patch(url,json={'expected_version':2,'done':False}).status_code==404
    login(client,'reader')
    assert client.get('/api/me/export').json()['preparation_items'][0]['done'] is True
    assert client.delete('/api/me/data').status_code==200
    assert client.get(base).json()['items']==[]
    assert svc.catalog()['total']==1


def test_items_reject_spoofed_official_and_bulk_read_requires_csrf(client,svc):
    target=published(svc);login(client,'reader')
    assert client.post('/api/me/actions/'+target+'/items',json={'text':'伪造官方要求','origin':'OFFICIAL','request_key':'spoof'}).status_code==422
    assert client.post('/api/me/notifications/read',json={'ids':[]},headers={'X-CSRF-Token':'wrong'}).status_code==403
    assert client.post('/api/me/notifications/read',json={'ids':[]}).status_code==200


def test_action_and_notice_envelopes_are_paginated_and_private(svc,tmp_path):
    from fastapi.testclient import TestClient
    from deepaha.product.api import create_app
    from deepaha.product.config import Settings
    with TestClient(create_app(Settings(data_dir=tmp_path,database_url=svc.database_url),svc)) as c:
        c.post('/api/auth/login',json={'username':'reader','password':'long-password-123'})
        r=c.get('/api/me/action-board?status=PREPARING').json()
        assert r.get('total')==0 and r.get('counts')=={}
        n=c.get('/api/me/notification-list?unread=true').json()
        assert n.get('total')==0 and n.get('unread_count')==0


def test_notification_batch_is_atomic_private_and_unread_filter_precedes_paging(client,svc):
    from deepaha.product.models import Notice
    from datetime import timedelta
    with svc.db.tx() as s:
        reader=s.scalar(select(Account).where(Account.username=='reader'))
        other=s.scalar(select(Account).where(Account.username=='reviewer'))
        rows=[]
        for i in range(65):
            n=Notice(account_id=reader.id,title=f'变化{i}',body='已保存机会的变化摘要',dedupe_key='change-'+str(i),due_at=now()-timedelta(seconds=5))
            s.add(n);s.flush();rows.append(n.id)
        foreign=Notice(account_id=other.id,title='其他用户消息',body='private',dedupe_key='foreign',due_at=now()-timedelta(seconds=5))
        s.add(foreign);s.flush();foreign_id=foreign.id
    login(client,'reader')
    assert client.post('/api/me/notifications/read',json={'ids':[rows[0],foreign_id]}).status_code==404
    assert client.get('/api/me/notification-list?unread=true').json()['total']==65
    r=client.post('/api/me/notifications/read',json={'ids':rows[:50]});assert r.status_code==200
    assert client.post('/api/me/notifications/read',json={'ids':rows[:50]}).status_code==200
    r=client.get('/api/me/notification-list?unread=true&limit=10').json()
    assert r['total']==15 and r['unread_count']==15 and len(r['items'])==10
    assert all(x['state']=='UNREAD' for x in r['items'])
