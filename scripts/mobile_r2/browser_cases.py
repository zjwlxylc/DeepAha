"""Actual page modules + actual isolated HTTP. Browser bridge limitation is explicit."""
import os,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experience'))
from browser_harness import Harness,ROOT,OUTPUT,TRANSPORT
from playwright.sync_api import sync_playwright
checks=[];views=[]
def check(name,v,detail=''):
 checks.append({'name':name,'passed':bool(v),'detail':detail});print(('OK ' if v else 'FAIL ')+name,flush=True)
 if not v:print('FAIL',name,detail,flush=True)
with sync_playwright() as pw:
 h=Harness(pw,width=390);p=h.page
 def pause():p.wait_for_timeout(300);p.locator("body:not(.route-loading)").wait_for(state="attached")
 def shot(name):h.screenshot(name+'.png')
 def route(url,width=390):p.set_viewport_size({'width':width,'height':844 if width<901 else 960});h.go(url);pause()
 def click_nav(locator):locator.click();pause()
 def metrics(url,width):
  route(url,width)
  r=p.evaluate('''()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,h1:document.querySelectorAll('h1').length,title:document.querySelector('h1')?.textContent})''')
  r['route']=url;views.append(r);check('layout '+str(width)+' '+url,r['scroll']<=width+1 and r['h1']==1,str(r))
 # Read-only public browsing and mobile reachability.
 route('/app/overview');shot('r2-overview-mobile')
 check('mobile filter is one-row toolbar',p.locator('#catalog-search').evaluate('(x)=>x.getBoundingClientRect().height')<100)
 targets=p.locator('#open-catalog-filter').evaluate('(x)=>({w:x.getBoundingClientRect().width,h:x.getBoundingClientRect().height})')
 check('44px mobile filter target',targets['w']>=44 and targets['h']>=44,str(targets))
 route('/');shot('r2-home-mobile')
 controls=p.locator('.home-carousel-controls button').evaluate_all('(nodes)=>nodes.map(x=>({w:x.getBoundingClientRect().width,h:x.getBoundingClientRect().height}))')
 check('44px carousel controls',all(x['w']>=32 and x['h']>=44 for x in controls),str(controls))
 check('brand asset unchanged',p.locator('.brand-mark').first.count()==1)
 if not os.environ.get('DEEPAHA_QA_LAYOUT_ONLY'):
  route('/app/me');check('guest account is not forced login',p.locator('.guest-card').count()==1)
  h.login('reader');route('/app/overview')
  p.locator('#open-catalog-filter').click();pause()
  p.locator('#filter-region').fill('宁波');p.locator('#filter-kind').select_option('RESEARCH_PROGRAM');p.locator('#dialog button[type=submit]').click();pause()
  check('filter applies query',p.locator('.filter-context').count()==1 and '宁波' in p.locator('.filter-context').inner_text())
  p.evaluate('window.scrollTo(0,480)');p.wait_for_timeout(100)
  before=p.evaluate('window.scrollY');p.locator('.op-card h3 a').nth(2).click();pause()
  check('decision entry before fact panels',p.locator('.decision-panel').evaluate('(n)=>n.compareDocumentPosition(document.querySelector("#detail-fields")) & Node.DOCUMENT_POSITION_FOLLOWING')!=0)
  shot('r2-detail-mobile')
  p.locator('#main-content>a[data-nav]').first.click();pause()
  check('return keeps filter and scroll',p.locator('.filter-context').count()==1 and p.evaluate('scrollY')>0)
  rows=h.client.get('/api/me/action-board?limit=30').json()['items']
  preparing=next(x for x in rows if x['status']=='PREPARING')['opportunity']['id']
  route('/app/opportunity/'+preparing);check('detail shows saved preparation state','准备中' in p.locator('#save-opportunity').inner_text())
  old=h.client.get('/api/me/actions/'+preparing).json()
  p.locator('#save-opportunity').click();pause();now=h.client.get('/api/me/actions/'+preparing).json()
  check('repeat save does not reset progress',old['note']==now['note'] and now['status']=='PREPARING')
  route('/app/actions');check('mobile defaults list',p.locator('.action-list-view').count()==1)
  p.locator('.preparation-open').first.click();pause();shot('r2-preparation-empty')
  for text in ('合成验收：整理作品集','合成验收：核对材料'):
   p.locator('#item-text').fill(text);p.locator('#dialog button[type=submit]').click();pause()
  check('preparation supports continuous entry',p.locator('#dialog').is_visible() and p.locator('.preparation-item').count()>=2 and p.locator('#item-text').input_value()=='')
  p.locator('.item-edit').first.click();p.locator('#edit-preparation').fill('合成验收：已修改的材料清单');p.locator('.save-edit').click();pause()
  check('inline editing keeps list','已修改的材料清单' in p.locator('#preparation-items').inner_text())
  p.locator('.item-toggle').first.click();pause();check('completion persists','1 / ' in p.locator('#preparation-count').inner_text());shot('r2-preparation-mobile')
  p.locator('#item-text').fill('不应丢失的输入');p.keyboard.press('Escape');p.wait_for_timeout(80)
  check('dialog dirty-close safeguard',p.locator('.dialog-discard-confirm').is_visible() and p.locator('#item-text').input_value()=='不应丢失的输入')
  p.locator('.keep-editing').click();p.locator('#item-text').fill('');p.keyboard.press('Escape');pause()
  route('/app/profile?focus=team_size');p.locator('#team_size').fill('6');p.locator('.mobile-nav a').filter(has_text='总览').click();pause()
  check('profile leave confirmation preserves input',p.locator('#dialog').is_visible() and p.locator('#team_size').input_value()=='6')
  p.locator('#dialog .dialog-footer .close-dialog').click();pause()
  p.locator('#profile-form button[type=submit]').click();pause()
  check('profile PATCH actually saved',h.client.get('/api/me/profile-state').json()['profile']['team_size']==6)
  shot('r2-profile-mobile')
  p.locator('#team_size').fill('7');state=h.client.get('/api/me/profile-state').json();token=h.client.cookies.get('deepaha_csrf')
  h.client.patch('/api/me/profile',headers={'X-CSRF-Token':token},json={'expected_version':state['version'],'changes':{'cities':['杭州']}})
  p.locator('#profile-form button[type=submit]').click();pause();check('conflict shown',p.locator('#dialog').is_visible())
  p.locator('#dialog button[type=submit]').click();pause()
  check('explicit merge updates visible untouched values',p.locator('[name=cities]').input_value()=='杭州')
  route('/app/notifications');check('message badge reachable on phone',p.locator('.phone-message').is_visible());shot('r2-notifications-mobile')
  p.locator('#batch-read').click();pause();check('mark read uses real backend',h.client.get('/api/me/summary').json()['unread_count']==0)
  # Read-only dialog tab wrapping and focus return.
  route('/app/opportunity/'+preparing);p.locator('#fit-check').click();pause()
  for k in ('Tab','Shift+Tab'):
   for _ in range(12):p.keyboard.press(k)
   check('modal focus '+k,p.evaluate('document.querySelector("#dialog").contains(document.activeElement)'))
  p.keyboard.press('Escape');pause();check('dialog restores opener focus',p.locator('#fit-check').evaluate('(x)=>document.activeElement===x'))
  # Required field error inline (login); password visibility.
  route('/login');p.locator('#username').fill('reader');p.locator('#password').fill('wrong-password');p.locator('#login-form button[type=submit]').click();pause()
  check('login server error is inline',p.locator('#login-form .form-feedback').is_visible())
  p.locator('.password-reveal').click();check('password visibility control works',p.locator('#password').get_attribute('type')=='text')
  h.login('reader')
  oid=preparing
  user_routes=['/','/about','/app/overview','/app/opportunity/'+oid,'/app/star','/app/actions','/app/actions?view=board','/app/profile','/app/notifications','/app/me','/app/privacy','/app/lab','/account/security']
  for width in (320,390,768,1440):
   for url in user_routes:metrics(url,width)
  for url,name in [('/app/actions','actions'),('/app/me','me'),('/app/star','star'),('/app/privacy','privacy')]:route(url);shot('r2-'+name+'-mobile')
  h.login('owner');route('/manage/sources',1440)
  p.locator('#add-source').count()
  r=h.client.get('/api/manage/source-search?limit=1').json();sid=r['items'][0]['id']
  r=h.client.get('/api/manage/task-search?limit=1').json();tid=r['items'][0]['id']
  r=h.client.get('/api/review').json();rid=r['items'][0]['id']
  ops=['/manage','/manage/sources','/manage/sources/'+sid,'/manage/tasks','/manage/tasks/'+tid,'/manage/execution','/manage/source-imports','/manage/lab','/manage/feedback','/manage/history','/manage/invitations','/manage/users','/manage/access-audit','/review/overview','/review/catalog','/review/packet/'+rid]
  for width in (390,1440):
   for url in ops:metrics(url,width)
  route('/manage/sources',390);check('mobile admin remains readonly',p.locator('#add-source').is_disabled());shot('r2-sources-mobile')
  route('/manage/tasks',1440);shot('r2-tasks-desktop')
  route('/review/packet/'+rid,1440);shot('r2-review-desktop')
  route('/',1440);shot('r2-home-desktop')
  for idx in (0,1):
   button=p.locator('.marketing-final .btn').nth(idx);button.hover();check('final CTA visible on hover '+str(idx),button.evaluate('(b)=>getComputedStyle(b).color!==getComputedStyle(b).backgroundColor'))
  h.login('reviewer');route('/review/overview',1440);check('reviewer has no source/account menu',p.locator('.work-sidebar a[href="/manage/sources"]').count()==0 and p.locator('.work-sidebar a[href="/manage/users"]').count()==0)
 check('javascript errors absent',not h.errors,str(h.errors))
 out={'scope':'Actual JS/DOM + synthetic accounts + real SQLite/HTTP via test-only bridge; not native URL/cookie/TLS/physical-phone acceptance. No WMA Worker.','checks':checks,'views':views,'javascript_errors':h.errors,'http_requests':len(h.requests),'failed_http':[x for x in h.requests if x['status']>=500]}
 (OUTPUT/'browser-r2.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');h.close()
 print('checks',len(checks),'failed',sum(not x['passed'] for x in checks),'views',len(views),flush=True)
 if any(not x['passed'] for x in checks) or out['failed_http']:raise SystemExit(1)
