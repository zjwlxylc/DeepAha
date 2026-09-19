import copy
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from deepaha_importer.contract import Package, digest
from deepaha_importer.errors import ImporterError
from deepaha_importer.repository import SQLiteRepository
from deepaha_importer.security import Principal, TokenSigner
from deepaha_importer.service import ImportService
from tests.helpers import handoff, raw, changed


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'test.db'
        self.repo = SQLiteRepository(self.db); self.repo.initialize()
        self.actor = Principal('tester', 'source-scout', frozenset({'scout:preview', 'scout:import', 'scout:read'}))
        self.service = ImportService(self.repo, TokenSigner(b'x' * 32), environment='TEST')
        self.p = Package.from_bytes(raw())

    def submit(self, package=None):
        p = self.p if package is None else package
        v = self.service.preview(p, self.actor)
        return self.service.commit(p, self.actor, v['confirmation_token'], True, 'TEST')

    def count(self, table):
        with sqlite3.connect(self.db) as db:
            return db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]

    def test_preview_is_readonly(self):
        before = self.db.read_bytes()
        v = self.service.preview(self.p, self.actor)
        self.assertTrue(v['can_commit']); self.assertEqual(v['counts']['ADD'], 5)
        self.assertEqual(before, self.db.read_bytes())
        self.assertEqual(self.count('scout_import_batch'), 0)

    def test_valid_import_and_readback(self):
        receipt = self.submit()
        self.assertEqual(receipt['status'], 'TEST_IMPORTED')
        self.assertEqual(self.count('scout_import_asset'), 5)
        self.assertEqual(self.service.receipt(self.p.run_key, self.actor), receipt)
        self.assertFalse(receipt['wma_automatically_started'])
        self.assertTrue(all(x['approval_status'] == 'PENDING_REVIEW'
                            for x in receipt['items'] if x['kind'] == 'source'))

    def test_idempotent_same_bytes(self):
        a = self.submit(); b = self.submit()
        self.assertEqual(a, b); self.assertEqual(self.count('scout_import_batch'), 1)
        self.assertEqual(self.count('scout_import_revision'), 5)

    def test_same_run_different_bytes(self):
        self.submit(); d = handoff(); d['warnings'].append('changed')
        v = self.service.preview(Package.from_bytes(raw(d)), self.actor)
        self.assertFalse(v['can_commit'])
        self.assertIn('BATCH_CONTENT_CONFLICT', [c['code'] for c in v['conflicts']])

    def test_changed_package_after_preview(self):
        v = self.service.preview(self.p, self.actor)
        d = handoff(); d['warnings'].append('changed')
        with self.assertRaises(ImporterError):
            self.service.commit(Package.from_bytes(raw(d)), self.actor, v['confirmation_token'], True, 'TEST')
        self.assertEqual(self.count('scout_import_batch'), 0)

    def test_confirmation_required(self):
        v = self.service.preview(self.p, self.actor)
        for value in [False, None, 'true', 1]:
            with self.subTest(value=value), self.assertRaises(ImporterError):
                self.service.commit(self.p, self.actor, v['confirmation_token'], value, 'TEST')

    def test_unauthorized_preview_and_commit(self):
        v = self.service.preview(self.p, self.actor)
        nobody = Principal('tester', 'source-scout', frozenset())
        with self.assertRaises(ImporterError): self.service.preview(self.p, nobody)
        with self.assertRaises(ImporterError):
            self.service.commit(self.p, nobody, v['confirmation_token'], True, 'TEST')

    def test_token_bound_to_actor_and_environment(self):
        v = self.service.preview(self.p, self.actor)
        stranger = Principal('other-user', 'source-scout', self.actor.scopes)
        for actor, env in [(stranger, 'TEST'), (self.actor, 'PRODUCTION')]:
            with self.subTest(actor=actor, env=env), self.assertRaises(ImporterError):
                self.service.commit(self.p, actor, v['confirmation_token'], True, env)

    def test_tampered_token(self):
        v = self.service.preview(self.p, self.actor); t = v['confirmation_token']
        with self.assertRaises(ImporterError):
            self.service.commit(self.p, self.actor, 'a' + t[1:], True, 'TEST')

    def test_stale_preview(self):
        v = self.service.preview(self.p, self.actor)
        d = handoff('another-run'); d['source_candidates'][0]['candidate_key'] = 'different'
        d['source_candidates'][0]['recommended_seed'] = 'https://example.org/another'
        d['agent_acquisition_briefs'][0]['source_ref'] = 'different'
        d['agent_acquisition_briefs'][0]['brief_key'] = 'different-brief'
        self.submit(Package.from_bytes(raw(d)))
        with self.assertRaises(ImporterError) as c:
            self.service.commit(self.p, self.actor, v['confirmation_token'], True, 'TEST')
        self.assertEqual(c.exception.code, 'STALE_PREVIEW')

    def test_external_revision_update(self):
        self.submit(); receipt = self.submit(Package.from_bytes(raw(changed())))
        src = next(x for x in receipt['items'] if x['kind'] == 'source')
        self.assertEqual(src['system_revision'], 2)
        self.assertEqual(src['scout_revision'], '2')
        self.assertIsNone(src['system_source_id'])
        self.assertEqual(src['action'], 'UPDATE')

    def test_old_external_revision_conflict(self):
        self.submit(); self.submit(Package.from_bytes(raw(changed())))
        d = changed(run_key='older-attempt'); d['source_candidates'][0]['source_name'] = 'bad overwrite'
        v = self.service.preview(Package.from_bytes(raw(d)), self.actor)
        self.assertFalse(v['can_commit'])

    def test_missing_external_base_is_not_assumed_to_be_database_revision(self):
        self.submit(); d = changed(); del d['source_candidates'][0]['base_revision']
        v = self.service.preview(Package.from_bytes(raw(d)), self.actor)
        self.assertFalse(v['can_commit'])

    def test_explicit_system_base_revision(self):
        self.submit(); d = changed(); d['source_candidates'][0]['base_revision'] = None
        d['source_candidates'][0]['system_base_revision'] = 1
        self.assertTrue(self.service.preview(Package.from_bytes(raw(d)), self.actor)['can_commit'])

    def test_unknown_reference(self):
        d = handoff(); d['source_candidates'][0]['evidence_refs'] = ['missing']
        v = self.service.preview(Package.from_bytes(raw(d)), self.actor)
        self.assertFalse(v['can_commit'])
        self.assertIn('UNRESOLVED_REFERENCE', [x['code'] for x in v['conflicts']])

    def test_known_reference_from_previous_batch(self):
        self.submit(); d = changed(); d['research_evidence'] = []
        self.assertTrue(self.service.preview(Package.from_bytes(raw(d)), self.actor)['can_commit'])

    def test_unknown_formal_system_source(self):
        d = handoff(); d['source_candidates'][0]['system_source_id'] = 'invented-id'
        v = self.service.preview(Package.from_bytes(raw(d)), self.actor)
        self.assertFalse(v['can_commit'])

    def test_two_keys_same_source_deduplicated(self):
        self.submit(); d = handoff('new-run')
        d['source_candidates'][0]['candidate_key'] = 'new-alias'
        d['agent_acquisition_briefs'] = []
        receipt = self.submit(Package.from_bytes(raw(d)))
        src = next(x for x in receipt['items'] if x['kind'] == 'source')
        self.assertEqual(src['action'], 'DUPLICATE')
        self.assertEqual(self.count('scout_import_asset'), 5)

    def test_whole_transaction_rolls_back(self):
        # Force a real database failure after the batch insert, not a mocked success path.
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE TRIGGER fail_asset BEFORE INSERT ON scout_import_asset BEGIN SELECT RAISE(ABORT, 'fixture failure'); END")
        with self.assertRaises(Exception): self.submit()
        self.assertEqual(self.count('scout_import_batch'), 0)
        self.assertEqual(self.count('scout_import_asset'), 0)

    def test_raw_handoff_preserved_exactly(self):
        self.submit()
        with sqlite3.connect(self.db) as db:
            saved = db.execute('SELECT raw_handoff FROM scout_import_batch').fetchone()[0]
        self.assertEqual(saved, self.p.raw)

    def test_unsupported_source_approval_fails_closed(self):
        actor = Principal('tester', 'source-scout', self.actor.scopes | {'scout:approve'})
        with self.assertRaises(ImporterError):
            self.service.preview(self.p, actor, approve_sources=['demo-source-a'])

    def test_repository_cannot_be_used_as_production_by_changing_environment(self):
        with self.assertRaises(ImporterError):
            ImportService(self.repo, TokenSigner(b'x' * 32), environment='PRODUCTION')

    def test_concurrent_identical_imports(self):
        v = self.service.preview(self.p, self.actor)
        def go(_):
            return self.service.commit(self.p, self.actor, v['confirmation_token'], True, 'TEST')
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(go, range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.count('scout_import_batch'), 1)

    def test_cross_producer_receipt_not_accessible(self):
        self.submit()
        actor = Principal('tester', 'other-producer', self.actor.scopes)
        with self.assertRaises(ImporterError): self.service.receipt(self.p.run_key, actor)

    def test_dependencies_persist_in_same_transaction(self):
        d = handoff(); data = b'example attachment'
        d['run_metadata']['file_dependencies'] = [{'relative_path': 'evidence/sample.txt', 'size_bytes': len(data), 'sha256': digest(data)}]
        p = Package.from_bytes(raw(d), [('evidence/sample.txt', data)])
        self.submit(p)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT content FROM scout_import_file').fetchone()[0], data)
