"""Exercise real HTTP failure recovery, not a mock that merely returns success."""
import tempfile
import threading
import unittest
from pathlib import Path
from wsgiref.simple_server import make_server
from deepaha_importer.client import ClientConfig, RemoteClient
from deepaha_importer.contract import Package, canonical_json
from deepaha_importer.demo import demo_client
from deepaha_importer.errors import ImporterError
from deepaha_importer.http_api import WSGIApplication, BearerAuthenticator, API_PREFIX
from tests.helpers import raw, handoff


class RecoveryTests(unittest.TestCase):
    def server(self, app):
        server=make_server('127.0.0.1',0,app)
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return 'http://127.0.0.1:'+str(server.server_port)

    def test_commit_response_failure_recovers_without_second_write(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        local=demo_client(Path(temp.name)); token='test-only-'+('x'*40)
        base=WSGIApplication(local.service,BearerAuthenticator([(token,local.principal)]))
        writes=[]
        def loss_after_commit(environ,start_response):
            captured=[]
            def capture(status,headers,exc_info=None): captured.append((status,headers))
            body=b''.join(base(environ,capture))
            if environ['PATH_INFO']==API_PREFIX+'/commit':
                writes.append(1)
                payload=canonical_json({'error':{'code':'REPLY_LOST','message':'synthetic transport fault','details':[]}})
                start_response('503 Service Unavailable',[('Content-Type','application/json'),('Content-Length',str(len(payload)))])
                return [payload]
            start_response(*captured[0]); return [body]
        url=self.server(loss_after_commit)
        c=RemoteClient(ClientConfig(url,'DEMO',allow_http_loopback=True),token)
        p=Package.from_bytes(raw(handoff('lost-response-demo')))
        v=c.preview(p); r=c.commit(p,v,True)
        self.assertEqual(r['status'],'DEMO_IMPORTED')
        self.assertEqual(len(writes),1)
        self.assertEqual(c.receipt(p),r)

    def test_redirect_never_forwards_authorization(self):
        calls=[]
        def redirect(environ,start_response):
            calls.append(environ['PATH_INFO'])
            start_response('302 Found',[('Location','http://127.0.0.1:1/credential-leak'),('Content-Length','0')])
            return [b'']
        url=self.server(redirect)
        c=RemoteClient(ClientConfig(url,'DEMO',allow_http_loopback=True),'test-only-'+'x'*40)
        with self.assertRaises(ImporterError) as e: c.capabilities()
        self.assertEqual(e.exception.code,'REDIRECT_BLOCKED')
        self.assertEqual(len(calls),1)
