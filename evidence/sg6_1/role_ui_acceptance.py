from pathlib import Path
import base64,re,json
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];STATIC=ROOT/'web/public/product';OUT=ROOT/'evidence/sg6_1';SHOT=OUT/'screenshots'

def modules():
 core=(STATIC/'core.js').read_text();names=re.findall(r'export (?:async )?(?:const|function) ([\w$]+)',core)
 core=core.replace("history[replace?'replaceState':'pushState']({},'',url);","window.__route=new URL(url,'http://deepaha.test');")
 mark='data:image/svg+xml;base64,'+base64.b64encode((STATIC/'mark.svg').read_bytes()).decode();core=core.replace('/product/mark.svg',mark).replace('export ','')
 out='window.M_core=(()=>{'+core+';return {'+','.join(names)+'};})();\n'
 for file,export in [('user.js','renderUser'),('scout.js','renderScout'),('workbench.js','renderWork')]:
  s=(STATIC/file).read_text();s=re.sub(r"import \{([^}]+)\} from './core.js';",r'const {\1}=window.M_core;',s);s=s.replace("import {renderScout} from './scout.js';",'const renderScout=window.M_renderScout;').replace('export ','');out+='window.M_'+export+'=(()=>{'+s+';return '+export+';})();\n'
 return out

def main():
 SHOT.mkdir(parents=True,exist_ok=True);checks=[];errors=[]
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
  page=browser.new_page(viewport={'width':1440,'height':900});page.on('pageerror',lambda e:errors.append(str(e)))
  html=(STATIC/'index.html').read_text();html=re.sub(r'<script[\s\S]*?</script>','',html);html=re.sub(r'<link[^>]*>','',html);page.set_content(html);page.add_style_tag(content=(STATIC/'brand-v2.css').read_text()+'\n'+(STATIC/'product.css').read_text());page.add_script_tag(content=(STATIC/'icons.js').read_text());page.add_script_tag(content=modules())
  page.add_script_tag(content="""window.fetch=async(path,options={})=>{let data={};if(path.startsWith('/api/catalog'))data={items:[],total:0};else if(path.startsWith('/api/review?'))data={items:[],total:0};else if(path.startsWith('/api/manage/history'))data=[];else data={};return new Response(JSON.stringify(data),{status:200,headers:{'content-type':'application/json'}});};""")
  async_render="""async({roles,path,mode})=>{window.M_core.state.user={username:'role-test',roles};let view=mode==='user'?await window.M_renderUser(path,new URLSearchParams()):await window.M_renderWork(path,new URLSearchParams());document.querySelector('#app').innerHTML=view.html;view.after();}"""
  page.evaluate(async_render,{'roles':['user'],'path':'/app/overview','mode':'user'});assert page.locator('.workspace-entry').count()==0;assert '收藏与行动' in page.locator('.desktop-main-nav').inner_text();checks.append('user_has_no_workspace_entry')
  page.evaluate(async_render,{'roles':['reviewer'],'path':'/app/overview','mode':'user'});assert page.locator('.workspace-entry').inner_text().strip()=='审核工作台';checks.append('reviewer_entry_label')
  page.evaluate(async_render,{'roles':['reviewer'],'path':'/review/overview','mode':'work'});side=page.locator('.work-sidebar').inner_text();assert '内容审核' in side and '系统管理' not in side;page.screenshot(path=str(SHOT/'04_reviewer_workspace.png'),full_page=True);checks.append('reviewer_workspace_scope')
  page.evaluate(async_render,{'roles':['operator'],'path':'/app/overview','mode':'user'});assert page.locator('.workspace-entry').inner_text().strip()=='系统管理';checks.append('operator_entry_label')
  page.evaluate(async_render,{'roles':['operator'],'path':'/manage/history','mode':'work'});side=page.locator('.work-sidebar').inner_text();assert '系统管理' in side and '审核收件箱' not in side;page.screenshot(path=str(SHOT/'05_operator_workspace.png'),full_page=True);checks.append('operator_workspace_scope')
  page.evaluate(async_render,{'roles':['user','reviewer','operator'],'path':'/app/overview','mode':'user'});assert page.locator('.workspace-entry').inner_text().strip()=='工作台';checks.append('combined_entry_label')
  page.evaluate(async_render,{'roles':['user','reviewer','operator'],'path':'/review/overview','mode':'work'});side=page.locator('.work-sidebar').inner_text();assert '内容审核' in side and '系统管理' in side;page.screenshot(path=str(SHOT/'06_owner_workspace.png'),full_page=True);checks.append('combined_workspace_sections')
  for width in (768,1024,1440,1920):
   page.set_viewport_size({'width':width,'height':900});assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1'),width
  checks.append('workspace_no_horizontal_overflow_768_1024_1440_1920');browser.close()
 assert not errors,errors
 result={'checks':checks,'page_errors':errors};(OUT/'role_ui_acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
