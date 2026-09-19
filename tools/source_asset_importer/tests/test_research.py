import importlib.util
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

class ResearchFeatureTests(unittest.TestCase):
    def test_research_adapter_available(self):
        self.assertIsNotNone(importlib.util.find_spec('deepaha_importer.research'),
                             'v0.2.0缺少研究包批量适配层')

class ResearchBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('deepaha_importer.research'), '缺少研究包适配层')
        from deepaha_importer.research.ingest import load_inputs
        from deepaha_importer.research.audit import analyze
        self.load, self.analyze = load_inputs, analyze
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
    def handoff(self, name='x_Handoff.json', key='a', run='20260912T000001_x', seed='https://example.org/jobs', **fields):
        obj={'schema_version':'deepaha.source-intelligence.run.v2.2','run_metadata':{'run_key':run,'generated_at':'2026-09-12T00:00:00+08:00'},
             'source_candidates':[{'candidate_key':key,'source_name':'研究院招聘','institution':'研究院','recommended_seed':seed,**fields}],
             'agent_acquisition_briefs':[], 'research_evidence':[], 'source_graph_delta':[]}
        p=self.root/name;p.write_text(json.dumps(obj,ensure_ascii=False),encoding='utf-8'); return p
    def test_repeated_identity_retains_versions(self):
        a=self.handoff();b=self.handoff('y_Handoff.json',run='20260912T000002_y', value_assessment='变化')
        r=self.analyze(self.load([a,b],namespace='gpt'))
        self.assertEqual(r['summary']['source_versions'],2);self.assertEqual(r['summary']['candidate_groups'],1)
        self.assertEqual(len(r['sources'][0]['versions']),2)
    def test_namespaces_do_not_merge_same_key(self):
        a=self.handoff();b=self.handoff('y_Handoff.json',run='20260912-0002-0002')
        r=self.analyze(self.load([a,b])); self.assertEqual(r['summary']['candidate_groups'],2)
    def test_same_url_is_suggestion_not_auto_merge(self):
        a=self.handoff();b=self.handoff('y_Handoff.json',key='b',run='20260912T000002_y')
        r=self.analyze(self.load([a,b]));self.assertEqual(r['summary']['candidate_groups'],2)
        self.assertTrue(any(x['kind']=='SAME_ENDPOINT' for x in r['relations']))
    def test_multi_url_kept_for_review(self):
        a=self.handoff(seed='https://example.org/a ; https://example.org/b')
        r=self.analyze(self.load([a]));s=r['sources'][0]
        self.assertEqual(len(s['seed_urls']),2);self.assertIn('MULTIPLE_SEEDS',s['issue_codes'])
    def test_fragment_route_not_collapsed(self):
        from deepaha_importer.research.normalize import url_key
        self.assertNotEqual(url_key('https://example.org/#/a'),url_key('https://example.org/#/b'))
        self.assertNotEqual(url_key('http://example.org/a'),url_key('https://example.org/a'))
        self.assertEqual(url_key('https://EXAMPLE.org:443/a?utm_source=x'), 'https://example.org/a')
    def test_duplicate_json_keys_rejected(self):
        from deepaha_importer.errors import ImporterError
        p=self.root/'bad_Handoff.json';p.write_text('{"a":1,"a":2}')
        with self.assertRaises(ImporterError): self.load([p])
    def test_unsafe_zip_rejected(self):
        from deepaha_importer.errors import ImporterError
        for name in ['../escape.json','/absolute','C:/windows/test','x/../../a']:
            p=self.root/'bad.zip'
            with zipfile.ZipFile(p,'w') as z:z.writestr(name,'{}')
            with self.assertRaises(ImporterError):self.load([p])
    def test_case_collision_zip_rejected(self):
        from deepaha_importer.errors import ImporterError
        p=self.root/'bad.zip'
        with zipfile.ZipFile(p,'w') as z:z.writestr('A.json','{}');z.writestr('a.json','{}')
        with self.assertRaises(ImporterError): self.load([p])
    def test_same_run_different_bytes_is_blocked(self):
        a=self.handoff();b=self.handoff('y_Handoff.json',value_assessment='另一结果')
        r=self.analyze(self.load([a,b]));self.assertIn('RUN_CONTENT_CONFLICT',r['sources'][0]['issue_codes'])
    def test_score_mismatch_reported(self):
        a=self.handoff(score_breakdown={'a':20,'b':10,'score_total':90},score_total=90)
        r=self.analyze(self.load([a])); self.assertIn('SCORE_ARITHMETIC_MISMATCH',r['sources'][0]['issue_codes'])
    def test_references_resolve_across_batches(self):
        a=self.handoff(evidence_refs=['E1']);b=self.handoff('y_Handoff.json',key='b',run='20260912T000002_y')
        d=json.loads(b.read_text());d['research_evidence']=[{'evidence_key':'E1','url':'https://example.org/e'}];b.write_text(json.dumps(d))
        r=self.analyze(self.load([a,b])); self.assertFalse(any(x['code']=='MISSING_EVIDENCE_REFERENCE' for x in r['issues']))
    def test_library_pseudo_url_not_public_evidence(self):
        a=self.handoff();d=json.loads(a.read_text());d['research_evidence']=[{'evidence_key':'E1','url':'library:/folder/file.json'}];a.write_text(json.dumps(d))
        r=self.analyze(self.load([a]));self.assertEqual(r['summary']['public_evidence_urls'],0)
    def test_empty_seed_blocks_handoff(self):
        r=self.analyze(self.load([self.handoff(seed='')]))
        self.assertTrue(r['sources'][0]['blocking']);self.assertIn('INVALID_SEED',r['sources'][0]['issue_codes'])
    def test_chinese_explanation_does_not_become_url(self):
        from deepaha_importer.research.normalize import seed_urls
        self.assertEqual(seed_urls('http://bm.example.org/kl2026（招考简章）'),['http://bm.example.org/kl2026'])
        self.assertEqual(seed_urls('https://example.org/a；https://example.org/b'),['https://example.org/a','https://example.org/b'])
    def test_directory_identity_uses_content_not_local_location(self):
        a=self.handoff(); first=self.load([self.root]);d=self.root/'copy';d.mkdir();(d/a.name).write_bytes(a.read_bytes())
        second=self.load([d]);self.assertEqual(first.files[0].input_sha256,second.files[0].input_sha256)
    def test_state_hash_is_not_an_official_attachment(self):
        a=self.handoff();d=json.loads(a.read_text());d['research_evidence']=[{'evidence_key':'E1','url':'library:/old_State.json','sha256':'0'*64}];a.write_text(json.dumps(d))
        r=self.analyze(self.load([a]));self.assertEqual(r['summary']['attachment_references'],0)
        self.assertEqual(len(r['state_reference_reconciliation']),1)
    def test_missing_attachment_issue_reaches_affected_source(self):
        a=self.handoff(evidence_refs=['E1']);d=json.loads(a.read_text());d['research_evidence']=[{'evidence_key':'E1','url':'https://example.org/a.pdf','sha256':'0'*64}];a.write_text(json.dumps(d))
        r=self.analyze(self.load([a]));self.assertIn('ATTACHMENT_DECLARED_HASH_NOT_IN_SELECTED_PACKAGE',r['sources'][0]['issue_codes'])
    def test_prose_evidence_ids_resolve_without_prefix_matches(self):
        a=self.handoff(evidence_refs=['EV-0010-001（列表）; EV-0010-010（详情）'])
        d=json.loads(a.read_text());d['research_evidence']=[{'evidence_key':k,'url':'https://example.org/'+k} for k in ['EV-0010-001','EV-0010-010']]
        d['agent_acquisition_briefs']=[{'brief_key':'B1','source_ref':'a','recon_evidence':['EV-0010-001（原页）、EV-0010-010（附件）']}]
        a.write_text(json.dumps(d));r=self.analyze(self.load([a]))
        self.assertFalse(any('MISSING' in x['code'] for x in r['issues']))
        self.assertEqual({e['key'] for e in r['sources'][0]['evidence_versions']},{'EV-0010-001','EV-0010-010'})
        self.assertTrue(any(x['code']=='REFERENCE_TEXT_NORMALIZATION_PROPOSAL' for x in r['issues']))
    def test_unknown_id_in_prose_remains_an_explicit_gap(self):
        a=self.handoff(evidence_refs=['EV-0010-001; EV-9999-009（未提供）'])
        d=json.loads(a.read_text());d['research_evidence']=[{'evidence_key':'EV-0010-001','url':'https://example.org/e'}];a.write_text(json.dumps(d))
        r=self.analyze(self.load([a]));missing=[x for x in r['issues'] if x['code']=='MISSING_EVIDENCE_REFERENCE']
        self.assertEqual([x['reference'] for x in missing],['EV-9999-009'])
    def test_wb_state_candidates_alias_resolves_brief_source(self):
        a=self.handoff(run='20260912-0001-0001');d=json.loads(a.read_text())
        d['agent_acquisition_briefs']=[{'brief_key':'B1','source_ref':'legacy-only'}];a.write_text(json.dumps(d))
        state=self.root/'20260912-0001-0001_State.json';state.write_text(json.dumps({'run_key':'20260912-0001-0001','candidates':[{'candidate_key':'legacy-only'}]}))
        r=self.analyze(self.load([a,state]));self.assertFalse(any(x['code']=='BRIEF_SOURCE_OUTSIDE_SELECTION' for x in r['issues']))
    def test_exported_review_bundle_is_not_silently_partially_reimported(self):
        from deepaha_importer.errors import ImporterError
        a=self.handoff();p=self.root/'review_export.zip'
        with zipfile.ZipFile(p,'w') as z:
            z.writestr('ResearchHandoff.json',json.dumps({'schema_version':'deepaha.research-handoff.v1'}))
            z.writestr('originals/0001/x_Handoff.json',a.read_bytes())
        with self.assertRaises(ImporterError) as e:self.load([p])
        self.assertEqual(e.exception.code,'REVIEW_BUNDLE_NOT_RESEARCH_INPUT')
