import importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
class ResearchLibraryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('deepaha_importer.research.library'),'研究包资料库桥不存在')
        from deepaha_importer.research.library import ResearchLibraryPull
        from deepaha_importer.codex_process import CodexLibraryConfig
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.root=Path(self.t.name)
        self.b=ResearchLibraryPull(CodexLibraryConfig(),self.root)
    def fake(self,success_tools=True,wrong_hash=False):
        from deepaha_importer.research.library import PROTOCOL
        from deepaha_importer.contract import digest
        def run(prompt,schema,workspace,action,cancel):
            req=json.loads(prompt.split('\nREQUEST_JSON:\n')[1]);data=b'{"hello":"original bytes"}'
            entry={'file_ref':'file_original','name':'source_Handoff.json','version':'v1','modified_at':None,'size_bytes':len(data),'sha256':digest(data)}
            transfers=[]
            if action=='fetch':
                (workspace/'payload'/'source_Handoff.json').write_bytes(data)
                transfers=[{'file_ref':'file_original','version':'v1','role':'research_package','relative_path':entry['name'],'size_bytes':len(data),'sha256':'0'*64 if wrong_hash else digest(data)}]
            result={'protocol':PROTOCOL,'request_id':req['request_id'],'action':action,'platform':'CHATGPT_LIBRARY','folder_path':req['folder_path'],'folder_ref':'folder_real','status':'OK','files':[entry] if action=='list' else [],'transfers':transfers,'listing_complete':True,'tools_used':[{'server':'files','tool':'materialize' if action=='fetch' else 'list'}],'message':''}
            return result,result['tools_used'] if success_tools else []
        self.b.process.run=Mock(side_effect=run)
    def test_app_invokes_codex_and_keeps_original_bytes(self):
        self.fake();catalog=self.b.list_files('/deepaha');result=self.b.fetch('/deepaha',catalog['folder_ref'],catalog['files'][0])
        self.assertEqual(Path(result['file_path']).read_bytes(),b'{"hello":"original bytes"}')
        self.assertEqual(result['database_submission'],'NOT_ATTEMPTED');self.assertEqual(self.b.process.run.call_count,2)
    def test_no_successful_tool_no_download_claim(self):
        from deepaha_importer.errors import ImporterError
        self.fake(success_tools=False)
        with self.assertRaises(ImporterError):self.b.list_files('/deepaha')
    def test_hash_failure_not_accepted(self):
        from deepaha_importer.errors import ImporterError
        self.fake(wrong_hash=True);cat=self.b.list_files('/deepaha')
        with self.assertRaises(ImporterError):self.b.fetch('/deepaha',cat['folder_ref'],cat['files'][0])
    def test_unrelated_folder_rejected(self):
        from deepaha_importer.errors import ImporterError
        with self.assertRaises(ImporterError):self.b.list_files('/private-other')
