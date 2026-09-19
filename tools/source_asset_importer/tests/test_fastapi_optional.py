import importlib.util
import tempfile
import unittest
from pathlib import Path
from deepaha_importer.contract import Package
from deepaha_importer.client import envelope
from deepaha_importer.demo import demo_client
from tests.helpers import raw

AVAILABLE=bool(importlib.util.find_spec('fastapi') and importlib.util.find_spec('httpx'))

@unittest.skipUnless(AVAILABLE,'可选 FastAPI/httpx 依赖未安装')
class FastAPITests(unittest.TestCase):
    def test_existing_app_mount_and_real_import(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from deepaha_importer.fastapi_adapter import create_router
        from deepaha_importer.http_api import API_PREFIX
        with tempfile.TemporaryDirectory() as td:
            local=demo_client(Path(td))
            app=FastAPI()
            # Simulated host auth only; database and importer use actual implementation.
            def authenticated_test_user(): return local.principal
            app.include_router(create_router(local.service, authenticated_test_user))
            with TestClient(app) as c:
                cap=c.get(API_PREFIX+'/capabilities'); self.assertEqual(cap.status_code,200,cap.text)
                p=Package.from_bytes(raw())
                body=envelope(p)|{'expected_environment':'DEMO','approve_sources':[]}
                v=c.post(API_PREFIX+'/preview',json=body); self.assertEqual(v.status_code,200,v.text)
                body|={'confirmation_token':v.json()['confirmation_token'],'confirmed':True}
                r=c.post(API_PREFIX+'/commit',json=body); self.assertEqual(r.status_code,200,r.text)
                receipt=c.get(API_PREFIX+'/batches/by-run/'+p.run_key)
                self.assertEqual(r.json(),receipt.json())
