"""SG1 browser acceptance against an upgraded copy of the user's real WMA-backed database.

Uses the same explicit HTTP bridge as the existing visual proof because this container's
Chromium is blocked from loopback by administrator policy.  Business reads/writes still hit
the real FastAPI process and SQLite copy; no business fixture responses are mocked.
"""
import asyncio,base64,json,os,re
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from playwright.async_api import async_playwright
from browser_visual_bridge import bundle,STATIC

ROOT=Path(__file__).resolve().parents[2]
BASE=os.getenv('DEEPAHA_TEST_URL','http://127.0.0.1:18081')
OUT=Path(os.getenv('PROOF_OUT',str(ROOT/'evidence/sg1/screenshots')))

async def main():
    if os.getenv('E2E_ALLOW_WRITES')!='1' or urlsplit(BASE).hostname not in ('127.0.0.1','localhost'):
        raise SystemExit('Require explicitly authorized isolated loopback writes.')
    OUT.mkdir(parents=True,exist_ok=True)
    calls=[];errors=[];checks=[]
    async with httpx.AsyncClient(base_url=BASE,timeout=60) as http,async_playwright() as pw:
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
        checks.append('authenticated_real_database')
        await page.evaluate("window.M_core.go('/review/overview?status=APPROVED')")
        await page.get_by_role('heading',name='审核收件箱',exact=True).wait_for()

        # Existing approved review record must expose 106 actionable targets while remaining one decision.
        await page.locator('a[href^="/review/packet/"]').first.click()
        await page.get_by_text('预计进入总览的具体机会',exact=True).wait_for()
        scope_text=await page.locator('.review-side').inner_text()
        assert '106 项' in scope_text,scope_text
        checks.append('review_one_root_106_action_targets')
        await page.screenshot(path=str(OUT/'01_review_106_targets.png'),full_page=False)

        await page.evaluate("window.M_core.go('/app/overview')")
        await page.get_by_role('heading',name='机会总览',exact=True).wait_for()
        assert await page.get_by_text('106 项机会',exact=True).count()==1
        first=page.locator('.op-card').first
        assert await first.get_by_text('岗位',exact=True).count()==1
        first_text=await first.inner_text()
        assert '浙江省省属事业单位2026年下半年集中公开招聘人员公告' in first_text
        checks.append('catalog_is_106_position_cards')
        await page.screenshot(path=str(OUT/'02_catalog_390.png'),full_page=False)

        # Search exact real position code/name and open a unit-scoped detail.
        await page.locator('input[name="q"]').fill('服务类专业教师')
        await page.locator('#catalog-search button[type=submit]').click()
        await page.get_by_role('heading',name='机会总览',exact=True).wait_for()
        assert await page.get_by_text('服务类专业教师',exact=True).count()>=1
        card=page.locator('.op-card').filter(has_text='服务类专业教师').first
        ctext=await card.inner_text();assert '编号 106' in ctext and '浙江省机电技师学院' in ctext
        href=await card.locator('a[href^="/app/opportunity/"]').first.get_attribute('href')
        await card.locator('a[href^="/app/opportunity/"]').first.click()
        await page.locator('#save-opportunity').wait_for()
        dtext=await page.locator('#main-content').inner_text()
        assert '岗位内容' in dtext and '公告共同条件' in dtext and '所属公告' in dtext
        assert '服务类专业教师' in dtext and '编号 106' in dtext
        checks.append('position_106_detail_has_own_ancestor_common_sections')

        # Mobile viewport must remain target-first and have no horizontal overflow.
        for width in (360,390,430):
            await page.set_viewport_size({'width':width,'height':844});await page.wait_for_timeout(100)
            assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth+1'),width
            checks.append(f'position_detail_no_overflow_{width}')
        await page.screenshot(path=str(OUT/'03_position_106_mobile.png'),full_page=False)

        # Action is bound to this unit, not to the parent root or sibling positions.
        await page.locator('#save-opportunity').click();await page.wait_for_timeout(100)
        await page.evaluate("window.M_core.go('/app/actions')")
        await page.get_by_role('heading',name='我的行动',exact=True).wait_for()
        action_text=await page.locator('#main-content').inner_text()
        assert '服务类专业教师' in action_text
        checks.append('unit_scoped_favorite_persisted')
        await page.screenshot(path=str(OUT/'04_unit_action.png'),full_page=True)

        # API shape observed by the browser must remain bounded/paged.
        catalog_calls=[x for x in calls if x['path'].startswith('/api/catalog')]
        assert any('limit=20' in x['path'] for x in catalog_calls)
        assert not errors,errors
        await browser.close()
    result={
        'transport':'EXPLICIT_TEST_HTTP_BRIDGE',
        'native_browser_network':'BLOCKED_BY_ADMINISTRATOR',
        'real_uploaded_database_copy':True,
        'expected_catalog_targets':106,
        'checks':checks,
        'page_errors':errors,
        'http_calls':calls,
    }
    (ROOT/'evidence/sg1/real_browser_acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':asyncio.run(main())
