"""Loopback endpoints with synthetic connection failure; no cloud access."""
import json,time
from unittest.mock import patch
import test_workbench as helpers
import unittest
class LibraryHttpTests(unittest.TestCase):
 setUp=helpers.WorkbenchTests.setUp
 close=helpers.WorkbenchTests.close
 request=helpers.WorkbenchTests.request
 def test_connection_failure_is_diagnosable_and_does_not_touch_reviews(self):
  health={'status':'BLOCKED','error_code':'CODEX_NOT_FOUND','library_access':'UNVERIFIED','checks':[]}
  with patch('deepaha_importer.codex_process.CodexProcess.preflight',return_value=health):
   code,raw,_=self.request('/api/library/list',body={'folder_path':'/deepaha'});self.assertEqual(code,202)
   jid=json.loads(raw)['job_id'];status={}
   for _ in range(40):
    code,raw,_=self.request('/api/job?id='+jid);status=json.loads(raw)
    if status['status']!='RUNNING':break
    time.sleep(.025)
   self.assertEqual(status['status'],'ERROR');self.assertEqual(status['error']['code'],'CODEX_NOT_FOUND')
  code,raw,headers=self.request('/api/library/diagnostic?job_id='+jid)
  self.assertEqual(code,200);self.assertIn('attachment',headers['Content-Disposition'])
  self.assertEqual(json.loads(raw)['error_code'],'CODEX_NOT_FOUND')
  self.assertEqual(self.server.app.workspace.list(),[])
  self.assertEqual(self.request('/api/library/diagnostic?job_id='+jid,token=False)[0],403)
  self.assertEqual(self.request('/api/library/diagnostic?job_id='+jid,headers={'Origin':'https://other.example'})[0],403)
 def test_config_change_invalidates_old_catalog(self):
  self.server.app.catalogs['old']={'files':[]}
  code,_,_=self.request('/api/config',body={'codex':{'executable':'codex','profile':'','model':'','timeout_seconds':300,'allow_network_downloads':False}})
  self.assertEqual(code,200);self.assertEqual(self.server.app.catalogs,{})
 def test_unknown_diagnostic_does_not_read_arbitrary_path(self):
  self.assertEqual(self.request('/api/library/diagnostic?job_id=../../etc/passwd')[0],404)
