"""Synthetic process/connector fixtures; never proof of a user's Library access."""
import json, os, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch
from deepaha_importer.codex_process import CodexProcess, CodexLibraryConfig
from deepaha_importer.errors import ImporterError

class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(); self.addCleanup(self.t.cleanup); self.root=Path(self.t.name)
    def process(self):
        return CodexProcess(CodexLibraryConfig(executable='codex'))
    def test_preflight_missing_binary_is_actionable_not_model_call(self):
        p=self.process(); self.assertTrue(hasattr(p,'preflight'),'缺少独立连接检查')
        with patch('deepaha_importer.codex_process._executable_prefix',side_effect=ImporterError('CODEX_NOT_FOUND','not found')):
            result=p.preflight(threading.Event())
        self.assertEqual(result['status'],'BLOCKED'); self.assertEqual(result['error_code'],'CODEX_NOT_FOUND')
        self.assertEqual(result['library_access'],'UNVERIFIED')
    def test_preflight_only_cli_readiness_not_library_readiness(self):
        p=self.process(); self.assertTrue(hasattr(p,'preflight'),'缺少独立连接检查')
        replies=[(0,b'codex-cli 1.0.0'),(0,b'--json --output-schema --output-last-message --skip-git-repo-check --sandbox --ephemeral'),(0,b'Logged in using ChatGPT person@example.com'),(0,b'apps stable true')]
        with patch('deepaha_importer.codex_process._executable_prefix',return_value=['codex']),patch.object(p,'_metadata_command',side_effect=replies):
            result=p.preflight(threading.Event())
        self.assertEqual(result['status'],'CODEX_READY_LIBRARY_UNVERIFIED')
        self.assertEqual(result['auth_mode'],'CHATGPT')
        self.assertNotIn('person@example.com',json.dumps(result));self.assertEqual(result['library_access'],'UNVERIFIED')
    def test_old_cli_rejected_before_exec(self):
        p=self.process(); self.assertTrue(hasattr(p,'preflight'),'缺少独立连接检查')
        with patch('deepaha_importer.codex_process._executable_prefix',return_value=['codex']),patch.object(p,'_metadata_command',side_effect=[(0,b'codex 0.1'),(0,b'--json')]):
            result=p.preflight(threading.Event())
        self.assertEqual(result['error_code'],'CODEX_FLAGS_UNSUPPORTED')
    def test_api_key_is_not_misdiagnosed_as_no_mcp_access(self):
        p=self.process(); self.assertTrue(hasattr(p,'preflight'),'缺少独立连接检查')
        replies=[(0,b'codex-cli 1'),(0,b'--json --output-schema --output-last-message --skip-git-repo-check --sandbox'),(0,b'Logged in using an API key sk-SECRET'),(0,b'apps stable true')]
        with patch('deepaha_importer.codex_process._executable_prefix',return_value=['codex']),patch.object(p,'_metadata_command',side_effect=replies):
            result=p.preflight(threading.Event())
        self.assertEqual(result['status'],'CODEX_READY_LIBRARY_UNVERIFIED');self.assertEqual(result['auth_mode'],'API_KEY')
        self.assertNotIn('SECRET',json.dumps(result))
    def test_cancel_preflight_no_launch(self):
        p=self.process(); self.assertTrue(hasattr(p,'preflight'),'缺少独立连接检查'); c=threading.Event();c.set()
        with patch('deepaha_importer.codex_process.subprocess.Popen') as launch:
            with self.assertRaises(ImporterError):p.preflight(c)
            launch.assert_not_called()
    def test_result_failure_message_does_not_leak_secrets(self):
        from deepaha_importer.research.library import ResearchLibraryPull,PROTOCOL
        b=ResearchLibraryPull(CodexLibraryConfig(),self.root)
        def fake(prompt,schema,workspace,action,cancel):
            req=json.loads(prompt.split('\nREQUEST_JSON:\n')[1])
            return {'protocol':PROTOCOL,'request_id':req['request_id'],'action':action,'platform':'CHATGPT_LIBRARY','folder_path':req['folder_path'],'status':'UNAVAILABLE','message':'sk-SECRET account@example.com'},[]
        b.process.run=fake
        with self.assertRaises(ImporterError) as e:b.list_files('/deepaha')
        self.assertNotIn('SECRET',e.exception.message)
    def test_diagnostics_survive_failed_connection(self):
        from deepaha_importer.research.library import ResearchLibraryPull
        b=ResearchLibraryPull(CodexLibraryConfig(),self.root)
        self.assertTrue(hasattr(b,'connect_and_list'),'没有可持久诊断的连接流程')
        with patch.object(b.process,'preflight',return_value={'status':'BLOCKED','error_code':'CODEX_NOT_FOUND','library_access':'UNVERIFIED','checks':[]}):
            with self.assertRaises(ImporterError):b.connect_and_list('/deepaha')
        ds=list((self.root/'library_diagnostics').glob('*.json'));self.assertEqual(len(ds),1)
        self.assertEqual(json.loads(ds[0].read_text())['error_code'],'CODEX_NOT_FOUND')
    def test_success_does_not_certify_download_before_bytes(self):
        from deepaha_importer.research.library import ResearchLibraryPull
        b=ResearchLibraryPull(CodexLibraryConfig(),self.root)
        self.assertTrue(hasattr(b,'connect_and_list'),'没有可持久诊断的连接流程')
        cat={'folder_path':'/deepaha','folder_ref':'folder_a','files':[], 'listing_complete':True,'observed_tools':[{'server':'files','tool':'list'}]}
        with patch.object(b.process,'preflight',return_value={'status':'CODEX_READY_LIBRARY_UNVERIFIED','library_access':'UNVERIFIED','checks':[]}),patch.object(b,'list_files',return_value=cat):
            out=b.connect_and_list('/deepaha')
        self.assertEqual(out['connection']['library_access'],'CATALOG_READ_OBSERVED')
        self.assertEqual(out['connection']['raw_export'],'UNVERIFIED')
    def test_invalid_folder_is_not_persisted_as_diagnostic_text(self):
        from deepaha_importer.research.library import ResearchLibraryPull
        b=ResearchLibraryPull(CodexLibraryConfig(),self.root)
        with self.assertRaises(ImporterError):b.connect_and_list('sk-private-folder-value')
        self.assertNotIn('sk-private-folder-value',json.dumps(b.last_diagnostic))
