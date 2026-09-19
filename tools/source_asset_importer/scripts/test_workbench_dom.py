"""Offline browser DOM integration test; does NOT bypass browser network policy.

The sandbox-managed Chromium disallows URL navigation. This test loads local
HTML/CSS/JS as DOM bytes on about:blank and stubs fetch/download/storage. Calls
are restricted to this application's Python methods (no network proxy). The
real HTTP security surface is tested separately in tests/test_workbench.py.
"""
import argparse,base64,json,sys,tempfile,zipfile
from pathlib import Path
from urllib.parse import urlsplit,parse_qs,unquote
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deepaha_importer.workbench import Application,WEB
from deepaha_importer.errors import ImporterError
from playwright.sync_api import sync_playwright

def main():
    p=argparse.ArgumentParser();p.add_argument('--gpt',type=Path,required=True);p.add_argument('--wb',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    results={'mode':'OFFLINE_DOM_WITH_APPLICATION_METHODS; FETCH_DOWNLOAD_STORAGE_STUBBED','direct_browser_http':'ENVIRONMENT_BLOCKED_BY_ADMINISTRATOR'};errors=[]
    with tempfile.TemporaryDirectory(prefix='deepaha-dom-test-') as tmp:
        app=Application(Path(tmp))
        def transport(req):
            parsed=urlsplit(req['path']);path=parsed.path;q=parse_qs(parsed.query)
            try:
                if path.startswith(('http:','https:')) or parsed.netloc:raise ValueError('No network proxy')
                d=json.loads(req.get('body') or '{}') if path!='/api/upload' else None
                if path=='/api/upload':r=app.add_upload(unquote(req['name']),base64.b64decode(req['raw']))
                elif path=='/api/sessions':r=app.workspace.list()
                elif path=='/api/session':r=app.session_summary(q['id'][0])
                elif path=='/api/analyze':r=app.job(lambda c,j:{'session_id':app.workspace.create(app.selected_paths(d['uploads']),d['namespace'])['id']})
                elif path=='/api/job':r={k:v for k,v in app.jobs[q['id'][0]].items() if k!='cancel'}
                elif path=='/api/source':
                    s=app.workspace.get(q['id'][0]);a=s['analysis'];g=next(g for g in a['sources'] if g['id']==q['source'][0]);names={x['id']:x['name'] for x in a['sources']}
                    r={'source':g,'issues':[x for x in a['issues'] if x.get('source_id')==g['id']], 'relations':[x|{'left_name':names[x['left']],'right_name':names[x['right']]} for x in a['relations'] if g['id'] in (x['left'],x['right'])], 'decision':s['decisions'].get(g['id']),'revision':s['revision']}
                elif path=='/api/decision':
                    s=app.workspace.decide(d['session_id'],d['source_id'],d['decision'],d['reason'],d['actor'],d['revision'],d['acknowledge_issues'],d['primary_seed']);r={'id':s['id'],'revision':s['revision']}
                elif path=='/api/undo':s=app.workspace.undo(d['session_id'],d['source_id'],d['reason'],d['actor'],d['revision']);r={'id':s['id'],'revision':s['revision']}
                elif path=='/api/export':r=app.job(lambda c,j:app.workspace.export(d['session_id'],d['revision']))
                elif path=='/api/download':
                    name=q['file'][0];assert Path(name).name==name
                    # Validate actual export locally, but do not navigate/download in managed browser.
                    with zipfile.ZipFile(app.workspace.exports/name) as z:
                        from hashlib import sha256
                        h=json.loads(z.read('ResearchHandoff.json'));assert h['submission_status']=='NOT_SUBMITTED'
                        assert h['readiness']=='UNFINISHED_REVIEW_NOT_FOR_APPROVAL'
                        m=json.loads(z.read('Manifest.json'))
                        for f in m['files']:
                            raw=z.read(f['path']);assert sha256(raw).hexdigest()==f['sha256'] and len(raw)==f['size_bytes']
                    results['export_all_member_hashes']='PASS';r={'download_transport':'STUBBED; actual archive checked in local application'}
                elif path=='/api/config':
                    from dataclasses import asdict
                    r={'codex':asdict(app.library_config())}
                else:raise ValueError('Unsupported test route '+path)
                return {'status':200,'data':r}
            except ImporterError as e:return {'status':e.status,'data':e.as_dict()}
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
                page=browser.new_page(viewport={'width':1440,'height':1080},device_scale_factor=1);page.on('pageerror',lambda e:errors.append(str(e)))
                page.expose_function('__localApplicationTestTransport',transport)
                html=(WEB/'index.html').read_text().replace('<link rel="stylesheet" href="/style.css">','').replace('<script defer src="/app.js"></script>','')
                page.set_content(html)
                page.add_style_tag(content=(WEB/'style.css').read_text())
                page.evaluate('''() => {
                  for (const name of ['sessionStorage','localStorage']) {const values=new Map();Object.defineProperty(window,name,{value:{getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,String(v))}});}
                  window.fetch=async(path,options={})=>{const req={path,method:options.method||'GET'};
                    if (options.body instanceof Blob){const bytes=new Uint8Array(await options.body.arrayBuffer());let value='';for(let i=0;i<bytes.length;i+=8192)value+=String.fromCharCode(...bytes.subarray(i,i+8192));req.raw=btoa(value);req.name=options.headers['X-File-Name'];}
                    else req.body=options.body||null;
                    const out=await window.__localApplicationTestTransport(req);return new Response(JSON.stringify(out.data),{status:out.status,headers:{'Content-Type':'application/json'}});
                  };
                  const click=HTMLAnchorElement.prototype.click;HTMLAnchorElement.prototype.click=function(){if(this.download){window.__testDownloadTriggered=this.download;return;}click.call(this);};
                }''')
                page.add_script_tag(content=(WEB/'app.js').read_text());page.wait_for_timeout(300)
                page.screenshot(path=str(args.output/'workbench-intake-desktop.png'),full_page=True)
                paths=sorted(args.gpt.glob('*_Handoff.json'))+[args.wb]
                page.locator('#file-input').set_input_files([str(p) for p in paths])
                page.wait_for_function("document.querySelectorAll('.upload-item').length===31",timeout=90000)
                page.locator('#analyze').click();page.locator('#pane-review').wait_for(state='visible',timeout=90000)
                page.wait_for_function("document.querySelectorAll('.source-row').length===89")
                results['real_asset_selection']=31;results['candidate_groups']=89
                page.locator('#producer').select_option('chatgpt-scout');page.locator('#search').fill('中国大学生在线');page.locator('.source-row').first.click()
                page.locator('#review-actor').fill('自动化界面测试（不是真人批准）');page.locator('#review-decision').select_option('DEFER');page.locator('#review-reason').fill('界面回归测试，随后撤销；不是真实资产批准。')
                page.get_by_role('button',name='保存意见',exact=True).click();page.wait_for_function("document.getElementById('review-subtitle').textContent.includes('1 次操作')")
                page.get_by_role('button',name='撤销这条意见',exact=True).click();page.wait_for_function("document.getElementById('review-subtitle').textContent.includes('2 次操作')")
                results['save_and_undo']='PASS';page.locator('#search').fill('');page.locator('#producer').select_option('all')
                page.screenshot(path=str(args.output/'workbench-review-desktop.png'),full_page=True)
                page.get_by_role('button',name='依据与附件',exact=True).click();page.get_by_role('button',name='版本记录',exact=True).click();page.get_by_role('button',name='处理意见',exact=True).click()
                results['evidence_and_version_tabs']='PASS'
                page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
                page.screenshot(path=str(args.output/'workbench-review-mobile.png'),full_page=True);results['mobile_390_no_horizontal_overflow']='PASS'
                page.get_by_role('button',name='← 返回来源列表',exact=True).click();assert not page.locator('#source-detail').is_visible()
                page.screenshot(path=str(args.output/'workbench-list-mobile.png'),full_page=True);results['mobile_back_to_list']='PASS'
                page.set_viewport_size({'width':1440,'height':1000});page.locator('.step[data-pane="export"]').click();page.locator('#export-button').click()
                page.wait_for_function('!!window.__testDownloadTriggered',timeout=90000)
                results['export_button']='PASS_APPLICATION; BROWSER_DOWNLOAD_STUBBED'
                page.screenshot(path=str(args.output/'workbench-export-desktop.png'),full_page=True)
                page.locator('#library-open').click();page.locator('#library-dialog').wait_for(state='visible');page.screenshot(path=str(args.output/'workbench-library-dialog.png'),full_page=True)
                results['library_dialog']='PASS_UI_ONLY_NO_LIVE_CODEX_CALL';browser.close()
            results['page_errors']=errors;assert not errors,errors
            (args.output/'browser_validation.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps(results,ensure_ascii=False,indent=2))
        finally:app.close()
if __name__=='__main__':main()
