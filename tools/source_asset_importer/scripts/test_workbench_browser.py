"""Browser acceptance against real provided assets in an isolated local test store.

Requires optional playwright and an installed Chromium. This does not exercise
Codex Library permissions, Windows packaging, or a production DeepAha instance.
"""
import argparse,json,sys,tempfile,threading,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deepaha_importer.workbench import create_server
from playwright.sync_api import sync_playwright

def main():
    p=argparse.ArgumentParser();p.add_argument('--gpt',type=Path,required=True);p.add_argument('--wb',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--chromium',default='/usr/bin/chromium');args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='deepaha-ui-test-') as temporary:
        server=create_server(Path(temporary));t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
        errors=[];results={}
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox'])
                page=browser.new_page(viewport={'width':1440,'height':1080},device_scale_factor=1)
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{server.server_port}/#{server.app.token}')
                page.screenshot(path=str(args.output/'workbench-intake-desktop.png'),full_page=True)
                # Use the UI for actual upload + analysis, not a prefilled screenshot.
                paths=sorted(args.gpt.glob('*_Handoff.json'))+[args.wb]
                page.locator('#file-input').set_input_files([str(p) for p in paths])
                page.wait_for_function("document.querySelectorAll('.upload-item').length===31",timeout=90000)
                page.locator('#analyze').click();page.locator('#pane-review').wait_for(state='visible',timeout=90000)
                page.wait_for_function("document.querySelectorAll('.source-row').length===89")
                results['real_assets_ui_uploads']=31;results['candidate_groups']=89
                page.locator('#producer').select_option('chatgpt-scout')
                page.locator('#search').fill('中国大学生在线');page.locator('.source-row').first.click()
                page.locator('#review-actor').fill('自动化界面测试（不是真人批准）')
                page.locator('#review-decision').select_option('DEFER');page.locator('#review-reason').fill('界面回归：先暂缓，随后撤销；这不是实际资产接纳决定。')
                page.get_by_role('button',name='保存意见',exact=True).click()
                page.wait_for_function("document.getElementById('review-subtitle').textContent.includes('1 次操作')")
                page.get_by_role('button',name='撤销这条意见',exact=True).click()
                page.wait_for_function("document.getElementById('review-subtitle').textContent.includes('2 次操作')")
                results['save_and_undo']='PASS'
                page.locator('#search').fill('');page.locator('#producer').select_option('all')
                page.screenshot(path=str(args.output/'workbench-review-desktop.png'),full_page=True)
                page.get_by_role('button',name='依据与附件',exact=True).click();page.locator('.detail-section h3').first.wait_for()
                results['evidence_and_history_tabs']='PASS'
                page.get_by_role('button',name='版本记录',exact=True).click();page.get_by_role('button',name='处理意见',exact=True).click()
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'), 'mobile horizontal overflow'
                page.screenshot(path=str(args.output/'workbench-review-mobile.png'),full_page=True)
                results['mobile_390px_no_horizontal_overflow']='PASS'
                page.set_viewport_size({'width':1440,'height':1000})
                page.locator('.step[data-pane="export"]').click()
                with page.expect_download(timeout=90000) as event:page.locator('#export-button').click()
                download=event.value;export=Path(temporary)/'ui-export.zip';download.save_as(export)
                from hashlib import sha256
                with zipfile.ZipFile(export) as z:
                    h=json.loads(z.read('ResearchHandoff.json'));m=json.loads(z.read('Manifest.json'))
                    assert h['submission_status']=='NOT_SUBMITTED' and h['readiness']=='UNFINISHED_REVIEW_NOT_FOR_APPROVAL'
                    for f in m['files']:
                        raw=z.read(f['path']);assert len(raw)==f['size_bytes'] and sha256(raw).hexdigest()==f['sha256']
                results['browser_export_and_all_member_hashes']='PASS'
                page.screenshot(path=str(args.output/'workbench-export-desktop.png'),full_page=True)
                page.locator('#library-open').click();page.locator('#library-dialog').wait_for(state='visible')
                page.screenshot(path=str(args.output/'workbench-library-dialog.png'),full_page=True)
                results['library_dialog']='PASS_UI_ONLY_NO_LIVE_CODEX_CALL'
                browser.close()
            results['page_errors']=errors
            assert not errors,errors
            (args.output/'browser_validation.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
            print(json.dumps(results,ensure_ascii=False,indent=2))
        finally:server.shutdown();server.server_close();t.join(5);server.app.close()
if __name__=='__main__':main()
