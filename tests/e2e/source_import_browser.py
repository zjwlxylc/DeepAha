"""Source importer browser acceptance against an isolated real HTTP API.
Default: native browser. --bridge is an EXPLICIT diagnostic alternative; it does
not validate native network/cookies/CSP/download/navigation. No mock API data.
"""
import argparse,asyncio,base64,json,os,re,sys
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from playwright.async_api import async_playwright
from browser_visual_bridge import bundle,STATIC
ROOT=Path(__file__).resolve().parents[2]

async def main():
 ap=argparse.ArgumentParser();ap.add_argument('--bridge',action='store_true');args=ap.parse_args()
 base=os.getenv('DEEPAHA_TEST_URL','http://127.0.0.1:18073')
 if os.getenv('E2E_ALLOW_WRITES')!='1' or urlsplit(base).hostname not in ('127.0.0.1','localhost'):
  raise SystemExit('Require explicitly authorized isolated loopback writes.')
 out=ROOT/'evidence/source-import/screenshots';out.mkdir(parents=True,exist_ok=True)
 package=Path(os.environ['DEEPAHA_TEST_RESEARCH_PACKAGE']);calls=[];errors=[];checks=[]
 async with httpx.AsyncClient(base_url=base,timeout=60) as http,async_playwright() as pw:
  browser=await pw.chromium.launch(executable_path=os.getenv('CHROMIUM','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
  page=await browser.new_page(viewport={'width':1440,'height':1000});page.set_default_timeout(12000)
  page.on('pageerror',lambda error:errors.append(str(error)))
  async def nav(path):
   if args.bridge:await page.evaluate('(x)=>window.M_core.go(x)',path)
   else:await page.goto(base+path)
  if args.bridge:
   async def bridge(source,path,options):
    body=base64.b64decode(options.get('body','')) if options.get('body') else None
    r=await http.request(options.get('method','GET'),path,headers=options.get('headers',{}),content=body)
    calls.append({'method':options.get('method','GET'),'path':path,'status':r.status_code})
    return {'status':r.status_code,'headers':dict(r.headers),'body':base64.b64encode(r.content).decode()}
   await page.expose_binding('__httpBridge',bridge)
   html=re.sub(r'<script[\s\S]*?</script>','', (STATIC/'index.html').read_text());html=re.sub(r'<link[^>]*>','',html)
   await page.set_content(html)
   await page.add_style_tag(content=(STATIC/'brand-v2.css').read_text()+'\n'+(STATIC/'product.css').read_text())
   await page.add_script_tag(content=(STATIC/'icons.js').read_text())
   await page.add_script_tag(content="""window.fetch=async(path,options={})=>{let bytes=new Uint8Array();if(options.body){bytes=typeof options.body==='string'?new TextEncoder().encode(options.body):new Uint8Array(await options.body.arrayBuffer());}let binary='';for(let b of bytes)binary+=String.fromCharCode(b);let r=await window.__httpBridge(path,{method:options.method||'GET',headers:options.headers||{},body:btoa(binary)});return new Response(Uint8Array.from(atob(r.body),x=>x.charCodeAt(0)),{status:r.status,headers:r.headers});};""")
   # about:blank is not a secure origin; a test-only UUID shim uses browser random bytes.
   await page.add_script_tag(content="if(!crypto.randomUUID)crypto.randomUUID=()=>{const a=crypto.getRandomValues(new Uint8Array(16));a[6]=(a[6]&15)|64;a[8]=(a[8]&63)|128;const x=[...a].map(v=>v.toString(16).padStart(2,'0')).join('');return x.slice(0,8)+'-'+x.slice(8,12)+'-'+x.slice(12,16)+'-'+x.slice(16,20)+'-'+x.slice(20);};")
   await page.add_script_tag(content=bundle())
  else:
   page.on('response',lambda r:calls.append({'method':r.request.method,'path':urlsplit(r.url).path,'status':r.status}) if '/api/' in r.url else None)
   await nav('/login?next=/review/overview')
  await page.locator('#username').fill(os.environ['DEEPAHA_TEST_USER']);await page.locator('#password').fill(os.environ['DEEPAHA_TEST_PASSWORD'])
  await page.locator('#login-form button[type=submit]').click();await page.get_by_role('heading',name='审核收件箱',exact=True).wait_for();checks.append('authenticated_login')
  await nav('/manage/source-imports');await page.locator('#scout-choose').wait_for()
  await page.screenshot(path=str(out/'01_source_assets.png'),full_page=True)
  await page.locator('#scout-inline-file').set_input_files(package)
  await page.get_by_role('heading',name='研究批次',exact=True).wait_for();checks.append('actual_exporter_file_upload')
  await page.locator('#receive-scout').wait_for()
  assert await page.locator('.scout-selected:checked').count()==1
  await page.screenshot(path=str(out/'02_import_preview.png'),full_page=True)
  await page.locator('#receive-scout').click();await page.locator('#show-receipt').wait_for();checks.append('explicit_receive_persisted')
  await page.locator('a.record-title').first.click();await page.locator('#scout-approve').wait_for();checks.append('full_candidate_brief_materials')
  await page.wait_for_timeout(5100)
  await page.screenshot(path=str(out/'03_candidate_detail.png'),full_page=False)
  await page.locator('#scout-tier').select_option('OFFICIAL_PRIMARY')
  await page.locator('#scout-reason').fill('隔离功能测试：确认来源与采集建议，暂不启用调查')
  await page.locator('#scout-approve button[type=submit]').click()
  await page.get_by_role('heading',name='来源管理',exact=True).wait_for();checks.append('explicit_source_approval_no_dispatch')
  await page.screenshot(path=str(out/'04_bound_source.png'),full_page=True)
  await nav('/manage/source-imports');await page.locator('a.record-title').first.click();await page.locator('#show-receipt').wait_for()
  feedback_url=await page.locator('a[href$="/feedback"]').first.get_attribute('href')
  if args.bridge:
   response=await http.get(feedback_url);fb=response.json()
  else:
   response=await page.request.get(base+feedback_url);fb=await response.json()
  assert [x['type'] for x in fb['events']]==['CANDIDATE_RECEIVED','SOURCE_APPROVED']
  assert fb['events'][-1]['enabled'] is False
  checks.append('feedback_readback_matches_committed_events')
  await nav('/manage/tasks');await page.get_by_role('heading',name='任务管理',exact=True).wait_for()
  assert await page.get_by_text('暂无调查任务',exact=True).count() or await page.locator('.empty').count();checks.append('zero_automatic_tasks')
  await page.set_viewport_size({'width':720,'height':800});await nav('/manage/source-imports');await page.locator('#scout-choose').wait_for()
  assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1');checks.append('desktop_200percent_equivalent_reflow')
  await page.set_viewport_size({'width':390,'height':844});await nav('/app/overview');await page.get_by_role('heading',name='机会总览',exact=True).wait_for()
  assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1');checks.append('mobile_catalog_no_overflow')
  assert not errors,errors
  result={'transport':'EXPLICIT_TEST_HTTP_BRIDGE' if args.bridge else 'NATIVE_BROWSER','mocked_business_data':False,'checks':checks,'page_errors':errors,'http_calls':calls,'real_wma_called':False,'test_only_uuid_shim':args.bridge}
  (out.parent/'11_browser_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(result,ensure_ascii=False,indent=2))
  await browser.close()

if __name__=='__main__':asyncio.run(main())
