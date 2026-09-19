import json
import tempfile
import unittest
from pathlib import Path
from deepaha_importer.contract import Package, canonical_url, digest, parse_json
from deepaha_importer.errors import ImporterError
from deepaha_importer.repository import SQLiteRepository
from deepaha_importer.security import Principal, TokenSigner
from deepaha_importer.service import ImportService
from tests.helpers import raw, handoff, changed


class AdditionalContractTests(unittest.TestCase):
    def test_malformed_metadata_is_a_controlled_error(self):
        with tempfile.TemporaryDirectory() as td:
            file = Path(td) / 'bad.json'; d = handoff(); d['run_metadata'] = 'bad'
            file.write_bytes(raw(d))
            with self.assertRaises(ImporterError): Package.from_file(file)

    def test_localhost_trailing_dot_rejected(self):
        with self.assertRaises(ImporterError): canonical_url('https://localhost./secret')

    def test_dns_hostname_validation(self):
        for u in ['https://bad$host.org/x', 'http://127.1/x']:
            with self.subTest(u=u), self.assertRaises(ImporterError): canonical_url(u)

    def test_secret_key_spelling_normalized(self):
        with self.assertRaises(ImporterError): parse_json(b'{"API Key":"secret"}')

    def test_source_basic_types(self):
        for key, value in [('score_breakdown', []), ('authority_assessment', 4), ('system_source_id', True)]:
            d=handoff(); d['source_candidates'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ImporterError): Package.from_bytes(raw(d))

    def test_traversal_dependency_rejected(self):
        d=handoff(); data=b'x'
        d['run_metadata']['file_dependencies']=[{'relative_path':'../outside.txt','sha256':digest(data),'size_bytes':1}]
        with self.assertRaises(ImporterError): Package.from_bytes(raw(d), [('../outside.txt',data)])

    def test_wrong_attachment_hash_rejected(self):
        d=handoff(); d['run_metadata']['file_dependencies']=[{'relative_path':'a.txt','sha256':'0'*64,'size_bytes':1}]
        with self.assertRaises(ImporterError): Package.from_bytes(raw(d), [('a.txt',b'x')])

    def test_unlisted_attachment_rejected(self):
        with self.assertRaises(ImporterError): Package.from_bytes(raw(), [('extra.txt', b'x')])

    def test_evidence_references_nonempty(self):
        d=handoff(); d['agent_acquisition_briefs'][0]['recon_evidence']=[]
        with self.assertRaises(ImporterError): Package.from_bytes(raw(d))


class AdditionalServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.repo=SQLiteRepository(Path(self.temp.name)/'db.sqlite'); self.repo.initialize()
        self.clock=[1000]
        self.actor=Principal('a','scout',frozenset({'scout:preview','scout:import','scout:read'}))
        self.service=ImportService(self.repo,TokenSigner(b'a'*32,clock=lambda:self.clock[0]),'TEST')

    def submit(self,d):
        p=Package.from_bytes(raw(d)); pre=self.service.preview(p,self.actor)
        return self.service.commit(p,self.actor,pre['confirmation_token'],True,'TEST')

    def test_expired_preview(self):
        p=Package.from_bytes(raw()); pre=self.service.preview(p,self.actor); self.clock[0]+=601
        with self.assertRaises(ImporterError) as c:
            self.service.commit(p,self.actor,pre['confirmation_token'],True,'TEST')
        self.assertEqual(c.exception.code,'PREVIEW_EXPIRED')

    def test_preview_shows_field_changes(self):
        self.submit(handoff()); pre=self.service.preview(Package.from_bytes(raw(changed())),self.actor)
        item=next(i for i in pre['items'] if i['kind']=='source')
        self.assertEqual(item['changes']['source_name']['before'],'演练来源 A')
        self.assertEqual(item['changes']['source_name']['after'],'演练来源 A（新版）')

    def test_same_revision_cannot_be_changed(self):
        self.submit(handoff()); d=changed(); d['source_candidates'][0]['revision']=1
        pre=self.service.preview(Package.from_bytes(raw(d)),self.actor)
        self.assertFalse(pre['can_commit'])

    def test_source_change_keeps_legacy_identity_as_conflict_not_duplicate_add(self):
        self.submit(handoff()); d=changed(); d['source_candidates'][0]['recommended_seed']='https://example.org/new-column'
        self.submit(d)
        old=handoff('rediscovered-old'); old['source_candidates'][0]['candidate_key']='new-name-for-old'
        old['agent_acquisition_briefs']=[]
        pre=self.service.preview(Package.from_bytes(raw(old)),self.actor)
        # The old endpoint is known historical identity, not a new source.
        self.assertFalse(pre['can_commit'])
        self.assertIn('IDENTITY_REVIEW_REQUIRED',[c['code'] for c in pre['conflicts']])
