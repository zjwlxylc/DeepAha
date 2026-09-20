from browser_harness import Harness,ROOT,OUTPUT,TRANSPORT
from playwright.sync_api import sync_playwright
import json
results=[];checks=[]
with sync_playwright() as p:
 h=Harness(p);page=h.page
 def record(label,fn):
  try:fn();checks.append({'test':label,'passed':True})
  except Exception as e:checks.append({'test':label,'passed':False,'error':str(e)[:450]})
 def assert_that(v,msg):
  if not v:raise AssertionError(msg)
 def view(route,width,save=None):
  page.set_viewport_size({'width':width,'height':844 if width<700 else 960});h.go(route)
  metrics=page.evaluate('''()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,h1:document.querySelectorAll('h1').length,title:document.querySelector('h1')?.textContent,overflow:[...document.querySelectorAll('body *')].filter(x=>x.getBoundingClientRect().right>innerWidth+1&&getComputedStyle(x).position!=='fixed'&&!x.closest('.work-table-wrap')).slice(0,8).map(x=>x.className)})''')
  results.append({'route':route,**metrics});
  if save:h.screenshot(save)
 # Public + retained brand hover
 for w in (1440,390,320):view('/',w,'home-'+str(w)+'.png')
 page.set_viewport_size({'width':1440,'height':960});h.go('/')
 for index in (0,1):
  b=page.locator('.marketing-final .btn').nth(index);b.hover();checks.append({'test':'final-button-hover-'+str(index),'computed':b.evaluate('(b)=>({text:getComputedStyle(b).color,background:getComputedStyle(b).backgroundColor,width:b.getBoundingClientRect().width,scroll:b.scrollWidth})')})
 # Actual login/PATCH flow (HTTP in isolated service, no real accounts)
 h.login('reader');h.go('/app/profile?focus=team_size')
 page.locator('#team_size').fill('4');page.set_viewport_size({'width':320,'height':844});page.set_viewport_size({'width':1440,'height':960})
 record('resize-preserves-draft',lambda:assert_that(page.locator('#team_size').input_value()=='4','Draft lost on resize'))
 page.locator('#profile-form button[type=submit]').click();page.wait_for_timeout(350)
 profile=h.client.get('/api/me/profile-state').json();record('profile-patch-preserves-other-fields',lambda:assert_that(profile['profile'].get('team_size')==4 and profile['profile'].get('certificates')==['CET6'] and profile['profile'].get('notification_enabled') is False,'PATCH lost fields'))
 # Concurrent version change: preserve user input and require explicit reconciliation.
 page.locator('#team_size').fill('5')
 csrf=h.client.cookies.get('deepaha_csrf')
 external=h.client.patch('/api/me/profile',headers={'X-CSRF-Token':csrf},json={'expected_version':profile['version'],'changes':{'cities':['杭州']}})
 page.locator('#profile-form button[type=submit]').click();page.wait_for_timeout(350)
 record('profile-conflict-dialog-and-preserved-draft',lambda:assert_that(page.locator('#dialog').is_visible() and page.locator('#team_size').input_value()=='5','Conflict must preserve draft'))
 if page.locator('#dialog').is_visible():page.locator('#dialog button[type=submit]').click();page.wait_for_timeout(350)
 after=h.client.get('/api/me/profile-state').json()['profile'];record('profile-explicit-merge-keeps-external-change',lambda:assert_that(after.get('team_size')==5 and after.get('cities')==['杭州'],'Merge did not preserve external field'))
 # Catalog filter roundtrip and detail preparation
 catalog=h.client.get('/api/catalog').json();oid=catalog['items'][0]['id']
 h.go('/app/overview?region=宁波&q=研究&kind=RESEARCH_PROGRAM');page.wait_for_timeout(200)
 if page.locator('.op-card a[data-nav]').count():
  page.locator('.op-card a[data-nav]').first.click();page.wait_for_timeout(200);page.locator('#main-content>a[data-nav]').first.click();page.wait_for_timeout(150)
  record('catalog-return-filters',lambda:assert_that('region=' in page.evaluate('window.__qaLocation?.search || location.search') and 'q=' in page.evaluate('window.__qaLocation?.search || location.search'),'Filters lost'))
 h.go('/app/actions');b=page.locator('.preparation-open').first;b.focus();b.click();page.wait_for_timeout(250)
 page.locator('#item-text').fill('QA：整理作品集');page.locator('#dialog button[type=submit]').click();page.wait_for_timeout(250)
 record('preparation-persists',lambda:assert_that(any(x['text']=='QA：整理作品集' for x in h.client.get('/api/me/actions/'+oid+'/items').json()['items']),'Item did not persist'))
 b=page.locator('.preparation-open').first;b.focus();b.click();page.wait_for_timeout(250)
 for key in ('Tab','Shift+Tab'):
  for _ in range(10):
   page.keyboard.press(key)
   record('dialog-focus-contained-'+key,lambda:assert_that(page.evaluate('document.querySelector("#dialog").contains(document.activeElement)'), 'Keyboard focus left dialog'))
 page.keyboard.press('Escape');page.wait_for_timeout(100)
 record('dialog-focus-return',lambda:assert_that(b.evaluate('(b)=>document.activeElement===b'),'Focus did not return'))
 public_routes=['/about','/app/overview','/app/opportunity/'+oid,'/app/star','/app/actions','/app/actions?view=list','/app/profile','/app/notifications','/app/me','/app/privacy','/app/lab','/account/security']
 for width in (1440,390,320):
  for route in public_routes:view(route,width,('user-'+route.split('/')[-1].split('?')[0]+'-'+str(width)+'.png') if width in (1440,390) else None)
 h.login('owner');page.set_viewport_size({'width':1440,'height':960})
 h.go('/manage/tasks');page.locator('.new-task').click();page.wait_for_timeout(300);page.locator('#source-query').fill('第120号');page.locator('#source-search-button').click();page.wait_for_timeout(200)
 record('remote-selector-finds-source-120',lambda:assert_that('第120号' in page.locator('#source-choice').inner_text(),'Source beyond50 missing'))
 page.keyboard.press('Escape');page.wait_for_timeout(80)
 sources=h.client.get('/api/manage/source-search?q=第120号').json();sid=sources['items'][0]['id']
 tasks=h.client.get('/api/manage/task-search').json();tid=tasks['items'][0]['id']
 review=h.client.get('/api/review').json();revs=(review.get('items',[]) if isinstance(review,dict) else review)

 op_routes=['/manage','/manage/sources','/manage/sources/'+sid,'/manage/tasks','/manage/tasks/'+tid,'/manage/execution','/manage/source-imports','/manage/lab','/manage/feedback','/manage/history','/manage/invitations','/manage/users','/manage/access-audit','/review/overview','/review/catalog']
 if revs:op_routes.append('/review/packet/'+revs[0]['id'])
 for width in (1440,390,320):
  for route in op_routes:view(route,width,('ops-'+route.split('/')[-1]+'-'+str(width)+'.png') if width in (1440,390) else None)
 page.set_viewport_size({'width':390,'height':844});h.go('/manage/sources')
 record('mobile-readonly-sources-visible',lambda:assert_that(page.locator('#main-content').is_visible() and page.locator('#add-source').is_disabled(),'Readonly workspace not available'))
 record('mobile-write-blocked',lambda:assert_that(page.locator('.source-toggle').first.is_disabled(),'Write action not disabled'))
 record('javascript-errors',lambda:assert_that(not h.errors,repr(h.errors)))
 out={'scope':('Native Chromium navigation + actual local HTTP, synthetic database; not production HTTPS or a human test.' if TRANSPORT=='native' else 'Actual JS/DOM, test-only virtual location + real isolated HTTP bridge. Native navigation blocked by runtime policy. Not browser-cookie or production HTTPS validation.'), 'transport':TRANSPORT,'pages':results,'checks':checks,'javascript_errors':h.errors,'request_count':len(h.requests),'unexpected_http':[r for r in h.requests if r['status']>=500]}
 (OUTPUT/'browser-full-final.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
 print('pages',len(results),'overflow',[(r['route'],r['width'],r['scroll']) for r in results if r['scroll']>r['width']+1]);print('failures',[x for x in checks if x.get('passed') is False]);print('h1 errors',[r for r in results if r['h1']!=1]);print('JS',h.errors)
 h.close()
 if any(x.get('passed') is False for x in checks) or any(r['scroll']>r['width']+1 or r['h1']!=1 for r in results) or out['unexpected_http']:raise SystemExit(1)
