from pathlib import Path
import base64,re,json
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; STATIC=ROOT/'web/public/product'; OUT=ROOT/'evidence/sg6_1'; SHOT=OUT/'screenshots'

def modules():
    core=(STATIC/'core.js').read_text(encoding='utf-8'); names=re.findall(r'export (?:async )?(?:const|function) ([\w$]+)',core)
    core=core.replace("history[replace?'replaceState':'pushState']({},'',url);","window.__route=new URL(url,'http://deepaha.test');")
    mark='data:image/svg+xml;base64,'+base64.b64encode((STATIC/'mark.svg').read_bytes()).decode(); core=core.replace('/product/mark.svg',mark).replace('export ','')
    out='window.M_core=(()=>{'+core+';return {'+','.join(names)+'};})();\n'
    for file,export in [('user.js','renderUser'),('scout.js','renderScout'),('workbench.js','renderWork')]:
        s=(STATIC/file).read_text(encoding='utf-8'); s=re.sub(r"import \{([^}]+)\} from './core.js';",r'const {\1}=window.M_core;',s); s=s.replace("import {renderScout} from './scout.js';",'const renderScout=window.M_renderScout;').replace('export ','')
        out+='window.M_'+export+'=(()=>{'+s+';return '+export+';})();\n'
    return out

def main():
    SHOT.mkdir(parents=True,exist_ok=True); checks=[]; errors=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
        page=browser.new_page(viewport={'width':1440,'height':900}); page.on('pageerror',lambda e:errors.append(str(e)))
        html=(STATIC/'index.html').read_text(encoding='utf-8'); html=re.sub(r'<script[\s\S]*?</script>','',html); html=re.sub(r'<link[^>]*>','',html)
        page.set_content(html); page.add_style_tag(content=(STATIC/'brand-v2.css').read_text(encoding='utf-8')+'\n'+(STATIC/'product.css').read_text(encoding='utf-8')); page.add_script_tag(content=(STATIC/'icons.js').read_text(encoding='utf-8')); page.add_script_tag(content=modules())
        page.add_script_tag(content="""window.fetch=async(path,options={})=>{let data={};if(path.startsWith('/api/catalog'))data={items:[],total:0};else if(path==='/api/me/actions')data=[];else if(path.startsWith('/api/me/recommendations'))data={items:[],featured:[],explore:[]};else if(path==='/api/me/profile')data={cities:[],career_directions:[],interests:[],opportunity_types:[]};else data={};return new Response(JSON.stringify(data),{status:200,headers:{'content-type':'application/json'}});};""")
        render="""async({roles,path})=>{window.M_core.state.user={username:'ux-test',roles};let view=await window.M_renderUser(path,new URLSearchParams());document.querySelector('#app').innerHTML=view.html;view.after();}"""
        # Desktop and tablet layouts.
        for width in (768,1024,1440,1920):
            page.set_viewport_size({'width':width,'height':900}); page.evaluate(render,{'roles':['user'],'path':'/app/overview'}); page.wait_for_timeout(30)
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1'),width
            assert page.locator('.desktop-main-nav').is_visible(),width
            assert page.locator('.mobile-nav').count()==0 or not page.locator('.mobile-nav').is_visible(),width
        checks.append('user_desktop_tablet_no_overflow_768_1024_1440_1920')
        # Mobile layout and 44px targets.
        for width in (360,390,430):
            page.set_viewport_size({'width':width,'height':800}); page.evaluate(render,{'roles':['user'],'path':'/app/overview'}); page.wait_for_timeout(30)
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1'),width
            assert not page.locator('.desktop-main-nav').is_visible(),width
            assert page.locator('.mobile-nav').is_visible(),width
            h=page.locator('.mobile-nav a').first.evaluate('el=>el.getBoundingClientRect().height'); assert h>=43.5,(width,h)
        checks.append('user_mobile_nav_and_touch_targets_360_390_430')
        page.screenshot(path=str(SHOT/'07_mobile_overview_390.png'),full_page=True)
        # Keyboard skip link.
        page.set_viewport_size({'width':1440,'height':900}); page.evaluate(render,{'roles':['user'],'path':'/app/overview'}); page.locator('.skip-link').focus()
        assert page.locator('.skip-link').evaluate('el=>document.activeElement===el')
        top=page.locator('.skip-link').evaluate('el=>el.getBoundingClientRect().top'); assert top < 20,top
        checks.append('skip_link_focusable_and_visible')
        # Reduced motion is honored by CSS.
        page.emulate_media(reduced_motion='reduce'); page.wait_for_timeout(20)
        duration=page.locator('.op-card').first.evaluate("el=>getComputedStyle(el).transitionDuration") if page.locator('.op-card').count() else page.locator('.desktop-main-nav a').first.evaluate("el=>getComputedStyle(el).transitionDuration")
        assert duration in ('0s','0.00001s','.00001s','1e-05s') or duration.startswith('0.00001'),duration
        checks.append('prefers_reduced_motion_honored')
        # Active page is programmatically identified.
        current=page.locator('[aria-current="page"]'); assert current.count()>=1
        checks.append('aria_current_present')
        browser.close()
    assert not errors,errors
    result={'transport':'FRONTEND_ONLY_MOCK_API','checks':checks,'page_errors':errors}; (OUT/'responsive_a11y_acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
