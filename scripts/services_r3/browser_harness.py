"""Render the actual ES modules in Chromium with an explicit test-only transport.
The runtime forbids all native URL navigation. No browser policy is changed.
A virtual location is used only inside the QA-loaded module copies; API calls
are forwarded to the isolated real HTTP service. No production code uses this harness.
"""
from pathlib import Path
import base64,json,re,httpx,os,shutil
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];PUBLIC=ROOT/'web/public/product'
OUTPUT=Path(os.environ['DEEPAHA_QA_OUTPUT'])
BASE='http://127.0.0.1:'+os.environ['DEEPAHA_QA_PORT']
TRANSPORT=os.environ.get('DEEPAHA_QA_TRANSPORT','native')

class Harness:
 def __init__(self,pw,width=1440):
  options={'headless':True}
  executable=os.environ.get('DEEPAHA_QA_CHROMIUM') or shutil.which('chromium')
  if executable:options['executable_path']=executable
  self.browser=pw.chromium.launch(**options)
  self.page=self.browser.new_page(viewport={'width':width,'height':960})
  self.client=httpx.Client(base_url=BASE,trust_env=False,timeout=30)
  self.errors=[];self.requests=[]
  self.page.on('pageerror',lambda e:self.errors.append(str(e)))
  def fetch(req):
   path=req['path'];r=self.client.request(req.get('method','GET'),path,headers=req.get('headers',{}),content=(base64.b64decode(req['binary']) if req.get('binary') else req.get('body')))
   self.requests.append({'path':path,'status':r.status_code,'method':req.get('method','GET')})
   return {'status':r.status_code,'text':r.text,'headers':dict(r.headers)}
  if TRANSPORT=='native':
   self.page.goto(BASE+'/',wait_until='networkidle');return
  self.page.expose_function('__qaFetch',fetch)
  html=(PUBLIC/'index.html').read_text();html=re.sub(r'<script.*?</script>','',html);html=re.sub(r'<link[^>]*>','',html)
  self.page.set_content(html)
  self.page.add_style_tag(content='\n'.join((PUBLIC/n).read_text() for n in ['brand-v2.css','product.css','access.css','experience.css','mobile-r2.css','membership-r3.css','sharing-r3.css']))
  self.page.add_script_tag(content=(PUBLIC/'icons.js').read_text())
  assets={}
  for f in [PUBLIC/'brand-logo.png',*(PUBLIC/'hero').glob('*'),*(PUBLIC/'share').glob('*.jpg')]:
   mime='image/png' if f.suffix=='.png' else 'image/webp' if f.suffix=='.webp' else 'image/jpeg'
   assets['/product/'+f.relative_to(PUBLIC).as_posix()]='data:'+mime+';base64,'+base64.b64encode(f.read_bytes()).decode()
  for name in ('default-wide.jpg','default-square.jpg'):
   assets['/share-assets/'+name]=assets['/product/share/'+name]
   assets['https://deepaha.com/share-assets/'+name]=assets['/product/share/'+name]
  self.page.evaluate('''assets=>{
   window.__qaLocation={pathname:'/',search:''};
   const change=url=>{const u=new URL(url,'https://fixture.invalid');window.__qaLocation.pathname=u.pathname;window.__qaLocation.search=u.search;};
   window.__qaHistory={pushState:(a,b,url)=>change(url),replaceState:(a,b,url)=>change(url)};
   window.__qaGo=url=>{change(url);window.dispatchEvent(new Event('routechange'));};
   window.fetch=async(path,options={})=>{let binary=null,body=options.body;if(body instanceof Blob){const bytes=new Uint8Array(await body.arrayBuffer());let str='';for(const byte of bytes)str+=String.fromCharCode(byte);binary=btoa(str);body=null;}const r=await window.__qaFetch({path,method:options.method||'GET',headers:options.headers||{},body,binary});return new Response(r.text,{status:r.status,headers:r.headers});};
   if(!crypto.randomUUID)crypto.randomUUID=()=>[1e7]+-1e3+-4e3+-8e3+-1e11+Math.random().toString(16).slice(2);
   const images=()=>document.querySelectorAll('img[src],source[srcset]').forEach(el=>{for(const key of ['src','srcset']){const path=el.getAttribute(key);if(assets[path])el.setAttribute(key,assets[path]);}});
   new MutationObserver(images).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['src','srcset']});
  }''',assets)
  sources={f.name:f.read_text() for f in PUBLIC.glob('*.js') if f.name!='icons.js'}
  self.page.evaluate('''async sources=>{
   const urls={};function build(name){if(urls[name])return urls[name];let code=sources[name];if(code===undefined)throw new Error('Missing module '+name);
    code=code.replace(/from (['"])(\\.\\/[^'"]+)\\1/g,(all,quote,path)=>'from '+quote+build(path.slice(2))+quote);
    code='const location=window.__qaLocation,history=window.__qaHistory;\\n'+code;
    return urls[name]=URL.createObjectURL(new Blob([code],{type:'text/javascript'}));
   }await import(build('app.js'));
  }''',sources)
 def go(self,path):
  self.page.evaluate('(p)=>{if(window.__qaGo)window.__qaGo(p);else{history.pushState({},"",p);window.dispatchEvent(new Event("routechange"));}}',path);self.page.wait_for_timeout(220)
  self.page.locator("body:not(.route-loading)").wait_for(state="attached")
 def login(self,name):
  if TRANSPORT=='native':
   r=self.client.post('/api/auth/login',json={'username':name,'password':'test-browser-123'});r.raise_for_status()
  self.go('/login');self.page.locator('#username').fill(name);self.page.locator('#password').fill('test-browser-123');self.page.locator('#login-form button[type=submit]').click();self.page.locator('#login-form').wait_for(state='detached');self.page.wait_for_timeout(250);self.page.locator("body:not(.route-loading)").wait_for(state="attached")
 def screenshot(self,name):self.page.screenshot(path=str(OUTPUT/name),full_page=True)
 def close(self):self.client.close();self.browser.close()
