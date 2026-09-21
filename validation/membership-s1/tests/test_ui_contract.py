from pathlib import Path
P=Path(__file__).parents[1]/'src/deepaha_membership/static'
def test_ui_real_pages_not_blank_placeholder():
    h=(P/'index.html').read_text()
    assert 'name="viewport"' in h and 'app.js' in h and 'style.css' in h
    assert 'aria-live' in h and '<dialog' in h
    j=(P/'app.js').read_text()
    for text in ['manage/plans','manage/services','submissions','watches/topics','review/leads','manage/orders','/confirm','/quote']:
        assert text in j
    assert 'localStorage' not in j
    assert 'textContent' in j
    assert 'crypto.randomUUID' in j

def test_responsive_layout_and_reduced_motion():
    css=(P/'style.css').read_text()
    assert '@media' in css and 'prefers-reduced-motion' in css and 'min-width:0' in css
    assert 'overflow-wrap:anywhere' in css
