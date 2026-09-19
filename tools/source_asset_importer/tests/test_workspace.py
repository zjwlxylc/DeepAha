import importlib.util,json,tempfile,unittest,zipfile
from pathlib import Path
class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('deepaha_importer.research.workspace'),'缺少持久审核工作区')
        from deepaha_importer.research.workspace import Workspace
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.root=Path(self.t.name)
        self.ws=Workspace(self.root/'data')
        self.f=self.root/'sample_Handoff.json'
        self.f.write_text(json.dumps({'schema_version':'deepaha.source-intelligence.run.v2.2','run_metadata':{'run_key':'20260912T000001_a'},'source_candidates':[{'candidate_key':'a','source_name':'研究院','recommended_seed':'https://example.org/jobs'}],'agent_acquisition_briefs':[]}))
        self.s=self.ws.create([self.f]);self.id=self.s['id'];self.g=self.s['analysis']['sources'][0]['id']
    def test_persistent_session(self):
        from deepaha_importer.research.workspace import Workspace
        self.assertEqual(Workspace(self.root/'data').get(self.id)['analysis']['summary']['candidate_groups'],1)
    def test_revision_guard(self):
        from deepaha_importer.errors import ImporterError
        self.ws.decide(self.id,self.g,'DEFER','先补证','负责人',0)
        with self.assertRaises(ImporterError):self.ws.decide(self.id,self.g,'REJECT','不用','负责人',0)
    def test_decision_requires_actor_and_reason(self):
        from deepaha_importer.errors import ImporterError
        with self.assertRaises(ImporterError):self.ws.decide(self.id,self.g,'DEFER','','',0)
    def test_review_ack_required(self):
        from deepaha_importer.errors import ImporterError
        with self.assertRaises(ImporterError):self.ws.decide(self.id,self.g,'PROPOSE_STAGING','保留作候选','负责人',0)
    def test_undo_retains_events(self):
        self.ws.decide(self.id,self.g,'DEFER','补证','负责人',0)
        self.ws.undo(self.id,self.g,'撤回','负责人',1)
        s=self.ws.get(self.id);self.assertNotIn(self.g,s['decisions']);self.assertEqual(len(s['events']),2)
    def test_export_contains_original_manifest_and_no_fake_receipt(self):
        out=self.ws.export(self.id,0)
        with zipfile.ZipFile(out['path']) as z:
            handoff=json.loads(z.read('ResearchHandoff.json'));m=json.loads(z.read('Manifest.json'))
            self.assertEqual(handoff['submission_status'],'NOT_SUBMITTED');self.assertTrue(any(x['path'].startswith('originals/') for x in m['files']))
            self.assertFalse(any('ImportReceipt' in n for n in z.namelist()))
    def test_export_rechecks_immutable_original_bytes(self):
        from deepaha_importer.errors import ImporterError
        for f in (self.root/'data'/'blobs').iterdir():f.write_bytes(b'changed')
        with self.assertRaises(ImporterError):self.ws.export(self.id,0)
    def test_fake_production_receipt_never_sets_official_state(self):
        receipt={'schema_version':'deepaha.scout-feedback.v1','issuer':'DeepAha','instance_id':'a','environment':'PRODUCTION','feedback_id':'f1','bundle_id':'0'*64,'observed_at':'2026-09-12T01:00:00Z','events':[]}
        self.ws.add_feedback(self.id,json.dumps(receipt).encode(),0)
        s=self.ws.get(self.id);self.assertEqual(s['feedback'][0]['verification']['authenticity'],'UNVERIFIED')
        self.assertIsNone(s['analysis']['sources'][0]['system_source_id'])
    def test_bad_id_not_path(self):
        from deepaha_importer.errors import ImporterError
        with self.assertRaises(ImporterError):self.ws.get('../a')
    def test_local_review_can_be_exported_unfinished(self):
        out=self.ws.export(self.id,0)
        with zipfile.ZipFile(out['path']) as z:
            h=json.loads(z.read('ResearchHandoff.json'));self.assertEqual(h['readiness'],'UNFINISHED_REVIEW_NOT_FOR_APPROVAL')
    def test_workspace_child_symlink_is_rejected_before_writes(self):
        from deepaha_importer.errors import ImporterError
        from deepaha_importer.research.workspace import Workspace
        import os
        if os.name=='nt':self.skipTest('symlink fixture requires permission')
        root=self.root/'other';root.mkdir();outside=self.root/'outside';outside.mkdir();(root/'blobs').symlink_to(outside,target_is_directory=True)
        with self.assertRaises(ImporterError):Workspace(root)
    def test_feedback_invalid_event_timestamp_rejected(self):
        from deepaha_importer.errors import ImporterError
        r={'schema_version':'deepaha.scout-feedback.v1','issuer':'DeepAha','instance_id':'a','environment':'TEST','feedback_id':'f1','bundle_id':'0'*64,'observed_at':'2026-09-12T01:00:00Z','events':[{'event_id':'e1','type':'CANDIDATE_RECEIVED','candidate_ref':'n::c','occurred_at':'not-a-time'}]}
        with self.assertRaises(ImporterError):self.ws.add_feedback(self.id,json.dumps(r).encode(),0)
    def test_feedback_empty_event_id_rejected(self):
        from deepaha_importer.errors import ImporterError
        r={'schema_version':'deepaha.scout-feedback.v1','issuer':'DeepAha','instance_id':'a','environment':'TEST','feedback_id':'f1','bundle_id':'0'*64,'observed_at':'2026-09-12T01:00:00Z','events':[{'event_id':'','type':'CANDIDATE_RECEIVED','candidate_ref':'n::c','occurred_at':'2026-09-12T01:00:00Z'}]}
        with self.assertRaises(ImporterError):self.ws.add_feedback(self.id,json.dumps(r).encode(),0)
