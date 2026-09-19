import io, json, zipfile
from datetime import date, timedelta, datetime, timezone
from sqlalchemy import inspect, text, select

from .test_contract import svc, packet


def approve(svc, blob=None, key='sg6-approve'):
    preview=svc.ingest(svc.test_source, blob or packet(), actor='operator')
    receipt=svc.decide(preview['id'],'APPROVE',preview['preview_hash'],'',key,actor='reviewer')
    return receipt['catalog_target_ids'][0]


def revised_packet(day):
    raw=json.loads(zipfile.ZipFile(io.BytesIO(packet())).read('opportunities.json'))
    raw['announcement_level']=[{
        'field':'报名截止','value':day,'status':'CONFIRMED',
        'evidence':[{'artifact_id':'a1','quote':'报名截止：'+day,'locator':{'line':2}}]
    }]
    files={
        'opportunities.json':json.dumps(raw,ensure_ascii=False).encode(),
        'evidence.json':json.dumps({'artifacts':[{'artifact_id':'a1','local_path':'artifacts/notice.txt','url':raw['official_url']}]},ensure_ascii=False).encode(),
        'report.md':('# '+raw['opportunity_name']+'\n截止更新。').encode(),
        'artifacts/notice.txt':('Public announcement\n报名截止：'+day+'\n').encode(),
    }
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:
        for k,v in files.items():z.writestr(k,v)
    return b.getvalue()


def test_action_history_persists_transitions(svc):
    target=approve(svc)
    svc.set_action(target,'SAVED',actor='reader',note='先收藏')
    svc.set_action(target,'PREPARING',actor='reader',note='准备材料')
    svc.set_action(target,'APPLIED',actor='reader',note='已经提交')
    history=svc.action_history(target,actor='reader')
    assert [x['to_status'] for x in history['events']][-3:]==['SAVED','PREPARING','APPLIED']
    assert history['current_status']=='APPLIED'
    assert history['events'][-1]['note']=='已经提交'


def test_outcome_feedback_updates_action_and_creates_offline_candidate_without_changing_fit(svc):
    target=approve(svc)
    before=svc.fit(target,actor='reader')['status']
    svc.set_action(target,'APPLIED',actor='reader')
    svc.feedback(target,{'previously_known':False,'useful':True,'outcome':'ACCEPTED','comment':'已录取'},actor='reader')
    action=next(x for x in svc.my_actions(actor='reader') if x['opportunity']['id']==target)
    assert action['status']=='COMPLETED'
    assert svc.fit(target,actor='reader')['status']==before
    candidates=svc.feedback_candidates(actor='operator',limit=20)
    assert candidates['total']==1
    row=candidates['items'][0]
    assert row['target_id']==target and row['state']=='CANDIDATE' and row['outcome']=='ACCEPTED'
    encoded=json.dumps(row,ensure_ascii=False)
    assert 'reader' not in encoded and 'major' not in encoded and 'birth_date' not in encoded


def test_notification_preferences_are_independent(svc):
    target=approve(svc)
    svc.set_profile({
        'notification_enabled':True,
        'notification_deadline_enabled':True,
        'notification_change_enabled':False,
        'notification_weekly_enabled':False,
        'deadline_reminder_days':[7,1],
    },actor='reader')
    svc.set_action(target,'SAVED',actor='reader')
    # Automatic deadline tracking is allowed, but change/weekly channels are off.
    with svc.db.tx(False) as s:
        rows=s.execute(text("select kind,state from product_target_notices where account_id=(select id from product_accounts where username='reader')")).all()
    assert rows and all(kind=='DEADLINE' for kind,_ in rows)
    assert svc.create_weekly_digest_notice(actor='reader') is None


def test_deadline_update_cancels_old_schedule_and_reschedules_new_current_deadline(svc):
    first=(date.today()+timedelta(days=45)).isoformat()
    target=approve(svc,revised_packet(first),'sg6-first')
    svc.set_profile({'notification_enabled':True,'notification_deadline_enabled':True,'notification_change_enabled':True,'notification_weekly_enabled':True,'deadline_reminder_days':[7,1]},actor='reader')
    svc.set_action(target,'SAVED',actor='reader')
    with svc.db.tx(False) as s:
        before=s.execute(text("select dedupe_key,state from product_target_notices where kind='DEADLINE'")).all()
    assert len(before)==2 and all(state=='UNREAD' for _,state in before)

    second=(date.today()+timedelta(days=60)).isoformat()
    preview=svc.ingest(svc.test_source,revised_packet(second),actor='operator')
    # Pending update must immediately invalidate the old date schedule.
    with svc.db.tx(False) as s:
        pending=s.execute(text("select state from product_target_notices where kind='DEADLINE'")).all()
    assert pending and all(state=='CANCELLED' for (state,) in pending)
    svc.decide(preview['id'],'APPROVE',preview['preview_hash'],'','sg6-second',actor='reviewer')
    with svc.db.tx(False) as s:
        current=s.execute(text("select dedupe_key,state,body from product_target_notices where kind='DEADLINE' order by created_at")).all()
    active=[r for r in current if r[1]=='UNREAD']
    assert len(active)==2
    assert all(second in r[2] for r in active)
    assert not any(first in r[2] for r in active)


def test_weekly_digest_is_deduplicated_and_includes_action_and_new_opportunities(svc):
    target=approve(svc)
    svc.set_profile({'notification_enabled':True,'notification_weekly_enabled':True,'notification_deadline_enabled':False,'notification_change_enabled':True},actor='reader')
    svc.set_action(target,'PREPARING',actor='reader')
    digest=svc.weekly_digest(actor='reader')
    assert digest['action_summary']['PREPARING']==1
    assert 'period_key' in digest and 'new_opportunities' in digest
    first=svc.create_weekly_digest_notice(actor='reader')
    second=svc.create_weekly_digest_notice(actor='reader')
    assert first is not None and first['created'] is True
    assert second['id']==first['id'] and second['created'] is False
    with svc.db.tx(False) as s:
        count=s.execute(text("select count(*) from product_notices where kind='WEEKLY'")).scalar_one()
    assert count==1


def test_master_notification_off_cancels_every_channel_and_prevents_new_notices(svc):
    target=approve(svc)
    svc.set_profile({'notification_enabled':True,'notification_deadline_enabled':True,'notification_change_enabled':True,'notification_weekly_enabled':True,'deadline_reminder_days':[1]},actor='reader')
    svc.set_action(target,'SAVED',actor='reader')
    svc.create_weekly_digest_notice(actor='reader')
    svc.set_profile({'notification_enabled':False,'notification_deadline_enabled':True,'notification_change_enabled':True,'notification_weekly_enabled':True,'deadline_reminder_days':[1]},actor='reader')
    with svc.db.tx(False) as s:
        target_states=s.execute(text("select state from product_target_notices")).all()
        root_states=s.execute(text("select state from product_notices")).all()
    assert target_states and root_states
    assert all(x[0]=='CANCELLED' for x in target_states+root_states)
    assert svc.create_weekly_digest_notice(actor='reader') is None


def test_action_loop_tables_are_explicit_schema_assets(svc):
    tables=set(inspect(svc.db.engine).get_table_names())
    assert {'product_target_action_events','product_feedback_candidates'}.issubset(tables)
    with svc.db.tx(False) as s:
        version=s.execute(text("select value from product_meta where key='action_loop_schema_version'")).scalar_one()
    assert version=='1'

def test_change_channel_off_still_invalidates_wrong_deadline_without_sending_change_notice(svc):
    first=(date.today()+timedelta(days=40)).isoformat()
    target=approve(svc,revised_packet(first),'sg6-change-off-first')
    svc.set_profile({'notification_enabled':True,'notification_deadline_enabled':True,'notification_change_enabled':False,'notification_weekly_enabled':False,'deadline_reminder_days':[7]},actor='reader')
    svc.set_action(target,'SAVED',actor='reader')
    second=(date.today()+timedelta(days=55)).isoformat()
    svc.ingest(svc.test_source,revised_packet(second),actor='operator')
    with svc.db.tx(False) as s:
        rows=s.execute(text("select kind,state from product_target_notices")).all()
    assert any(kind=='DEADLINE' and state=='CANCELLED' for kind,state in rows)
    assert not any(kind=='CHANGE' and state!='CANCELLED' for kind,state in rows)


def test_weekly_scheduler_creates_at_most_one_notice_per_week(svc):
    from deepaha.product.action_loop import schedule_weekly_digests
    svc.set_profile({'notification_enabled':True,'notification_weekly_enabled':True,'notification_deadline_enabled':False,'notification_change_enabled':True},actor='reader')
    at=datetime(2026,9,18,2,tzinfo=timezone.utc)
    assert schedule_weekly_digests(svc,at=at)==1
    assert schedule_weekly_digests(svc,at=at+timedelta(hours=1))==0


def test_erase_personal_removes_action_history_and_feedback_candidates_but_not_catalog(svc):
    target=approve(svc)
    svc.set_action(target,'SAVED',actor='reader')
    svc.feedback(target,{'useful':True,'outcome':'APPLIED'},actor='reader')
    assert svc.catalog()['total']==1
    svc.erase_personal(actor='reader')
    with svc.db.tx(False) as s:
        assert s.execute(text("select count(*) from product_target_action_events")).scalar_one()==0
        assert s.execute(text("select count(*) from product_feedback_candidates")).scalar_one()==0
    assert svc.catalog()['total']==1


def test_removed_action_remains_in_personal_export_history(svc):
    target=approve(svc,key='sg6-export-removed')
    svc.set_action(target,'SAVED',actor='reader',note='先收藏')
    svc.remove_action(target,actor='reader')
    exported=svc.export_personal(actor='reader')
    assert not any(x['opportunity']['id']==target for x in exported['actions'])
    histories=[x for x in exported['action_history'] if x['target_id']==target]
    assert len(histories)==1
    assert [x['to_status'] for x in histories[0]['events']][-2:]==['SAVED','DISMISSED']
    assert histories[0]['events'][-1]['event_type']=='REMOVE'
