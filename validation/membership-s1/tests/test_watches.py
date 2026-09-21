import importlib
from datetime import timedelta
import pytest
from sqlalchemy import select,func
from deepaha_membership.db import jobs,notices
from deepaha_membership.errors import DomainError
from deepaha_membership.periods import parse
from conftest import actor
from test_commerce import admin,grant,order
from test_contributions import submit,approve

class Core:
    def __init__(self):
        self.calls=[];self.tasks={};self.sources={};self.catalog_calls=0;self.lose_once=False
        self.items=[dict(id='op1',title='测试公开机会',version='v1',status='CURRENT')]
    def register(self,a,l):
        self.calls.append(('register',a.name,l['approved_url']))
        self.sources.setdefault(l['id'],dict(id='source-'+l['id'],enabled=False,policy_version=1))
        return self.sources[l['id']]
    def enable(self,a,l):
        s=self.sources[l['id']];s['enabled']=True;return s
    def enqueue(self,a,l,key,connection):
        self.calls.append(('enqueue',key))
        if not self.sources[l['id']]['enabled']:raise DomainError('来源未启用',409)
        self.tasks.setdefault(key,dict(id='task-'+key,status='QUEUED'))
        if self.lose_once:self.lose_once=False;raise TimeoutError('lost response')
        return self.tasks[key]
    def task(self,a,id):return next(v for v in self.tasks.values() if v['id']==id)
    def catalog(self,**kw):
        self.catalog_calls+=1
        return dict(items=self.items,read_version=1,total=len(self.items),has_more=False)

@pytest.fixture
def watchers(store,commerce):
    try:M=importlib.import_module('deepaha_membership.tracking')
    except ImportError:pytest.fail('tracking implementation missing')
    return M.Tracking(store,commerce,Core(),dns=lambda u:u)

@pytest.fixture
def contrib(store):
    from deepaha_membership.contributions import Contributions
    return Contributions(store)

def custom(c):
    o=order(c,'custom')
    q=c.quote(admin(),o['id'],1,9900,2,3,10,'为三个公开网站提供公开机会跟踪，不承诺结果','custom-quote-1')
    q=c.accept_quote(actor(),q['id'],q['version'],'custom-accept-1')
    return c.confirm(admin(),q['id'],q['version'],'TRIAL',0,'','人工定制试用','custom-confirm-1')

def site(w,c,contrib):
    custom(c);s=submit(contrib);approve(contrib,s['lead'])
    return w.create_site(actor(),s['id'],'site-create-1')

def test_free_cannot_create_paid_topic(watchers):
    with pytest.raises(DomainError) as e:watchers.create_topic(actor(),'校招','校招','','','topic-key-01')
    assert e.value.code=='ENTITLEMENT_REQUIRED'

def test_topics_quota_enforced_server_side(watchers,commerce):
    grant(commerce)
    for i in range(3):watchers.create_topic(actor(),f'主题{i}',f'关键词{i}','','',f'topic-key-{i}')
    with pytest.raises(DomainError) as e:watchers.create_topic(actor(),'第四个','更多','','','topic-overflow')
    assert e.value.code=='QUOTA_EXCEEDED'

def test_topic_identity_and_ownership(watchers,commerce):
    grant(commerce)
    a=watchers.create_topic(actor(),'校招','校招','','','topic-key-01')
    b=watchers.create_topic(actor(),'校招','校招','','','topic-key-01')
    assert a['id']==b['id'] and watchers.mine(actor('bob'))==[]
    with pytest.raises(DomainError):watchers.toggle(actor('bob'),a['id'],1,False,'toggle-key-01')

def test_paused_frees_quota_and_reenable_respects_limit(watchers,commerce):
    grant(commerce)
    xs=[watchers.create_topic(actor(),str(i),'校招','','',f'create-topic-{i}') for i in range(3)]
    watchers.toggle(actor(),xs[0]['id'],1,False,'pause-topic-1')
    watchers.create_topic(actor(),'新主题','广告','','','new-topic-04')
    with pytest.raises(DomainError):watchers.toggle(actor(),xs[0]['id'],2,True,'resume-topic-1')

def test_topic_scan_notice_dedup_and_version_change(watchers,commerce,store):
    grant(commerce);watchers.create_topic(actor(),'校招','校招','','','topic-key-01')
    assert watchers.scan_topics(admin())['notices_created']==1
    assert watchers.scan_topics(admin())['checked']==0
    store.clock.value+=timedelta(days=1)
    assert watchers.scan_topics(admin())['notices_created']==0
    watchers.core.items[0]['version']='v2';watchers.core.items[0]['status']='UPDATE_PENDING'
    store.clock.value+=timedelta(days=1)
    assert watchers.scan_topics(admin())['notices_created']==1
    with store.read() as c:
        ns=c.execute(select(notices.c.body).where(notices.c.key.like('watch:%'))).scalars().all()
    assert any('待确认' in n for n in ns)

def test_expired_topic_is_retained_not_scanned(watchers,commerce,store):
    g=grant(commerce);watchers.create_topic(actor(),'校招','校招','','','topic-key-01')
    store.clock.value=parse(g['ends_at'])
    assert watchers.scan_topics(admin())['checked']==0
    assert len(watchers.mine(actor()))==1
    assert watchers.mine(actor())[0]['effective'] is False

def test_partial_catalog_scan_not_counted_success(watchers,commerce,store):
    grant(commerce);watchers.create_topic(actor(),'校招','校招','','','topic-key-01')
    watchers.core.catalog=lambda **kw:dict(items=[{'id':'op1'}],read_version=1,total=100,has_more=True)
    result=watchers.scan_topics(admin())
    assert result['failed']==1
    assert watchers.mine(actor())[0]['last_checked'] is None
    with store.read() as c:assert c.execute(select(func.count()).select_from(notices).where(notices.c.key.like('watch:%'))).scalar()==0

def test_basic_cannot_create_site(watchers,commerce,contrib):
    grant(commerce);s=submit(contrib);approve(contrib,s['lead'])
    with pytest.raises(DomainError):watchers.create_site(actor(),s['id'],'site-key-01')

def test_custom_needs_approved_owned_submission(watchers,commerce,contrib):
    custom(commerce);s=submit(contrib)
    with pytest.raises(DomainError):watchers.create_site(actor(),s['id'],'site-key-01')
    approve(contrib,s['lead'])
    with pytest.raises(DomainError):watchers.create_site(actor('bob'),s['id'],'site-key-02')

def test_approval_and_watch_do_not_enqueue(watchers,commerce,contrib):
    w=site(watchers,commerce,contrib)
    assert w['kind']=='SITE' and watchers.core.calls==[]

def test_adoption_never_auto_enables_source(watchers,commerce,contrib):
    w=site(watchers,commerce,contrib)
    lid=w['config']['lead_id']
    s=watchers.adopt(admin(),lid)
    assert not s['enabled'] and len(watchers.core.tasks)==0

def test_dispatch_stable_key_recovers_lost_response(watchers,commerce,contrib):
    w=site(watchers,commerce,contrib);lid=w['config']['lead_id']
    watchers.adopt(admin(),lid);watchers.enable_source(admin(),lid)
    j=watchers.prepare(admin(),w['id'],'default','prepare-job-01')
    watchers.core.lose_once=True
    first=watchers.dispatch(admin(),j['id'])
    assert first['state']=='RETRYABLE'
    assert len(watchers.core.tasks)==1
    second=watchers.dispatch(admin(),j['id'])
    assert second['state']=='CORE_QUEUED' and len(watchers.core.tasks)==1
    assert watchers.dispatch(admin(),j['id'])['core_task_id']==second['core_task_id']

def test_expiry_blocks_dispatch_before_external_call(watchers,commerce,contrib,store):
    w=site(watchers,commerce,contrib);lid=w['config']['lead_id']
    watchers.adopt(admin(),lid);watchers.enable_source(admin(),lid)
    j=watchers.prepare(admin(),w['id'],'default','prepare-job-01')
    store.clock.value+=timedelta(days=90)
    out=watchers.dispatch(admin(),j['id'])
    assert out['state']=='BLOCKED' and not watchers.core.tasks

def test_source_ready_is_not_published(watchers,commerce,contrib):
    w=site(watchers,commerce,contrib);lid=w['config']['lead_id']
    watchers.adopt(admin(),lid);watchers.enable_source(admin(),lid)
    j=watchers.prepare(admin(),w['id'],'default','prepare-job-01');watchers.dispatch(admin(),j['id'])
    for t in watchers.core.tasks.values():t['status']='READY'
    out=watchers.refresh(admin(),j['id'])
    assert out['state']=='RESULT_PENDING_REVIEW'
    assert 'published' not in out

def test_only_operator_can_authorize_site_call(watchers,commerce,contrib):
    w=site(watchers,commerce,contrib)
    with pytest.raises(DomainError):watchers.prepare(actor('r',('reviewer',)),w['id'],'default','prepare-job-01')

def test_pending_job_reused_and_connection_change_rejected(watchers,commerce,contrib):
    w=site(watchers,commerce,contrib)
    j=watchers.prepare(admin(),w['id'],'default','prepare-job-01')
    assert watchers.prepare(admin(),w['id'],'default','prepare-job-02')['id']==j['id']
    with pytest.raises(DomainError):watchers.prepare(admin(),w['id'],'other','prepare-job-03')

def test_site_dns_block_no_enqueue(watchers,commerce,contrib):
    w=site(watchers,commerce,contrib);lid=w['config']['lead_id']
    watchers.adopt(admin(),lid);watchers.enable_source(admin(),lid)
    j=watchers.prepare(admin(),w['id'],'default','prepare-job-01')
    def deny(u):raise DomainError('不能访问此地址',400,'UNSAFE_DNS')
    watchers.dns=deny
    assert watchers.dispatch(admin(),j['id'])['state']=='RETRYABLE'
    assert not watchers.core.tasks

def test_lower_tier_overquota_old_watches_effectively_pause(watchers,commerce,store):
    g=grant(commerce,'deep',key='deep-grant-01')
    for i in range(5):watchers.create_topic(actor(),str(i),'校招','','',f'topic-key-{i}')
    grant(commerce,'basic',key='basic-grant-01')
    store.clock.value=parse(g['ends_at'])
    assert sum(w['effective'] for w in watchers.mine(actor()))==3

def test_site_watch_notifies_only_published_source_items(watchers,commerce,contrib,store):
    w=site(watchers,commerce,contrib);watchers.adopt(admin(),w['config']['lead_id'])
    watchers.core.catalog_for_source=lambda lead,**kw:dict(items=[dict(id='public-site-1',title='已审核的定制网站机会',version='v1',status='CURRENT')],total=1,has_more=False,read_version=1)
    assert hasattr(watchers,'scan_site_publications'),'missing published source notification loop'
    r=watchers.scan_site_publications(admin())
    assert r['notices_created']==1
    assert watchers.mine(actor())[0]['last_checked'] is None  # scanning must not delay collection jobs
    assert watchers.scan_site_publications(admin())['checked']==0
    with store.read() as c:
        n=c.execute(select(notices.c.body).where(notices.c.key.like('site-publication:%'))).scalars().one()
    assert '已进入机会总览' in n

def test_site_publication_expiry_and_dedupe(watchers,commerce,contrib,store):
    w=site(watchers,commerce,contrib);watchers.adopt(admin(),w['config']['lead_id'])
    watchers.core.catalog_for_source=lambda lead,**kw:dict(items=[dict(id='public-site-1',title='网站机会',version='v1',status='CURRENT')],total=1,has_more=False,read_version=1)
    assert hasattr(watchers,'scan_site_publications')
    watchers.scan_site_publications(admin());store.clock.value+=timedelta(hours=6)
    assert watchers.scan_site_publications(admin())['notices_created']==0
    store.clock.value+=timedelta(days=90)
    assert watchers.scan_site_publications(admin())['checked']==0

def test_paid_website_collection_interval_separate_from_light_catalog_scan(watchers,commerce,contrib,store):
    w=site(watchers,commerce,contrib);lid=w['config']['lead_id']
    watchers.adopt(admin(),lid);watchers.enable_source(admin(),lid)
    j=watchers.prepare(admin(),w['id'],'default','first-daily-job');watchers.dispatch(admin(),j['id'])
    for task in watchers.core.tasks.values():task['status']='READY'
    watchers.refresh(admin(),j['id'])
    store.clock.value+=timedelta(hours=6)
    with pytest.raises(DomainError) as e:watchers.prepare(admin(),w['id'],'default','early-second-job')
    assert e.value.code=='NOT_DUE'
    store.clock.value+=timedelta(hours=18)
    assert watchers.prepare(admin(),w['id'],'default','next-daily-job')['state']=='QUEUED'

def test_parent_source_default_enabled_does_not_bypass_local_authorization(watchers,commerce,contrib):
    w=site(watchers,commerce,contrib);lid=w['config']['lead_id']
    watchers.adopt(admin(),lid)
    # The inspected parent main defaults SourceProfile.scheduling_enabled=True.
    watchers.core.sources[lid]['enabled']=True
    j=watchers.prepare(admin(),w['id'],'default','prepare-no-local-auth')
    with pytest.raises(DomainError):watchers.dispatch(admin(),j['id'])
    assert not watchers.core.tasks
