import importlib
import pytest
from sqlalchemy import select, func
from deepaha_membership.db import leads, submissions
from deepaha_membership.errors import DomainError
from conftest import actor
from test_commerce import admin

@pytest.fixture
def contrib(store):
    try:return importlib.import_module('deepaha_membership.contributions').Contributions(store)
    except ImportError:pytest.fail('contributions implementation missing')

def submit(c,who=None,url='https://example.org/jobs',key='submission-key-01'):
    return c.submit(who or actor(),'某机构机会栏目',url,'SOURCE','希望跟踪公开招聘公告',True,key)

def approve(c,lead):
    return c.decide(actor('reviewer',('reviewer',)),lead['id'],lead['version'],'APPROVE','已核对公开栏目','仅调查此公开栏目中的招聘公告，所有结果仍需整体审核。',lead['url'],'COMMUNITY_SIGNAL','approve-'+lead['id'])

def test_free_user_can_contribute_but_not_publish(contrib,store):
    s=submit(contrib)
    assert s['lead']['state']=='PENDING'
    assert s['lead']['source_id'] is None
    assert len(contrib.queue(admin()))==1

def test_consent_is_required(contrib):
    with pytest.raises(DomainError):contrib.submit(actor(),'机构','https://example.org','SOURCE','需求',False,'no-consent-key')

def test_url_dedupe_does_not_leak_other_submitter(contrib,store):
    a=submit(contrib)
    b=submit(contrib,actor('bob'),'https://example.org/jobs?utm_source=test#top','submission-bob')
    assert a['lead']['id']==b['lead']['id']
    mine=contrib.mine(actor('bob'))
    assert len(mine)==1 and mine[0]['owner']=='bob'
    assert 'alice' not in str(mine)
    with store.read() as c:assert c.execute(select(func.count()).select_from(leads)).scalar()==1

def test_duplicate_submission_same_owner_preserves_one_record(contrib):
    first=submit(contrib)
    again=submit(contrib,key='second-submit-key')
    assert first['id']==again['id']
    assert len(contrib.mine(actor()))==1

def test_review_permission_and_version(contrib):
    s=submit(contrib);l=s['lead']
    with pytest.raises(DomainError) as e:approve_as_user(contrib,l)
    assert e.value.status==403
    approve(contrib,l)
    with pytest.raises(DomainError):approve(contrib,{**l,'version':0})

def approve_as_user(c,l):
    return c.decide(actor(),l['id'],1,'APPROVE','核对完成','公开来源仍需人工整体审核','https://example.org/jobs','COMMUNITY_SIGNAL','bad-approve-key')

def test_review_does_not_create_source_or_task(contrib):
    l=approve(contrib,submit(contrib)['lead'])
    assert l['state']=='APPROVED' and l['source_id'] is None
    assert len(contrib.mine(actor()))==1

def test_supplement_resubmits_needs_info_without_overwriting_other_user(contrib):
    a=submit(contrib);b=submit(contrib,actor('bob'),key='bob-submit-01')
    l=contrib.decide(admin(),a['lead']['id'],1,'NEEDS_INFO','请补充栏目说明','','','COMMUNITY_SIGNAL','needs-info-key')
    out=contrib.supplement(actor(),a['id'],l['version'],'这是无需登录的公开招聘栏目','supplement-key')
    assert out['lead']['state']=='PENDING'
    assert contrib.mine(actor('bob'))[0]['note']==b['note']
    with pytest.raises(DomainError):contrib.supplement(actor('bob'),a['id'],2,'试图修改别人','attack-key-01')

def test_approved_lead_cannot_be_mutated_by_submitter(contrib):
    s=submit(contrib);l=approve(contrib,s['lead'])
    with pytest.raises(DomainError):contrib.supplement(actor(),s['id'],l['version'],'修改公告指令','mutate-approved')

def test_daily_abuse_limit(contrib):
    for n in range(20):submit(contrib,url=f'https://example.org/jobs/{n}',key=f'submit-key-{n}')
    with pytest.raises(DomainError) as e:submit(contrib,url='https://example.org/overflow',key='overflow-key-01')
    assert e.value.status==429

def test_operator_inherits_reviewer_not_inverse(contrib):
    assert contrib.queue(admin())==[]
    with pytest.raises(DomainError):contrib.queue(actor())
