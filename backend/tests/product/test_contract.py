"""Current product acceptance: real persistence, not prototype state."""
import io
import json
import zipfile
import pytest
from pathlib import Path
from datetime import date,timedelta
FUTURE_DATE=(date.today()+timedelta(days=60)).isoformat()


def packet(title='科研项目助理招募', extra=None):
    data = {'opportunity_name': title, 'publish_unit': '海湾研究中心',
            'opportunity_type':'RESEARCH_PROGRAM', 'official_url':'https://research.example.org/notices/101',
            'announcement_level':[
              {'field':'报名截止','value':FUTURE_DATE,'status':'CONFIRMED','evidence':[{'artifact_id':'a1','quote':'报名截止：'+FUTURE_DATE,'locator':{'line':2}}]},
              {'field':'最低服务期','value':'最低服务期五年','status':'CONFIRMED','evidence':[]},
            ], 'units':[{'id':'u1','name':'科研部','positions':[{'id':'p1','name':'研究助理','facts':[{'field':'学历','value':'硕士研究生以上','status':'UNKNOWN','evidence':[]}]}]}]}
    if extra: data.update(extra)
    files = {'opportunities.json':json.dumps(data,ensure_ascii=False).encode(),
             'evidence.json':json.dumps({'artifacts':[{'artifact_id':'a1','local_path':'artifacts/notice.txt','url':data['official_url']}]},ensure_ascii=False).encode(),
             'report.md':f'# {title}\n已读取公告，服务期未定位。'.encode(),
             'artifacts/notice.txt':b'Public announcement\n'+ ('报名截止：'+FUTURE_DATE+'\n').encode()}
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w') as z:
        for k,v in files.items():z.writestr(k,v)
    return buf.getvalue()


@pytest.fixture
def svc(tmp_path):
    from deepaha.product.service import Product
    p=Product(f'sqlite:///{tmp_path}/app.db',tmp_path/'objects')
    p.initialize()
    p.create_account('reviewer','long-password-123',['reviewer'])
    p.create_account('operator','long-password-123',['operator'])
    p.create_account('reader','long-password-123',['user'])
    src=p.add_source('海湾研究中心','https://research.example.org/',actor='operator')
    p.test_source=src['id']
    return p


def test_partial_evidence_approve_persists_and_never_qualifies(svc):
    a=svc.ingest(svc.test_source,packet(),actor='operator')
    assert a['can_approve'] and a['notes']
    r=svc.decide(a['id'],'APPROVE',a['preview_hash'],'','same-request',actor='reviewer')
    assert r['decision']=='APPROVE'
    assert svc.decide(a['id'],'APPROVE',a['preview_hash'],'','same-request',actor='reviewer')==r
    from deepaha.product.service import Product
    again=Product(svc.database_url,svc.object_root)
    rows=again.catalog()['items']
    assert len(rows)==1
    detail=again.detail(rows[0]['id'])
    assert '最低服务期五年' in json.dumps(detail,ensure_ascii=False)
    assert detail['eligibility']=='UNCERTAIN'
    assert not any(x in json.dumps(detail) for x in ['password_hash','reviewer','raw_manifest','internal_note'])


def test_reject_one_reason_and_no_catalog(svc):
    a=svc.ingest(svc.test_source,packet(),actor='operator')
    from deepaha.product.errors import Problem
    with pytest.raises(Problem):svc.decide(a['id'],'REJECT',a['preview_hash'],'','r1',actor='reviewer')
    svc.decide(a['id'],'REJECT',a['preview_hash'],'来源不适用','r2',actor='reviewer')
    assert not svc.catalog()['items']


def test_permission_separation(svc):
    from deepaha.product.errors import Problem
    a=svc.ingest(svc.test_source,packet(),actor='operator')
    with pytest.raises(Problem):svc.decide(a['id'],'APPROVE',a['preview_hash'],'','x',actor='reader')
    with pytest.raises(Problem):svc.add_source('不能写','https://other.example.org',actor='reviewer')
    assert svc.decide(a['id'],'APPROVE',a['preview_hash'],'','operator-review',actor='operator')['decision']=='APPROVE'


def test_stale_and_opposite_decisions(svc):
    from deepaha.product.errors import Problem
    a=svc.ingest(svc.test_source,packet(),actor='operator')
    with pytest.raises(Problem):svc.decide(a['id'],'APPROVE','0'*64,'','x',actor='reviewer')
    svc.decide(a['id'],'APPROVE',a['preview_hash'],'','x',actor='reviewer')
    with pytest.raises(Problem):svc.decide(a['id'],'REJECT',a['preview_hash'],'更改','y',actor='reviewer')


def test_source_mismatch_not_approvable(svc):
    a=svc.ingest(svc.test_source,packet(extra={'official_url':'https://unrelated.example.net/notice'}),actor='operator')
    assert not a['can_approve']


def test_zip_traversal_refused(svc):
    from deepaha.product.errors import Problem
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:z.writestr('../stolen.txt','no')
    with pytest.raises(Problem):svc.ingest(svc.test_source,b.getvalue(),actor='operator')


def test_duplicate_import_not_duplicate_review(svc):
    a=svc.ingest(svc.test_source,packet(),actor='operator')
    b=svc.ingest(svc.test_source,packet(),actor='operator')
    assert a['id']==b['id']


def test_conflicting_dates_keep_values_and_disable_date_action(svc):
    extra={'announcement_level':[
      {'field':'报名截止','value':'2026-12-20','status':'CONFLICT','evidence':[]},
      {'field':'报名截止','value':'2026-12-21','status':'CONFLICT','evidence':[]}]}
    a=svc.ingest(svc.test_source,packet(extra=extra),actor='operator')
    assert a['can_approve']
    assert len(a['opportunities'][0]['fields'])==2
    assert a['opportunities'][0]['deadline'] is None


def test_source_pause_does_not_withdraw_content(svc):
    a=svc.ingest(svc.test_source,packet(),actor='operator')
    svc.decide(a['id'],'APPROVE',a['preview_hash'],'','x',actor='reviewer')
    svc.source_status(svc.test_source,False,'暂缓新采集',actor='operator')
    assert len(svc.catalog()['items'])==1


def test_favorites_feedback_are_per_user(svc):
    a=svc.ingest(svc.test_source,packet(),actor='operator')
    svc.decide(a['id'],'APPROVE',a['preview_hash'],'','x',actor='reviewer')
    oid=svc.catalog()['items'][0]['id']
    svc.set_action(oid,'SAVED',actor='reader')
    assert len(svc.my_actions(actor='reader'))==1
    svc.create_account('other','long-password-123',['user'])
    assert svc.my_actions(actor='other')==[]


def test_authentication_csrf_and_session_revocation(svc):
    from deepaha.product.errors import Problem
    login=svc.login('reader','long-password-123')
    assert svc.authenticate(login['token'],login['csrf'])['username']=='reader'
    with pytest.raises(Problem):svc.authenticate(login['token'],'bad-csrf')
    svc.logout(login['token'])
    with pytest.raises(Problem):svc.authenticate(login['token'])


def test_change_invalidates_reminder_and_prevents_old_approval(svc):
    from deepaha.product.models import Notice
    from sqlalchemy import select
    a=svc.ingest(svc.test_source,packet(),actor='operator')
    r=svc.decide(a['id'],'APPROVE',a['preview_hash'],'','a',actor='reviewer')
    oid=r['public_ids'][0]
    svc.set_action(oid,'SAVED',actor='reader')
    svc.set_reminder(oid,actor='reader')
    b=svc.ingest(svc.test_source,packet(extra={'announcement_level':[{'field':'报名截止','value':'2026-12-21','status':'CONFLICT','evidence':[]}]}),actor='operator')
    assert svc.detail(oid)['deadline'] is None
    assert svc.detail(oid)['status']=='UPDATE_PENDING'
    with svc.db.tx(False) as s:
        assert all(n.state=='CANCELLED' for n in s.scalars(select(Notice).where(Notice.kind=='DEADLINE')))
    svc.decide(b['id'],'APPROVE',b['preview_hash'],'','b',actor='reviewer')
    assert svc.detail(oid)['status']=='CURRENT'
    assert svc.detail(oid)['deadline'] is None
    svc.withdraw(oid,'官方已撤销',actor='reviewer')
    assert not svc.catalog()['items']


def test_concurrent_opposite_decisions_only_one_wins(svc):
    from concurrent.futures import ThreadPoolExecutor
    from deepaha.product.errors import Problem
    a=svc.ingest(svc.test_source,packet(),actor='operator')
    def save(d):
        try:return svc.decide(a['id'],d,a['preview_hash'],'整体理由',d,actor='reviewer')['decision']
        except Problem as e:return e.code
    with ThreadPoolExecutor(max_workers=2) as e:out=list(e.map(save,['APPROVE','REJECT']))
    assert out.count('ALREADY_DECIDED')==1
    assert len(svc.catalog()['items'])==(1 if 'APPROVE' in out else 0)


def test_report_and_internal_fields_never_public(svc):
    a=svc.ingest(svc.test_source,packet(extra={'internal_note':'private-key-material','debug':'do-not-publish'}),actor='operator')
    r=svc.decide(a['id'],'APPROVE',a['preview_hash'],'internal overall reason','k',actor='reviewer')
    text=json.dumps(svc.detail(r['public_ids'][0]))
    assert 'private-key-material' not in text and 'do-not-publish' not in text and 'internal overall reason' not in text


def test_unsupported_type_and_unknown_fields_retained(svc):
    a=svc.ingest(svc.test_source,packet(extra={'opportunity_type':'艺术驻地','知识产权':'著作权归作者，主办方可展览。'}),actor='operator')
    assert a['can_approve']
    r=svc.decide(a['id'],'APPROVE',a['preview_hash'],'','k',actor='reviewer')
    assert '著作权归作者' in json.dumps(svc.detail(r['public_ids'][0]),ensure_ascii=False)


def test_corrupt_json_still_has_raw_receipt(svc):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:z.writestr('opportunities.json','{invalid');z.writestr('report.md','# 已取得的材料')
    a=svc.ingest(svc.test_source,b.getvalue(),actor='operator')
    assert not a['can_approve']
    assert svc.raw_file(a['id'],'report.md',actor='reviewer')=='# 已取得的材料'.encode()


def test_password_wrong_rate_limit_persists(svc):
    from deepaha.product.errors import Problem
    for _ in range(8):
        with pytest.raises(Problem):svc.login('reader','wrong')
    with pytest.raises(Problem) as e:svc.login('reader','long-password-123')
    assert e.value.status==429


def test_real_blob_tamper_detected(svc):
    from deepaha.artifacts.object_store import ObjectIntegrityError
    from deepaha.product.models import Revision,Snapshot
    a=svc.ingest(svc.test_source,packet(),actor='operator')
    with svc.db.tx(False) as s:
        r=s.get(Revision,a['id']);snap=s.get(Snapshot,r.snapshot_id);meta=snap.manifest['report.md']
    path=svc.object_root/'deepaha-raw'/'objects'/meta['key'];path.write_bytes(b'changed')
    with pytest.raises(ObjectIntegrityError):svc.raw_file(a['id'],'report.md',actor='reviewer')


def test_located_quote_does_not_certify_a_different_deadline(svc):
    a=svc.ingest(svc.test_source,packet(extra={'announcement_level':[{'field':'报名截止','value':'2026-12-29','status':'CONFIRMED','evidence':[{'artifact_id':'a1','quote':'报名截止：2026-12-20','locator':{}}]}]}),actor='operator')
    assert a['can_approve']
    assert a['opportunities'][0]['deadline'] is None


def test_nested_return_layout_readable(svc):
    import zipfile,io
    original=zipfile.ZipFile(io.BytesIO(packet()))
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:
        for name in original.namelist():z.writestr('result/'+name if name.endswith(('.json','.md')) else name,original.read(name))
    a=svc.ingest(svc.test_source,b.getvalue(),actor='operator')
    assert a['can_approve']


def test_external_scout_asset_does_not_start_collection(svc):
    r=svc.import_sources({'sources':[{'name':'新研究室','url':'https://lab.example.org','brief':'先查看招募栏目。'}]},actor='operator')
    assert r['tasks_created']==0
    assert not next(s for s in svc.list_sources(actor='operator') if s['id']==r['imported'][0]['source_id'])['enabled']
