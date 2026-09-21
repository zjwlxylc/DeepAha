from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import pytest
from deepaha_membership.errors import DomainError
from deepaha_membership.periods import parse
from conftest import actor


def admin():return actor('maintainer',('operator',))
def publish(c,code='basic'):
    p=c.plan(code,admin=True)
    c.set_status(admin(),code,'PUBLISHED',p['version'])
    return c.plan(code)
def order(c,code='basic',key='order-key-001',who=None):
    p=publish(c,code)
    return c.create_order(who or actor(),code,p['version'],key,note='请跟踪我关注的公开招聘网站' if code=='custom' else '')
def grant(c,code='basic',who=None,key='order-key-001'):
    o=order(c,code,key,who)
    return c.confirm(admin(),o['id'],o['version'],'TRIAL',0,'','试用功能核验',key+'confirm')


def test_seed_is_draft_and_not_public(commerce):
    assert commerce.list_plans()==[]
    assert {x['code'] for x in commerce.list_plans(admin=True)}=={'basic','deep','custom'}

def test_operator_only_can_publish(commerce):
    with pytest.raises(DomainError) as e:commerce.set_status(actor('r',('reviewer',)),'basic','PUBLISHED',1)
    assert e.value.status==403

def test_order_does_not_grant_entitlement(commerce):
    o=order(commerce)
    assert o['state']=='PENDING'
    assert commerce.entitlements(actor())['tier']=='FREE'

def test_user_cannot_confirm_own_order(commerce):
    o=order(commerce)
    with pytest.raises(DomainError) as e:commerce.confirm(actor(),o['id'],o['version'],'TRIAL',0,'','not authorized','confirm-bad-01')
    assert e.value.status==403

def test_trial_opens_exact_two_month_term(commerce):
    g=grant(commerce)
    assert g['ends_at'].startswith('2026-11-21T08:00:00')
    assert g['method']=='TRIAL'
    assert commerce.entitlements(actor())['topic_limit']==3

def test_expiry_is_exclusive_and_does_not_destroy_history(commerce,store):
    g=grant(commerce)
    store.clock.value=parse(g['ends_at'])
    assert commerce.entitlements(actor())['tier']=='FREE'
    assert len(commerce.list_orders(actor()))==1

def test_renewal_starts_after_existing_term(commerce):
    a=grant(commerce,key='order-one-01')
    b=grant(commerce,key='order-two-02')
    assert b['starts_at']==a['ends_at']
    assert commerce.entitlements(actor())['tier']=='BASIC'

def test_tier_change_is_next_term_not_overwrite(commerce):
    a=grant(commerce,key='order-one-01')
    b=grant(commerce,code='deep',key='order-two-02')
    assert b['starts_at']==a['ends_at']
    assert commerce.entitlements(actor())['tier']=='BASIC'

def test_order_snapshot_survives_price_edit_and_archiving(commerce):
    o=order(commerce)
    p=commerce.plan('basic',admin=True)
    payload=dict(p['terms']);payload['price_cents']=3990;payload['topic_limit']=1
    commerce.revise_plan(admin(),'basic',p['version'],payload)
    commerce.set_status(admin(),'basic','ARCHIVED',2)
    g=commerce.confirm(admin(),o['id'],o['version'],'MANUAL',2990,'bank-check-20260921-a','人工核对收款单据','confirm-frozen')
    assert g['terms']['price_cents']==2990
    assert g['terms']['topic_limit']==3

def test_stale_price_order_rejected(commerce):
    p=publish(commerce)
    data=dict(p['terms']);data['price_cents']=3990
    commerce.revise_plan(admin(),'basic',1,data)
    with pytest.raises(DomainError) as e:commerce.create_order(actor(),'basic',1,'old-price-key')
    assert e.value.code=='STALE_VERSION'

def test_idempotent_same_body_returns_same_order(commerce):
    a=order(commerce)
    b=commerce.create_order(actor(),'basic',1,'order-key-001')
    assert a['id']==b['id']
    assert len(commerce.list_orders(actor()))==1

def test_idempotent_key_with_different_body_rejected(commerce):
    order(commerce)
    publish(commerce,'deep')
    with pytest.raises(DomainError) as e:commerce.create_order(actor(),'deep',1,'order-key-001')
    assert e.value.code=='IDEMPOTENCY_CONFLICT'

def test_confirm_concurrent_distinct_keys_opens_one_term(commerce):
    o=order(commerce)
    def perform(i):
        try:return commerce.confirm(admin(),o['id'],o['version'],'TRIAL',0,'','并发开通测试',f'concurrent-{i}')
        except DomainError as e:return e.code
    with ThreadPoolExecutor(max_workers=4) as pool:out=list(pool.map(perform,range(4)))
    assert sum(isinstance(x,dict) for x in out)==1
    assert len(commerce.list_grants(actor()))==1

def test_manual_confirmation_must_match_amount(commerce):
    o=order(commerce)
    with pytest.raises(DomainError):commerce.confirm(admin(),o['id'],1,'MANUAL',1,'receipt-01','已经核对单据','confirm-key-1')
    assert commerce.entitlements(actor())['tier']=='FREE'

def test_settlement_reference_cannot_pay_two_orders(commerce):
    a=order(commerce,key='first-order-01');b=order(commerce,key='second-order-02',who=actor('bob'))
    commerce.confirm(admin(),a['id'],1,'MANUAL',2990,'one-receipt','已经核对单据','confirm-key-a')
    with pytest.raises(DomainError):commerce.confirm(admin(),b['id'],1,'MANUAL',2990,'one-receipt','已经核对单据','confirm-key-b')
    assert commerce.entitlements(actor('bob'))['tier']=='FREE'

def test_other_user_cannot_read_order(commerce):
    o=order(commerce)
    with pytest.raises(DomainError) as e:commerce.get_order(actor('bob'),o['id'])
    assert e.value.status==404

def test_custom_quote_requires_acceptance(commerce):
    o=order(commerce,'custom')
    assert o['state']=='REQUESTED'
    q=commerce.quote(admin(),o['id'],1,19900,2,3,10,'核验三个公开网站，按公开机会更新提供站内提醒','quote-key-one')
    with pytest.raises(DomainError):commerce.confirm(admin(),q['id'],q['version'],'TRIAL',0,'','试用定制服务','early-confirm')
    accepted=commerce.accept_quote(actor(),q['id'],q['version'],'accept-quote-key')
    g=commerce.confirm(admin(),q['id'],accepted['version'],'TRIAL',0,'','试用定制服务','normal-confirm')
    assert g['terms']['site_limit']==3

def test_expired_quote_not_accepted(commerce,store):
    o=order(commerce,'custom')
    q=commerce.quote(admin(),o['id'],1,19900,2,3,10,'仅跟踪已核验的公开机会网站','quote-key-two')
    store.clock.value+=timedelta(days=8)
    with pytest.raises(DomainError):commerce.accept_quote(actor(),q['id'],q['version'],'expired-accept')

def test_revoke_stops_new_benefit_not_refund_claim(commerce):
    g=grant(commerce)
    out=commerce.revoke(admin(),g['id'],'误开通已经核实','revoke-grant-1')
    assert out['revoked_at']
    assert commerce.entitlements(actor())['tier']=='FREE'
    assert commerce.get_order(actor(),g['order_id'])['state']=='FULFILLED_TRIAL'

@pytest.mark.parametrize('amount',[-1,0,29.9,True])
def test_invalid_fixed_prices_rejected(commerce,amount):
    p=commerce.plan('basic',admin=True);data=dict(p['terms']);data['price_cents']=amount
    with pytest.raises((DomainError,ValueError)):commerce.revise_plan(admin(),'basic',1,data)

def test_quote_cannot_sell_capability_absent_from_frozen_services(commerce):
    p=commerce.plan('custom',admin=True);terms=dict(p['terms']);terms['site_limit']=0;terms['service_codes']=['topic_watch','inapp_alerts']
    commerce.revise_plan(admin(),'custom',1,terms)
    o=order(commerce,'custom')
    with pytest.raises(DomainError):commerce.quote(admin(),o['id'],1,9900,2,3,10,'指定网站不在订单能力中，不能只靠改名额销售','invalid-quote-key')
