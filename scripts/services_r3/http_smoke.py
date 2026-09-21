#!/usr/bin/env python3
"""Real loopback TCP/HTTP smoke on a fresh synthetic database; NO WMA worker."""
import argparse,json,os,socket,subprocess,sys,tempfile,time
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[2]
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True);checks=[]
    def check(name,condition):
        checks.append({'test':name,'passed':bool(condition)})
        if not condition:raise AssertionError(name)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='deepaha-http-smoke-') as data:
        env={k:v for k,v in os.environ.items() if not k.startswith(('DEEPAHA_','WMA_'))}
        env.update(DEEPAHA_QA_DATA=data,DEEPAHA_QA_PORT=str(port),PYTHONUTF8='1',PYTHONPATH=str(ROOT/'backend/src'))
        with (out/'server.log').open('w',encoding='utf-8') as log:
            child=subprocess.Popen([sys.executable,str(ROOT/'scripts/experience/fixture_server.py')],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            try:
                with httpx.Client(base_url=f'http://127.0.0.1:{port}',trust_env=False,timeout=15) as c:
                    for _ in range(100):
                        if child.poll() is not None:raise RuntimeError('Synthetic service exited')
                        try:
                            if c.get('/health/ready').status_code==200:break
                        except httpx.HTTPError:pass
                        time.sleep(.2)
                    else:raise RuntimeError('Synthetic service not ready')
                    for route in ['/health/live','/health/ready','/','/app/overview','/review/overview','/manage/execution']:
                        check('GET '+route,c.get(route).status_code==200)
                    page=c.get('/');csp=page.headers.get('Content-Security-Policy','')
                    check('strict CSP retained',next((part.strip() for part in csp.split(";") if part.strip().startswith("script-src")),"")=="script-src 'self'")
                    for asset in ['app.js','core.js','home.js','experience.css','profile-editor.js','operations-ui.js','actions-ui.js','brand-logo.png']:
                        check('static '+asset,c.get('/product/'+asset).status_code==200)
                    check('anonymous management denied',c.get('/api/manage/source-search').status_code==401)
                    auth=c.post('/api/auth/login',json={'username':'reader','password':'test-browser-123'});check('reader login',auth.status_code==200)
                    headers={'X-CSRF-Token':auth.json()['csrf']}
                    check('reader management denied',c.get('/api/manage/task-search').status_code==403)
                    state=c.get('/api/me/profile-state').json()
                    body={'expected_version':state['version'],'changes':{'team_size':4}}
                    check('missing csrf denied',c.patch('/api/me/profile',json=body).status_code==403)
                    updated=c.patch('/api/me/profile',json=body,headers=headers);check('versioned PATCH',updated.status_code==200)
                    check('unmodified fields preserved',updated.json()['profile']['certificates']==['CET6'])
                    check('stale version rejected',c.patch('/api/me/profile',json=body,headers=headers).status_code==409)
                    oid=c.get('/api/catalog').json()['items'][0]['id']
                    item={'text':'Synthetic smoke preparation item','request_key':'http-smoke-item'}
                    added=c.post('/api/me/actions/'+oid+'/items',json=item,headers=headers);check('preparation persisted',added.status_code==200)
                    check('preparation idempotency',c.post('/api/me/actions/'+oid+'/items',json=item,headers=headers).json()['id']==added.json()['id'])
                    check('personal export includes preparation',len(c.get('/api/me/export').json()['preparation_items'])==1)
                    auth=c.post('/api/auth/login',json={'username':'owner','password':'test-browser-123'});check('operator login',auth.status_code==200)
                    check('source beyond50 discoverable',c.get('/api/manage/source-search',params={'q':'第120号'}).json()['total']==1)
                    check('operator inherits review',c.get('/api/review').status_code==200)
                    check('conservative serial',c.get('/api/manage/execution-policies').json()['items'][0]['effective_concurrent']==1)
                    # R3 new endpoints are served by the same application/session.
                    check('R3 membership current',c.get('/api/membership/info').json()['host_iteration']=='services-r3')
                    check('R3 operator service catalog',len(c.get('/api/membership/manage/plans').json())==3)
                    check('R3 drafts are not public',c.get('/api/membership/plans').json()==[])
                    check('R3 default automatic service disabled',c.get('/api/membership/runtime-status').json()['enabled'] is False)
                    check('R3 share management ready',c.get('/api/manage/sharing').status_code==200)
                    check('R3 OG initially rendered','property="og:title"' in c.get('/').text)
                    check('R3 private no OG','og:title' not in c.get('/app/profile').text)
                    share=c.get('/share')
                    check('R3 share landing clickable',share.status_code==200 and 'href="/app/overview"' in share.text)
                    check('R3 SDK CSP only public sharing','https://res.wx.qq.com' in share.headers['content-security-policy'])
                    check('R3 default wide image',c.get('/share-assets/default-wide.jpg').headers.get('content-type')=='image/jpeg')
                    check('R3 default square image',c.get('/share-assets/default-square.jpg').status_code==200)
                    check('R3 unconfigured WeChat no remote',c.get('/api/share/wechat-signature',params={'url':'https://deepaha.com/share'}).json()['enabled'] is False)
                    check('R3 no external signing',c.get('/api/share/wechat-signature',params={'url':'https://attacker.example/share'}).status_code==400)
                    # R2 release identity and dependency graph, via actual TCP/HTTP.
                    site=c.get('/api/site').json();build=site['frontend_build'];prefix='/product/_v/'+build+'/'
                    check('HTML never cached',c.get('/').headers.get('cache-control')=='no-store')
                    check('served build matches HTML',prefix+'app.js' in c.get('/').text)
                    manifest=c.get('/product/asset-release.json').json()
                    import hashlib
                    for name,digest in manifest['files'].items():
                        response=c.get(prefix+name)
                        check('versioned bytes '+name,response.status_code==200 and hashlib.sha256(response.content).hexdigest()==digest and 'immutable' in response.headers.get('cache-control',''))
                    check('old alias revalidates',c.get('/product/user.js').headers.get('cache-control')=='no-cache')
                    check('unknown build fails closed',c.get('/product/_v/mobile-r2-000000000000/app.js').status_code==404)
                    auth=c.post('/api/auth/login',json={'username':'reader','password':'test-browser-123'});headers={'X-CSRF-Token':auth.json()['csrf']}
                    action='/api/me/actions/'+oid
                    check('save state is persisted',c.get(action).json()['saved'])
                    check('preparing action update',c.put(action,json={'status':'PREPARING','note':'keep preparation note'},headers=headers).status_code==200)
                    check('save without CSRF rejected',c.post(action+'/save').status_code==403)
                    again=c.post(action+'/save',headers=headers).json()
                    check('repeat save preserves status and note',not again['created'] and again['status']=='PREPARING' and again['note']=='keep preparation note')
                    check('summary reflects real data',c.get('/api/me/summary').json()['counts']['PREPARING']==1)
                    check('summary excludes private notes','keep preparation note' not in c.get('/api/me/summary').text)
                    check('cross-origin save rejected',c.post(action+'/save',headers={**headers,'Origin':'https://untrusted.example'}).status_code==403)

            finally:
                child.terminate()
                try:child.wait(timeout=15)
                except subprocess.TimeoutExpired:child.kill();child.wait()
                result={'iteration':'mobile-r3','scope':'Fresh isolated database and actual loopback HTTP; not TLS, native Windows or live WMA. No worker started.','checks':checks,'status':'PASS' if len(checks)>=25 and all(x['passed'] for x in checks) else 'FAIL','wma_called':False}
                (out/'http-smoke.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(result['status'],len(checks),'HTTP checks');return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
