"""Versioned, narrow import API; no arbitrary SQL, file fetch, publish or scheduler."""
from __future__ import annotations
import base64
import hashlib
import hmac
import logging
import re
from http import HTTPStatus
from urllib.parse import unquote
from .contract import Package, MAX_TOTAL, canonical_json, parse_json, require_keys
from .errors import ImporterError

API_PREFIX = '/api/scout-import/v1'
MAX_BODY = 92 * 1024 * 1024
log = logging.getLogger(__name__)


class BearerAuthenticator:
    """Reference identity mapping. Production should inject its existing auth dependency.

    Tokens are supplied by environment/host, never by Handoff or source code.
    Only hashes are retained after construction; no token is logged.
    """
    def __init__(self, credentials):
        self._credentials = []
        for token, principal in credentials:
            if not isinstance(token, str) or len(token) < 24 or any(c.isspace() for c in token):
                raise ValueError('Reference API credentials require at least 24 non-space characters')
            self._credentials.append((hashlib.sha256(token.encode()).digest(), principal))
        if not self._credentials: raise ValueError('No credentials configured')

    def __call__(self, authorization: str):
        if not isinstance(authorization, str) or not authorization.startswith('Bearer ') or len(authorization) > 8192:
            raise ImporterError('UNAUTHORIZED', '需要有效的导入授权。', 401)
        incoming = hashlib.sha256(authorization[7:].encode()).digest()
        for expected, principal in self._credentials:
            if hmac.compare_digest(expected, incoming): return principal
        raise ImporterError('UNAUTHORIZED', '导入授权无效或已撤销。', 401)


def decode_package(body):
    require_keys(body, {'handoff_b64', 'files'}, 'HTTP请求')
    if not isinstance(body['handoff_b64'], str) or not isinstance(body['files'], list) or len(body['files']) > 100:
        raise ImporterError('BAD_REQUEST', '交付包传输结构错误。', 422)
    try:
        raw = base64.b64decode(body['handoff_b64'], validate=True)
        files = []
        total = len(raw)
        for file in body['files']:
            require_keys(file, {'relative_path', 'content_b64'}, 'HTTP附件')
            if set(file) != {'relative_path', 'content_b64'}: raise ValueError
            blob = base64.b64decode(file['content_b64'], validate=True)
            total += len(blob)
            if total > MAX_TOTAL: raise ImporterError('SIZE_LIMIT', '传输包超过总大小限制。', 413)
            files.append((file['relative_path'], blob))
    except (ValueError, TypeError) as exc:
        raise ImporterError('BAD_ENCODING', '交付文件编码无效。', 422) from exc
    return Package.from_bytes(raw, files)


class Router:
    def __init__(self, service): self.service = service

    def dispatch(self, method, path, body, principal):
        if method == 'GET' and path == '/capabilities':
            return self.service.capabilities(principal)
        if method == 'GET' and path.startswith('/batches/by-run/'):
            run_key = unquote(path[len('/batches/by-run/'):])
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}', run_key):
                raise ImporterError('BAD_RUN_KEY', '批次键无效。', 422)
            return self.service.receipt(run_key, principal)
        if method == 'POST' and path in {'/preview', '/commit'}:
            principal.require('scout:preview' if path == '/preview' else 'scout:import')
            allowed = {'handoff_b64', 'files', 'expected_environment', 'approve_sources'}
            if path == '/commit': allowed |= {'confirmation_token', 'confirmed'}
            require_keys(body, allowed, 'HTTP请求')
            if set(body) != allowed:
                raise ImporterError('UNSUPPORTED_REQUEST_FIELD', '请求含有未支持字段，不能由客户端指定身份或权限。', 422)
            if body['expected_environment'] != self.service.environment:
                raise ImporterError('ENVIRONMENT_MISMATCH', '请求目标环境与服务端不一致。', 409)
            package = decode_package(body)
            if path == '/preview':
                return self.service.preview(package, principal, body['approve_sources'])
            return self.service.commit(package, principal, body['confirmation_token'], body['confirmed'],
                                       body['expected_environment'], body['approve_sources'])
        raise ImporterError('NOT_FOUND', '该接口不存在；本服务仅处理人工来源情报导入。', 404)


class WSGIApplication:
    """Mountable WSGI adapter. The bundled wsgiref server is loopback DEMO only."""
    def __init__(self, service, authenticator, prefix=API_PREFIX):
        self.router, self.authenticator, self.prefix = Router(service), authenticator, prefix

    def __call__(self, environ, start_response):
        status = 200
        try:
            path = environ.get('PATH_INFO', '')
            if not path.startswith(self.prefix + '/'):
                raise ImporterError('NOT_FOUND', '接口不存在。', 404)
            principal = self.authenticator(environ.get('HTTP_AUTHORIZATION', ''))
            method = environ.get('REQUEST_METHOD', '')
            body = {}
            if method == 'POST':
                if environ.get('CONTENT_TYPE', '').split(';')[0].strip() != 'application/json':
                    raise ImporterError('CONTENT_TYPE', '请求需使用 application/json。', 415)
                try: size = int(environ.get('CONTENT_LENGTH', ''))
                except ValueError: raise ImporterError('LENGTH_REQUIRED', '需要有效 Content-Length。', 411)
                if not 0 < size <= MAX_BODY:
                    raise ImporterError('SIZE_LIMIT', '请求体为空或超过限制。', 413)
                raw = environ['wsgi.input'].read(size)
                if len(raw) != size: raise ImporterError('TRUNCATED_BODY', '请求体不完整。', 400)
                body = parse_json(raw, MAX_BODY)
            result = self.router.dispatch(method, path[len(self.prefix):], body, principal)
        except ImporterError as exc:
            status, result = exc.status, exc.as_dict()
        except Exception as exc:
            # Avoid logging exception text: SQL/driver exceptions may contain request parameters.
            log.error('Importer internal exception type=%s', type(exc).__name__)
            status = 500
            result = ImporterError('SERVER_ERROR', '服务端无法确认本次结果；请查询批次回执，勿盲目重复提交。', 500).as_dict()
        response = canonical_json(result)
        headers = [('Content-Type', 'application/json; charset=utf-8'), ('Content-Length', str(len(response))),
                   ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff')]
        if status == 401: headers.append(('WWW-Authenticate', 'Bearer'))
        start_response(f'{status} {HTTPStatus(status).phrase}', headers)
        return [response]
