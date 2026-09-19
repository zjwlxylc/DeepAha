from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]


def test_review_catalog_uses_grouped_management_workspace():
    js=(ROOT/'web/public/product/workbench.js').read_text(encoding='utf-8')
    for token in ['按公告','按具体机会','时间待确认','已过截止','/api/review/catalog/summary','/api/review/catalog/groups']:
        assert token in js
    assert '628 项当前可读机会' not in js


def test_public_time_display_prefers_safe_milestone():
    core=(ROOT/'web/public/product/core.js').read_text(encoding='utf-8')
    user=(ROOT/'web/public/product/user.js').read_text(encoding='utf-8')
    for token in ['primary_milestone','time_readiness']:
        assert token in core or token in user
    assert '滚动受理' in core or '滚动受理' in user
