"""Local/remote clients. TLS verification stays enabled; redirects never followed."""
from __future__ import annotations
import base64
import socket
import ssl
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler
from .contract import Package, canonical_json, parse_json, require_keys
from .errors import ImporterError
from .http_api import API_PREFIX, MAX_BODY


@dataclass(frozen=True)
class ClientConfig:
    base_url: str
    expected_environment: str = 'STAGING'
    expected_target_id: str | None = None
    allow_http_loopback: bool = False
    timeout_seconds: int = 45
    ca_file: str | None = None

    def validate(self):
        try:
            u = urlsplit(self.base_url)
            if not u.hostname or u.username or u.password or u.query or u.fragment or '\\' in self.base_url or any(c.isspace() for c in self.base_url):
                raise ValueError
            if u.scheme != 'https' and not (u.scheme == 'http' and self.allow_http_loopback and u.hostname in {'127.0.0.1', '::1', 'localhost'}):
                raise ValueError
            if self.expected_environment not in {'DEMO', 'TEST', 'STAGING', 'PRODUCTION'}: raise ValueError
            if type(self.timeout_seconds) is not int or not 1 <= self.timeout_seconds <= 300: raise ValueError
            if self.expected_environment == 'PRODUCTION' and u.scheme != 'https': raise ValueError
            _ = u.port
        except (ValueError, TypeError) as exc:
            raise ImporterError('UNSAFE_SERVER_CONFIG', '请配置无凭据的 HTTPS 服务地址；明文 HTTP 仅限显式允许的本机演练。', 400) from exc


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ImporterError('REDIRECT_BLOCKED', '服务器发生重定向，已停止，避免把授权发送到其他地址。', 502)


def envelope(package: Package):
    return {'handoff_b64': base64.b64encode(package.raw).decode('ascii'),
            'files': [{'relative_path': n, 'content_b64': base64.b64encode(b).decode('ascii')} for n, b in package.files]}


def check_receipt(receipt, package, environment, target_id=None):
    required = {'schema_version', 'receipt_key', 'run_key', 'batch_id', 'environment', 'package_hash',
                'handoff_sha256', 'target_id', 'items', 'status', 'approved_source_keys'}
    require_keys(receipt, required, '服务器回执')
    if receipt['schema_version'] != 'deepaha.source-intelligence.import-receipt.v1' or receipt['environment'] != environment or receipt['run_key'] != package.run_key or receipt['package_hash'] != package.package_hash or receipt['handoff_sha256'] != package.sha256:
        raise ImporterError('RECEIPT_MISMATCH', '回执与本次文件或环境不一致，不能视为已确认成功。', 502)
    if target_id and target_id != receipt['target_id']:
        raise ImporterError('TARGET_MISMATCH', '回执来自不同存储目标。', 502)
    expected_status = 'IMPORTED' if environment == 'PRODUCTION' else environment + '_IMPORTED'
    if receipt['status'] != expected_status or not isinstance(receipt['items'], list):
        raise ImporterError('RECEIPT_MISMATCH', '回执未证明该环境已完成导入。', 502)
    return receipt


class RemoteClient:
    def __init__(self, config: ClientConfig, token: str):
        config.validate()
        if not isinstance(token, str) or not token or any(c.isspace() for c in token):
            raise ImporterError('TOKEN_REQUIRED', '请在本机输入导入授权；不要把凭据发到聊天。', 401)
        self.config, self._token = config, token
        context = ssl.create_default_context(cafile=config.ca_file)
        self.opener = build_opener(HTTPSHandler(context=context), NoRedirect())
        self._caps = None

    @property
    def environment(self): return self.config.expected_environment

    def _request(self, method, path, data=None):
        body = canonical_json(data) if data is not None else None
        if body and len(body) > MAX_BODY: raise ImporterError('SIZE_LIMIT', '传输包过大。', 413)
        url = self.config.base_url.rstrip('/') + API_PREFIX + path
        request = Request(url, data=body, method=method,
                          headers={'Authorization': 'Bearer ' + self._token, 'Content-Type': 'application/json',
                                   'Accept': 'application/json', 'User-Agent': 'DeepAha-Source-Importer/0.2.0'})
        try:
            with self.opener.open(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read(MAX_BODY + 1)
                if len(raw) > MAX_BODY: raise ImporterError('RESPONSE_TOO_LARGE', '服务端响应超过限制。', 502)
                if response.headers.get_content_type() != 'application/json':
                    raise ImporterError('UNEXPECTED_RESPONSE', '服务端返回的不是导入协议 JSON。', 502)
                return parse_json(raw, MAX_BODY)
        except HTTPError as exc:
            try:
                error = parse_json(exc.read(1024 * 1024), 1024 * 1024)['error']
                message = error.get('message', '请求被拒绝。')
                code = error.get('code', 'HTTP_ERROR')
                details = error.get('details', [])
            except Exception:
                message, code, details = '服务器拒绝请求，请检查地址、权限或服务状态。', 'HTTP_ERROR', []
            raise ImporterError(code, message, exc.code, details) from None
        except (URLError, TimeoutError, socket.timeout, OSError) as exc:
            raise ImporterError('NETWORK_ERROR', '网络连接失败或超时；提交阶段可能已完成，请查询批次回执。', 503) from exc

    def capabilities(self):
        cap = self._request('GET', '/capabilities')
        require_keys(cap, {'api_contract', 'environment', 'target_id', 'producer', 'subject', 'can_import', 'supports_source_approval'}, '服务能力')
        if cap['api_contract'] != 'deepaha.scout-import.api.v1' or cap['environment'] != self.environment:
            raise ImporterError('ENVIRONMENT_MISMATCH', '服务协议或目标环境不匹配，尚未上传资产包。', 409)
        if self.config.expected_target_id and cap['target_id'] != self.config.expected_target_id:
            raise ImporterError('TARGET_MISMATCH', '服务器目标 ID 不匹配，尚未上传资产包。', 409)
        if self.environment == 'PRODUCTION' and cap.get('reference_backend', True):
            raise ImporterError('PRODUCTION_NOT_INTEGRATED', '服务仍是参考暂存后端，不能视为正式 DeepAha。', 409)
        self._caps = cap
        return cap

    def preview(self, package, approve_sources=None):
        cap = self.capabilities()
        data = envelope(package) | {'expected_environment': self.environment, 'approve_sources': approve_sources or []}
        result = self._request('POST', '/preview', data)
        require_keys(result, {'package_hash', 'run_key', 'environment', 'target_id', 'items', 'can_commit', 'confirmation_token', 'approve_sources'}, '预览')
        if result['package_hash'] != package.package_hash or result['run_key'] != package.run_key or result['environment'] != self.environment or result['target_id'] != cap['target_id']:
            raise ImporterError('PREVIEW_MISMATCH', '服务端预览与所选文件不一致。', 502)
        result['can_commit'] = bool(result['can_commit']) and cap['can_import'] is True
        return result

    def commit(self, package, preview, confirmed=False):
        if confirmed is not True or preview.get('can_commit') is not True:
            raise ImporterError('CONFIRMATION_REQUIRED', '必须完成有效预览并明确确认。', 400)
        if preview.get('package_hash') != package.package_hash:
            raise ImporterError('INPUT_CHANGED', '文件已变化，请重新预览。', 409)
        data = envelope(package) | {'expected_environment': self.environment,
                'approve_sources': preview['approve_sources'], 'confirmed': True,
                'confirmation_token': preview['confirmation_token']}
        try:
            response = self._request('POST', '/commit', data)
        except ImporterError as exc:
            if exc.status < 500: raise
            # Recovery only reads. Never auto-replay a write after an uncertain network result.
            try:
                recovered = self.receipt(package)
                if recovered['approved_source_keys'] != preview['approve_sources']:
                    raise ImporterError('RECEIPT_MISMATCH', '回执批准范围不一致。', 502)
                return recovered
            except ImporterError:
                raise ImporterError('SUBMISSION_UNKNOWN', '提交结果暂不能确认。请保留文件并点“查询/恢复回执”，不要改批次重传。', 503) from exc
        check_receipt(response, package, self.environment, preview['target_id'])
        try:
            persisted = self.receipt(package)
        except ImporterError as exc:
            raise ImporterError('READBACK_UNAVAILABLE', '提交响应已收到，但回执回读失败。请稍后查询回执，不要新建批次重传。', 503) from exc
        if canonical_json(response) != canonical_json(persisted):
            raise ImporterError('READBACK_MISMATCH', '提交响应与已保存回执不一致。', 502)
        return persisted

    def receipt(self, package):
        cap = self._caps or self.capabilities()
        result = self._request('GET', '/batches/by-run/' + quote(package.run_key, safe=''))
        return check_receipt(result, package, self.environment, cap['target_id'])


class LocalClient:
    """Same service, explicitly marked demo/test. No pretending to be production."""
    def __init__(self, service, principal):
        if service.environment not in {'DEMO', 'TEST'}:
            raise ImporterError('LOCAL_MODE_RESTRICTED', '本地直连入口仅供演练/测试，正式环境请走服务端接口。', 400)
        self.service, self.principal = service, principal

    @property
    def environment(self): return self.service.environment

    def capabilities(self): return self.service.capabilities(self.principal)

    def preview(self, package, approve_sources=None):
        return self.service.preview(package, self.principal, approve_sources)

    def commit(self, package, preview, confirmed=False):
        return self.service.commit(package, self.principal, preview['confirmation_token'], confirmed,
                                   self.environment, preview.get('approve_sources', []))

    def receipt(self, package):
        return check_receipt(self.service.receipt(package.run_key, self.principal), package, self.environment)
