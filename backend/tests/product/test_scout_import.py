"""Cross-product acceptance uses the actual supplied v0.3.1 exporter."""
import io
import json
import sys
import zipfile
from pathlib import Path
import pytest
from sqlalchemy import select, func
from .test_contract import svc
from .test_api import client, login
from deepaha.product.models import Source, Task

IMPORTER = Path(__file__).resolve().parents[3] / 'tools/source_asset_importer'
sys.path.insert(0, str(IMPORTER))


def handoff(run='20260917T080000_A', key='SC-NEW', url='https://institute.example.org/jobs/', name='海岸研究所'):
    return {'schema_version':'deepaha.source-intelligence.run.v2.2',
      'run_metadata':{'run_key':run,'generated_at':'2026-09-17T08:00:00+08:00'},
      'source_candidates':[{'candidate_key':key,'source_name':name,'institution':name,'recommended_seed':url,
                            'source_role':'OFFICIAL_PRIMARY','evidence_refs':['EV-A'],'recommendation':'PRIORITY_ADD'}],
      'agent_acquisition_briefs':[{'source_ref':key,'brief_key':'BRIEF-A','revision':1,'recommended_seed':url,
                                  'navigation_advice':'先查看研究助理栏目，再打开原公告和附件。',
                                  'stop_escalation_rule':'遇验证码停止。','recon_evidence':['EV-A']}],
      'research_evidence':[{'evidence_key':'EV-A','url':url,'observation':'研究原始观察，未独立认证。'}],
      'demand_map':[{'theme':'科研实践'}], 'lifecycle_delta':[{'operation':'RETIRE','entity_ref':'unrelated'}]}


def zipped(entries):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
        for k,v in entries.items(): z.writestr(k, v if isinstance(v,bytes) else json.dumps(v,ensure_ascii=False).encode())
    return b.getvalue()


@pytest.fixture
def exported(tmp_path):
    from deepaha_importer.research.workspace import Workspace
    root=tmp_path/'input';root.mkdir();f=root/'Handoff.json';f.write_text(json.dumps(handoff(),ensure_ascii=False),encoding='utf8')
    w=Workspace(tmp_path/'workbench');s=w.create([f]);g=s['analysis']['sources'][0]
    s=w.decide(s['id'],g['id'],'PROPOSE_STAGING','纳入候选','外部测试操作者',s['revision'],acknowledge_issues=True)
    out=w.export(s['id'],s['revision']);return w,s,Path(out['path']).read_bytes()


def test_rebuild_exposes_actual_source_import_route(client):
    login(client,'operator')
    r=client.get('/api/manage/scout/capabilities')
    assert r.status_code==200, 'rc1缺少研究交接包接口'
    assert 'deepaha.research-handoff.v1' in r.json()['formats']


def test_actual_export_preview_commit_roundtrip(svc,exported):
    w,s,raw=exported
    assert hasattr(svc,'scout_prepare'), 'rc1只有简化来源JSON，没有研究ZIP适配'
    p=svc.scout_prepare(raw,'研究交接.zip',actor='operator')
    assert p['bundle_id']==s['export_history'][0]['bundle_id'] if s['export_history'] else p['format']=='deepaha.research-handoff.v1'
    groups=svc.scout_items(p['id'],actor='operator')['items'];assert len(groups)==1
    before=len(svc.list_sources(actor='operator'))
    r=svc.scout_commit(p['id'],p['preview_hash'],[g['id'] for g in groups],'commit-1',actor='operator')
    assert r['sources_created']==r['tasks_created']==0
    assert len(svc.list_sources(actor='operator'))==before
    assert svc.scout_commit(p['id'],p['preview_hash'],[g['id'] for g in groups],'commit-1',actor='operator')==r
    fb=svc.scout_feedback(p['id'],actor='operator')
    from deepaha_importer.research.feedback import inspect_feedback
    check=inspect_feedback(json.dumps(fb).encode(),[p['bundle_id']])
    assert check['verification']['bundle_binding']=='MATCH'
    assert check['verification']['authenticity']=='UNVERIFIED'
    assert [e['type'] for e in fb['events']]==['CANDIDATE_RECEIVED']


def prepare_receive(svc,raw=None):
    raw=raw or json.dumps(handoff(),ensure_ascii=False).encode()
    p=svc.scout_prepare(raw,'Handoff.json' if raw[:1]==b'{' else 'Research.zip',actor='operator')
    assert p['status']=='PREPARED',p
    groups=svc.scout_items(p['id'],actor='operator')['items']
    r=svc.scout_commit(p['id'],p['preview_hash'],[g['id'] for g in groups],'c-'+p['id'],actor='operator')
    return p,r,svc.scout_candidate_detail(p['id'],groups[0]['id'],actor='operator')


def approve(svc,detail,**changes):
    params=dict(actor='operator',approval_version=detail['approval_version'],binding_version=detail['binding_version'],
        name=detail['name'],url=detail['seed_urls'][0],tier='OFFICIAL_PRIMARY',reason='确认本次来源及调查建议',
        brief_id=detail['briefs'][0]['id'] if detail['briefs'] else None,request_key='a-'+detail['observation_id'])
    params.update(changes)
    return svc.scout_approve(detail['observation_id'],**params)


def test_approve_freezes_brief_and_no_auto_task(svc,exported):
    _,_,raw=exported;p,r,g=prepare_receive(svc,raw)
    a=approve(svc,g)
    assert not a['enabled'] and a['tasks_created']==0
    src=next(s for s in svc.list_sources(actor='operator') if s['id']==a['system_source_id'])
    assert '先查看研究助理' in src['brief']
    assert svc.tasks(actor='operator')==[]
    with pytest.raises(Exception):svc.create_task(src['id'],src['url'],actor='operator',request_key='disabled')
    svc.source_status(src['id'],True,'手动启用',actor='operator',expected_version=src['policy_version'])
    t=svc.create_task(src['id'],src['url'],actor='operator',request_key='explicit-wma')
    assert 'source_context' in svc.task_detail(t['id'],actor='operator'), '任务必须绑定来源与Brief版本'
    ctx=svc.task_detail(t['id'],actor='operator')['source_context']
    assert ctx['intelligence']['candidate_revision_id']==g['observation_id']
    assert ctx['intelligence']['brief_payload']['navigation_advice'].startswith('先查看')
    assert [e['type'] for e in svc.scout_feedback(p['id'],actor='operator')['events']]==['CANDIDATE_RECEIVED','SOURCE_APPROVED']


def test_raw_wb_and_state_do_not_double_count(svc):
    raw=zipped({'WB/Handoff.json':handoff(run='20260917-0800-0001'),
                'WB/State.json':{'schema_version':'deepaha.source-intelligence.state.v2.2','source_candidates':[{'candidate_key':'SHOULD-NOT-COUNT'}]},
                'attachment.zip':zipped({'opaque.txt':b'not expanded'})})
    p=svc.scout_prepare(raw,'WB-scout.zip',actor='operator')
    assert p['status']=='PREPARED'
    r=svc.scout_items(p['id'],actor='operator')
    assert r['total']==1 and r['items'][0]['namespace']=='wb-scout'


def test_unfinished_export_stages_without_fake_approval(svc,tmp_path):
    from deepaha_importer.research.workspace import Workspace
    f=tmp_path/'Handoff.json';f.write_text(json.dumps(handoff()),encoding='utf8')
    w=Workspace(tmp_path/'incomplete');x=w.create([f]);out=w.export(x['id'],0)
    p=svc.scout_prepare(Path(out['path']).read_bytes(),'unfinished.zip',actor='operator')
    assert p['readiness']=='UNFINISHED_REVIEW_NOT_FOR_APPROVAL'
    g=svc.scout_items(p['id'],actor='operator')['items'][0]
    assert not g['suggested']
    r=svc.scout_commit(p['id'],p['preview_hash'],[],'archive-only',actor='operator')
    assert r['received']==0 and r['not_selected']==1 and r['sources_created']==0


def test_same_run_changed_bytes_conflict_without_override(svc):
    p,r,g=prepare_receive(svc)
    h=handoff(name='恶意变更机构')
    p2,r2,g2=prepare_receive(svc,json.dumps(h).encode())
    assert r2['conflicts']==1 and g2['state']=='CONFLICT'
    from deepaha.product.errors import Problem
    with pytest.raises(Problem):approve(svc,g2)
    assert svc.scout_receipt(p['id'],actor='operator')==r


def test_cross_namespace_never_silent_merge_and_existing_url_explicit(svc):
    p,r,g=prepare_receive(svc);a=approve(svc,g)
    p2,r2,g2=prepare_receive(svc,json.dumps(handoff(run='20260917-0900-0001')).encode())
    assert r['candidates'][0]['candidate_id']!=r2['candidates'][0]['candidate_id']
    from deepaha.product.errors import Problem
    with pytest.raises(Problem) as e:approve(svc,g2)
    assert e.value.code=='SOURCE_LINK_REQUIRED'
    linked=approve(svc,g2,existing_source_id=a['system_source_id'],expected_policy_version=a['policy_version'])
    assert linked['system_source_id']==a['system_source_id']


def test_feedback_stable_and_survives_restart(svc):
    p,r,g=prepare_receive(svc)
    from deepaha.product.service import Product
    again=Product(svc.database_url,svc.object_root);again.initialize()
    assert again.scout_receipt(p['id'],actor='operator')==r
    assert again.scout_feedback(p['id'],actor='operator')==svc.scout_feedback(p['id'],actor='operator')
    assert '+' in again.scout_feedback(p['id'],actor='operator')['observed_at']


def test_roles_csrf_and_forged_actor(client):
    assert client.get('/api/manage/scout/batches').status_code==401
    login(client,'reviewer');assert client.get('/api/manage/scout/batches').status_code==403
    login(client,'operator')
    raw=json.dumps(handoff()).encode()
    assert client.post('/api/manage/scout/previews?filename=Handoff.json',content=raw,headers={'X-CSRF-Token':'wrong'}).status_code==403
    p=client.post('/api/manage/scout/previews?filename=Handoff.json',content=raw).json()
    assert p['status']=='PREPARED'
    r=client.post('/api/manage/scout/batches/'+p['id']+'/receive',json={'preview_hash':p['preview_hash'],'selected_ids':[],'request_key':'f','actor':'admin'})
    assert r.status_code==422
    assert client.get('/api/catalog').json()['total']==0


@pytest.mark.parametrize('member', ['../escape.json','/absolute.json','C:/secrets.json','X\\bad.json','CON.txt','a/../b.json'])
def test_archive_paths_are_rejected_preserving_raw(svc,member):
    raw=zipped({member:b'{}'})
    p=svc.scout_prepare(raw,'bad.zip',actor='operator')
    assert p['status']=='INVALID' and not p['can_receive']
    assert svc.scout_file(p['id'],'upload/bad.zip',actor='operator')==raw


def test_research_manifest_tamper(svc,exported):
    _,_,raw=exported
    with zipfile.ZipFile(io.BytesIO(raw)) as z:entries={n:z.read(n) for n in z.namelist()}
    entries['originals/0001/Handoff.json']=b'{"changed":true}'
    p=svc.scout_prepare(zipped(entries),'tampered.zip',actor='operator')
    assert p['status']=='INVALID' and '哈希' in p['error']


def test_client_audit_cannot_inject_formal_source(svc,exported):
    from deepaha_importer.contract import digest,canonical_json
    _,_,raw=exported
    with zipfile.ZipFile(io.BytesIO(raw)) as z:entries={n:z.read(n) for n in z.namelist()}
    a=json.loads(entries['Audit.json']);a['sources'][0]['name']='伪造机构';a['sources'][0]['seed_urls']=['https://evil.example.org/']
    entries['Audit.json']=json.dumps(a).encode()
    h=json.loads(entries['ResearchHandoff.json']);d=json.loads(entries['Decisions.json'])
    h['bundle_id']=digest(canonical_json({'originals':h['original_inventory'],'analysis_sha256':digest(canonical_json(a)),
           'decisions':d['decisions'],'revision':h['review_revision'],'events':d['events']}))
    entries['ResearchHandoff.json']=json.dumps(h).encode()
    m=json.loads(entries['Manifest.json']);m['bundle_id']=h['bundle_id']
    for f in m['files']:
        f['sha256']=digest(entries[f['path']]);f['size_bytes']=len(entries[f['path']])
    entries['Manifest.json']=json.dumps(m).encode()
    p=svc.scout_prepare(zipped(entries),'forged-audit.zip',actor='operator')
    assert p['status']=='PREPARED'
    rows=svc.scout_items(p['id'],actor='operator')['items']
    assert rows[0]['name']=='海岸研究所'
    assert not any('evil.example' in u for u in rows[0]['seed_urls'])


def test_original_schema_cannot_use_rc1_direct_source_route(svc):
    from deepaha.product.errors import Problem
    with pytest.raises(Problem) as e:svc.import_sources(handoff(),actor='operator')
    assert e.value.code=='USE_SCOUT_INTAKE'


def test_old_preview_changed_registry_requires_refresh(svc):
    from deepaha.product.errors import Problem
    p=svc.scout_prepare(json.dumps(handoff()).encode(),'Handoff.json',actor='operator')
    g=svc.scout_items(p['id'],actor='operator')['items'][0]
    svc.add_source('原机构','https://institute.example.org/jobs/',actor='operator')
    with pytest.raises(Problem) as e:svc.scout_commit(p['id'],p['preview_hash'],[g['id']],'stale',actor='operator')
    assert e.value.code=='SCOUT_STALE_PREVIEW'


def test_no_receipt_before_commit_and_failed_tx_rolls_back(svc,monkeypatch):
    from deepaha.product.errors import Problem
    from deepaha.product.scout_models import ScoutCandidate
    p=svc.scout_prepare(json.dumps(handoff()).encode(),'Handoff.json',actor='operator')
    with pytest.raises(Problem):svc.scout_receipt(p['id'],actor='operator')
    g=svc.scout_items(p['id'],actor='operator')['items'][0]
    original=svc._audit
    def fail(s,actor,action,target,summary):
        if action=='SCOUT_RECEIVE':raise RuntimeError('injected rollback')
        original(s,actor,action,target,summary)
    monkeypatch.setattr(svc,'_audit',fail)
    with pytest.raises(RuntimeError):svc.scout_commit(p['id'],p['preview_hash'],[g['id']],'rollback',actor='operator')
    with pytest.raises(Problem):svc.scout_receipt(p['id'],actor='operator')
    with svc.db.tx(False) as s:assert s.scalar(select(func.count()).select_from(ScoutCandidate))==0


def test_recompressed_identical_export_reuses_canonical_batch(svc,exported):
    _,_,raw=exported
    p,r,g=prepare_receive(svc,raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:entries={n:z.read(n) for n in z.namelist()}
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_STORED) as z:
        for n,b in reversed(list(entries.items())):z.writestr('外层/'+n,b)
    p2=svc.scout_prepare(buf.getvalue(),'repacked.zip',actor='operator')
    assert p2['id']==p['id']
    assert svc.scout_feedback(p['id'],actor='operator')['events'][0]['type']=='CANDIDATE_RECEIVED'


def test_overlong_research_identity_is_bounded(svc):
    data=handoff(key='x'*3000)
    p=svc.scout_prepare(json.dumps(data).encode(),'Handoff.json',actor='operator')
    assert p['status']=='INVALID'
    assert svc.scout_file(p['id'],'upload/Handoff.json',actor='operator')


def test_existing_source_detail_is_self_contained(svc):
    p,r,g=prepare_receive(svc);a=approve(svc,g)
    p2,r2,g2=prepare_receive(svc,json.dumps(handoff(run='20260917-0900-0001')).encode())
    assert g2['existing_sources'][0]['tier']=='OFFICIAL_PRIMARY'
    assert g2['existing_sources'][0]['allowed_hosts']==['institute.example.org']


def test_worker_consumes_bound_brief_and_returns_run_feedback(svc):
    import asyncio
    from .test_contract import packet
    from deepaha.product.storage import unpack
    from deepaha.product.worker import run_once
    p,r,g=prepare_receive(svc);a=approve(svc,g,enabled=True)
    task=svc.create_task(a['system_source_id'],g['seed_urls'][0],actor='operator',request_key='run-feedback')
    class Fake:
        def __init__(self):self.uploads={};self.prompts=[]
        async def create(self,id,checkpoint):checkpoint('test-runtime','test-session')
        def binding_evidence(self):return {'type':'ISOLATED_TEST'}
        async def upload(self,path,raw):self.uploads[path]=raw
        async def prompt(self,prompt,timeout_seconds):self.prompts.append(prompt);return 'end_turn'
        async def download(self,path,max_bytes):return unpack(packet())[path.split('/result/',1)[-1]]
        async def aclose(self):pass
    f=Fake();out=asyncio.run(run_once(svc,client_factory=lambda:f))
    assert out['state']=='READY',out
    sent=json.loads(next(b for n,b in f.uploads.items() if n.endswith('/task.json')))
    assert sent['source_intelligence']['candidate_revision_id']==g['observation_id']
    assert '先查看研究助理' in sent['source_brief']
    assert len(f.prompts)==1
    fb=svc.scout_feedback(p['id'],actor='operator')
    assert fb['events'][-1]['type']=='PRODUCTION_RUN_COMPLETED'
    assert fb['events'][-1]['opportunity_approved'] is False
    from deepaha_importer.research.feedback import inspect_feedback
    assert inspect_feedback(json.dumps(fb).encode(),[p['bundle_id']])['verification']['bundle_binding']=='MATCH'


def test_policy_change_prevents_remote_start(svc):
    import asyncio
    from deepaha.product.worker import run_once
    p,r,g=prepare_receive(svc);a=approve(svc,g,enabled=True)
    t=svc.create_task(a['system_source_id'],g['seed_urls'][0],actor='operator',request_key='policy-frozen')
    svc.source_status(a['system_source_id'],False,'暂停',actor='operator',expected_version=a['policy_version'])
    svc.source_status(a['system_source_id'],True,'恢复',actor='operator',expected_version=a['policy_version']+1)
    class Fake:
        async def create(self,*a,**kw):raise AssertionError('不得创建远程运行')
        async def aclose(self):pass
    assert asyncio.run(run_once(svc,client_factory=lambda:Fake()))['state']=='IDLE'
    assert svc.task_detail(t['id'],actor='operator')['stage']=='POLICY_CHANGED'
    assert [e['type'] for e in svc.scout_feedback(p['id'],actor='operator')['events']]==['CANDIDATE_RECEIVED','SOURCE_APPROVED','SOURCE_SUSPENDED']


def test_additive_upgrade_keeps_accounts_and_original_rows(svc,tmp_path):
    from deepaha.product.upgrade import upgrade_source_intake
    from deepaha.product.scout_models import ScoutBatch,ScoutRun,ScoutCandidate,ScoutObservation,ScoutBinding,ScoutEvent,ScoutApproval,TaskSourceContext
    from deepaha.product.models import Account,Meta
    # Only this test's tmp_path database is modified. Recreate the exact rc1 table boundary.
    models=[TaskSourceContext,ScoutApproval,ScoutEvent,ScoutBinding,ScoutObservation,ScoutRun,ScoutCandidate,ScoutBatch]
    for m in models:m.__table__.drop(svc.db.engine)
    with svc.db.tx() as s:
        for key in ('scout_epoch','scout_schema_version','instance_id'):
            row=s.get(Meta,key)
            if row:s.delete(row)
        ids=[a.id for a in s.scalars(select(Account))]
    result=upgrade_source_intake(svc,tmp_path/'backup.zip')
    assert result['backup_verified'] and result['source_intake_version']=='1'
    with svc.db.tx(False) as s:assert ids==[a.id for a in s.scalars(select(Account))]
    result2=upgrade_source_intake(svc,tmp_path/'second.zip')
    assert result2['already_current'] and not (tmp_path/'second.zip').exists()


def test_non_string_candidate_key_remains_research_not_approvable(svc):
    h=handoff();h['source_candidates'][0]['candidate_key']=123
    p=svc.scout_prepare(json.dumps(h).encode(),'Handoff.json',actor='operator')
    assert p['status']=='PREPARED'
    assert svc.scout_items(p['id'],actor='operator')['items'][0]['blocking']


def test_reverse_proxy_has_matching_source_upload_envelope():
    root=Path(__file__).resolve().parents[3]
    nginx=(root/'infra/product/nginx.conf.example').read_text()
    assert 'location = /api/manage/scout/previews' in nginx
    assert 'client_max_body_size 101m;' in nginx


def test_original_export_custom_research_namespace_preserved(svc,tmp_path):
    from deepaha_importer.research.workspace import Workspace
    f=tmp_path/'Handoff.json';f.write_text(json.dumps(handoff()),encoding='utf8')
    w=Workspace(tmp_path/'custom');x=w.create([f],namespace='research-team-a');g=x['analysis']['sources'][0]
    x=w.decide(x['id'],g['id'],'PROPOSE_STAGING','待系统接收','测试操作者',0,acknowledge_issues=True)
    out=w.export(x['id'],x['revision']);p=svc.scout_prepare(Path(out['path']).read_bytes(),'Research.zip',actor='operator')
    row=svc.scout_items(p['id'],actor='operator')['items'][0]
    assert row['namespace']=='research-team-a' and row['suggested']
    assert row['id']==g['id']
