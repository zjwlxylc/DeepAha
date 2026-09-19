"""Native browser acceptance. Deliberately NOT marked passing in this delivery.
Prepare an isolated local database, a test operator+reviewer account and pending
fictional examples. Set E2E_ALLOW_WRITES=1 and test credentials explicitly.
"""
import asyncio,json,os
from pathlib import Path
from urllib.parse import urlsplit
from playwright.async_api import async_playwright

async def main():
    base=os.getenv('DEEPAHA_TEST_URL','http://127.0.0.1:8000')
    if os.getenv('E2E_ALLOW_WRITES')!='1' or urlsplit(base).hostname not in ('127.0.0.1','localhost'):
        raise SystemExit('Only explicit isolated loopback writes are allowed. Do not use a real-user database.')
    async with async_playwright() as p:
        options={'headless':True}
        if os.getenv('CHROMIUM'):options['executable_path']=os.environ['CHROMIUM']
        browser=await p.chromium.launch(**options)
        page=await browser.new_page(viewport={'width':1440,'height':960})
        page.set_default_timeout(10000)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        # No route interception, cookie replacement, injected bundles or HTTP bridges.
        await page.goto(base+'/login?next=/review/overview')
        await page.locator('#username').fill(os.environ['DEEPAHA_TEST_USER'])
        await page.locator('#password').fill(os.environ['DEEPAHA_TEST_PASSWORD'])
        await page.locator('#login-form button[type=submit]').click()
        await page.get_by_role('heading',name='审核收件箱',exact=True).wait_for()
        cookies=await page.context.cookies()
        assert any(c['name']=='deepaha_session' and c['httpOnly'] for c in cookies)
        await page.locator('a[href^="/review/packet/"]').first.click()
        await page.locator('#approve').click()
        await page.locator('a[href^="/app/opportunity/"]').first.click()
        await page.locator('#save-opportunity').wait_for()
        await page.reload();await page.locator('#save-opportunity').wait_for()
        await page.locator('#save-opportunity').click()
        await page.goto(base+'/app/actions')
        await page.get_by_role('heading',name='我的行动',exact=True).wait_for()
        for width in (360,390,430):
            await page.set_viewport_size({'width':width,'height':844})
            await page.goto(base+'/app/overview')
            await page.get_by_role('heading',name='机会总览',exact=True).wait_for()
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        assert not errors,errors
        await browser.close()
    print(json.dumps({'native_browser':'PASS','mocked_business_responses':False,'page_errors':errors},ensure_ascii=False))

if __name__=='__main__':asyncio.run(main())
