import base64
import json
import tempfile
import threading
import unittest
from pathlib import Path
from wsgiref.simple_server import make_server

from deepaha_importer.contract import Package
from deepaha_importer.errors import ImporterError
from deepaha_importer.repository import SQLiteRepository
from deepaha_importer.security import Principal, TokenSigner
from deepaha_importer.service import ImportService
from deepaha_importer.http_api import WSGIApplication, BearerAuthenticator
from deepaha_importer.client import RemoteClient, ClientConfig, LocalClient
from tests.helpers import raw


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        repo = SQLiteRepository(Path(cls.tmp.name) / 'test.db'); repo.initialize()
        cls.actor = Principal('human', 'source-scout', frozenset({'scout:preview', 'scout:import', 'scout:read'}))
        cls.service = ImportService(repo, TokenSigner(b'x' * 32), environment='TEST')
        cls.token = 'unit-test-token-only-' + 'x' * 30
        app = WSGIApplication(cls.service, BearerAuthenticator([(cls.token, cls.actor)]))
        cls.server = make_server('127.0.0.1', 0, app)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True); cls.thread.start()
        cls.url = 'http://127.0.0.1:' + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()
        cls.tmp.cleanup()

    def client(self, token=None, environment='TEST'):
        return RemoteClient(ClientConfig(self.url, environment, allow_http_loopback=True), self.token if token is None else token)

    def test_real_loopback_import_and_lookup(self):
        c = self.client(); p = Package.from_bytes(raw())
        cap = c.capabilities(); self.assertEqual(cap['environment'], 'TEST')
        preview = c.preview(p)
        receipt = c.commit(p, preview, confirmed=True)
        self.assertEqual(c.receipt(p), receipt)

    def test_bad_token(self):
        with self.assertRaises(ImporterError) as ctx: self.client('bad-token').capabilities()
        self.assertEqual(ctx.exception.status, 401)

    def test_environment_mismatch_before_transfer(self):
        with self.assertRaises(ImporterError): self.client(environment='PRODUCTION').capabilities()

    def test_insecure_remote_url_rejected(self):
        for url in ['http://example.org', 'file:///tmp/x', 'https://name:password@example.org',
                    'https://example.org/path?token=x', 'http://localhost.evil.org']:
            with self.subTest(url=url), self.assertRaises(ImporterError):
                RemoteClient(ClientConfig(url, 'TEST'), 'x' * 32)

    def test_loopback_http_requires_explicit_flag(self):
        with self.assertRaises(ImporterError): RemoteClient(ClientConfig(self.url, 'TEST'), self.token)

    def test_auth_is_not_taken_from_handoff(self):
        c = self.client(); p = Package.from_bytes(raw())
        cap = c.capabilities()
        self.assertEqual(cap['subject'], 'human')
        self.assertEqual(cap['producer'], 'source-scout')

    def test_router_rejects_publish(self):
        c = self.client()
        with self.assertRaises(ImporterError) as ctx: c._request('POST', '/publish', {})
        self.assertEqual(ctx.exception.status, 404)

    def test_undeclared_body_key_rejected(self):
        c = self.client()
        with self.assertRaises(ImporterError):
            c._request('POST', '/preview', {'handoff_b64': base64.b64encode(raw()).decode(),
                       'files': [], 'approve_sources': [], 'expected_environment': 'TEST', 'actor': 'admin'})

    def test_confirm_cannot_be_skipped(self):
        c = self.client(); p = Package.from_bytes(raw())
        v = c.preview(p)
        with self.assertRaises(ImporterError): c.commit(p, v, confirmed=False)

    def test_wrong_target_pin(self):
        c = RemoteClient(ClientConfig(self.url, 'TEST', expected_target_id='wrong', allow_http_loopback=True), self.token)
        with self.assertRaises(ImporterError): c.capabilities()
