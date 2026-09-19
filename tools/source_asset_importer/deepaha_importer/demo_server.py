"""Loopback-only development server. Never use wsgiref as a public production server."""
import argparse
import os
from wsgiref.simple_server import make_server
from .config import default_data_dir
from .demo import demo_client
from .http_api import WSGIApplication, BearerAuthenticator


def main():
    p = argparse.ArgumentParser(description='Local DEMO HTTP server only')
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--data-dir', default=str(default_data_dir() / 'http-demo'))
    a = p.parse_args()
    token = os.environ.get('DEEPAHA_IMPORT_DEMO_TOKEN', '')
    if len(token) < 24:
        raise SystemExit('Set DEEPAHA_IMPORT_DEMO_TOKEN to a local random value of at least 24 characters. Never send it in chat.')
    local = demo_client(a.data_dir)
    app = WSGIApplication(local.service, BearerAuthenticator([(token, local.principal)]))
    with make_server('127.0.0.1', a.port, app) as server:
        print(f'DEMO ONLY: http://127.0.0.1:{server.server_port} (Ctrl+C to stop)')
        server.serve_forever()

if __name__ == '__main__': main()
