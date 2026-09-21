"""Failure injection is QA-only; successful underlying writes use the real local API."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experience'))
from browser_harness import Harness,OUTPUT,TRANSPORT
from playwright.sync_api import sync_playwright
checks=[]
def ck(name,value):checks.append({'name':name,'passed':bool(value)});print(name,value,flush=True)
with sync_playwright() as pw:
 h=Harness(pw,width=390);p=h.page
 def wait():p.wait_for_timeout(400);p.locator("body:not(.route-loading)").wait_for(state="attached")
 h.login('reader');h.go('/app/actions');wait();p.locator('.preparation-open').first.click();wait()
 p.evaluate('''()=>{window.__originalFetch=window.fetch;window.__failResponse=true;window.fetch=async(path,options={})=>{const response=await window.__originalFetch(path,options);if(window.__failResponse&&String(path).endsWith('/items')&&options.method==='POST'){window.__failResponse=false;throw new TypeError('QA simulated lost response after backend write')}return response;};}''')
 p.locator('#item-text').fill('Retry without duplicate');p.locator('#dialog button[type=submit]').click();wait()
 ck('lost write response keeps input',p.locator('#item-text').input_value()=='Retry without duplicate')
 ck('uncertain write shown inline','尚未确认' in p.locator('#dialog .form-feedback').inner_text())
 p.locator('#dialog button[type=submit]').click();wait();ck('retry uses same idempotency key',p.locator('.preparation-item').count()==1)
 p.set_viewport_size({'width':390,'height':500});p.wait_for_timeout(200)
 button=p.locator('#dialog button[type=submit]').bounding_box();ck('dialog action visible in short viewport',button is not None and button['y']>=0 and button['y']+button['height']<=500)
 p.screenshot(path=str(OUTPUT/'short-viewport.png'));p.keyboard.press('Escape');wait();p.set_viewport_size({'width':390,'height':844})
 p.evaluate('''()=>{window.fetch=async(path,options={})=>{if(String(path).startsWith('/api/catalog?'))throw new TypeError('QA read unavailable');return window.__originalFetch(path,options);};}''')
 h.go('/app/overview?q=青年');wait();ck('read failure offers local retry',p.locator('#retry-page').count()==1)
 p.evaluate('()=>{window.fetch=window.__originalFetch;}');p.locator('#retry-page').click();wait();ck('retry keeps query',p.locator('#catalog-search [name=q]').input_value()=='青年')
 h.go('/manage');wait();ck('reader sees clear permission error','没有访问' in p.locator('h1').inner_text())
 h.go('/app/opportunity/not-a-real-target');wait();ck('missing content offers safe return',p.locator('.error-panel a[href="/app/overview"]').count()==1)
 # Reminder settings are explicitly respected, with a return to the same opportunity.
 snapshot=h.client.get('/api/me/profile-state').json();h.client.patch('/api/me/profile',json={'expected_version':snapshot['version'],'changes':{'notification_enabled':False}},headers={'X-CSRF-Token':h.client.cookies.get('deepaha_csrf')})
 oid=h.client.get('/api/catalog').json()['items'][0]['id'];h.go('/app/opportunity/'+oid);wait();p.locator('#remind').click();wait()
 ck('disabled reminders point to setting',p.locator('#dialog a[data-nav]').count()==1 and '截止提醒已关闭' in p.locator('#dialog h2').inner_text())
 ck('settings link returns to opportunity','return=' in p.locator('#dialog a[data-nav]').get_attribute('href'))
 ck('no JS errors',not h.errors);h.close()
(OUTPUT/'edges.json').write_text(json.dumps({'scope':'HTTP + QA-only loss injection; short viewport is not a physical mobile keyboard test','checks':checks},ensure_ascii=False,indent=2),encoding='utf-8')
raise SystemExit(int(any(not c['passed'] for c in checks)))
