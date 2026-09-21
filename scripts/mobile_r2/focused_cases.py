"""Focused regression scenarios: edit loss, toast clipping and source picker state."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experience'))
from browser_harness import Harness,OUTPUT
from playwright.sync_api import sync_playwright
checks=[]
def ck(name,value,detail=''):
 checks.append(dict(name=name,passed=bool(value),detail=detail));print(name,value,flush=True)
with sync_playwright() as pw:
 h=Harness(pw,width=390);p=h.page
 def wait():p.wait_for_timeout(400);p.locator("body:not(.route-loading)").wait_for(state="attached")
 h.login('reader');h.go('/app/actions');wait();p.locator('.preparation-open').first.click();wait()
 p.locator('#item-text').fill('test row one');p.locator('#dialog button[type=submit]').click();wait()
 p.locator('#item-text').fill('test row two');p.locator('#dialog button[type=submit]').click();wait()
 p.locator('.item-edit').first.click();p.locator('#edit-preparation').fill('unfinished editing must survive')
 p.locator('.item-toggle').last.click();wait()
 ck('editing another item cannot discard unsaved draft',p.locator('#edit-preparation').count()==1)
 if p.locator('#edit-preparation').count():ck('inline draft contents retained',p.locator('#edit-preparation').input_value()=='unfinished editing must survive');p.locator('.cancel-edit').click();wait()
 p.locator('#item-text').fill('next item');p.locator('#dialog button[type=submit]').click();wait()
 rect=p.locator('#toast').evaluate('(n)=>{const r=n.getBoundingClientRect();return {x:r.x,right:r.right,w:innerWidth}}')
 ck('success message fits viewport',rect['x']>=0 and rect['right']<=rect['w'],str(rect))
 p.keyboard.press('Escape');wait();h.login('owner');p.set_viewport_size({'width':1440,'height':960})
 h.go('/manage/sources?q=研究&health=NEVER');wait();p.locator('.record-title').first.click();wait()
 p.locator('#main-content>a[data-nav]').click();wait();ck('source return keeps filters',p.locator('#source-filter [name=q]').input_value()=='研究' and p.locator('#source-filter [name=health]').input_value()=='NEVER')
 h.go('/manage/tasks?status=QUEUED');wait();p.locator('.record-title').first.click();wait();p.locator('#main-content>a[data-nav]').click();wait()
 ck('task return keeps status','status=QUEUED' in p.locator('.action-filters a.active').get_attribute('href'))
 p.locator('.new-task').click();wait();p.locator('#source-query').fill('第120号唯一');p.locator('#source-search-button').click();wait()
 choices=p.locator('#source-choice option').evaluate_all('(a)=>a.filter(x=>x.value).map(x=>x.value)');ck('remote search reaches source outside first page',len(choices)==1)
 p.locator('#source-choice').select_option(choices[0]);wait();autourl=p.locator('#task-url').input_value();ck('selected source prefills task URL',autourl.startswith('https://source119.'))
 p.locator('#source-choice').select_option('');ck('clearing selection clears only auto URL',p.locator('#task-url').input_value()=='')
 p.locator('#source-choice').select_option(choices[0]);p.locator('#task-url').fill('https://source119.example.org/specific');p.locator('#source-choice').select_option('');ck('clearing source does not erase user URL',p.locator('#task-url').input_value().endswith('/specific'))
 p.keyboard.press('Escape');wait()
 if p.locator('.dialog-discard-confirm').is_visible():p.locator('.discard-editing').click();wait()
 h.go('/review/overview?q=青年&status=PENDING');wait()
 approved=p.locator('.table-controls a.chip').nth(1).get_attribute('href')
 ck('review status switch retains search','q=' in approved)
 h.go('/review/catalog?kind=RESEARCH_PROGRAM&status=CURRENT');wait()
 ck('catalog view switch retains filters',all('kind=RESEARCH_PROGRAM' in a for a in p.locator('.chips a').evaluate_all('(n)=>n.map(x=>x.getAttribute("href"))')))
 h.login('reader');p.set_viewport_size({'width':390,'height':844});h.go('/app/profile?focus=major');wait();p.locator('#major').fill('erase-this-unsaved-draft')
 # Direct harness routechange emulates native browser Back: no in-app go confirmation.
 h.go('/app/privacy');wait();p.locator('#erase-data').click();p.locator('#dialog input[name=confirm]').fill('确认清除');p.locator('#dialog button[type=submit]').click();wait()
 h.go('/app/profile');wait();ck('erasing personal data also clears private in-memory drafts',p.locator('#major').input_value()=='')
 ck('no unexpected JS errors',not h.errors,str(h.errors));h.close()
(OUTPUT/'focused.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
raise SystemExit(int(any(not c['passed'] for c in checks)))
