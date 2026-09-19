"""SG6 acceptance against a fresh copy of the user's multi-WMA data.
No WMA call is performed. The source archive copy is never modified.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib, json, shutil, sqlite3, sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend/src'))
from sqlalchemy import select
from deepaha.product.service import Product
from deepaha.product.errors import Problem
from deepaha.product.models import CatalogTarget, TargetAction, TargetNotice, SourceProfile, Task, now
from deepaha.product.action_loop import schedule_weekly_digests
from deepaha.product.worker import schedule_due
from deepaha.product.upgrade import upgrade_time_semantics, upgrade_action_loop

SOURCE=Path('/mnt/data/sg6_realdata/deepaha-data')
DATA=Path('/mnt/data/sg6_final_realdata')
if DATA.exists(): shutil.rmtree(DATA)
shutil.copytree(SOURCE,DATA)
for suffix in ('deepaha.db-wal','deepaha.db-shm'):
    try:(DATA/suffix).unlink()
    except FileNotFoundError:pass

p=Product('sqlite:///'+str(DATA/'deepaha.db'),DATA/'objects')
sg51=upgrade_time_semantics(p,DATA/'backups'/'before-sg5-1-for-sg6-acceptance.zip')

TABLES=[
    'product_opportunity_identity','product_opportunity_units','product_overview_decisions',
    'product_overview_publications','product_overview_revisions','product_result_snapshots',
    'product_tasks','product_catalog_targets','product_accounts','product_profiles'
]
def table_digest(name):
    c=sqlite3.connect(DATA/'deepaha.db');c.row_factory=sqlite3.Row
    h=hashlib.sha256();count=0
    for r in c.execute(f'SELECT * FROM {name} ORDER BY 1'):
        count+=1;h.update(json.dumps(dict(r),ensure_ascii=False,sort_keys=True,default=str,separators=(',',':')).encode())
    c.close();return {'rows':count,'sha256':h.hexdigest()}
def objects_digest():
    h=hashlib.sha256();count=0
    for f in sorted((DATA/'objects').rglob('*')):
        if f.is_file():
            count+=1;h.update(str(f.relative_to(DATA/'objects')).encode());h.update(hashlib.sha256(f.read_bytes()).digest())
    return {'files':count,'sha256':h.hexdigest()}

before={x:table_digest(x) for x in TABLES};before['_objects']=objects_digest()
sg6=upgrade_action_loop(p,DATA/'backups'/'before-sg6-acceptance.zip')
sg6_second=upgrade_action_loop(p,DATA/'backups'/'unused-second.zip')
after={x:table_digest(x) for x in TABLES};after['_objects']=objects_digest()
assert before==after,(before,after)

try:p.create_account('sg6-accept','long-password-123',['user','reviewer','operator'])
except Problem as e:
    if e.status!=409:raise

with p.db.tx(False) as s:
    targets=list(s.scalars(select(CatalogTarget).where(CatalogTarget.status=='CURRENT').order_by(CatalogTarget.public_id)))
# choose a future safe deadline with generous space for automatic reminder days
target=next(x for x in targets if isinstance(x.content,dict) and (x.content.get('deadline') or '')>='2026-10-01')
tid=target.public_id
p.set_profile({
    'notification_enabled':True,'notification_deadline_enabled':True,
    'notification_change_enabled':True,'notification_weekly_enabled':True,
    'deadline_reminder_days':[30,7,1],
},actor='sg6-accept')

p.set_action(tid,'SAVED',actor='sg6-accept',note='真实数据收藏')
with p.db.tx(False) as s:
    account=p._account(s,'sg6-accept')
    scheduled=list(s.scalars(select(TargetNotice).where(
        TargetNotice.account_id==account.id,TargetNotice.target_public_id==tid,
        TargetNotice.kind=='DEADLINE',TargetNotice.state=='UNREAD')))
assert scheduled, 'safe future target did not create automatic reminder schedule'

p.set_action(tid,'PREPARING',actor='sg6-accept',note='材料准备中')
history=p.action_history(tid,actor='sg6-accept')
assert [x['to_status'] for x in history['events']][-2:]==['SAVED','PREPARING']

fit_before=p.fit(tid,actor='sg6-accept')['status']
p.feedback(tid,{
    'previously_known':False,'useful':True,'action_reason':'准备申请',
    'outcome':'INTERVIEW','comment':'进入面试',
},actor='sg6-accept')
with p.db.tx(False) as s:
    account=p._account(s,'sg6-accept')
    action=s.scalar(select(TargetAction).where(TargetAction.account_id==account.id,TargetAction.target_public_id==tid))
    active_deadlines=list(s.scalars(select(TargetNotice).where(
        TargetNotice.account_id==account.id,TargetNotice.target_public_id==tid,
        TargetNotice.kind=='DEADLINE',TargetNotice.state!='CANCELLED')))
assert action and action.status=='WAITING'
assert not active_deadlines
assert p.fit(tid,actor='sg6-accept')['status']==fit_before

candidates=p.feedback_candidates(actor='sg6-accept',limit=100)
candidate=next(x for x in candidates['items'] if x['target_id']==tid)
assert candidate['state']=='CANDIDATE' and candidate['outcome']=='INTERVIEW'
encoded=json.dumps(candidate,ensure_ascii=False)
assert 'sg6-accept' not in encoded and '进入面试' not in encoded

digest=p.weekly_digest(actor='sg6-accept')
assert digest['action_summary']['WAITING']>=1
at=datetime(2026,9,18,12,tzinfo=timezone.utc)
weekly_first=schedule_weekly_digests(p,at=at)
weekly_second=schedule_weekly_digests(p,at=at+timedelta(hours=1))
assert weekly_first>=1 and weekly_second==0

exported=p.export_personal(actor='sg6-accept')
timeline=next(x for x in exported['action_history'] if x['target_id']==tid)
assert timeline['events'][-1]['event_type']=='OUTCOME'

# Reuse SG3 periodic source monitoring; only queue RECHECK, do not execute WMA.
sources=p.list_sources(actor='sg6-accept',limit=50)
source=next((x for x in sources if x['active'] and x.get('enabled') and x['name']=='宁波求职补贴'),None)
if source is None:source=next(x for x in sources if x['active'] and x.get('enabled') and not x.get('legacy'))
p.schedule_source(source['id'],24,actor='sg6-accept')
with p.db.tx() as s:
    profile=s.get(SourceProfile,source['id']);profile.next_due=now()-timedelta(minutes=1)
rechecks=schedule_due(p,actor='sg6-accept')
with p.db.tx(False) as s:
    source_tasks=list(s.scalars(select(Task).where(Task.source_id==source['id']).order_by(Task.created_at.desc()).limit(5)))
assert rechecks>=1 and any(x.kind=='RECHECK' and x.status=='QUEUED' for x in source_tasks)

result={
    'source':'COPY_OF_USER_MULTI_WMA_DATA',
    'wma_called':False,
    'sg5_1_upgrade':sg51,
    'sg6_upgrade':sg6,
    'sg6_second_upgrade':sg6_second,
    'preexisting_tables_and_objects_unchanged_by_sg6':before==after,
    'current_targets':len(targets),
    'target':{'id':tid,'title':target.content.get('title'),'safe_deadline':target.content.get('deadline')},
    'automatic_deadline_schedules_created':len(scheduled),
    'action_history_states':[x['to_status'] for x in history['events']],
    'outcome_action_status':action.status,
    'eligibility_before_and_after_feedback':fit_before,
    'feedback_candidate':candidate,
    'weekly_digest':{
        'period_key':digest['period_key'],'action_summary':digest['action_summary'],
        'due_soon_count':len(digest['due_soon']),'change_count':len(digest['changes']),
        'new_opportunity_count':len(digest['new_opportunities']),
    },
    'weekly_scheduler_created_first':weekly_first,
    'weekly_scheduler_created_second':weekly_second,
    'periodic_recheck_tasks_created':rechecks,
    'periodic_recheck_source':source['name'],
    'personal_export_timeline_events':len(timeline['events']),
    'objects_digest':after['_objects'],
}
OUT=ROOT/'evidence/sg6/REAL_WMA_SG6_ACCEPTANCE.json'
OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2,default=str))
