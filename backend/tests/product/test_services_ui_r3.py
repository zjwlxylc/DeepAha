from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
WEB=ROOT/'web/public/product'


def test_membership_is_native_spa_not_iframe_or_parallel_login():
    user=(WEB/'user.js').read_text();work=(WEB/'workbench.js').read_text()
    assert 'renderMembership' in user and 'renderMembership' in work
    ui=(WEB/'membership-ui.js').read_text()
    assert "from './core.js'" in ui and 'iframe' not in ui and 'hashchange' not in ui
    for p in ['/app/subscription','/app/sources','/app/tracking','/services']:
        assert p in user
    assert '/manage/sharing' in work and '/review/sources' in work


def test_notice_and_privacy_have_new_routes_and_retention():
    user=(WEB/'user.js').read_text();n=(WEB/'actions-ui.js').read_text()
    assert 'target_url' in n and "SERVICE:'服务进展'" in n
    assert '订单' in user and '跟踪' in user


def test_share_sdk_does_not_claim_completed_share():
    s=(WEB/'share-page.js').read_text()
    assert 'updateAppMessageShareData' in s and 'updateTimelineShareData' in s
    assert '分享成功' not in s and 'AppSecret' not in s
    assert '.split(\'#\')[0]' in s
