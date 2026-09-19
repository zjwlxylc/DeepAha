from pathlib import Path

ROOT=Path('web/public/product')


def test_sg7_2_migrates_public_home_about_and_uploaded_brand_without_touching_product_contracts():
    user=(ROOT/'user.js').read_text(encoding='utf-8')
    core=(ROOT/'core.js').read_text(encoding='utf-8')
    css=(ROOT/'product.css').read_text(encoding='utf-8')
    html=(ROOT/'index.html').read_text(encoding='utf-8')
    logo=ROOT/'brand-logo.png'
    assert logo.exists() and logo.stat().st_size > 10_000
    assert '/product/brand-logo.png' in core
    assert '机会星图' in user and '让属于你的机会，' in user and '不再擦肩而过' in user
    assert '它怎样替你找到机会' in user
    assert '怎样判断你是否符合' in user
    assert '怎样帮你继续行动' in user
    assert "path==='/about'" in user and '用 AI 助力青年' in user and '用户做主' in user
    assert 'marketingShell' in user and '.marketing-hero' in css and '.about-hero' in css
    assert 'brand-logo.png' in html
    assert '94%' not in user


def test_sg7_2_home_keeps_real_product_entry_points():
    user=(ROOT/'user.js').read_text(encoding='utf-8')
    for path in ('/app/overview','/app/star','/app/actions','/app/me'):
        assert path in user
    assert '/manage/lab' in (ROOT/'workbench.js').read_text(encoding='utf-8')
    assert "path==='/app/lab'" in user
