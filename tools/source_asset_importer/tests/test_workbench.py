import importlib.util,json,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('deepaha_importer.workbench'),'缺少回环工作台')
        from deepaha_importer.workbench import create_server
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.server=create_server(Path(self.t.name),port=0);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'
        self.addCleanup(self.close)
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join(5);self.server.app.close()
    def request(self,path,token=True,body=None,headers=None):
        h={'X-DeepAha-Session':self.server.app.token} if token else {}
        h.update(headers or {})
        raw=json.dumps(body).encode() if body is not None else None
        if raw is not None:h['Content-Type']='application/json'
        req=urllib.request.Request(self.base+path,data=raw,headers=h)
        try:
            with urllib.request.urlopen(req,timeout=5) as r:return r.status,r.read(),r.headers
        except urllib.error.HTTPError as e:return e.code,e.read(),e.headers
    def test_public_shell_but_no_public_session_data(self):
        code,body,h=self.request('/',False);self.assertEqual(code,200);self.assertIn('Content-Security-Policy',h)
        self.assertEqual(self.request('/api/sessions',False)[0],403)
    def test_cross_origin_blocked(self):self.assertEqual(self.request('/api/sessions',headers={'Origin':'https://evil.example'})[0],403)
    def test_rebinding_host_blocked(self):self.assertEqual(self.request('/api/sessions',headers={'Host':'evil.example'})[0],403)
    def test_upload_path_traversal_blocked(self):
        req=urllib.request.Request(self.base+'/api/upload',data=b'{}',headers={'X-DeepAha-Session':self.server.app.token,'X-File-Name':'../evil.json'})
        with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(req)
    def test_download_does_not_read_arbitrary_path(self):self.assertNotEqual(self.request('/api/download?file=../../etc/passwd')[0],200)
    def test_api_no_production_commit_route(self):self.assertEqual(self.request('/api/commit',body={})[0],404)
    def test_no_remote_ui_resources(self):
        code,body,_=self.request('/app.js',False);self.assertEqual(code,200);self.assertNotIn(b'innerHTML',body)
    def test_cli_exposes_workbench(self):
        from deepaha_importer.cli import parser
        p=parser()
        self.assertIn('workbench',next(a for a in p._actions if hasattr(a,'choices') and isinstance(a.choices,dict)).choices)
