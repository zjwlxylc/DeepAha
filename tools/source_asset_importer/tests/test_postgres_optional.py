"""Opt-in PostgreSQL integration test, never connects to an unspecified database."""
import importlib.util
import os
import unittest
import uuid
from deepaha_importer.contract import Package
from deepaha_importer.repository import PostgresRepository
from deepaha_importer.security import Principal, TokenSigner
from deepaha_importer.service import ImportService
from tests.helpers import raw, handoff

ENABLED=(os.environ.get('DEEPAHA_IMPORT_TEST_ALLOW_SCHEMA')=='YES_ISOLATED_DATABASE'
         and bool(os.environ.get('DEEPAHA_IMPORT_TEST_POSTGRES_DSN'))
         and bool(importlib.util.find_spec('psycopg')))

@unittest.skipUnless(ENABLED,'PostgreSQL 实环境未提供；需要隔离测试 DSN、显式 DDL 授权和 psycopg')
class PostgresIntegrationTests(unittest.TestCase):
    def test_import_is_durable_and_idempotent(self):
        repo=PostgresRepository(os.environ['DEEPAHA_IMPORT_TEST_POSTGRES_DSN']); repo.initialize()
        actor=Principal('integration-test','isolated-'+str(uuid.uuid4()),frozenset({'scout:preview','scout:import','scout:read'}))
        service=ImportService(repo,TokenSigner(os.urandom(32)),'TEST')
        p=Package.from_bytes(raw(handoff('pg-'+str(uuid.uuid4()))))
        pre=service.preview(p,actor)
        first=service.commit(p,actor,pre['confirmation_token'],True,'TEST')
        second=service.commit(p,actor,pre['confirmation_token'],True,'TEST')
        self.assertEqual(first,second)
        self.assertEqual(service.receipt(p.run_key,actor),first)
