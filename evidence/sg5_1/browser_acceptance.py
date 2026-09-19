"""SG5.1 visual proof using an explicit TestClient bridge.
Native Chromium navigation is blocked by administrator policy in this environment,
so this loads the real static JS/CSS into set_content and forwards every business
request into the real FastAPI + copied user SQLite database.  This is not native
cookie/CSP/networking certification.
"""
from pathlib import Path
import base64,json,re,sys
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];STATIC=ROOT/'web/public/product'
sys.path.insert(0,str(ROOT/'backend/src'))
from deepaha.product.service import Product
from deepaha.product.api import create_app
from deepaha.product.config import Settings
DATA=Path('/mnt/data/sg5_1_realdata');OUT=ROOT/'evidence/sg5_1';SHOT=OUT/'screenshots'
p=Product('sqlite:///'+str(DATA/'deepaha.db'),DATA/'objects')
app=create_app(Settings(database_url=p.database_url,data_dir=DATA,public_catalog=True,allowed_hosts=['testserver']),product=p)

def bundle(initial='/review/catalog'):
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
  s=s.replace("import {renderScout} from './scout.js';",'const renderScout=window.M_renderScout;')
  s=s.replace('export ','')
  out+='window.M_'+export+'=(()=>{'+s+';return '+export+';})();\n'
 s=(STATIC/'app.js').read_text(encoding='utf-8')
 s=re.sub(r"import \{([^}]+)\} from './core.js';",r'const {\1}=window.M_core;',s)
 s=s.replace("import {renderUser} from './user.js';",'const renderUser=window.M_renderUser;').replace("import {renderWork} from './workbench.js';",'const renderWork=window.M_renderWork;')
 s=s.replace('location.pathname','window.__route.pathname').replace('location.search','window.__route.search')
 out+='window.appReady=(async()=>{'+s+'})();'
 return out

def main():
 OUT.mkdir(parents=True,exist_ok=True);SHOT.mkdir(parents=True,exist_ok=True);calls=[];errors=[];checks=[]
 with TestClient(app) as client:
  r=client.post('/api/auth/login',json={'username':'sg51-reviewer','password':'long-password-123'});assert r.status_code==200,r.text
  client.headers['X-CSRF-Token']=r.json()['csrf']
  def bridge(source,path,options):
   raw=base64.b64decode(options.get('body','')) if options.get('body') else None
   headers=options.get('headers') or {}
   if client.headers.get('X-CSRF-Token'):headers['X-CSRF-Token']=client.headers['X-CSRF-Token']
   res=client.request(options.get('method','GET'),path,headers=headers,content=raw)
   calls.append({'method':options.get('method','GET'),'path':path,'status':res.status_code})
   return {'status':res.status_code,'headers':dict(res.headers),'body':base64.b64encode(res.content).decode()}
  with sync_playwright() as pw:
   browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
   page=browser.new_page(viewport={'width':1716,'height':864});page.on('pageerror',lambda e:errors.append(str(e)));page.expose_binding('__httpBridge',bridge)
   html=(STATIC/'index.html').read_text(encoding='utf-8');html=re.sub(r'<script[\s\S]*?</script>','',html);html=re.sub(r'<link[^>]*>','',html)
   page.set_content(html);page.add_style_tag(content=(STATIC/'brand-v2.css').read_text()+'\n'+(STATIC/'product.css').read_text());page.add_script_tag(content=(STATIC/'icons.js').read_text())
   page.add_script_tag(content="""window.fetch=async(path,options={})=>{let bytes=new Uint8Array();if(options.body){bytes=typeof options.body==='string'?new TextEncoder().encode(options.body):new Uint8Array(await options.body.arrayBuffer());}let binary='';for(let b of bytes)binary+=String.fromCharCode(b);let r=await window.__httpBridge(path,{method:options.method||'GET',headers:options.headers||{},body:btoa(binary)});return new Response(Uint8Array.from(atob(r.body),x=>x.charCodeAt(0)),{status:r.status,headers:r.headers});};""")
   page.add_script_tag(content=bundle('/review/catalog'));page.wait_for_selector('.catalog-group-card')
   text=page.locator('body').inner_text();assert '收录管理' in text and '按公告' in text and '按具体机会' in text and '时间待确认' in text
   assert '328' in text and '浙江省省属事业单位2026年下半年集中公开招聘人员公告' in text
   checks.append('grouped_catalog_real_data');page.screenshot(path=str(SHOT/'01_grouped_catalog_real_data.png'),full_page=True)
   page.locator('.group-toggle').nth(1).click();page.wait_for_selector('.catalog-target-panel:not([hidden]) .work-table')
   checks.append('group_expands_specific_targets');page.screenshot(path=str(SHOT/'02_group_expanded.png'),full_page=True)
   page.evaluate("window.M_core.go('/review/catalog?view=targets')");page.wait_for_selector('.work-table .withdraw')
   assert '撤回具体机会' in page.locator('body').inner_text();checks.append('exact_target_view_preserved');page.screenshot(path=str(SHOT/'03_exact_target_view.png'),full_page=True)
   page.evaluate("window.M_core.go('/app/overview')");page.wait_for_selector('.op-card')
   public=page.locator('body').inner_text();assert '报名时间 2026-' in public or '关键截止待确认' in public
   checks.append('public_safe_time_display');page.screenshot(path=str(SHOT/'04_public_safe_times.png'),full_page=True)
   for width in (1280,1440,1920):
    page.set_viewport_size({'width':width,'height':900});page.evaluate("window.M_core.go('/review/catalog')");page.wait_for_selector('.catalog-group-card');assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1'),width
   checks.append('desktop_no_overflow_1280_1440_1920');browser.close()
 assert not errors,errors
 result={'transport':'EXPLICIT_TEST_HTTP_BRIDGE','native_browser_navigation':'BLOCKED_BY_ADMINISTRATOR','database':'COPY_OF_USER_WMA_DATA_AFTER_SG5_1_BACKFILL','checks':checks,'http_calls':calls,'page_errors':errors}
 (OUT/'browser_acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
