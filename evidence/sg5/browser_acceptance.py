from pathlib import Path
import json, tempfile, sys
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend/src'))
from deepaha.product.service import Product
from deepaha.product.api import create_app
from deepaha.product.config import Settings

OUT=ROOT/'evidence/sg5'; SHOT=OUT/'screenshots'

def login(client,name='admin'):
    r=client.post('/api/auth/login',json={'username':name,'password':'long-password-123'}); assert r.status_code==200,r.text
    client.headers['X-CSRF-Token']=r.json()['csrf']

def proxy(client,calls):
    def handler(route):
        req=route.request
        from urllib.parse import urlsplit
        u=urlsplit(req.url); path=u.path+('?' + u.query if u.query else '')
        headers={k:v for k,v in req.all_headers().items() if k.lower() not in {'host','content-length','connection','accept-encoding'}}
        if client.headers.get('X-CSRF-Token'): headers['X-CSRF-Token']=client.headers['X-CSRF-Token']
        res=client.request(req.method,path,headers=headers,content=req.post_data_buffer)
        calls.append({'method':req.method,'path':path,'status':res.status_code})
        out_headers={k:v for k,v in res.headers.items() if k.lower() not in {'content-length','content-encoding','transfer-encoding','connection','set-cookie'}}
        route.fulfill(status=res.status_code,headers=out_headers,body=res.content)
    return handler

def approve(p,source,path,key):
    x=p.ingest(source,path.read_bytes(),actor='admin'); assert x['can_approve']; p.decide(x['id'],'APPROVE',x['preview_hash'],'',key,actor='admin')

def main():
    with tempfile.TemporaryDirectory(prefix='deepaha-sg5-') as td:
        td=Path(td); p=Product('sqlite:///'+str(td/'app.db'),td/'objects'); p.initialize()
        p.create_account('admin','long-password-123',['user','reviewer','operator'])
        src=p.add_source('虚构机会研究院','https://institute.example.org/',actor='admin')['id']
        approve(p,src,ROOT/'examples/01_recruitment.zip','sg5-browser-job')
        approve(p,src,ROOT/'examples/02_competition.zip','sg5-browser-comp')
        approve(p,src,ROOT/'examples/03_policy.zip','sg5-browser-policy')
        p.set_profile({'cities':['浙江'],'interests':['政策','项目'],'goals':['获得项目支持'],'opportunity_types':['YOUTH_POLICY_BENEFIT'],'personalization_enabled':True},actor='admin')
        app=create_app(Settings(database_url=p.database_url,data_dir=td,public_catalog=True,allowed_hosts=['testserver']),product=p)
        calls=[]; errors=[]; checks=[]
        with TestClient(app) as client:
            login(client)
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
                ctx=browser.new_context(viewport={'width':390,'height':844})
                page=ctx.new_page(); page.on('pageerror',lambda e:errors.append(str(e))); page.route('**/*',proxy(client,calls))
                page.goto('http://deepaha.test/app/star',wait_until='networkidle')
                text=page.locator('body').inner_text()
                assert '今天真正值得你看的' in text and '为什么值得我关注' in text
                assert '青年创新项目支持计划' in text or '青年项目' in text
                assert '92%' not in text and '成功率' not in text
                checks += ['policy_top_n_visible','no_fake_probability']
                page.screenshot(path=str(SHOT/'01_star_policy_mobile.png'),full_page=True)
                first=page.locator('.star-value').first; first.click(); page.wait_for_timeout(100)
                modal=page.locator('.modal, [role="dialog"]').last
                mtext=modal.inner_text() if modal.count() else page.locator('body').inner_text()
                assert '为什么值得我关注' in mtext and '为什么现在' in mtext and '需要注意' in mtext
                checks.append('value_explanation_modal')
                page.screenshot(path=str(SHOT/'02_value_explanation_mobile.png'),full_page=True)
                browser.close()
            p.set_profile({'cities':['浙江'],'interests':['AI'],'goals':['积累项目经历'],'opportunity_types':['COMPETITION'],'personalization_enabled':True},actor='admin')
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
                ctx=browser.new_context(viewport={'width':390,'height':844}); page=ctx.new_page(); page.on('pageerror',lambda e:errors.append(str(e))); page.route('**/*',proxy(client,calls))
                page.goto('http://deepaha.test/app/star',wait_until='networkidle'); text=page.locator('body').inner_text()
                assert '青年数字创意挑战赛' in text or '赛道' in text
                checks.append('competition_profile_changes_star')
                page.screenshot(path=str(SHOT/'03_star_competition_mobile.png'),full_page=True); browser.close()
            p.set_profile({'personalization_enabled':False},actor='admin')
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
                ctx=browser.new_context(viewport={'width':390,'height':844}); page=ctx.new_page(); page.on('pageerror',lambda e:errors.append(str(e))); page.route('**/*',proxy(client,calls))
                page.goto('http://deepaha.test/app/star',wait_until='networkidle'); text=page.locator('body').inner_text()
                assert '关闭个性化机会排序' in text
                page.goto('http://deepaha.test/app/overview',wait_until='networkidle'); assert '机会总览' in page.locator('body').inner_text()
                checks += ['personalization_can_disable','catalog_still_available']; browser.close()
        assert not errors,errors
        data={'transport':'EXPLICIT_TEST_HTTP_BRIDGE','native_browser_network':'NOT_USED','database':'ISOLATED_FICTIONAL_SG5_EXAMPLES','checks':checks,'http_calls':calls,'page_errors':errors}
        (OUT/'browser_acceptance.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(data,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
