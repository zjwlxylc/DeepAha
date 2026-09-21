"""Actual Product, actual mbr and original WMA worker; provider transport simulated."""
import asyncio,json
from datetime import datetime,timedelta,timezone
from sqlalchemy import select,update
from .test_api import client,login
from .test_contract import svc,packet
from .test_services_r3 import trial,P
from .test_dispatch_policy import FakeClient
from deepaha_membership.auth import Actor
from deepaha_membership.db import grants,jobs,watches,row
from deepaha.product.models import Task,Account
from deepaha.product.worker import run_once
A=Actor('operator',frozenset({'operator'}))


def site_job(client,svc):
    trial(client,'custom')
    t=client.app.state.membership_tracking;t.dns=lambda u:['93.184.216.34']
    r=client.post(P+'/submissions',json={'key':'host-source-r3','name':'科研公开栏目','url':'https://research.example.org/notices/101','kind':'CUSTOM','note':'私人：我是大二，希望进入研究院','consent':True});assert r.status_code==200,r.text
    sub=r.json();lead=sub['lead']
    login(client,'operator')
    r=client.post(P+'/review/leads/'+lead['id']+'/decision',json={'key':'host-review-r3','version':lead['version'],'decision':'APPROVE','note':'来源已核对','approved_url':lead['url'],'tier':'COMMUNITY_SIGNAL','public_brief':'仅调查该栏目公开科研机会，读取原公告和附件，不携带任何用户身份。'});assert r.status_code==200,r.text
    assert client.post(P+'/manage/leads/'+lead['id']+'/adopt').status_code==200
    assert client.post(P+'/manage/leads/'+lead['id']+'/enable').status_code==200
    login(client,'reader')
    r=client.post(P+'/watches/sites',json={'key':'host-watch-r3','submission_id':sub['id']});assert r.status_code==200,r.text
    watch=r.json();login(client,'operator')
    job=t.prepare(A,watch['id'],'default','host-prepare-r3')
    return t,watch,job


def test_real_queued_run_review_publish_and_personal_notice(client,svc):
    t,w,j=site_job(client,svc)
    job=t.dispatch(A,j['id']);assert job['state']=='CORE_QUEUED'
    assert len(svc.tasks(actor='operator'))==1
    assert t.dispatch(A,j['id'])['core_task_id']==job['core_task_id']
    FakeClient.prompts=0
    result=asyncio.run(run_once(svc,FakeClient));assert result['state']=='READY',result
    assert FakeClient.prompts==1 and svc.catalog()['total']==0
    state=t.refresh(A,j['id']);assert state['state']=='RESULT_PENDING_REVIEW'
    revision=svc.preview(result['revision_id'],actor='operator')
    svc.decide(revision['id'],'APPROVE',revision['preview_hash'],'','host-approval-r3',actor='operator')
    assert t.refresh(A,j['id'])['state']=='PUBLISHED'
    r=t.scan_site_publications(A);assert r['notices_created']==1,r
    assert t.scan_site_publications(A)['notices_created']==0
    login(client,'reader')
    items=client.get('/api/me/notification-list').json()['items']
    notice=next(n for n in items if (n.get('target_url') or '').startswith('/app/opportunity/'))
    assert client.get(notice['target_url']).status_code==200
    assert '私人' not in svc.task_detail(job['core_task_id'],actor='operator')['instruction']


def test_expired_after_enqueue_blocks_remote_creation(client,svc):
    t,w,j=site_job(client,svc);job=t.dispatch(A,j['id'])
    with svc.db.engine.begin() as c:c.execute(update(grants).values(ends_at=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()))
    class Never(FakeClient):
        creates=0
        async def create(self,*a,**kw):type(self).creates+=1;return await super().create(*a,**kw)
    result=asyncio.run(run_once(svc,Never))
    assert Never.creates==0 and result['code']=='MEMBERSHIP_AUTHORITY_REVOKED',result


def test_revoked_during_upload_blocks_actual_prompt(client,svc):
    t,w,j=site_job(client,svc);t.dispatch(A,j['id'])
    class RevokeBeforePrompt(FakeClient):
        prompts=0
        async def upload(self,path,data):
            if path.endswith('task.json'):
                with svc.db.engine.begin() as c:c.execute(update(grants).values(revoked_at=datetime.now(timezone.utc).isoformat()))
    r=asyncio.run(run_once(svc,RevokeBeforePrompt))
    assert RevokeBeforePrompt.prompts==0 and r['code']=='MEMBERSHIP_AUTHORITY_REVOKED',r


def test_clear_after_dispatch_stops_queue_and_no_new_call(client,svc):
    t,w,j=site_job(client,svc);job=t.dispatch(A,j['id'])
    login(client,'reader');assert client.delete('/api/me/data').status_code==200
    assert svc.task_detail(job['core_task_id'],actor='operator')['status']=='CANCELLED'
    FakeClient.prompts=0;r=asyncio.run(run_once(svc,FakeClient))
    assert r['state']=='IDLE' and FakeClient.prompts==0


def test_account_disable_stops_effective_service(client,svc):
    t,w,j=site_job(client,svc);t.dispatch(A,j['id'])
    with svc.db.tx() as s:s.scalar(select(Account).where(Account.username=='reader')).active=False
    assert not t.mine(A,manage=True)[0]['effective']
    FakeClient.prompts=0;r=asyncio.run(run_once(svc,FakeClient))
    assert FakeClient.prompts==0 and r['code']=='MEMBERSHIP_AUTHORITY_REVOKED'


def test_erase_during_ambiguous_dispatch_does_not_restore_deleted_job(client,svc):
    t,w,j=site_job(client,svc);enqueue=t.core.enqueue
    created=[]
    def then_clear(*a,**kw):
        value=enqueue(*a,**kw);created.append(value['id']);svc.erase_personal(actor='reader');return value
    t.core.enqueue=then_clear
    result=t.dispatch(A,j['id'])
    assert result['state']=='CANCELLED'
    with svc.db.engine.connect() as c:assert row(c,select(jobs).where(jobs.c.id==j['id'])) is None
    assert svc.task_detail(created[0],actor='operator')['status']=='CANCELLED'
