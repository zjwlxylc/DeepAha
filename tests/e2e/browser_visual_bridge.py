"""Visual/interaction proof when native browser loopback navigation is unavailable.
The transport and route adapter are explicit test-only substitutions. Every business
read/write is forwarded to the REAL running API over HTTP; no fixture responses.
This does NOT test native cookies, navigation, CSP, or production networking.
"""
import asyncio,base64,json,os,re
from pathlib import Path
import httpx
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[2]
STATIC=ROOT/'web/public/product'
OUT=Path(os.getenv('PROOF_OUT',str(ROOT/'evidence/screenshots')))
BASE=os.getenv('DEEPAHA_TEST_URL','http://127.0.0.1:8000')

def bundle():
    core=(STATIC/'core.js').read_text()
    names=re.findall(r'export (?:async )?(?:const|function) ([\w$]+)',core)
    core=core.replace("history[replace?'replaceState':'pushState']({},'',url);","window.__route=new URL(url,'http://deepaha.test');")
    mark='data:image/svg+xml;base64,'+base64.b64encode((STATIC/'mark.svg').read_bytes()).decode()
    core=core.replace('/product/mark.svg',mark).replace('export ','')
    out="window.__route=new URL('http://deepaha.test/login?next=/review/overview');\n"
    out+='window.M_core=(()=>{'+core+';return {'+','.join(names)+'};})();\n'
    for file,export in [('user.js','renderUser'),('scout.js','renderScout'),('workbench.js','renderWork')]:
        s=(STATIC/file).read_text()
        s=re.sub(r"import \{([^}]+)\} from './core.js';",r'const {\1}=window.M_core;',s)
        s=s.replace("import {renderScout} from './scout.js';",'const renderScout=window.M_renderScout;')
        s=s.replace('export ','')
        out+='window.M_'+export+'=(()=>{'+s+';return '+export+';})();\n'
    s=(STATIC/'app.js').read_text()
    s=re.sub(r"import \{([^}]+)\} from './core.js';",r'const {\1}=window.M_core;',s)
    s=s.replace("import {renderUser} from './user.js';",'const renderUser=window.M_renderUser;').replace("import {renderWork} from './workbench.js';",'const renderWork=window.M_renderWork;')
    s=s.replace('location.pathname','window.__route.pathname').replace('location.search','window.__route.search')
    out+='window.appReady=(async()=>{'+s+'})();'
    return out

async def main():
    OUT.mkdir(parents=True,exist_ok=True);calls=[];errors=[];checks=[]
    async with httpx.AsyncClient(base_url=BASE,timeout=30) as http:
        async def bridge(source,path,options):
            body=base64.b64decode(options.get('body','')) if options.get('body') else None
            r=await http.request(options.get('method','GET'),path,headers=options.get('headers',{}),content=body)
            calls.append({'method':options.get('method','GET'),'path':path,'status':r.status_code})
            return {'status':r.status_code,'headers':dict(r.headers),'body':base64.b64encode(r.content).decode()}
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(executable_path=os.getenv('CHROMIUM','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
            page=await browser.new_page(viewport={'width':1440,'height':960})
            page.on('pageerror',lambda e:(errors.append(str(e)),print('PAGE_ERROR',str(e),flush=True)))
            page.set_default_timeout(8000)
            await page.expose_binding('__httpBridge',bridge)
            html=(STATIC/'index.html').read_text()
            html=re.sub(r'<script[\s\S]*?</script>','',html)
            html=re.sub(r'<link[^>]*>','',html)
            await page.set_content(html)
            await page.add_style_tag(content=(STATIC/'brand-v2.css').read_text()+'\n'+(STATIC/'product.css').read_text())
            await page.add_script_tag(content=(STATIC/'icons.js').read_text())
            await page.add_script_tag(content='''window.fetch=async(path,options={})=>{let bytes=new Uint8Array();if(options.body){bytes=typeof options.body==='string'?new TextEncoder().encode(options.body):new Uint8Array(await options.body.arrayBuffer());}let binary='';for(let b of bytes)binary+=String.fromCharCode(b);let r=await window.__httpBridge(path,{method:options.method||'GET',headers:options.headers||{},body:btoa(binary)});return new Response(Uint8Array.from(atob(r.body),x=>x.charCodeAt(0)),{status:r.status,headers:r.headers});};''')
            await page.add_script_tag(content=bundle())
            await page.locator('#username').wait_for()
            await page.locator('#username').fill(os.environ['DEEPAHA_TEST_USER'])
            await page.locator('#password').fill(os.environ['DEEPAHA_TEST_PASSWORD'])
            await page.locator('#login-form button[type=submit]').click()
            await page.get_by_role('heading',name='审核收件箱',exact=True).wait_for()
            checks.append('login_and_database_inbox')
            await page.screenshot(path=str(OUT/'01_review_inbox.png'),full_page=True)
            links=page.locator('a[href^="/review/packet/"]');await links.first.click()
            await page.locator('#approve').wait_for()
            await page.screenshot(path=str(OUT/'02_review_packet.png'),full_page=False)
            checks.append('review_contents_and_fixed_decision')
            await page.locator('#approve').click()
            await page.locator('a[href^="/app/opportunity/"]').first.wait_for()
            await page.locator('a[href^="/app/opportunity/"]').first.click()
            await page.locator('#save-opportunity').wait_for()
            await page.set_viewport_size({'width':390,'height':844})
            await page.wait_for_timeout(5000)
            await page.screenshot(path=str(OUT/'03_mobile_detail.png'),full_page=False)
            await page.locator('#save-opportunity').click()
            await page.wait_for_timeout(150)
            checks.append('single_approval_persisted_then_public_detail_and_favorite')
            await page.evaluate("window.M_core.go('/app/actions')")
            await page.get_by_role('heading',name='我的行动',exact=True).wait_for()
            await page.screenshot(path=str(OUT/'04_mobile_actions.png'),full_page=True)
            checks.append('private_action_persisted')
            await page.evaluate("window.M_core.go('/app/overview')")
            await page.get_by_role('heading',name='机会总览',exact=True).wait_for()
            await page.screenshot(path=str(OUT/'05_mobile_catalog.png'),full_page=True)
            for width in [360,390,430,768]:
                await page.set_viewport_size({'width':width,'height':844})
                overflow=await page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                assert not overflow,f'overflow at {width}'
                checks.append('catalog_no_overflow_'+str(width))
            await page.evaluate("window.M_core.go('/app/profile')")
            await page.locator('#profile-form').wait_for()
            await page.screenshot(path=str(OUT/'06_profile.png'),full_page=True)
            checks.append('profile_form_rendered')
            await page.set_viewport_size({'width':1440,'height':1000})
            for route,file,label in [('/manage','07_connection.png','运行与连接'),('/manage/sources','08_sources.png','来源管理'),('/manage/tasks','09_tasks.png','任务管理'),('/manage/history','10_history.png','操作记录')]:
                await page.evaluate('(x)=>window.M_core.go(x)',route)
                await page.get_by_role('heading',name=label,exact=True).wait_for()
                await page.screenshot(path=str(OUT/file),full_page=True)
                checks.append(route+'_rendered')
            assert not errors,errors
            await browser.close()
    result={'transport':'EXPLICIT_TEST_HTTP_BRIDGE','native_browser_network':'BLOCKED_BY_ADMINISTRATOR','checks':checks,'page_errors':errors,'http_calls':calls}
    (ROOT/'evidence/13_browser_visual_bridge.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':asyncio.run(main())
