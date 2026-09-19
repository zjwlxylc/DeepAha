"""Offline DOM verification, not browser HTTP or live Cloud Library certification.

Managed Chromium forbids loopback navigation here. The application UI is loaded
as local DOM bytes on about:blank. Fetch and download are explicit test doubles
calling only our local Python methods; no network forwarding occurs.
"""
import argparse,base64,json,sys,tempfile,time,zipfile
from pathlib import Path
from urllib.parse import urlsplit,parse_qs,unquote
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deepaha_importer.workbench import Application,WEB
from deepaha_importer.research.library import ResearchLibraryPull
from deepaha_importer.research.workspace import _dumps
from deepaha_importer.errors import ImporterError
from playwright.sync_api import sync_playwright

p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
results={'mode':'OFFLINE_DOM_FETCH_DOWNLOAD_STORAGE_STUBBED','http_browser':'ADMINISTRATOR_BLOCKED_NOT_BYPASSED','cloud_library':'NOT_TESTED','initial_session':'ISOLATED_FIXTURE_RECONSTRUCTED_FROM_USER_EXPORT'};errors=[]
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp);app=Application(root)
 with zipfile.ZipFile(args.input) as z:
  a=json.loads(z.read('Audit.json'));d=json.loads(z.read('Decisions.json'))
  raw=z.read('originals/0001/WB-scout.zip');(root/'WB-scout.zip').write_bytes(raw)
 s=app.workspace.create([root/'WB-scout.zip']);s.update(analysis=a,decisions=d['decisions'],events=d['events'],revision=d['revision'])
 with app.workspace.connect() as con:con.execute('UPDATE review_sessions SET revision=?,payload=? WHERE id=?',(s['revision'],_dumps(s),s['id']))
 list_calls=0
 def transport(req):
  global list_calls
  parsed=urlsplit(req['path']);path=parsed.path;q=parse_qs(parsed.query)
  if parsed.netloc or parsed.scheme:raise ValueError('No network allowed in test transport')
  body=json.loads(req.get('body') or '{}') if path!='/api/upload' else None
  try:
   if path=='/api/sessions':r=app.workspace.list()
   elif path=='/api/session':r=app.session_summary(q['id'][0])
   elif path=='/api/config':
    from dataclasses import asdict
    r={'codex':asdict(app.library_config())}
   elif path=='/api/library/list':
    list_calls+=1
    if list_calls==1:
     def waiting(cancel,job):
      job['progress']='3/3 目录响应等待测试（合成场景）'
      while not cancel.wait(.03):pass
      job['diagnostic']={'schema_version':'deepaha.library-diagnostic.v1','test_fixture':True,'status':'CANCELLED','error_code':'LIBRARY_CANCELLED'}
      raise ImporterError('LIBRARY_CANCELLED','已取消资料库获取，原审核不变。')
     r=app.job(waiting)
    else:
     bridge=ResearchLibraryPull(app.library_config(),root)
     def real_missing(cancel,job):
      try:return bridge.connect_and_list(body['folder_path'],cancel=cancel,progress=lambda text:job.update(progress=text))
      finally:job['diagnostic']=bridge.last_diagnostic
     r=app.job(real_missing)
   elif path=='/api/job':r={k:v for k,v in app.jobs[q['id'][0]].items() if k!='cancel'}
   elif path=='/api/cancel':app.jobs[body['job_id']]['cancel'].set();r={'status':'CANCEL_REQUESTED'}
   elif path=='/api/library/diagnostic':r=app.jobs[q['job_id'][0]]['diagnostic'];results['diagnostic_download_requested']=True
   elif path=='/api/upload':r=app.add_upload(unquote(req['name']),base64.b64decode(req['raw']))
   else:raise ValueError('Unexpected local route '+path)
   return {'status':200,'data':r}
  except ImporterError as e:return {'status':e.status,'data':e.as_dict()}
 try:
  with sync_playwright() as pw:
   b=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);page=b.new_page(viewport={'width':1440,'height':1000})
   page.on('pageerror',lambda e:errors.append(str(e)));page.expose_function('__localTest',transport)
   html=(WEB/'index.html').read_text().replace('<link rel="stylesheet" href="/style.css">','').replace('<script defer src="/app.js"></script>','')
   page.set_content(html);page.add_style_tag(content=(WEB/'style.css').read_text())
   page.evaluate('''() => {
    for (const n of ['localStorage','sessionStorage']) {const v=new Map();Object.defineProperty(window,n,{value:{getItem:k=>v.get(k)||null,setItem:(k,x)=>v.set(k,String(x))}});}
    window.fetch=async(path,o={})=>{const req={path,body:o.body||null};if(o.body instanceof Blob){const b=new Uint8Array(await o.body.arrayBuffer());let s='';for(let i=0;i<b.length;i+=8192)s+=String.fromCharCode(...b.subarray(i,i+8192));req.raw=btoa(s);req.name=o.headers['X-File-Name'];req.body=null;}const r=await __localTest(req);return new Response(JSON.stringify(r.data),{status:r.status,headers:{'Content-Type':'application/json'}});};
    HTMLAnchorElement.prototype.click=function(){if(this.download){window.__download=this.download;return;}throw Error('Unexpected navigation in offline test');};
   }''')
   page.add_script_tag(content=(WEB/'app.js').read_text())
   page.get_by_role('heading',name='本次来源都已处理').wait_for();assert '58 次操作' in page.locator('#review-subtitle').inner_text()
   results['r58_restored_complete_state']='PASS';page.screenshot(path=str(args.output/'review-r58-completed.png'),full_page=True)
   page.get_by_role('button',name='查看已处理来源',exact=True).click();assert page.locator('.source-row').count()==52
   results['all_52_decisions_accessible']='PASS';page.locator('#library-open').click();page.locator('#library-dialog').wait_for(state='visible')
   page.locator('#library-list-button').click();page.wait_for_function('document.getElementById("library-progress-text").textContent.includes("目录响应")')
   assert page.locator('#library-list-button').is_disabled();assert list_calls==1
   page.locator('#library-cancel').focus();assert page.evaluate('document.activeElement.id')=='library-cancel'
   page.screenshot(path=str(args.output/'library-progress-cancel-desktop.png'),full_page=True)
   page.set_viewport_size({'width':390,'height':844});page.locator('#library-cancel').scroll_into_view_if_needed()
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
   page.screenshot(path=str(args.output/'library-progress-cancel-mobile.png'),full_page=True)
   page.locator('#library-cancel').click();page.wait_for_function('document.getElementById("library-status").textContent.includes("已取消")')
   assert not page.locator('#library-progress').is_visible();assert not page.locator('#library-list-button').is_disabled()
   results['modal_cancel_focus_and_click']='PASS_DESKTOP_FOCUS_MOBILE_CLICK';results['duplicate_click_guard']='PASS'
   page.set_viewport_size({'width':1440,'height':1000})
   page.locator('#library-diagnostic').click();page.wait_for_function('window.__download==="DeepAha_Library_Diagnostic.json"')
   page.locator('#library-list-button').click();page.wait_for_function('document.getElementById("library-status").textContent.includes("没有找到")')
   results['real_environment_missing_cli_handled']='PASS';assert not page.locator('#library-progress').is_visible()
   page.screenshot(path=str(args.output/'library-blocked-desktop.png'),full_page=True)
   page.set_viewport_size({'width':390,'height':844})
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
   assert page.evaluate('document.getElementById("library-dialog").scrollWidth<=document.getElementById("library-dialog").clientWidth')
   page.locator('#library-diagnostic').scroll_into_view_if_needed();page.screenshot(path=str(args.output/'library-blocked-mobile.png'),full_page=True)
   results['mobile_dialog_no_horizontal_overflow']='PASS'
   page.locator('#library-local-files').click();assert not page.locator('#library-dialog').is_visible()
   page.locator('#file-input').set_input_files(str(root/'WB-scout.zip'));page.wait_for_function('document.querySelectorAll(".upload-item").length===1')
   results['manual_file_input_preserved']='PASS';assert app.workspace.get(s['id'])['decisions']==d['decisions']
   results['original_review_decisions_unchanged']='PASS';results['page_errors']=errors;assert not errors,errors;b.close()
 finally:app.close()
(args.output/'dialog_validation.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n');print(json.dumps(results,ensure_ascii=False,indent=2))
