"""Isolated public landing: actual HTTP HTML/CSS/JS loaded via explicit QA bridge."""
from pathlib import Path
import os,re,base64,json
from urllib.parse import urlsplit
import httpx
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(os.environ['DEEPAHA_QA_OUTPUT']);checks=[]
base='http://127.0.0.1:'+os.environ['DEEPAHA_QA_PORT']

def check(name,ok):
 checks.append({'name':name,'passed':bool(ok)})
 if not ok:raise AssertionError(name)
with httpx.Client(base_url=base,trust_env=False,timeout=20) as client,sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path=os.environ.get('DEEPAHA_QA_CHROMIUM') or '/usr/bin/chromium',headless=True)
 page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 html=client.get('/share').text;check('public OG before JS','property="og:title"' in html)
 html=re.sub(r'<script.*?</script>','',html);html=re.sub(r'<link[^>]*>','',html)
 for path in set(re.findall(r'<img[^>]+src="([^"]+)"',html)):
  response=client.get(urlsplit(path).path);response.raise_for_status()
  html=html.replace('src="'+path+'"','src="data:'+response.headers['content-type']+';base64,'+base64.b64encode(response.content).decode()+'"')
 page.set_content(html)
 page.add_style_tag(content=client.get('/product/share-page.css').text)
 page.evaluate("Object.defineProperty(navigator,'clipboard',{value:{writeText:async(text)=>window.__copied=text},configurable:true})")
 page.add_script_tag(content=client.get('/product/share-page.js').text)
 for width in (390,1440):
  page.set_viewport_size({'width':width,'height':900});page.wait_for_timeout(100)
  check('share layout '+str(width),page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
  page.screenshot(path=str(OUT/('share-landing-'+str(width)+'.png')),full_page=True)
 check('CTA target same product',page.locator('a.primary').get_attribute('href')=='/app/overview')
 page.locator('#copy-share').click();page.wait_for_timeout(100)
 check('copy public canonical link',page.evaluate("window.__copied==='https://deepaha.com/share?sv=0'"))
 check('copy feedback is not false completed-share',page.locator('#share-status').inner_text().startswith('链接已复制'))
 check('no JS errors',not errors)
 browser.close()
(OUT/'share-browser.json').write_text(json.dumps({'transport':'Explicit QA HTTP/DOM bridge, no native navigation or real WeChat','checks':checks,'errors':errors},ensure_ascii=False,indent=2))
print(len(checks),'share landing checks passed')
