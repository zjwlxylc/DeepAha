"""R3 real host UI flows. No Worker/provider/payment requests; reserved test sites."""
import json,os,sys
from pathlib import Path
from playwright.sync_api import sync_playwright
from browser_harness import Harness,ROOT,OUTPUT,TRANSPORT
checks=[];shots=[];views=[]

def check(name,ok=True,detail=''):
    checks.append({'name':name,'passed':bool(ok),'detail':detail})
    print(('PASS ' if ok else 'FAIL ')+name,flush=True)
    if not ok:raise AssertionError(name+' '+detail)

with sync_playwright() as pw:
 h=Harness(pw,width=1440);p=h.page
 def wait():
  p.wait_for_timeout(130);p.locator("body:not(.route-loading)").wait_for(state="attached",timeout=15000)
 def route(path,width=1440):
  p.set_viewport_size({'width':width,'height':960 if width>900 else 844});h.go(path);wait()
  check('route '+path,p.locator('h1').count()==1 and not p.locator('.page-error').count(),p.locator('body').inner_text()[:200])
 def shot(name,width):
  p.set_viewport_size({'width':width,'height':960 if width>900 else 844});wait()
  p.evaluate("document.querySelector('#toast')?.classList.remove('visible')")
  metrics=p.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})')
  check('layout '+name+' '+str(width),metrics['scroll']<=width+1,str(metrics));views.append({'name':name,**metrics})
  file=name+'-'+str(width)+'.png';p.screenshot(path=str(OUTPUT/file),full_page=True);shots.append(file)
 def dialog_submit():
  p.locator('#dialog button[type=submit]').click();p.locator("#dialog:not([open])").wait_for(state="attached",timeout=10000);wait()
 def api(path,method='GET',data=None):
  hdr={'X-CSRF-Token':h.client.cookies.get('deepaha_csrf','')}
  r=h.client.request(method,path,json=data,headers=hdr);check('api '+method+' '+path,r.status_code<400,r.text[:300]);return r.json()
 try:
  route('/services');check('plans start draft','服务方案正在准备中' in p.locator('#main-content').inner_text())
  h.login('owner');route('/manage/services')
  for _ in range(3):p.get_by_role('button',name='确认上架',exact=True).first.click();dialog_submit()
  check('native pricing persisted',len(api('/api/membership/plans'))==3)
  route('/services')
  for width in (320,390,768,1440):shot('services',width)
  h.login('reader');route('/services',390)
  p.get_by_role('button',name='申请 基础订阅',exact=True).click();p.locator('#dialog [name=accepted]').check();dialog_submit()
  route('/app/subscription',390);check('order waiting not claimed paid','待确认' in p.locator('#main-content').inner_text());shot('subscription-pending',390)
  h.login('owner');route('/manage/services/orders')
  p.get_by_role('button',name='赠送试用',exact=True).click();p.locator('#dialog [name=reason]').fill('本地合成验收试用开通');p.locator('#dialog [name=confirm]').check();dialog_submit()
  h.login('reader');route('/app/tracking',390)
  p.get_by_role('button',name='＋ 添加跟踪主题',exact=True).click();p.locator('#dialog [name=name]').fill('宁波科研实践');p.locator('#dialog [name=q]').fill('科研');p.locator('#dialog [name=region]').fill('宁波');dialog_submit()
  check('tracking saved','宁波科研实践' in p.locator('#main-content').inner_text());shot('tracking',390)
  route('/app/sources',390);p.get_by_role('button',name='＋ 提交网站',exact=True).click()
  p.locator('#dialog [name=name]').fill('海湾科研栏目');p.locator('#dialog [name=url]').fill('https://research.example.org/')
  p.locator('#dialog [name=note]').fill('私人目标：关注本科科研助理，不要公开个人信息。');p.locator('#dialog [name=consent]').check();dialog_submit()
  check('source automatically pending','待确认' in p.locator('#main-content').inner_text());shot('source-submission',390)
  h.login('reviewer');route('/review/sources')
  check('reviewer not price admin',p.locator('.work-sidebar a[href="/manage/services"]').count()==0)
  p.get_by_role('button',name='处理线索',exact=True).click();p.locator('#dialog [name=note]').fill('公开栏目可接入，后续资料仍须整体审核。');p.locator('#dialog [name=public_brief]').fill('仅调查科研栏目公开的项目公告，下载附件并保留来源证据。');dialog_submit();shot('source-review',1440)
  h.login('owner');route('/review/sources');p.get_by_role('button',name='登记到原来源管理',exact=True).click();wait();check('source adopted','已关联来源' in p.locator('#main-content').inner_text())
  p.get_by_role('button',name='明确启用此来源',exact=True).click();p.locator('#dialog [name=agree]').check();dialog_submit()
  route('/manage/services/items');shot('service-items',1440)
  route('/manage/services/runtime');p.get_by_role('button',name='调整运行设置',exact=True).click();p.locator('#dialog [name=enabled]').check();dialog_submit()
  p.get_by_role('button',name='按当前设置执行一轮',exact=True).click();dialog_submit()
  r=api('/api/membership/manage/runtime');check('scheduled directory scan completed',r['last_result']['state']=='COMPLETED',str(r))
  check('no paid auto enabled',r['allow_site_enqueue'] is False)
  h.login('reader');route('/app/notifications',390);check('unified services notices',p.get_by_text('服务进展',exact=True).count()>0);shot('unified-messages',390)
  route('/app/me',390);check('native account has subscriptions',p.locator('a[href="/app/subscription"]').count()>0);shot('account',390)
  route('/services',390);p.get_by_role('button',name='提交定制需求',exact=True).click();p.locator('#dialog [name=note]').fill('希望跟踪研究院公开的科研项目栏目');p.locator('#dialog [name=site_name]').fill('定制科研来源');p.locator('#dialog [name=site_url]').fill('https://custom.example.org/notices');p.locator('#dialog [name=source_consent]').check();p.locator('#dialog [name=accepted]').check();dialog_submit();check('custom source submitted once',len(api('/api/membership/submissions'))==2)
  h.login('owner');route('/manage/services/orders');p.get_by_role('button',name='制定报价',exact=True).click();p.locator('#dialog [name=amount]').fill('199');p.locator('#dialog [name=scope]').fill('跟踪指定公开科研栏目，按约定周期核对，不保证一定有新机会。');dialog_submit();shot('quoted-orders',1440)
  h.login('reader');route('/app/subscription',390);p.get_by_role('button',name='查看并确认报价',exact=True).click();p.locator('#dialog [name=agree]').check();dialog_submit();check('custom quote accepted','定制订阅' in p.locator('#main-content').inner_text())
  # Review/read-only boundary enforced by original R2 handler.
  h.login('owner');route('/manage/services',390);shot('management-readonly',390);check('mobile write buttons disabled',p.get_by_role('button',name='＋ 新建套餐',exact=True).is_disabled())
  route('/manage/sharing');shot('sharing-settings',1440)
  p.locator('#share-config [name=title]').fill('机会星图｜看见你的下一步');p.locator('#share-config [name=description]').fill('官方机会与持续关注，让适合你的机会不再轻易擦肩而过。')
  check('share preview updates immediately',p.locator('#share-preview-title').inner_text()=='机会星图｜看见你的下一步')
  p.locator('#share-config button[type=submit]').click();wait();check('share settings persisted',api('/api/manage/sharing')['title']=='机会星图｜看见你的下一步')
  p.locator('#share-cover-file').set_input_files(str(ROOT/'web/public/product/share/default-wide.jpg'));wait();p.wait_for_timeout(400)
  p.locator('#share-config button[type=submit]').click();wait();check('share cover upload persisted',len(api('/api/manage/sharing')['cover'])==68)
  for width in (390,768):shot('sharing-settings',width)
  # Safety rendered preview quotes escaped; real public raw HTML has metadata.
  page=h.client.get('/share');check('public HTML is standalone OG',page.status_code==200 and 'property="og:title"' in page.text)
  check('public canonical not fixture host','https://deepaha.com/share' in page.text)
  for path in ['/app/privacy','/app/subscription','/app/tracking','/app/sources']:
   h.login('reader')
   for width in (320,390,1440):route(path,width);shot(path.split('/')[-1],width)
  h.login('owner')
  for path in ['/manage/services','/manage/services/items','/manage/services/grants','/manage/services/jobs','/manage/services/audit','/manage/services/runtime','/review/sources','/manage/sharing']:
   for width in (390,1440):route(path,width)
  check('no javascript page errors',not h.errors,str(h.errors))
  check('no server errors',not [r for r in h.requests if r['status']>=500])
 finally:
  p.screenshot(path=str(OUTPUT/"last-page.png"),full_page=True)
  (OUTPUT/"last-page.txt").write_text(p.locator("body").inner_text(),encoding="utf-8")
  (OUTPUT/'browser-r3.json').write_text(json.dumps({'transport':TRANSPORT,'scope':'Real DOM/ES modules and real local FastAPI/SQLite; QA-only transport bridge when native navigation is blocked. No live WMA/payment/WeChat.', 'checks':checks,'screenshots':shots,'views':views,'errors':h.errors,'http_requests':h.requests},ensure_ascii=False,indent=2))
  h.close()
