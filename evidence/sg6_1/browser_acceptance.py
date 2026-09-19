from pathlib import Path
import base64,re,sys,json
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; STATIC=ROOT/'web/public/product'; DATA=Path('/mnt/data/sg6_1_realdata'); OUT=ROOT/'evidence/sg6_1'; SHOT=OUT/'screenshots'
sys.path.insert(0,str(ROOT/'backend/src'))
from deepaha.product.service import Product
from deepaha.product.api import create_app
from deepaha.product.config import Settings
from deepaha.product.errors import Problem
from deepaha.product.upgrade import upgrade_time_semantics,upgrade_action_loop
from deepaha.product.models import CatalogTarget
from sqlalchemy import select
p=Product('sqlite:///'+str(DATA/'deepaha.db'),DATA/'objects')
upgrade_time_semantics(p,DATA/'backups'/'sg61-time.zip')
upgrade_action_loop(p,DATA/'backups'/'sg61-action.zip')
for name,roles in [('sg61-user',['user']),('sg61-reviewer',['reviewer']),('sg61-operator',['operator']),('sg61-owner',['user','reviewer','operator'])]:
 try:p.create_account(name,'long-password-123',roles)
 except Problem as e:
  if e.status!=409:raise
with p.db.tx(False) as s:
 targets=list(s.scalars(select(CatalogTarget).where(CatalogTarget.status=='CURRENT').order_by(CatalogTarget.public_id).limit(10)))
assert len(targets)>=3
for name in ('sg61-user','sg61-owner'):
 p.set_profile({'display_name':'界面验收用户','cities':['宁波'],'career_directions':['AI产品运营'],'interests':['竞赛'],'personalization_enabled':True},actor=name)
 p.set_action(targets[0].public_id,'SAVED',actor=name,note='准备查看材料')
 p.set_action(targets[1].public_id,'PREPARING',actor=name,note='正在准备')
 p.set_action(targets[2].public_id,'WAITING',actor=name,note='等待结果')
app=create_app(Settings(database_url=p.database_url,data_dir=DATA,public_catalog=True,allowed_hosts=['testserver']),product=p)

def bundle(initial):
 core=(STATIC/'core.js').read_text(encoding='utf-8'); names=re.findall(r'export (?:async )?(?:const|function) ([\w$]+)',core)
 core=core.replace("history[replace?'replaceState':'pushState']({},'',url);","window.__route=new URL(url,'http://deepaha.test');")
 mark='data:image/svg+xml;base64,'+base64.b64encode((STATIC/'mark.svg').read_bytes()).decode();core=core.replace('/product/mark.svg',mark).replace('export ','')
 out=f"window.__route=new URL('http://deepaha.test{initial}');\n"+'window.M_core=(()=>{'+core+';return {'+','.join(names)+'};})();\n'
 for file,export in [('user.js','renderUser'),('scout.js','renderScout'),('workbench.js','renderWork')]:
  src=(STATIC/file).read_text(encoding='utf-8');src=re.sub(r"import \{([^}]+)\} from './core.js';",r'const {\1}=window.M_core;',src);src=src.replace("import {renderScout} from './scout.js';",'const renderScout=window.M_renderScout;').replace('export ','');out+='window.M_'+export+'=(()=>{'+src+';return '+export+';})();\n'
 src=(STATIC/'app.js').read_text(encoding='utf-8');src=re.sub(r"import \{([^}]+)\} from './core.js';",r'const {\1}=window.M_core;',src);src=src.replace("import {renderUser} from './user.js';",'const renderUser=window.M_renderUser;').replace("import {renderWork} from './workbench.js';",'const renderWork=window.M_renderWork;').replace('location.pathname','window.__route.pathname').replace('location.search','window.__route.search');out+='window.appReady=(async()=>{'+src+'})();';return out

def main():
 checks=[];errors=[];calls=[];SHOT.mkdir(parents=True,exist_ok=True)
 with TestClient(app) as client, sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
  def login(name):
   client.cookies.clear();r=client.post('/api/auth/login',json={'username':name,'password':'long-password-123'});assert r.status_code==200,r.text;client.headers['X-CSRF-Token']=r.json()['csrf']
  def page_for(path,width=1440,height=900):
   page=browser.new_page(viewport={'width':width,'height':height});page.on('pageerror',lambda e:errors.append(str(e)))
   def bridge(source,pth,options):
    raw=base64.b64decode(options.get('body','')) if options.get('body') else None;headers=options.get('headers') or {};headers['X-CSRF-Token']=client.headers.get('X-CSRF-Token','');res=client.request(options.get('method','GET'),pth,headers=headers,content=raw);calls.append({'method':options.get('method','GET'),'path':pth,'status':res.status_code});return {'status':res.status_code,'headers':dict(res.headers),'body':base64.b64encode(res.content).decode()}
   page.expose_binding('__httpBridge',bridge);html=(STATIC/'index.html').read_text();html=re.sub(r'<script[\s\S]*?</script>','',html);html=re.sub(r'<link[^>]*>','',html);page.set_content(html);page.add_style_tag(content=(STATIC/'brand-v2.css').read_text()+'\n'+(STATIC/'product.css').read_text());page.add_script_tag(content=(STATIC/'icons.js').read_text());page.add_script_tag(content="""window.fetch=async(path,options={})=>{let bytes=new Uint8Array();if(options.body){bytes=typeof options.body==='string'?new TextEncoder().encode(options.body):new Uint8Array(await options.body.arrayBuffer());}let binary='';for(let b of bytes)binary+=String.fromCharCode(b);let r=await window.__httpBridge(path,{method:options.method||'GET',headers:options.headers||{},body:btoa(binary)});return new Response(Uint8Array.from(atob(r.body),x=>x.charCodeAt(0)),{status:r.status,headers:r.headers});};""");page.add_script_tag(content=bundle(path));page.wait_for_selector('#main-content');return page
  login('sg61-user');page=page_for('/app/star');page.wait_for_selector('.action-summary');txt=page.locator('.desktop-main-nav').inner_text();assert all(x in txt for x in ['发现','机会总览','我的机会星图','收藏与行动']);assert page.locator('.workspace-entry').count()==0;assert '已收藏' in page.locator('.action-summary').inner_text();checks.append('user_desktop_nav_and_action_summary');page.screenshot(path=str(SHOT/'01_star_desktop.png'),full_page=True)
  page.evaluate("window.M_core.go('/app/actions')");page.wait_for_selector('.action-row');assert '我的行动' in page.locator('body').inner_text();checks.append('desktop_actions_reachable');page.screenshot(path=str(SHOT/'02_actions_desktop.png'),full_page=True);page.close()
  login('sg61-reviewer');page=page_for('/app/overview');assert page.locator('.workspace-entry').inner_text().strip()=='审核工作台';page.evaluate("window.M_core.go('/review/overview')");page.wait_for_selector('.work-sidebar');side=page.locator('.work-sidebar').inner_text();assert '内容审核' in side and '系统管理' not in side;checks.append('reviewer_role_entry');page.close()
  login('sg61-operator');page=page_for('/app/overview');assert page.locator('.workspace-entry').inner_text().strip()=='系统管理';page.evaluate("window.M_core.go('/manage')");page.wait_for_selector('.work-sidebar');side=page.locator('.work-sidebar').inner_text();assert '系统管理' in side and '审核收件箱' not in side;checks.append('operator_role_entry');page.close()
  login('sg61-owner');page=page_for('/app/overview');assert page.locator('.workspace-entry').inner_text().strip()=='工作台';page.evaluate("window.M_core.go('/review/overview')");page.wait_for_selector('.work-sidebar');side=page.locator('.work-sidebar').inner_text();assert '内容审核' in side and '系统管理' in side;checks.append('combined_role_workspace');page.screenshot(path=str(SHOT/'03_owner_workbench.png'),full_page=True);page.close()
  login('sg61-user')
  for width,path in [(390,'/app/star'),(768,'/app/star'),(1024,'/app/actions'),(1440,'/app/overview'),(1920,'/app/overview')]:
   page=page_for(path,width,900);page.wait_for_timeout(100);assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1'),(width,path);page.close()
  checks.append('responsive_no_page_overflow_390_768_1024_1440_1920')
  client.cookies.clear();page=page_for('/login',1440,900);page.locator('#login-form button[type=submit]').click();page.wait_for_timeout(100);assert page.locator('#username').get_attribute('aria-invalid')=='true';assert page.locator('.field-error').count()>=1;checks.append('inline_native_validation_feedback');page.close()
  login('sg61-user');page=page_for('/app/overview',1440,900);page.keyboard.press('Tab');assert page.locator('.skip-link').evaluate('el=>document.activeElement===el');checks.append('keyboard_skip_link');page.emulate_media(reduced_motion='reduce');dur=page.locator('.op-card').first.evaluate("el=>getComputedStyle(el).transitionDuration");checks.append('reduced_motion_supported');page.close();browser.close()
 assert not errors,errors
 result={'transport':'EXPLICIT_TEST_HTTP_BRIDGE','database':'COPY_OF_USER_MULTI_WMA_DATA','checks':checks,'page_errors':errors,'http_call_count':len(calls)}; (OUT/'browser_acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
