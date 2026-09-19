import json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from deepaha_importer.research.workspace import Workspace

class PatchWorkbenchTests(unittest.TestCase):
    def test_modal_has_its_own_cancellation_and_progress(self):
        html=(Path(__file__).parents[1]/'deepaha_importer/web/index.html').read_text()
        dialog=html.split('<dialog id="library-dialog"')[1].split('</dialog>')[0]
        self.assertIn('id="library-cancel"',dialog)
        self.assertIn('id="library-progress"',dialog)
        self.assertIn('id="library-diagnostic"',dialog)
    def test_no_infinite_browser_poll_loop(self):
        js=(Path(__file__).parents[1]/'deepaha_importer/web/app.js').read_text()
        self.assertIn('deadline',js)
        self.assertIn('library-cancel',js)
    def test_empty_pending_view_has_next_action(self):
        js=(Path(__file__).parents[1]/'deepaha_importer/web/app.js').read_text()
        self.assertIn('查看已处理来源',js)
    def test_export_timestamp_is_export_not_analysis(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);f=root/'one_Handoff.json'
            f.write_text(json.dumps({'schema_version':'deepaha.source-intelligence.run.v2.2','run_metadata':{'run_key':'r1'},'source_candidates':[{'candidate_key':'c1','source_name':'研究','recommended_seed':'https://example.org'}]}))
            w=Workspace(root/'data');s=w.create([f]);g=s['analysis']['sources'][0]['id']
            w.decide(s['id'],g,'DEFER','补证','local-test',0)
            with patch('deepaha_importer.research.workspace.now',return_value='2030-01-02T00:00:00+00:00'):
                result=w.export(s['id'],1)
            with zipfile.ZipFile(result['path']) as z:h=json.loads(z.read('ResearchHandoff.json'))
            self.assertEqual(h['created_at'],'2030-01-02T00:00:00+00:00')
            self.assertIn('analyzed_at',h);self.assertIn('last_reviewed_at',h)
            with patch('deepaha_importer.research.workspace.now',return_value='2030-01-03T00:00:00+00:00'):
                again=w.export(s['id'],1)
            self.assertEqual(result['sha256'],again['sha256'])
    def test_legacy_export_is_returned_unchanged(self):
        # Existing exports must not be silently rewritten by the timestamp fix.
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);f=root/'one_Handoff.json'
            f.write_text(json.dumps({'schema_version':'deepaha.source-intelligence.run.v2.2','run_metadata':{'run_key':'r1'},'source_candidates':[{'candidate_key':'c','source_name':'a','recommended_seed':'https://example.org'}]}))
            w=Workspace(root/'data');s=w.create([f]);o=w.export(s['id'],0)
            self.assertEqual(w.export(s['id'],0)['sha256'],o['sha256'])
