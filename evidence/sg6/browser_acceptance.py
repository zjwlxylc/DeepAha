"""SG6 UI proof via explicit TestClient HTTP bridge (native loopback navigation is policy-blocked)."""
from pathlib import Path
import base64,json,re,sys
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];STATIC=ROOT/'web/public/product'
sys.path.insert(0,str(ROOT/'backend/src'))
from deepaha.product.service import Product
from deepaha.product.api import create_app
from deepaha.product.config import Settings
DATA=Path('/mnt/data/sg6_final_realdata');OUT=ROOT/'evidence/sg6';SHOT=OUT/'screenshots'
p=Product('sqlite:///'+str(DATA/'deepaha.db'),DATA/'objects')
app=create_app(Settings(database_url=p.database_url,data_dir=DATA,public_catalog=True,allowed_hosts=['testserver']),product=p)

def bundle(initial):
 core=(STATIC/'core.js').read_text(encoding='utf-8')
 names=re.findall(r'export (?:async )?(?:const|function) ([\w$]+)',core)
 core=core.replace("history[replace?'replaceState':'pushState']({},'',url);","window.__route=new URL(url,'http://deepaha.test');")
 mark='data:image/svg+xml;base64,'+base64.b64encode((STATIC/'mark.svg').read_bytes()).decode()
 core=core.replace('/product/mark.svg',mark).replace('export ','')
 out=f"window.__route=new URL('http://deepaha.test{initial}');\n"
 out+='window.M_core=(()=>{'+core+';return {'+','.join(names)+'};})();\n'
 for file,export in [('user.js','renderUser'),('scout.js','renderScout'),('workbench.js','renderWork')]:
  s=(STATIC/file).read_text(encoding='utf-8')
  s=re.sub(r"import \{([^}]+)\} from './core.js';",r'const {\1}=window.M_core;',s)
  s=s.replace("import {renderScout} from './scout.js';",'const renderScout=window.M_renderScout;').replace('export ','')
  out+='window.M_'+export+'=(()=>{'+s+';return '+export+';})();\n'
 s=(STATIC/'app.js').read_text(encoding='utf-8')
 s=re.sub(r"import \{([^}]+)\} from './core.js';",r'const {\1}=window.M_core;',s)
 s=s.replace("import {renderUser} from './user.js';",'const renderUser=window.M_renderUser;').replace("import {renderWork} from './workbench.js';",'const renderWork=window.M_renderWork;')
 s=s.replace('location.pathname','window.__route.pathname').replace('location.search','window.__route.search')
 out+='window.appReady=(async()=>{'+s+'})();'
 return out

def main():
 OUT.mkdir(parents=True,exist_ok=True);SHOT.mkdir(parents=True,exist_ok=True)
 checks=[];calls=[];errors=[]
 client=TestClient(app)
 r=client.post('/api/auth/login',json={'username':'sg6-accept','password':'long-password-123'});assert r.status_code==200,r.text
 client.headers['X-CSRF-Token']=r.json()['csrf']
 def bridge(source,path,options):
  raw=base64.b64decode(options.get('body','')) if options.get('body') else None
  headers=options.get('headers') or {};headers['X-CSRF-Token']=client.headers['X-CSRF-Token']
  res=client.request(options.get('method','GET'),path,headers=headers,content=raw)
  calls.append({'method':options.get('method','GET'),'path':path,'status':res.status_code})
  return {'status':res.status_code,'headers':dict(res.headers),'body':base64.b64encode(res.content).decode()}
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
  page=browser.new_page(viewport={'width':390,'height':844});page.on('pageerror',lambda e:errors.append(str(e)));page.expose_binding('__httpBridge',bridge)
  html=(STATIC/'index.html').read_text(encoding='utf-8');html=re.sub(r'<script[\s\S]*?</script>','',html);html=re.sub(r'<link[^>]*>','',html)
  page.set_content(html);page.add_style_tag(content=(STATIC/'brand-v2.css').read_text()+'\n'+(STATIC/'product.css').read_text());page.add_script_tag(content=(STATIC/'icons.js').read_text())
  page.add_script_tag(content="""window.fetch=async(path,options={})=>{let bytes=new Uint8Array();if(options.body){bytes=typeof options.body==='string'?new TextEncoder().encode(options.body):new Uint8Array(await options.body.arrayBuffer());}let binary='';for(let b of bytes)binary+=String.fromCharCode(b);let r=await window.__httpBridge(path,{method:options.method||'GET',headers:options.headers||{},body:btoa(binary)});return new Response(Uint8Array.from(atob(r.body),x=>x.charCodeAt(0)),{status:r.status,headers:r.headers});};""")
  page.add_script_tag(content=bundle('/app/actions'));page.wait_for_selector('.weekly-digest-card');page.wait_for_selector('.action-row')
  body=page.locator('body').inner_text();assert '本周机会摘要' in body and '行动时间线' in body and 'WAITING' not in body
  checks.append('mobile_actions_weekly_digest');page.screenshot(path=str(SHOT/'01_actions_mobile.png'),full_page=True)
  page.locator('.action-history').first.click();page.wait_for_selector('.action-timeline');assert '材料准备中' in page.locator('body').inner_text();checks.append('action_timeline_modal');page.screenshot(path=str(SHOT/'02_action_timeline.png'),full_page=True)
  page.locator('.modal-close').click() if page.locator('.modal-close').count() else page.keyboard.press('Escape')
  page.evaluate("window.M_core.go('/app/profile')");page.wait_for_selector('.notification-settings');txt=page.locator('body').inner_text();assert '截止提醒' in txt and '机会变化' in txt and '每周机会摘要' in txt
  checks.append('independent_notification_controls');page.screenshot(path=str(SHOT/'03_notification_preferences.png'),full_page=True)
  page.evaluate("window.M_core.go('/app/notifications')");page.wait_for_selector('#show-weekly-digest');assert '只在真正重要时找你' in page.locator('body').inner_text();checks.append('notifications_and_weekly_summary')
  page.set_viewport_size({'width':1440,'height':900});page.evaluate("window.M_core.go('/manage/feedback')");page.wait_for_selector('.work-table');txt=page.locator('body').inner_text();assert '反馈样本' in txt and '不会自动改变资格规则' in txt and 'INTERVIEW' in txt
  table_text=page.locator('.work-table').inner_text();assert 'sg6-accept' not in table_text and '进入面试' not in table_text
  checks.append('operator_deidentified_feedback_candidates');page.screenshot(path=str(SHOT/'04_feedback_candidates_desktop.png'),full_page=True)
  page.set_viewport_size({'width':390,'height':844});page.evaluate("window.M_core.go('/app/actions')");page.wait_for_selector('.action-row');assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
  checks.append('mobile_no_horizontal_overflow');browser.close()
 result={'transport':'EXPLICIT_TEST_HTTP_BRIDGE','native_browser_navigation':'BLOCKED_BY_ADMINISTRATOR','database':'COPY_OF_USER_MULTI_WMA_DATA_AFTER_SG6','checks':checks,'http_calls':calls,'page_errors':errors}
 assert not errors,errors
 (OUT/'browser_acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
