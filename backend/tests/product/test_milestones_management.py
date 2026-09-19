import io
import json
import zipfile
from datetime import date, timedelta

from .test_contract import svc


def _zip(files):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for name,value in files.items():z.writestr(name,value)
    return out.getvalue()


def time_packet(*,title='时间语义测试公告',fields=None,kind='PUBLIC_INSTITUTION_JOB',positions=1):
    official='https://research.example.org/notices/time'
    fields=list(fields or [])
    root={
        'opportunity_name':title,'publish_unit':'海湾研究中心','opportunity_type':kind,'official_url':official,
        'announcement_level':fields,
        'units':[{'id':'g1','name':'海湾研究中心业务部','positions':[
            {'id':f'p{i+1}','name':f'测试岗位{i+1}','code':f'T{i+1:02d}','facts':[]} for i in range(positions)
        ]}],
    }
    quotes=[]
    for f in fields:
        for ev in f.get('evidence',[]) if isinstance(f,dict) else []:
            if ev.get('quote'):quotes.append(ev['quote'])
    body='\n'.join(quotes)+'\n'
    return _zip({
        'opportunities.json':json.dumps(root,ensure_ascii=False).encode(),
        'evidence.json':json.dumps({'artifacts':[{'artifact_id':'a1','local_path':'artifacts/notice.txt','url':official}]},ensure_ascii=False).encode(),
        'report.md':b'# time fixture','artifacts/notice.txt':body.encode(),
    })


def located(field,value,state='CONFIRMED'):
    return {'field':field,'value':value,'status':state,'evidence':[{'artifact_id':'a1','quote':value,'locator':{'line':1}}]}


def approve(svc,blob,key):
    preview=svc.ingest(svc.test_source,blob,actor='operator')
    svc.decide(preview['id'],'APPROVE',preview['preview_hash'],'',key,actor='reviewer')
    return svc.catalog(limit=50)['items']


def test_located_registration_range_creates_safe_open_and_deadline(svc):
    rows=approve(svc,time_packet(fields=[located('报名时间','2026年8月13日9:00—8月19日16:00')]),'time-range')
    detail=svc.detail(rows[0]['id'])
    assert detail['deadline']=='2026-08-19'
    assert detail['deadline_precision']=='minute'
    assert detail['time_readiness']['state']=='READY'
    ms=detail['milestones']
    assert any(x['kind']=='APPLICATION_OPEN' and x['date']=='2026-08-13' and x['time']=='09:00' for x in ms)
    assert any(x['kind']=='APPLICATION_DEADLINE' and x['date']=='2026-08-19' and x['time']=='16:00' and x['computable'] for x in ms)


def test_unlocated_registration_deadline_never_becomes_countdown(svc):
    rows=approve(svc,time_packet(fields=[{'field':'registration_deadline','value':'2026-10-31','status':'UNKNOWN','evidence':[]}]),'time-unlocated')
    detail=svc.detail(rows[0]['id'])
    assert detail['deadline'] is None
    assert detail['time_readiness']['state'] in {'UNKNOWN','PARTIAL'}
    assert not any(x.get('computable') for x in detail['milestones'] if x['kind']=='APPLICATION_DEADLINE')


def test_conflicting_located_deadlines_are_preserved_but_not_computable(svc):
    rows=approve(svc,time_packet(fields=[located('报名截止','2026-10-30'),located('报名截止时间','2026-10-31')]),'time-conflict')
    detail=svc.detail(rows[0]['id'])
    assert detail['deadline'] is None
    assert detail['time_readiness']['state']=='CONFLICT'
    assert {x['date'] for x in detail['milestones'] if x['kind']=='APPLICATION_DEADLINE'}=={'2026-10-30','2026-10-31'}


def test_rolling_application_is_explicit_and_has_no_fake_deadline(svc):
    rows=approve(svc,time_packet(fields=[located('申请时间','全年滚动受理，招满即止')]),'time-rolling')
    detail=svc.detail(rows[0]['id'])
    assert detail['deadline'] is None
    assert detail['time_readiness']['state']=='ROLLING'
    assert any(x['kind']=='ROLLING_APPLICATION' and x['computable'] is False for x in detail['milestones'])


def test_submission_deadline_does_not_replace_registration_deadline(svc):
    rows=approve(svc,time_packet(kind='COMPETITION',fields=[located('作品提交截止时间','2026-11-20 17:00')]),'time-submission')
    detail=svc.detail(rows[0]['id'])
    assert detail['deadline'] is None
    assert any(x['kind']=='SUBMISSION_DEADLINE' and x['date']=='2026-11-20' for x in detail['milestones'])
    assert detail['time_readiness']['state']=='PARTIAL'


def test_original_and_corrected_deadlines_choose_corrected_value(svc):
    rows=approve(svc,time_packet(kind='COMPETITION',fields=[
        located('报名时间（原定）','2026年10月1日—10月15日'),
        located('报名截止时间（更正后）','2026年10月20日'),
    ]),'time-corrected')
    detail=svc.detail(rows[0]['id'])
    assert detail['deadline']=='2026-10-20'
    assert detail['time_readiness']['state']=='READY'
    historical=[x for x in detail['milestones'] if x.get('historical')]
    assert historical


def test_sg3_pending_deadline_disables_time_action(svc):
    rows=approve(svc,time_packet(fields=[located('报名截止','2026-12-20')]),'time-pending')
    public_id=rows[0]['id']
    from deepaha.product.models import CatalogTarget
    from sqlalchemy import select
    with svc.db.tx() as s:
        target=s.scalar(select(CatalogTarget).where(CatalogTarget.public_id==public_id,CatalogTarget.status=='CURRENT'))
        target.status='UPDATE_PENDING'
        body=dict(target.content)
        body['currentness']={'change_kind':'FIELD_CHANGE','affected_fields':['common_fields:报名截止#1'],'summary':'报名截止有新版本待收录'}
        target.content=body
    from deepaha.product.milestones import apply_target_milestones
    with svc.db.tx() as s:
        target=s.scalar(select(CatalogTarget).where(CatalogTarget.public_id==public_id,CatalogTarget.status=='UPDATE_PENDING'))
        apply_target_milestones(svc,s,target)
    detail=svc.detail(public_id)
    assert detail['deadline'] is None
    assert detail['time_readiness']['state']=='PENDING_UPDATE'


def test_management_summary_groups_targets_by_parent_announcement(svc):
    future=(date.today()+timedelta(days=50)).isoformat()
    approve(svc,time_packet(title='两岗集中招聘公告',positions=2,fields=[located('报名截止',future)]),'management-group')
    summary=svc.catalog_management_summary(actor='reviewer')
    assert summary['targets']==2
    assert summary['roots']==1
    assert summary['time_ready']==2
    groups=svc.catalog_management_groups(actor='reviewer',limit=20)
    assert groups['total']==1
    group=groups['items'][0]
    assert group['title']=='两岗集中招聘公告'
    assert group['target_count']==2
    assert group['time_states']['READY']==2
    detail=svc.catalog_management_group_targets(group['root_public_id'],actor='reviewer',limit=20)
    assert detail['total']==2
    assert all(x['deadline']==future for x in detail['items'])


def test_management_time_filter_returns_only_matching_groups(svc):
    future=(date.today()+timedelta(days=60)).isoformat()
    approve(svc,time_packet(title='时间完整公告',fields=[located('报名截止',future)]),'management-ready')
    # separate source identity via URL is needed for a second root; change source_record_key is stable enough inside same source.
    blob=time_packet(title='滚动政策',kind='YOUTH_POLICY_BENEFIT',fields=[located('受理时间','全年滚动受理')])
    preview=svc.ingest(svc.test_source,blob,actor='operator')
    svc.decide(preview['id'],'APPROVE',preview['preview_hash'],'','management-rolling',actor='reviewer')
    rolling=svc.catalog_management_groups(actor='reviewer',time_state='ROLLING',limit=20)
    assert rolling['total']==1
    assert rolling['items'][0]['time_states']['ROLLING']>=1


def test_reviewer_management_api_exposes_grouped_catalog(svc):
    from fastapi.testclient import TestClient
    from deepaha.product.api import create_app
    from deepaha.product.config import Settings
    future=(date.today()+timedelta(days=40)).isoformat()
    approve(svc,time_packet(title='API分组公告',positions=2,fields=[located('报名截止',future)]),'management-api')
    app=create_app(Settings(database_url=svc.database_url,data_dir=svc.object_root.parent,public_catalog=True,allowed_hosts=['testserver']),product=svc)
    with TestClient(app) as client:
        login=client.post('/api/auth/login',json={'username':'reviewer','password':'long-password-123'}).json()
        client.headers['X-CSRF-Token']=login['csrf']
        summary=client.get('/api/review/catalog/summary')
        assert summary.status_code==200,summary.text
        assert summary.json()['targets']==2
        groups=client.get('/api/review/catalog/groups')
        assert groups.status_code==200,groups.text
        root=groups.json()['items'][0]
        assert root['target_count']==2
        targets=client.get('/api/review/catalog/groups/'+root['root_public_id']+'/targets')
        assert targets.status_code==200,targets.text
        assert targets.json()['total']==2
        exact=client.get('/api/review/catalog/targets')
        assert exact.status_code==200,exact.text
        assert exact.json()['total']==2
        assert all(item['publication_id'] for item in exact.json()['items'])


def test_sg5_1_time_backfill_is_backup_first_and_idempotent(svc,tmp_path):
    future=(date.today()+timedelta(days=35)).isoformat()
    rows=approve(svc,time_packet(title='旧SG5日期公告',fields=[located('报名截止',future)]),'time-backfill-source')
    from deepaha.product.models import CatalogTarget
    from sqlalchemy import select
    with svc.db.tx() as s:
        target=s.scalar(select(CatalogTarget).where(CatalogTarget.public_id==rows[0]['id'],CatalogTarget.status=='CURRENT'))
        body=dict(target.content)
        for key in ('milestones','time_readiness','primary_milestone','deadline_at'):
            body.pop(key,None)
        body['deadline']=None;body['deadline_precision']=None
        target.content=body
    from deepaha.product.upgrade import upgrade_time_semantics
    backup=tmp_path/'before-sg5-1.zip'
    first=upgrade_time_semantics(svc,backup)
    assert first['backup_verified'] is True
    assert first['targets_refreshed']==1
    assert backup.exists()
    assert svc.detail(rows[0]['id'])['deadline']==future
    second=upgrade_time_semantics(svc,tmp_path/'unused-second.zip')
    assert second['already_current'] is True
    assert second['data_modified'] is False
    assert not (tmp_path/'unused-second.zip').exists()

def test_non_time_application_labels_do_not_create_time_noise(svc):
    rows=approve(svc,time_packet(kind='COMPETITION',fields=[
        located('报名方式','学校统一提交'),
        located('学校报名上限','每校50队'),
        located('申请方式','线下窗口办理'),
    ]),'time-non-time-labels')
    detail=svc.detail(rows[0]['id'])
    assert detail['milestones']==[]
    assert detail['time_readiness']['state']=='UNKNOWN'
