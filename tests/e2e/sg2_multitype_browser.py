"""SG2 visual acceptance against an isolated database populated with bundled fictional examples.

Uses the explicit HTTP bridge because this container blocks Chromium loopback navigation.
All business calls still hit the real FastAPI process; no API fixtures are injected.
"""
import asyncio, base64, json, os, re
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from playwright.async_api import async_playwright

from browser_visual_bridge import bundle, STATIC

ROOT=Path(__file__).resolve().parents[2]
BASE=os.getenv('DEEPAHA_TEST_URL','http://127.0.0.1:18082')
OUT=Path(os.getenv('PROOF_OUT',str(ROOT/'evidence/sg2/screenshots')))

async def main():
    if os.getenv('E2E_ALLOW_WRITES')!='1' or urlsplit(BASE).hostname not in ('127.0.0.1','localhost'):
        raise SystemExit('Require explicitly authorized isolated loopback writes.')
    OUT.mkdir(parents=True,exist_ok=True)
    calls=[];errors=[];checks=[]
    async with httpx.AsyncClient(base_url=BASE,timeout=60) as http, async_playwright() as pw:
        async def bridge(source,path,options):
            body=base64.b64decode(options.get('body','')) if options.get('body') else None
            r=await http.request(options.get('method','GET'),path,headers=options.get('headers',{}),content=body)
            calls.append({'method':options.get('method','GET'),'path':path,'status':r.status_code})
            return {'status':r.status_code,'headers':dict(r.headers),'body':base64.b64encode(r.content).decode()}

        browser=await pw.chromium.launch(executable_path=os.getenv('CHROMIUM','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
        page=await browser.new_page(viewport={'width':1440,'height':960});page.set_default_timeout(12000)
        page.on('pageerror',lambda err:errors.append(str(err)))
        await page.expose_binding('__httpBridge',bridge)
        html=re.sub(r'<script[\s\S]*?</script>','',(STATIC/'index.html').read_text());html=re.sub(r'<link[^>]*>','',html)
        await page.set_content(html)
        await page.add_style_tag(content=(STATIC/'brand-v2.css').read_text()+'\n'+(STATIC/'product.css').read_text())
        await page.add_script_tag(content=(STATIC/'icons.js').read_text())
        await page.add_script_tag(content="""window.fetch=async(path,options={})=>{let bytes=new Uint8Array();if(options.body){bytes=typeof options.body==='string'?new TextEncoder().encode(options.body):new Uint8Array(await options.body.arrayBuffer());}let binary='';for(let b of bytes)binary+=String.fromCharCode(b);let r=await window.__httpBridge(path,{method:options.method||'GET',headers:options.headers||{},body:btoa(binary)});return new Response(Uint8Array.from(atob(r.body),x=>x.charCodeAt(0)),{status:r.status,headers:r.headers});};""")
        await page.add_script_tag(content=bundle())
        await page.locator('#username').fill(os.environ['DEEPAHA_TEST_USER'])
        await page.locator('#password').fill(os.environ['DEEPAHA_TEST_PASSWORD'])
        await page.locator('#login-form button[type=submit]').click()
        await page.get_by_role('heading',name='审核收件箱',exact=True).wait_for()
        checks.append('authenticated_isolated_multitype_database')

        await page.evaluate("window.M_core.go('/app/overview')")
        await page.set_viewport_size({'width':390,'height':844})
        await page.get_by_role('heading',name='机会总览',exact=True).wait_for()
        page_text=await page.locator('#main-content').inner_text()
        for label in ('竞赛','科研','人才政策','奖学金','升学'):
            assert label in page_text,label
        checks.append('five_category_filters_visible')
        await page.screenshot(path=str(OUT/'01_multitype_catalog_mobile.png'),full_page=True)

        # Competition: never present as a job and keeps competition vocabulary.
        await page.evaluate("window.M_core.go('/app/overview?kind=COMPETITION')")
        await page.get_by_text('数字叙事赛道',exact=True).wait_for()
        card=page.locator('.op-card').filter(has_text='数字叙事赛道').first
        ctext=await card.inner_text()
        assert '赛道' in ctext and '岗位' not in ctext,ctext
        await card.locator('a[href^="/app/opportunity/"]').first.click()
        await page.locator('h2',has_text='赛事共同规则').wait_for()
        detail=await page.locator('#main-content').inner_text()
        assert '赛道内容' in detail and '赛事共同规则' in detail and '所属赛事' in detail,detail
        checks.append('competition_track_vocabulary_and_scope')
        await page.screenshot(path=str(OUT/'02_competition_detail_mobile.png'),full_page=True)

        # Policy: rolling time remains text; absence of online apply URL does not hide it.
        await page.evaluate("window.M_core.go('/app/overview?kind=YOUTH_POLICY_BENEFIT')")
        await page.get_by_text('创新实践项目',exact=True).wait_for()
        policy=page.locator('.op-card').filter(has_text='创新实践项目').first
        assert '时间见详情' in (await policy.inner_text()) or '受理时间' in (await policy.inner_text())
        await policy.locator('a[href^="/app/opportunity/"]').first.click()
        await page.locator('h2',has_text='政策共同条件').wait_for()
        ptext=await page.locator('#main-content').inner_text()
        assert '滚动受理' in ptext and '受理时间' in ptext,ptext
        checks.append('rolling_policy_no_fake_deadline')

        # Scholarship unknown field and postgrad category remain discoverable.
        await page.evaluate("window.M_core.go('/app/overview?kind=SCHOLARSHIP&q=%E5%85%AC%E7%9B%8A')")
        await page.get_by_text('卓越奖',exact=True).wait_for()
        assert await page.get_by_text('卓越奖',exact=True).count()>=1
        checks.append('unknown_scholarship_field_searchable')
        await page.evaluate("window.M_core.go('/app/overview?kind=POSTGRAD_RECOMMENDATION')")
        await page.get_by_text('学术研究组',exact=True).wait_for()
        pg=page.locator('.op-card').filter(has_text='学术研究组').first
        assert '项目类别' in await pg.inner_text()
        checks.append('postgrad_program_tiers_visible')

        for width in (360,390,430):
            await page.set_viewport_size({'width':width,'height':844});await page.wait_for_timeout(60)
            assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth+1'),width
            checks.append(f'no_overflow_{width}')
        assert not errors,errors
        await browser.close()

    result={
        'transport':'EXPLICIT_TEST_HTTP_BRIDGE',
        'native_browser_network':'BLOCKED_BY_ADMINISTRATOR',
        'database':'ISOLATED_FICTIONAL_SG2_EXAMPLES',
        'checks':checks,
        'page_errors':errors,
        'http_calls':calls,
    }
    (ROOT/'evidence/sg2').mkdir(parents=True,exist_ok=True)
    (ROOT/'evidence/sg2/browser_acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':asyncio.run(main())
