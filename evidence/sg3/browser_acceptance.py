from pathlib import Path
import json, tempfile
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0,str(ROOT/'backend/src'))
from deepaha.product.service import Product
from deepaha.product.api import create_app
from deepaha.product.config import Settings

EX=ROOT/'examples/sg3-currentness'
OUT=ROOT/'evidence/sg3'
SHOT=OUT/'screenshots'

def login(client,name='admin'):
    r=client.post('/api/auth/login',json={'username':name,'password':'long-password-123'})
    assert r.status_code==200,r.text
    client.headers['X-CSRF-Token']=r.json()['csrf']

def proxy(client,calls):
    def handler(route):
        req=route.request
        from urllib.parse import urlsplit
        u=urlsplit(req.url);path=u.path+('?' + u.query if u.query else '')
        headers={k:v for k,v in req.all_headers().items() if k.lower() not in {'host','content-length','connection','accept-encoding'}}
        if client.headers.get('X-CSRF-Token'):headers['X-CSRF-Token']=client.headers['X-CSRF-Token']
        res=client.request(req.method,path,headers=headers,content=req.post_data_buffer)
        calls.append({'method':req.method,'path':path,'status':res.status_code})
        out_headers={k:v for k,v in res.headers.items() if k.lower() not in {'content-length','content-encoding','transfer-encoding','connection','set-cookie'}}
        route.fulfill(status=res.status_code,headers=out_headers,body=res.content)
    return handler

def main():
    with tempfile.TemporaryDirectory(prefix='deepaha-sg3-') as td:
        td=Path(td);p=Product('sqlite:///'+str(td/'app.db'),td/'objects');p.initialize()
        p.create_account('admin','long-password-123',['user','reviewer','operator'])
        source=p.add_source('海湾研究中心（虚构）','https://research.example.org/',actor='admin')
        first=p.ingest(source['id'],(EX/'01_initial.zip').read_bytes(),actor='admin')
        p.decide(first['id'],'APPROVE',first['preview_hash'],'','sg3-browser-v1',actor='admin')
        cards={x['code']:x for x in p.catalog(limit=50)['items']}
        a01,a02=cards['A01'],cards['A02']
        p.set_action(a01['id'],'SAVED',actor='admin');p.set_action(a02['id'],'SAVED',actor='admin')
        p.set_reminder(a01['id'],actor='admin');p.set_reminder(a02['id'],actor='admin')
        pending=p.ingest(source['id'],(EX/'02_deadline_extension_A01.zip').read_bytes(),actor='admin')
        after={x['code']:x for x in p.catalog(limit=50)['items']}
        assert after['A01']['status']=='UPDATE_PENDING' and after['A01']['deadline'] is None
        assert after['A02']['status']=='CURRENT' and after['A02']['deadline']=='2026-11-20'
        app=create_app(Settings(database_url=p.database_url,data_dir=td,public_catalog=True,allowed_hosts=['testserver']),product=p)
        calls=[];errors=[]
        with TestClient(app) as client:
            login(client)
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
                ctx=browser.new_context(viewport={'width':1440,'height':980})
                page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                page.route('**/*',proxy(client,calls))
                page.goto('http://deepaha.test/review/packet/'+pending['id'],wait_until='networkidle')
                text=page.locator('body').inner_text()
                assert '变更范围' in text and '智能制造工程助理' in text and '定向复查' in text
                page.screenshot(path=str(SHOT/'01_review_precise_change.png'),full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                page.goto('http://deepaha.test/app/opportunity/'+a01['id'],wait_until='networkidle')
                text=page.locator('body').inner_text()
                assert '有新的官方变化等待收录' in text and '更新待收录' in text
                page.screenshot(path=str(SHOT/'02_a01_pending_mobile.png'),full_page=True)
                page.goto('http://deepaha.test/app/opportunity/'+a02['id'],wait_until='networkidle')
                assert '更新待收录' not in page.locator('body').inner_text()
                browser.close()
            decision=p.decide(pending['id'],'APPROVE',pending['preview_hash'],'','sg3-browser-v2',actor='admin')
            assert p.detail(a01['id'])['deadline']=='2026-12-05'
            history=p.target_history(a01['id']);assert len(history['versions'])>=2
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
                ctx=browser.new_context(viewport={'width':390,'height':844})
                page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                page.route('**/*',proxy(client,calls))
                page.goto('http://deepaha.test/app/opportunity/'+a01['id'],wait_until='networkidle')
                text=page.locator('body').inner_text()
                assert '2026-12-05' in text and '版本记录' in text and '2 个版本' in text
                page.screenshot(path=str(SHOT/'03_a01_accepted_history_mobile.png'),full_page=True)
                browser.close()
        assert not errors,errors
        data={
          'transport':'EXPLICIT_TEST_HTTP_BRIDGE','native_browser_network':'NOT_USED',
          'database':'ISOLATED_FICTIONAL_SG3_EXAMPLES','checks':[
            'A01_only_update_pending','A02_sibling_remains_current','review_precise_change_scope',
            'A01_pending_mobile_warning','A01_old_deadline_not_actionable','approved_new_deadline',
            'target_history_visible','no_page_errors'],
          'initial_targets':{'A01':a01['id'],'A02':a02['id']},
          'pending_revision':pending['id'],'approved_receipt':decision['id'],
          'http_calls':calls,'page_errors':errors,
        }
        (OUT/'browser_acceptance.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(data,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
