import importlib.util,json,tempfile,unittest
from pathlib import Path
class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('deepaha_importer.research.baseline'),'缺少受控基线模块')
        from deepaha_importer.research.baseline import create_controlled_baseline,verify_state_chain
        self.create,self.verify=create_controlled_baseline,verify_state_chain
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.p=Path(self.t.name)
    def fixture(self):
        from deepaha_importer.contract import digest
        a=self.p/'parent_State.json';a.write_text(json.dumps({'run_key':'p','source_candidates':[{'candidate_key':'old','first_seen_at':None}]}))
        b=self.p/'child_State.json';b.write_text(json.dumps({'schema_version':'deepaha.source-intelligence.state.v2.2','run_key':'c','state_complete':False,'state_inheritance':'PARTIAL','source_candidates':[{'candidate_key':'old','first_seen_at':None}], 'missing_history':['RUN003'], 'parent_state_ref':{'run_key':'p','sha256':digest(a.read_bytes()),'size_bytes':a.stat().st_size}}))
        return a,b
    def test_hash_chain_checked(self):
        a,b=self.fixture();r=self.verify([b],a);self.assertEqual(r['status'],'PASS');self.assertEqual(r['checked_links'],1)
    def test_bad_parent_hash_rejects_baseline(self):
        from deepaha_importer.errors import ImporterError
        a,b=self.fixture();a.write_text('{}')
        with self.assertRaises(ImporterError):self.create(b,[b],authorizing_user='项目所有者',external_parent=a)
    def test_original_unknown_and_history_retained(self):
        a,b=self.fixture();original=b.read_bytes();r=self.create(b,[b],authorizing_user='项目所有者',external_parent=a)
        self.assertEqual(b.read_bytes(),original);self.assertFalse(r['state_complete']);self.assertEqual(r['source_candidates'][0]['first_seen_at'],None)
        self.assertEqual(r['controlled_baseline']['operational_status'],'READY');self.assertTrue(r['controlled_baseline']['permanent_migration_gaps'])
    def test_no_fake_system_receipt(self):
        a,b=self.fixture();r=self.create(b,[b],authorizing_user='项目所有者',external_parent=a)
        self.assertEqual(r.get('received_import_receipts',[]),[]);self.assertEqual(r['controlled_baseline']['production_state'],'NOT_OBSERVED')
    def test_authorization_is_required(self):
        from deepaha_importer.errors import ImporterError
        a,b=self.fixture()
        with self.assertRaises(ImporterError):self.create(b,[b],authorizing_user='',external_parent=a)
    def test_selected_state_bytes_must_be_part_of_verified_chain(self):
        from deepaha_importer.errors import ImporterError
        a,b=self.fixture();fake=self.p/'other_State.json';d=json.loads(b.read_text());d['injected_claim']='not verified';fake.write_text(json.dumps(d))
        with self.assertRaises(ImporterError):self.create(fake,[b],authorizing_user='项目所有者',external_parent=a)
