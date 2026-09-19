import json
"""Delivery guardrails: paging, full text, malformed input, and stale packets."""
from datetime import timedelta
import pytest
from .test_contract import svc, packet
from .test_api import client, login
from deepaha.product.errors import Problem


def accept(p,b=None,key='delivery-quality'):
    r=p.ingest(p.test_source,b or packet(),actor='operator')
    rec=p.decide(r['id'],'APPROVE',r['preview_hash'],'',key,actor='reviewer')
    return rec['public_ids'][0],r


def test_older_pending_packet_cannot_replace_newer_received_content(svc):
    a=svc.ingest(svc.test_source,packet(),actor='operator')
    b=svc.ingest(svc.test_source,packet(extra={'announcement_level':[{'field':'最低服务期','value':'新版本最低服务期三年'}]}),actor='operator')
    assert a['id']!=b['id']
    with pytest.raises(Problem) as e:
        svc.decide(a['id'],'APPROVE',a['preview_hash'],'','stale-pending',actor='reviewer')
    assert e.value.status==409
    svc.decide(b['id'],'APPROVE',b['preview_hash'],'','latest-pending',actor='reviewer')


def test_invalid_json_does_not_crash_private_endpoint(client):
    login(client,'reader')
    r=client.put('/api/me/profile',content=b'{broken',headers={'Content-Type':'application/json'})
    assert r.status_code==400


def test_full_text_is_reachable_without_huge_first_response(client,svc):
    long='完整的复杂申请条件；'*1500
    public_id,_=accept(svc,packet(extra={'announcement_level':[{'field':'服务期','value':long}]}))
    c=client.get('/api/catalog/'+public_id).json()
    f=c['fields'][0]
    assert len(f['value'])<=6000
    assert f['value_total']==len(long)
    r=client.get(f'/api/catalog/{public_id}/text',params={'field':f['id'],'offset':6000,'version':c['version']})
    assert r.status_code==200
    assert f['value']+r.json()['text']==long[:12000]


def test_catalog_text_search_and_paging_are_sql_bounded(svc):
    public_id,r=accept(svc)
    original=svc._target;calls=[]
    def wrapped(target,opp):calls.append(target.id);return original(target,opp)
    svc._target=wrapped
    assert svc.catalog(q='服务期')['total']==1
    assert len(calls)==1
    assert svc.catalog(q='不存在的词语')['total']==0
    assert len(calls)==1


def test_future_notices_do_not_hide_due_notices(svc):
    from deepaha.product.models import Notice,now
    with svc.db.tx() as s:
        a=svc._account(s,'reader')
        for i in range(60):s.add(Notice(account_id=a.id,dedupe_key='future-'+str(i),title='未来',body='',due_at=now()+timedelta(days=30)))
        s.add(Notice(account_id=a.id,dedupe_key='due',title='当前提醒',body='',due_at=now()-timedelta(minutes=1),created_at=now()-timedelta(days=1)))
    assert [x['title'] for x in svc.notifications(actor='reader')]==['当前提醒']


def test_legacy_history_requires_operator(client):
    login(client,'reader')
    assert client.get('/api/manage/legacy').status_code==403
    login(client,'operator')
    r=client.get('/api/manage/legacy')
    assert r.status_code==200
    assert r.json()['mode']=='READ_ONLY'


def test_review_first_page_bounded_and_entire_scope_preserved(client,svc):
    r=svc.ingest(svc.test_source,packet(extra={'announcement_level':[{'field':'条件','value':str(i)} for i in range(1000)]}),actor='operator')
    login(client,'reviewer')
    first=client.get('/api/review/'+r['id']).json()
    assert len(first['opportunities'][0]['fields'])==50
    assert first['opportunities'][0]['field_total']==1000
    assert first['scope']['fields']>=1000
    rest=client.get('/api/review/'+r['id']+'/content',params={'offset':950,'version':r['preview_hash']})
    assert rest.status_code==200
    assert rest.json()['items'][-1]['value']=='999'
    approved=client.post('/api/review/'+r['id']+'/decision',json={'decision':'APPROVE','preview_hash':r['preview_hash'],'request_key':'large','note':''})
    assert approved.status_code==200
    assert len(svc.detail(approved.json()['public_ids'][0])['fields'])==1000


def test_one_bad_opportunity_does_not_block_other_usable_objects(svc):
    import json,io,zipfile
    from deepaha.product.storage import unpack
    files=unpack(packet());good=json.loads(files['opportunities.json'])
    bad={**good,'opportunity_name':'来源错配的另一项','official_url':'https://another.example.net/none'}
    files['opportunities.json']=json.dumps({'opportunities':[good,bad,{'facts':[]}]}).encode()
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:
        for k,v in files.items():z.writestr(k,v)
    r=svc.ingest(svc.test_source,b.getvalue(),actor='operator')
    assert r['can_approve']
    assert len(r['opportunities'])==1
    assert len(r['excluded_objects'])==2


def test_multiple_distinct_notice_urls_keep_identity_across_versions(svc):
    import json,io,zipfile
    from deepaha.product.storage import unpack
    def multi(extra):
        files=unpack(packet());a=json.loads(files['opportunities.json'])
        b={**a,'opportunity_name':'另一公告','official_url':'https://research.example.org/notices/102'}
        a['summary']=extra
        files['opportunities.json']=json.dumps({'opportunities':[a,b]}).encode();buff=io.BytesIO()
        with zipfile.ZipFile(buff,'w') as z:
            for k,v in files.items():z.writestr(k,v)
        return buff.getvalue()
    first=svc.ingest(svc.test_source,multi('第一版'),actor='operator')
    one=svc.decide(first['id'],'APPROVE',first['preview_hash'],'','multi-1',actor='reviewer')
    second=svc.ingest(svc.test_source,multi('第二版'),actor='operator')
    two=svc.decide(second['id'],'APPROVE',second['preview_hash'],'','multi-2',actor='reviewer')
    assert one['public_ids']==two['public_ids']
    assert svc.catalog()['total']==2


def test_nested_internal_keys_are_not_public(svc):
    r=svc.ingest(svc.test_source,packet(extra={'支持详情':{'amount':'每年最高5万元','internal_note':'PRIVATE_MARKER_847','nested':[{'api_key':'SECRET_MARKER_374','条件':'须满足考核'}]}}),actor='operator')
    svc.decide(r['id'],'APPROVE',r['preview_hash'],'','nested-private',actor='reviewer')
    out=json.dumps(svc.catalog(),ensure_ascii=False)
    oid=svc.catalog()['items'][0]['id'];out+=json.dumps(svc.detail(oid),ensure_ascii=False)
    assert 'PRIVATE_MARKER_847' not in out and 'SECRET_MARKER_374' not in out
    assert '每年最高5万元' in out and '须满足考核' in out


def test_deep_child_content_keeps_text_accessible(svc):
    node={'id':'deep','name':'深层条目','fields':[{'field':'特殊条件','value':'DEEP_REQUIRED_TEXT_284'}]}
    for n in range(7):node={'id':str(n),'name':str(n),'children':[node]}
    r=svc.ingest(svc.test_source,packet(extra={'units':[node]}),actor='operator')
    svc.decide(r['id'],'APPROVE',r['preview_hash'],'','deep-text',actor='reviewer')
    assert 'DEEP_REQUIRED_TEXT_284' in json.dumps(svc.detail(svc.catalog()['items'][0]['id']))


def test_notification_opt_out_covers_changes(svc):
    r=svc.ingest(svc.test_source,packet(),actor='operator');svc.decide(r['id'],'APPROVE',r['preview_hash'],'','n1',actor='reviewer')
    oid=svc.catalog()['items'][0]['id'];svc.set_action(oid,'SAVED',actor='reader')
    svc.set_profile({'notification_enabled':False},actor='reader')
    svc.withdraw(oid,'来源撤回',actor='reviewer')
    assert svc.notifications(actor='reader')==[]


def test_controlled_legacy_identity_adoption_preserves_id(svc):
    from deepaha.product.models import Opportunity,uid
    old_id=uid();public_id='opp_'+old_id.replace('-','')
    with svc.db.tx() as s:s.add(Opportunity(opportunity_id=old_id,public_id=public_id,type='RESEARCH_PROGRAM',canonical_title='旧项目',issuer_name='海湾研究中心'))
    assert svc.adopt_identity(svc.test_source,'https://research.example.org/notices/101',public_id,actor='operator')['published'] is False
    r=svc.ingest(svc.test_source,packet(),actor='operator');svc.decide(r['id'],'APPROVE',r['preview_hash'],'','reuse-id',actor='reviewer')
    card=svc.catalog()['items'][0]
    assert card['root_public_id']==public_id
    assert card['id']!=public_id and card['id'].startswith('unit_')
    assert svc.announcement(public_id)['id']==public_id
