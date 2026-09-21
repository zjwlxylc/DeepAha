"""DOM/JS against real local HTTP via an explicit QA transport bridge.
Native navigation is attempted first and recorded. No policy modification.
This does NOT validate native cookie/TLS/navigation/service-worker behavior.
"""
from pathlib import Path
import argparse,base64,json,socket,sys,tempfile,threading,time,uuid
import httpx,uvicorn
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from deepaha_membership.demo import create_demo


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',default='evidence/browser');parser.add_argument('--chromium',default='/usr/bin/chromium');args=parser.parse_args()
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    result={'mode':'DOM_JS_REAL_LOCAL_HTTP_QA_BRIDGE','native_navigation':'NOT_ATTEMPTED','checks':[],'errors':[],'screenshots':[]}
    static=Path(__file__).resolve().parents[1]/'src/deepaha_membership/static'
    with tempfile.TemporaryDirectory() as tmp:
        passwords={n:uuid.uuid4().hex for n in ('alice','bob','maintainer','reviewer')}
        app=create_demo(Path(tmp)/'browser.db',passwords)
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
        base=f'http://127.0.0.1:{port}'
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error'))
        thread=threading.Thread(target=server.run,daemon=True);thread.start()
        with httpx.Client(base_url=base,timeout=20) as transport:
            for _ in range(100):
                try:
                    if transport.get('/api/membership/info').status_code==200:break
                except httpx.ConnectError:time.sleep(.05)
            def bridge(path,options):
                if not str(path).startswith('/api/'):raise ValueError('QA bridge only allows app API paths')
                headers=dict(options.get('headers') or {});headers['Origin']=base
                r=transport.request(options.get('method','GET'),path,headers=headers,content=options.get('body'))
                return {'status':r.status_code,'body':r.text,'headers':dict(r.headers)}
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox'])
                page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
                page.on('pageerror',lambda e:result['errors'].append(str(e)))
                try:
                    try:page.goto(base+'/membership',timeout=4000);result['native_navigation']='AVAILABLE'
                    except Exception as e:result['native_navigation']=str(e).split('\n')[0]
                    # The blocked error page may still be navigating. Use a fresh about:blank
                    # page for permitted DOM testing; do not change browser policy.
                    page.close()
                    page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
                    page.on('pageerror',lambda e:result['errors'].append(str(e)))
                    # QA transport is explicit regardless of native-navigation availability.
                    html=(static/'index.html').read_text().replace('<link rel="stylesheet" href="/membership/style.css">','').replace('<script src="/membership/app.js" defer></script>','')
                    page.set_content(html)
                    page.add_style_tag(content=(static/'style.css').read_text())
                    page.expose_function('qaTransport',bridge)
                    page.add_script_tag(content="""
                    window.fetch=async(path,options={})=>{const r=await window.qaTransport(path,options);return new Response(r.body,{status:r.status,headers:r.headers});};
                    // about:blank is not the production HTTPS/loopback secure context.
                    if(!crypto.randomUUID)crypto.randomUUID=()=>Array.from(crypto.getRandomValues(new Uint8Array(16)),b=>b.toString(16).padStart(2,'0')).join('');
                    """)
                    page.add_script_tag(content=(static/'app.js').read_text())
                    def wait():page.wait_for_function("!document.querySelector('#content .loading')");page.wait_for_timeout(80)
                    def route(r):page.evaluate('(r)=>{location.hash=r}',r);wait()
                    def check(name,fn):fn();result['checks'].append(name)
                    def login(name):
                        route('login');page.locator('#login-form [name=username]').fill(name);page.locator('#login-form [name=password]').fill(passwords[name]);page.locator('#login-form button').click();page.wait_for_function("!document.querySelector('#login-form')");wait()
                    def submit_dialog():page.locator('#dialog-form button[type=submit]').click();page.wait_for_function("!document.querySelector('#modal').open",timeout=5000);wait()
                    def shot(name,width=1440):
                        page.set_viewport_size({'width':width,'height':1000 if width>780 else 844});page.wait_for_timeout(80)
                        overflow=page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                        assert not overflow,f'page overflow {name} {width}'
                        page.evaluate("document.querySelector('#toast').hidden=true")
                        filename=f'{name}-{width}.png';page.screenshot(path=str(out/filename),full_page=True);result['screenshots'].append(filename);result['checks'].append(f'layout:{name}:{width}')
                    wait();assert '服务方案正在准备中' in page.locator('#content').inner_text();result['checks'].append('public-draft-empty')
                    login('maintainer');assert page.locator('h1').inner_text()=='服务管理';result['checks'].append('operator-login')
                    for _ in range(3):
                        page.get_by_role('button',name='确认上架',exact=True).first.click();submit_dialog()
                    route('services');shot('services',390);shot('services',1440)
                    for width in (320,768):shot('services',width)
                    login('alice');route('services');page.get_by_role('button',name='申请 基础订阅',exact=True).click();page.locator('#dialog-form [name=accepted]').check();submit_dialog()
                    route('account');assert '待确认' in page.locator('#content').inner_text();result['checks'].append('create-order-no-grant')
                    login('maintainer');route('manage-orders');page.get_by_role('button',name='赠送试用',exact=True).click();page.locator('#dialog-form [name=reason]').fill('浏览器合成数据试用验证');page.locator('#dialog-form [name=confirm]').check();submit_dialog()
                    login('alice');route('account');assert '基础订阅' in page.locator('#content').inner_text();shot('account',390)
                    route('watches');page.get_by_role('button',name='＋ 添加跟踪主题',exact=True).click();page.locator('#dialog-form [name=name]').fill('我的品牌校招');page.locator('#dialog-form [name=q]').fill('校招');submit_dialog();assert '我的品牌校招' in page.locator('#content').inner_text();shot('watches',390)
                    route('feedback');page.get_by_role('button',name='＋ 提交网站',exact=True).click();page.locator('#dialog-form [name=name]').fill('演示机构公开招聘栏目');page.locator('#dialog-form [name=url]').fill('https://example.org/jobs');page.locator('#dialog-form [name=note]').fill('请关注品牌策划相关公开岗位 <script>window.BAD=1</script>');page.locator('#dialog-form [name=consent]').check();submit_dialog();assert page.evaluate('window.BAD===undefined');shot('feedback',390);result['checks'].append('feedback-text-not-executed')
                    login('reviewer');route('review');page.get_by_role('button',name='处理线索',exact=True).click();page.locator('#dialog-form [name=note]').fill('公开招聘栏目已核验');page.locator('#dialog-form [name=public_brief]').fill('仅检查公开栏目中的招聘机会，保存原文依据并等待整体审核');submit_dialog();assert '线索通过' in page.locator('#content').inner_text();shot('review',1440)
                    route('manage');assert '此区域仅对维护员开放' in page.locator('#content').inner_text();result['checks'].append('reviewer-no-admin-ui')
                    login('maintainer');route('manage-jobs');page.get_by_role('button',name='检查已发布主题机会',exact=True).click();page.wait_for_timeout(300)
                    login('alice');route('notices');assert '演示数据' in page.locator('#content').inner_text();shot('notices',390);result['checks'].append('topic-scan-to-real-inapp-notice')
                    login('bob');route('services');page.get_by_role('button',name='提交定制需求',exact=True).click();page.locator('#dialog-form [name=note]').fill('请为我跟踪指定公开网站的品牌岗位');page.locator('#dialog-form [name=accepted]').check();submit_dialog()
                    login('maintainer');route('manage-orders');page.get_by_role('button',name='制定报价',exact=True).click();page.locator('#dialog-form [name=amount]').fill('199.00');page.locator('#dialog-form [name=scope]').fill('核验三个公开网站，按约定周期跟踪公开招聘机会并提供站内提醒');submit_dialog();result['checks'].append('custom-request-to-quote')
                    login('bob');route('account');page.get_by_role('button',name='查看并确认报价',exact=True).click();page.locator('#dialog-form [name=agree]').check();submit_dialog();result['checks'].append('user-explicit-quote-acceptance')
                    login('maintainer');route('manage-orders');page.get_by_role('button',name='赠送试用',exact=True).click();page.locator('#dialog-form [name=reason]').fill('合成定制订阅端到端验证');page.locator('#dialog-form [name=confirm]').check();submit_dialog()
                    login('bob');route('feedback');page.get_by_role('button',name='＋ 提交网站',exact=True).click();page.locator('#dialog-form [name=name]').fill('另一个用户提交同一网站');page.locator('#dialog-form [name=url]').fill('https://example.org/jobs');page.locator('#dialog-form [name=note]').fill('我的定制公开网站需求');page.locator('#dialog-form [name=consent]').check();submit_dialog()
                    assert '<script>' not in page.locator('#content').inner_text()
                    page.get_by_role('button',name='加入定制跟踪',exact=True).click();page.wait_for_function("location.hash==='#watches'");wait();assert '演示机构公开招聘栏目' in page.locator('#content').inner_text();result['checks'].append('custom-owned-approved-site-watch')
                    login('maintainer');route('review');page.get_by_role('button',name='登记到原来源管理',exact=True).click();page.get_by_role('button',name='明确启用此来源',exact=True).wait_for();page.get_by_role('button',name='明确启用此来源',exact=True).click();page.locator('#dialog-form [name=agree]').check();submit_dialog();result['checks'].append('operator-source-adopt-and-explicit-enable')
                    route('manage-jobs');page.get_by_role('button',name='安排一轮检查',exact=True).click();page.locator('#dialog-form [name=agree]').check();submit_dialog();page.get_by_role('button',name='交接原采集任务',exact=True).click();page.get_by_role('button',name='模拟结果返回',exact=True).wait_for();page.get_by_role('button',name='模拟结果返回',exact=True).click();page.wait_for_function("document.querySelector('#content').innerText.includes('已有结果 · 等待整体审核')");result['checks'].append('site-job-queued-to-results-not-publication')
                    login('bob');route('notices');assert '网站调查结果已收到' in page.locator('#content').inner_text();shot('custom-notices',390)
                    login('maintainer')
                    for r in ('manage','manage-services','manage-orders','manage-grants','manage-jobs','manage-audit','review'):
                        route(r)
                        for width in (390,1440):shot(r,width)
                    # Test a real plan edit using visible controls, preserving old order.
                    route('manage');page.get_by_role('button',name='编辑新版本',exact=True).first.click();page.locator('#dialog-form [name=price]').fill('39.90');submit_dialog();assert '39.90' in page.locator('#content').inner_text();result['checks'].append('operator-edit-price')
                    assert result['errors']==[],result['errors']
                    result['status']='PASS'
                except Exception as e:
                    result['status']='FAIL';result['failure']=str(e);page.screenshot(path=str(out/'failure.png'),full_page=True)
                    result['visible_text']=page.locator('body').inner_text()[:12000]
                    raise
                finally:
                    (out/'browser-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');browser.close()
                    server.should_exit=True;thread.join(timeout=5)
    print(json.dumps({k:v for k,v in result.items() if k not in ('screenshots',)},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
