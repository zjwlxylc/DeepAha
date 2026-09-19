import json
import tempfile
import unittest
from pathlib import Path

from tests.helpers import handoff, raw
from deepaha_importer.contract import Package, parse_json, canonical_url
from deepaha_importer.errors import ImporterError


class ContractTests(unittest.TestCase):
    def test_valid_handoff(self):
        p = Package.from_bytes(raw())
        self.assertEqual(p.run_key, 'demo-20260906-001')
        self.assertEqual(len(p.assets('source')), 1)
        self.assertEqual(p.raw, raw())

    def test_duplicate_json_keys(self):
        with self.assertRaises(ImporterError):
            parse_json(b'{"x":1,"x":2}')

    def test_nonfinite(self):
        for s in [b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}']:
            with self.subTest(s=s), self.assertRaises(ImporterError):
                parse_json(s)

    def test_missing_field(self):
        d = handoff(); del d['source_candidates'][0]['recommended_seed']
        with self.assertRaises(ImporterError):
            Package.from_bytes(raw(d))

    def test_unknown_schema(self):
        d = handoff(); d['schema_version'] = 'anything'
        with self.assertRaises(ImporterError):
            Package.from_bytes(raw(d))

    def test_wrong_delivery(self):
        d = handoff(); d['run_metadata']['submission_status'] = 'IMPORTED'
        with self.assertRaises(ImporterError):
            Package.from_bytes(raw(d))

    def test_references_collected(self):
        p = Package.from_bytes(raw())
        self.assertIn(('evidence', 'ev-demo-a'), p.references())
        self.assertIn(('source', 'demo-source-a'), p.references())

    def test_unsafe_seed(self):
        for url in ['file:///etc/passwd', 'http://127.0.0.1/a', 'http://10.0.0.1/x',
                    'https://user:pass@example.org/a', 'https://localhost/x', 'javascript:alert(1)']:
            d = handoff(); d['source_candidates'][0]['recommended_seed'] = url
            with self.subTest(url=url), self.assertRaises(ImporterError):
                Package.from_bytes(raw(d))

    def test_url_preserves_query_fragment(self):
        self.assertEqual(canonical_url('HTTPS://EXAMPLE.ORG:443/a?b=1&a=2#x'),
                         'https://example.org/a?b=1&a=2#x')

    def test_does_not_confuse_prompt_and_schema_version(self):
        p = Package.from_bytes(raw())
        self.assertEqual(p.data['run_metadata']['prompt_version'], '2.2.1')
        self.assertEqual(p.data['schema_version'], 'deepaha.source-intelligence.run.v2.2')

    def test_secret_fields_rejected(self):
        d = handoff(); d['source_candidates'][0]['api_key'] = 'secret'
        with self.assertRaises(ImporterError):
            Package.from_bytes(raw(d))

    def test_incomplete_package_rejected(self):
        d = handoff(); d['run_metadata']['package_complete'] = False
        with self.assertRaises(ImporterError):
            Package.from_bytes(raw(d))

    def test_json_depth_limit(self):
        with self.assertRaises(ImporterError):
            parse_json(('[' * 80 + '0' + ']' * 80).encode())

    def test_fixture_file_load(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / 'input.json'; f.write_bytes(raw())
            self.assertEqual(Package.from_file(f).raw, raw())

    def test_duplicate_asset_identity_in_package_rejected(self):
        d = handoff(); d['source_candidates'].append(dict(d['source_candidates'][0]))
        with self.assertRaises(ImporterError):
            Package.from_bytes(raw(d))

    def test_title_case_brief_aliases_supported_without_changing_original(self):
        d = handoff(); b = d['agent_acquisition_briefs'][0]
        b['Recommended Seed'] = b.pop('recommended_seed')
        p = Package.from_bytes(raw(d))
        self.assertIn('Recommended Seed', p.data['agent_acquisition_briefs'][0])
        self.assertEqual(p.assets('brief')[0].payload['recommended_seed'], b['Recommended Seed'])

    def test_alias_conflict_rejected(self):
        d = handoff(); d['agent_acquisition_briefs'][0]['Recommended Seed'] = 'https://example.org/other'
        with self.assertRaises(ImporterError):
            Package.from_bytes(raw(d))
