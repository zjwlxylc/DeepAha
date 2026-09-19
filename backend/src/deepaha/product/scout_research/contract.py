"""Strict Handoff reader and explicit executable profile of Scout v2.2.

No fetching, code execution, semantic repair, source approval or database access.
Raw bytes remain authoritative. Aliases only normalize spelling; conflicts fail.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, urlunsplit

from .errors import ImporterError

SCHEMA = 'deepaha.source-intelligence.run.v2.2'
PROFILE = 'deepaha.source-intelligence.import-profile.v1'
MAX_JSON = 8 * 1024 * 1024
MAX_FILE = 20 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
MAX_DEPTH = 48
MAX_ITEMS = 20000
ARRAY_KINDS = {
    'source_candidates': 'source', 'agent_acquisition_briefs': 'brief',
    'research_evidence': 'evidence', 'source_graph_delta': 'graph',
    'demand_map': 'demand', 'demand_delta': 'demand_delta',
    'lifecycle_delta': 'lifecycle', 'pattern_delta': 'pattern',
    'blind_spots': 'blind_spot', 'next_exploration_queue': 'queue',
    'manual_review_manifest': 'manual_review',
}
META_REQUIRED = {
    'run_key', 'prompt_version', 'generated_at', 'run_mode', 'state_inheritance',
    'prior_state_ref', 'prior_run_at', 'baseline_refs', 'state_scope', 'system_feedback',
    'import_receipt_ref', 'delivery_mode', 'submission_status', 'result_status',
    'package_complete', 'limitations',
}
SOURCE_REQUIRED = {
    'candidate_key', 'legacy_id', 'system_source_id', 'institution', 'source_name',
    'recommended_seed', 'source_role', 'authority_assessment', 'demand_themes',
    'opportunity_types', 'target_youth', 'value_assessment', 'score_breakdown',
    'score_total', 'recommendation', 'recon_status', 'first_seen_at', 'last_checked_at',
    'evidence_refs', 'uncertainties', 'proposed_operation',
}
BRIEF_REQUIRED = {
    'source_ref', 'brief_key', 'revision', 'base_revision', 'recommended_seed',
    'source_topology', 'opportunity_pattern', 'navigation_advice', 'discovery_strategy',
    'source_network', 'evidence_hotspots', 'attachment_pattern', 'change_pattern',
    'observed_access_shape', 'agent_capability_needs', 'known_obstacles',
    'stop_escalation_rule', 'expected_candidate_evidence_package',
    'suggested_revisit_pattern', 'scout_confidence', 'recon_evidence', 'last_checked_at',
}
KEY_FIELDS = {'source': 'candidate_key', 'brief': 'brief_key', 'evidence': 'evidence_key',
              'graph': 'edge_key', 'demand': 'demand_key', 'pattern': 'pattern_key',
              'lifecycle': 'proposal_key', 'queue': 'queue_key'}
SECRETS = {'api_key', 'password', 'access_token', 'refresh_token', 'authorization',
           'cookie', 'cookies', 'database_password', 'private_key', 'worker_token'}
ALIASES = {'stop_escalation_rule': 'stop_escalation_rule',
           'expected_candidateevidencepackage': 'expected_candidate_evidence_package',
           'expected_evidence_package': 'expected_candidate_evidence_package',
           'source_role_authority': 'source_role_authority',
           'scout_confidence_high_medium_low': 'scout_confidence',
           'page_title': 'title', 'public_url': 'url', 'verification_time': 'checked_at',
           'observed_at': 'checked_at', 'supported_observation': 'observation',
           'source': 'from_ref', 'target': 'to_ref'}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(data) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def fail(message: str, code='INVALID_HANDOFF'):
    raise ImporterError(code, message, 422)


def parse_json(raw: bytes, limit: int = MAX_JSON):
    if not isinstance(raw, bytes) or len(raw) > limit:
        fail('JSON 超过允许大小或不是字节输入。', 'SIZE_LIMIT')

    def pairs(items):
        obj = {}
        for key, value in items:
            if key in obj:
                fail('JSON 包含重复字段，拒绝按后值覆盖。', 'DUPLICATE_JSON_KEY')
            obj[key] = value
        return obj

    def constant(_):
        fail('JSON 不能包含 NaN 或 Infinity。', 'NONFINITE_NUMBER')

    try:
        data = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ImporterError('INVALID_JSON', '无法完整解析 UTF-8 JSON。', 422) from exc
    stack = [(data, 0)]
    count = 0
    while stack:
        value, depth = stack.pop(); count += 1
        if depth > MAX_DEPTH or count > 300000:
            fail('JSON 嵌套或节点数超过安全限制。', 'STRUCTURE_LIMIT')
        if isinstance(value, dict):
            for key, item in value.items():
                try:
                    key.encode('utf-8')
                except UnicodeError:
                    fail('JSON 字段名包含无效 Unicode。')
                if re.sub(r'[^a-z0-9_]+', '_', key.casefold()).strip('_') in SECRETS:
                    fail('交付包包含敏感凭据字段，请先移除。', 'SECRET_FIELD')
                stack.append((item, depth + 1))
        elif isinstance(value, list):
            stack.extend((x, depth + 1) for x in value)
        elif isinstance(value, float) and not math.isfinite(value):
            fail('JSON 数值必须有限。', 'NONFINITE_NUMBER')
        elif isinstance(value, str):
            try:
                value.encode('utf-8')
            except UnicodeError:
                fail('JSON 包含无效 Unicode。')
    return data


def require_keys(value, keys: set[str], label: str):
    if not isinstance(value, dict):
        fail(f'{label} 必须是 JSON 对象。')
    missing = sorted(keys - value.keys())
    if missing:
        fail(f'{label} 缺少字段：' + ', '.join(missing))


def text(value, label: str, max_len=4096) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_len:
        fail(f'{label} 必须是非空文本且不超过 {max_len} 字符。')
    if any(ord(c) < 32 for c in value):
        fail(f'{label} 包含控制字符。')
    return value


def timestamp(value, label: str, nullable=False):
    if value is None and nullable:
        return
    text(value, label, 100)
    try:
        d = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if d.tzinfo is None or d.utcoffset() is None:
            raise ValueError
    except ValueError as exc:
        raise ImporterError('INVALID_TIMESTAMP', f'{label} 必须包含日期、时间和时区。', 422) from exc


def canonical_url(value: str) -> str:
    text(value, '公开 URL')
    try:
        u = urlsplit(value)
        host = u.hostname
        if u.scheme.lower() not in {'http', 'https'} or not host or u.username or u.password:
            fail('来源 URL 必须是无凭据的公开 HTTP(S) 地址。', 'UNSAFE_URL')
        if any(c.isspace() for c in value) or '\\' in value or '%' in host:
            fail('URL 含有不安全字符。', 'UNSAFE_URL')
        host = host.encode('idna').decode('ascii').lower().rstrip('.')
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            if ('.' not in host or host.endswith(('.localhost', '.local', '.internal'))
                    or re.fullmatch(r'[0-9.]+', host)
                    or len(host) > 253
                    or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in host.split('.'))):
                fail('拒绝本地或内部网络来源地址。', 'UNSAFE_URL')
        else:
            if not addr.is_global:
                fail('拒绝本地或内部 IP 来源地址。', 'UNSAFE_URL')
        port = u.port
        netloc = f'[{host}]' if ':' in host else host
        if port is not None and not (u.scheme.lower() == 'https' and port == 443
                                     or u.scheme.lower() == 'http' and port == 80):
            netloc += f':{port}'
        return urlunsplit((u.scheme.lower(), netloc, u.path or '/', u.query, u.fragment))
    except (ValueError, UnicodeError) as exc:
        raise ImporterError('UNSAFE_URL', '来源 URL 格式无效。', 422) from exc


def normalize_fields(record: dict) -> dict:
    output = {}
    for key, value in record.items():
        k = re.sub(r'[^a-z0-9_]+', '_', key.casefold()).strip('_') if key.isascii() else key
        k = ALIASES.get(k, k)
        if k in output and output[k] != value:
            fail('字段别名发生冲突，不能选择性覆盖。', 'ALIAS_CONFLICT')
        output[k] = value
    return output


def revision(value):
    if value is None:
        return None
    if type(value) not in (int, str) or not str(value).strip() or len(str(value)) > 120:
        fail('revision 必须是整数、非空文本或 null。')
    return str(value)


def reference(value) -> str:
    if isinstance(value, dict):
        values = [value[k] for k in ('candidate_key', 'evidence_key', 'brief_key', 'ref') if k in value]
        if len(values) != 1:
            fail('引用对象必须有一个明确的 candidate_key/evidence_key/brief_key/ref。')
        value = values[0]
    return text(value, '引用')


def ref_list(value, label) -> list[str]:
    if not isinstance(value, list):
        fail(f'{label} 必须是引用数组。')
    return [reference(v) for v in value]


@dataclass(frozen=True)
class Asset:
    kind: str
    key: str
    payload: dict
    external_revision: str | None = None
    base_revision: str | None = None
    system_base_revision: int | None = None
    identity: str | None = None

    @property
    def content_hash(self):
        # Observation time and external bookkeeping do not create semantic duplicates.
        ignored = {'base_revision', 'system_base_revision', 'revision', 'last_checked_at',
                   'first_seen_at', 'proposed_operation', 'candidate_key'} if self.kind == 'source' else {'base_revision', 'system_base_revision'}
        return digest(canonical_json({k: v for k, v in self.payload.items() if k not in ignored}))


@dataclass(frozen=True)
class Package:
    raw: bytes
    files: tuple[tuple[str, bytes], ...] = ()

    @classmethod
    def from_bytes(cls, raw: bytes, files=()) -> 'Package':
        p = cls(raw, tuple(sorted(files)))
        p.validate()
        return p

    @property
    def data(self) -> dict:
        return parse_json(self.raw)

    @property
    def run_key(self) -> str:
        return self.data['run_metadata']['run_key']

    @property
    def sha256(self) -> str:
        return digest(self.raw)

    @property
    def package_hash(self) -> str:
        return digest(canonical_json({'handoff_sha256': self.sha256,
                                      'files': [(name, digest(blob)) for name, blob in self.files]}))

    @classmethod
    def from_file(cls, path: str | Path) -> 'Package':
        path = Path(path).expanduser()
        if not path.is_file() or path.suffix.lower() != '.json':
            fail('请选择实际存在的 Handoff.json 文件。', 'FILE_NOT_FOUND')
        if path.stat().st_size > MAX_JSON:
            fail('Handoff JSON 过大。', 'SIZE_LIMIT')
        raw = path.read_bytes(); data = parse_json(raw)
        require_keys(data, {'run_metadata'}, 'Handoff')
        require_keys(data['run_metadata'], META_REQUIRED, 'run_metadata')
        dependencies = data['run_metadata'].get('file_dependencies', [])
        if not isinstance(dependencies, list) or len(dependencies) > 100:
            fail('file_dependencies 必须是不超过 100 项的清单。')
        root = path.resolve().parent
        files = []
        for dep in dependencies:
            name = safe_name(dep.get('relative_path') if isinstance(dep, dict) else None)
            child = root / name
            # Do not allow symlinks (even when currently pointing inside the allowed root).
            cursor = root
            for part in PurePosixPath(name).parts:
                cursor = cursor / part
                if cursor.is_symlink():
                    fail('依赖文件或目录不能是符号链接。', 'UNSAFE_PATH')
            if not child.resolve().is_relative_to(root) or not child.is_file():
                fail('必需依赖文件不存在或超出所选目录。', 'MISSING_DEPENDENCY')
            if child.stat().st_size > MAX_FILE:
                fail('依赖文件过大。', 'SIZE_LIMIT')
            files.append((name, child.read_bytes()))
        return cls.from_bytes(raw, files)

    def assets(self, kind: str | None = None) -> list[Asset]:
        data = self.data; out = []
        for section, asset_kind in ARRAY_KINDS.items():
            if kind is not None and kind != asset_kind:
                continue
            for record in data[section]:
                r = normalize_fields(record) if isinstance(record, dict) else {'text': record}
                key_field = KEY_FIELDS.get(asset_kind, 'asset_key')
                key = r.get(key_field)
                if key is None:
                    key = asset_kind + ':' + digest(canonical_json(r))
                identity = None
                if asset_kind == 'source':
                    institution = unicodedata.normalize('NFKC', r['institution']).strip().casefold()
                    identity = digest(canonical_json([institution, canonical_url(r['recommended_seed'])]))
                out.append(Asset(asset_kind, key, r, revision(r.get('revision')),
                                 revision(r.get('base_revision')), r.get('system_base_revision'), identity))
        return out

    def references(self) -> set[tuple[str, str]]:
        out = set()
        for a in self.assets():
            r = a.payload
            for k in ('evidence_refs', 'recon_evidence'):
                if k in r:
                    out.update(('evidence', ref) for ref in ref_list(r[k], k))
            if a.kind == 'brief':
                out.add(('source', reference(r['source_ref'])))
            if a.kind == 'graph':
                out.add(('source', reference(r['from_ref'])))
                out.add(('source', reference(r['to_ref'])))
            if a.kind == 'lifecycle':
                out.add((r.get('entity_type', 'source'), reference(r['entity_ref'])))
                for key in ('replacement_ref', 'merge_target'):
                    if r.get(key) is not None:
                        out.add(('source', reference(r[key])))
        return out

    def validate(self):
        data = self.data
        require_keys(data, set(ARRAY_KINDS) | {'schema_version', 'run_metadata', 'state_snapshot_ref', 'metrics', 'warnings'}, 'Handoff')
        allowed = set(ARRAY_KINDS) | {'schema_version', 'run_metadata', 'state_snapshot_ref', 'metrics', 'warnings'}
        if data.keys() - allowed:
            fail('Handoff 出现未支持的顶层字段；请按导入协议适配，不会静默丢弃。')
        if data['schema_version'] != SCHEMA:
            fail('当前只支持 deepaha.source-intelligence.run.v2.2。', 'UNSUPPORTED_SCHEMA')
        meta = data['run_metadata']; require_keys(meta, META_REQUIRED, 'run_metadata')
        if not ('run_mode_reason' in meta or 'reason' in meta):
            fail('run_metadata 缺少 run_mode_reason。')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}', text(meta['run_key'], 'run_key', 120)):
            fail('run_key 只允许字母、数字、点、横线、下划线。')
        timestamp(meta['generated_at'], 'generated_at')
        timestamp(meta['prior_run_at'], 'prior_run_at', True)
        if meta['delivery_mode'] != 'MANUAL_EXPORT_ONLY' or meta['submission_status'] != 'NOT_SUBMITTED':
            fail('只接受人工交接且导出时尚未提交的原始资产包。', 'BAD_DELIVERY_STATE')
        if meta['package_complete'] is not True:
            fail('资产包不完整，不能提交；请先补齐必需文件和字段。', 'INCOMPLETE_PACKAGE')
        if meta['state_inheritance'] not in {'PASS', 'PARTIAL', 'UNAVAILABLE', 'CORRUPT'}:
            fail('未知 state_inheritance。')
        if meta['result_status'] not in {'COMPLETE', 'PARTIAL', 'STANDALONE_RESEARCH_RESULT'}:
            fail('未知 result_status。')
        if meta['run_mode'] not in {'NORMAL_REFRESH', 'EXPLORATION_BURST', 'HYGIENE_REVIEW', 'TARGETED_RECON'}:
            fail('未知 run_mode。')
        if not isinstance(data['metrics'], dict) or not isinstance(data['warnings'], list):
            fail('metrics 必须为对象，warnings 必须为数组。')
        if not isinstance(meta['baseline_refs'], list) or not isinstance(meta['limitations'], list):
            fail('baseline_refs 和 limitations 必须为数组。')
        count = 0
        for section in ARRAY_KINDS:
            if not isinstance(data[section], list):
                fail(f'{section} 必须是数组。')
            count += len(data[section])
            for r in data[section]:
                if not isinstance(r, dict) and not (section in {'blind_spots', 'next_exploration_queue'} and isinstance(r, str)):
                    fail(f'{section} 中每项必须为对象（盲区/队列也允许文本）。')
        if count > MAX_ITEMS:
            fail('资产条目数超过单批限制。', 'SIZE_LIMIT')
        # Check record structure before computing identities or references.
        for original in data['source_candidates']:
            r = normalize_fields(original); require_keys(r, SOURCE_REQUIRED, 'source_candidates')
            for k in ('candidate_key', 'institution', 'source_name', 'recommended_seed'):
                text(r[k], k)
            canonical_url(r['recommended_seed'])
            if not isinstance(r['score_breakdown'], dict): fail('score_breakdown 必须是对象。')
            if not isinstance(r['authority_assessment'], (dict, str)): fail('authority_assessment 必须是对象或文本。')
            if not isinstance(r['value_assessment'], (dict, str)): fail('value_assessment 必须是对象或文本。')
            for id_field in ('system_source_id', 'legacy_id'):
                if r[id_field] is not None: text(r[id_field], id_field)
            ref_list(r['evidence_refs'], 'source.evidence_refs')
            if not r['evidence_refs']:
                fail('来源必须提供可解析的研究证据引用。')
            for k in ('demand_themes', 'opportunity_types', 'target_youth', 'uncertainties'):
                if not isinstance(r[k], list): fail(f'{k} 必须是数组。')
            timestamp(r['first_seen_at'], 'source.first_seen_at', True)
            timestamp(r['last_checked_at'], 'source.last_checked_at', True)
            if r['recommendation'] not in {'PRIORITY_ADD', 'EXPLORE', 'WATCH', 'DEFER', 'REJECT'}:
                fail('未知来源推荐值。')
            if r['proposed_operation'] not in {None, 'ADD', 'UPDATE', 'DOWNGRADE', 'MERGE', 'SUPERSEDE', 'RETIRE', 'REJECT', 'NO_CHANGE'}:
                fail('未知生命周期建议。')
            if r['score_total'] is not None and (type(r['score_total']) not in (int, float) or not 0 <= r['score_total'] <= 100):
                fail('score_total 必须为 0–100 或 null。')
        for original in data['agent_acquisition_briefs']:
            r = normalize_fields(original); require_keys(r, BRIEF_REQUIRED, 'AgentAcquisitionBrief')
            if not ({'source_role', 'authority'} <= r.keys() or 'source_role_authority' in r):
                fail('Brief 需提供 source_role 与 authority，或 source_role_authority。')
            canonical_url(r['recommended_seed']); reference(r['source_ref'])
            timestamp(r['last_checked_at'], 'brief.last_checked_at', True)
            ref_list(r['recon_evidence'], 'brief.recon_evidence')
            if not r['recon_evidence']: fail('Brief 需要至少一条可解析的侦察证据引用。')
        for original in data['research_evidence']:
            r = normalize_fields(original)
            require_keys(r, {'evidence_key', 'url', 'title', 'checked_at', 'observation', 'locator'}, 'research_evidence')
            canonical_url(r['url']); timestamp(r['checked_at'], 'evidence.checked_at')
            for k in ('evidence_key', 'title', 'observation'):
                if not isinstance(r[k], str) or not r[k].strip(): fail(f'evidence.{k} 必须是非空文本。')
        for original in data['source_graph_delta']:
            r = normalize_fields(original)
            require_keys(r, {'from_ref', 'to_ref', 'edge_type', 'evidence_refs', 'confidence'}, 'source_graph_delta')
        for original in data['lifecycle_delta']:
            r = normalize_fields(original)
            require_keys(r, {'entity_ref', 'operation', 'reason', 'evidence_refs', 'confidence'}, 'lifecycle_delta')
            if r.get('entity_type', 'source') not in {'source', 'brief'}:
                fail('生命周期 entity_type 只支持 source / brief。')
        seen = set()
        for a in self.assets():
            text(a.key, a.kind + ' key')
            if (a.kind, a.key) in seen: fail('同批资产键重复。', 'DUPLICATE_ASSET_KEY')
            seen.add((a.kind, a.key))
            if a.system_base_revision is not None and (type(a.system_base_revision) is not int or a.system_base_revision < 1):
                fail('system_base_revision 只能是实际系统正整数版本。')
        self.references()
        declared = meta.get('file_dependencies', [])
        if not isinstance(declared, list) or len(declared) > 100:
            fail('file_dependencies 必须是不超过 100 项的清单。')
        found = dict(self.files)
        if len(found) != len(self.files): fail('依赖文件重名。')
        expected = set(); total = len(self.raw)
        for item in declared:
            require_keys(item, {'relative_path', 'sha256', 'size_bytes'}, 'file_dependencies')
            name = safe_name(item['relative_path'])
            if name in expected: fail('依赖清单有重复路径。')
            expected.add(name)
            if name not in found: fail('缺少清单中的必需依赖文件。', 'MISSING_DEPENDENCY')
            blob = found[name]; total += len(blob)
            if len(blob) > MAX_FILE or total > MAX_TOTAL: fail('依赖文件超过大小限制。', 'SIZE_LIMIT')
            if type(item['size_bytes']) is not int or item['size_bytes'] != len(blob) or item['sha256'] != digest(blob):
                fail('依赖文件的实际字节数或 SHA-256 不一致。', 'DEPENDENCY_HASH_MISMATCH')
        if set(found) != expected:
            fail('发现未在清单声明的附件，不会擅自上传。', 'UNDECLARED_DEPENDENCY')


def safe_name(value) -> str:
    text(value, 'relative_path', 240)
    p = PurePosixPath(value)
    if p.is_absolute() or any(x in {'..', '.'} for x in value.split('/')) or '\\' in value or ':' in value or '//' in value:
        fail('依赖路径必须是无跳级、无盘符的相对路径。', 'UNSAFE_PATH')
    return value
