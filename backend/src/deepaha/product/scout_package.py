"""Receive real Importer v0.3.1 exports. Client audit/decisions never grant authority."""
from __future__ import annotations

import io
import re
import stat
import tempfile
import zipfile
from pathlib import Path

from .errors import Problem
from .scout_research.contract import canonical_json, digest, parse_json
from .scout_research.errors import ImporterError
from .scout_research.research.ingest import Limits, load_inputs, safe_member
from .scout_research.research.audit import analyze

FORMAT = 'deepaha.research-handoff.v1'
RAW_FORMAT = 'deepaha.source-intelligence.run.v2.2'
MAX_UPLOAD = 100 * 1024 * 1024
MAX_GROUPS = 2000
MAX_VERSIONS = 10000


class Budget:
    def __init__(self, limits=None):
        self.limits = limits or Limits()
        self.members = 0
        self.expanded = 0

    def add(self, size):
        self.members += 1
        self.expanded += size
        if self.members > self.limits.members or self.expanded > self.limits.expanded_bytes:
            raise Problem('研究包展开内容超过保护上限，请拆分后上传', 413, 'SCOUT_PACKAGE_LIMIT')


def read_zip(raw: bytes, budget: Budget) -> dict[str, bytes]:
    out = {}
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            if len(z.infolist()) + budget.members > budget.limits.members:
                raise Problem('研究包成员过多', 413, 'SCOUT_PACKAGE_LIMIT')
            seen = set()
            # Check every declaration before decompression, including directory entries.
            for info in z.infolist():
                name = safe_member(info.filename.rstrip('/'))
                if name != info.filename.rstrip('/'):
                    raise Problem('压缩包路径有歧义', 400, 'UNSAFE_ARCHIVE_PATH')
                if name.casefold() in seen:
                    raise Problem('压缩包有重复或大小写冲突路径', 400, 'ZIP_DUPLICATE_PATH')
                seen.add(name.casefold())
                mode = (info.external_attr >> 16) & 0xffff
                if stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise Problem('压缩包包含链接或特殊文件', 400, 'UNSAFE_ARCHIVE_MEMBER')
                if info.flag_bits & 1:
                    raise Problem('不能读取加密研究包', 400, 'ENCRYPTED_ARCHIVE')
                if info.file_size > budget.limits.member_bytes or info.file_size / max(1, info.compress_size) > budget.limits.ratio:
                    raise Problem('压缩成员大小或压缩比超过上限', 413, 'SCOUT_PACKAGE_LIMIT')
                budget.add(info.file_size)
            # A malicious member cannot allocate beyond the already checked bound.
            for info in z.infolist():
                if info.is_dir():
                    continue
                with z.open(info) as f:
                    data = f.read(budget.limits.member_bytes + 1)
                if len(data) != info.file_size:
                    raise Problem('压缩成员读取不完整', 400, 'ARCHIVE_INCOMPLETE')
                out[info.filename] = data
    except ImporterError as exc:
        raise Problem(exc.message, exc.status, exc.code) from None
    except (zipfile.BadZipFile, RuntimeError, OSError, NotImplementedError, EOFError, ValueError):
        raise Problem('无法安全读取研究压缩包', 400, 'UNREADABLE_RESEARCH_ARCHIVE') from None
    return out


def _json(data):
    try:
        return parse_json(data, 8 * 1024 * 1024)
    except ImporterError as exc:
        raise Problem(exc.message, exc.status, exc.code) from None


def _inventory(rows, members, expected, code):
    if not isinstance(rows, list) or len(rows) > 10000:
        raise Problem('文件清单格式不正确', 400, code)
    indexed = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('path'), str):
            raise Problem('文件清单条目缺少路径', 400, code)
        name = row['path']
        if name in indexed or name not in members:
            raise Problem('文件清单包含重复或不存在的文件', 400, code)
        data = members[name]
        if type(row.get('size_bytes')) is not int or row['size_bytes'] != len(data) or row.get('sha256') != digest(data):
            raise Problem('研究包文件的哈希或大小与清单不符', 409, code)
        indexed[name] = row
    if set(indexed) != set(expected):
        raise Problem('研究包清单未完整覆盖实际文件', 409, code)
    return indexed


def parse_package(raw: bytes, filename: str, limits=None) -> dict:
    if not raw or len(raw) > MAX_UPLOAD:
        raise Problem('请选择不超过100MiB的研究包', 413, 'SCOUT_UPLOAD_LIMIT')
    filename = Path(filename.replace('\\', '/')).name
    if not filename or len(filename) > 200 or any(ord(c) < 32 for c in filename):
        raise Problem('文件名不正确', 400, 'INVALID_FILENAME')
    if not filename.lower().endswith(('.zip', '.json')):
        raise Problem('请选择研究交接ZIP或Handoff.json', 400, 'UNSUPPORTED_SCOUT_FILE')
    budget = Budget(limits)
    archived = {'upload/' + filename: raw}
    decisions = {}
    handoff = {}
    audit_claim = {}
    warnings = []
    original_files = {}
    if filename.lower().endswith('.zip'):
        outer = read_zip(raw, budget)
        hits = [n for n in outer if n.split('/')[-1] == 'ResearchHandoff.json']
        if hits:
            if len(hits) != 1:
                raise Problem('一批只能提交一份研究交接包', 400, 'MULTIPLE_RESEARCH_HANDOFFS')
            prefix = hits[0][:-len('ResearchHandoff.json')]
            if any(not n.startswith(prefix) for n in outer):
                raise Problem('交接包外层目录不一致', 400, 'RESEARCH_ROOT_MISMATCH')
            members = {n[len(prefix):]: b for n, b in outer.items()}
            for name in ('ResearchHandoff.json', 'Audit.json', 'Decisions.json', 'Manifest.json'):
                if name not in members:
                    raise Problem('交接包缺少' + name, 400, 'RESEARCH_FILE_MISSING')
            handoff = _json(members['ResearchHandoff.json'])
            audit_claim = _json(members['Audit.json'])
            decision_file = _json(members['Decisions.json'])
            manifest = _json(members['Manifest.json'])
            if not all(isinstance(x, dict) for x in (handoff, audit_claim, decision_file, manifest)):
                raise Problem('交接控制文件必须为JSON对象', 400, 'RESEARCH_SHAPE')
            if handoff.get('schema_version') != FORMAT or manifest.get('schema_version') != 'deepaha.research-bundle-manifest.v1':
                raise Problem('研究包版本不支持', 400, 'RESEARCH_VERSION')
            if handoff.get('submission_status') != 'NOT_SUBMITTED' or handoff.get('delivery_mode') != 'MANUAL_EXPORT_ONLY':
                raise Problem('交接包的提交语义不兼容', 400, 'RESEARCH_SUBMISSION_STATE')
            if type(handoff.get('review_revision')) is not int or handoff['review_revision'] < 0:
                raise Problem('审核版本不正确', 400, 'RESEARCH_REVISION')
            if decision_file.get('revision') != handoff['review_revision']:
                raise Problem('审核记录版本与交接版本不同', 409, 'RESEARCH_REVISION')
            _inventory(manifest.get('files'), members, set(members) - {'Manifest.json'}, 'RESEARCH_MANIFEST_MISMATCH')
            originals = _inventory(handoff.get('original_inventory'), members,
                                   {n for n in members if n.startswith('originals/')}, 'ORIGINAL_INVENTORY_MISMATCH')
            decisions = decision_file.get('decisions')
            events = decision_file.get('events')
            if not isinstance(decisions, dict) or not isinstance(events, list):
                raise Problem('外部审核记录格式不正确', 400, 'RESEARCH_DECISIONS')
            computed = digest(canonical_json({'originals': handoff['original_inventory'],
                  'analysis_sha256': digest(canonical_json(audit_claim)), 'decisions': decisions,
                  'revision': handoff['review_revision'], 'events': events}))
            if computed != handoff.get('bundle_id') or manifest.get('bundle_id') != computed:
                raise Problem('交接包标识与原件、审核版本不一致', 409, 'RESEARCH_BUNDLE_MISMATCH')
            for name in originals:
                original_files[name] = members[name]
                if name.lower().endswith('.zip'):
                    # Exactly the supported second layer. Deeper ZIPs are opaque attachments.
                    read_zip(members[name], budget)
            archived.update({'bundle/' + n: b for n, b in members.items()})
            format_name = FORMAT
            bundle_id = computed
        else:
            # Raw WB/GPT batch ZIP; its nested official archives stay opaque.
            original_files['originals/0001/' + filename] = raw
            archived.update({'raw-members/' + n: b for n, b in outer.items()})
            format_name = RAW_FORMAT
            bundle_id = digest(raw)
    else:
        original_files['originals/0001/' + filename] = raw
        format_name = RAW_FORMAT
        bundle_id = digest(raw)

    try:
        with tempfile.TemporaryDirectory(prefix='deepaha-scout-') as tmp:
            paths = []
            for name, data in original_files.items():
                p = Path(tmp) / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
                paths.append(p)
            inputs = load_inputs(paths, limits=limits or Limits())
            if not inputs.handoffs:
                raise Problem('未找到支持的Handoff；State、Review和WMA结果不能代替来源资产', 400, 'NO_SCOUT_HANDOFF')
            # v0.3.1 exports explicit per-input research namespaces only in Audit.
            # Adopt just that metadata when run key AND original bytes match; never
            # adopt its candidate content, scores, system IDs or authority decisions.
            namespace_hints={}
            for claim in audit_claim.get('batches',[]):
                if not isinstance(claim,dict):continue
                origin=claim.get('origin',{})
                namespace=claim.get('namespace')
                if not isinstance(origin,dict) or not isinstance(namespace,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}',namespace):continue
                key=(claim.get('run_key'),origin.get('sha256'))
                if not all(isinstance(x,str) for x in key):continue
                namespace_hints.setdefault(key,set()).add(namespace)
            input_namespaces={}
            for document in inputs.handoffs:
                hint=namespace_hints.get((document['run_key'],document['blob'].sha256),set())
                if len(hint)>1:raise Problem('同一原始批次声明了多个研究分组，请在工具中明确后重新导出',409,'SCOUT_NAMESPACE_AMBIGUOUS')
                if hint:document['namespace']=next(iter(hint))
                input_namespaces.setdefault(document['blob'].input_sha256,set()).add(document['namespace'])
            for state in inputs.states:
                hint=input_namespaces.get(state['blob'].input_sha256,set())
                if len(hint)==1:state['namespace']=next(iter(hint))
            # Enforce bounded semantic size before potentially quadratic relationship analysis.
            count = sum(len(d['data']['source_candidates']) for d in inputs.handoffs)
            if count > MAX_VERSIONS:
                raise Problem('候选版本过多，请分批提交', 413, 'SCOUT_VERSION_LIMIT')
            identities=set()
            from .scout_research.research.normalize import field
            for document in inputs.handoffs:
                if len(document['namespace'])>80 or len(document['run_key'])>120:
                    raise Problem('研究批次标识过长；原件已保留',413,'SCOUT_IDENTITY_LIMIT')
                for candidate in document['data']['source_candidates']:
                    if not isinstance(candidate,dict):continue
                    key=field(candidate,'candidate_key','source_id','id',default='')
                    if isinstance(key,str):
                        if len(key)>500:raise Problem('来源候选标识过长；原件已保留',413,'SCOUT_IDENTITY_LIMIT')
                        identities.add((document['namespace'],key))
            if len(identities)>MAX_GROUPS:
                raise Problem('候选身份超过2000个，请分批提交',413,'SCOUT_GROUP_LIMIT')
            analysis = analyze(inputs)
            if len(analysis['sources']) > MAX_GROUPS:
                raise Problem('候选身份超过2000个，请分批提交', 413, 'SCOUT_GROUP_LIMIT')
            runs = [{'namespace':d['namespace'], 'run_key':d['run_key'], 'sha256':d['blob'].sha256,
                     'payload':d['data'], 'origin':d['blob'].metadata()} for d in inputs.handoffs]
            # Persist each expanded material with a stable locator for authorized download.
            for b in inputs.files:
                archived['materials/' + b.input_sha256 + '/' + b.name] = b.data
    except ImporterError as exc:
        raise Problem(exc.message, exc.status, exc.code) from None
    except (TypeError, KeyError, AttributeError, ValueError, RecursionError, OverflowError):
        raise Problem('研究字段结构不完整，原件已保留；请在工具中整理后重新导出', 400, 'SCOUT_STRUCTURE') from None

    known = {g['id']:g for g in analysis['sources']}
    proposals = handoff.get('staging_proposals', [])
    if not isinstance(proposals, list):
        raise Problem('交接候选清单格式不正确', 400, 'RESEARCH_PROPOSALS')
    recommended = set()
    for proposal in proposals:
        if not isinstance(proposal, dict):
            raise Problem('交接候选清单条目格式不正确', 400, 'RESEARCH_PROPOSALS')
        gid = proposal.get('review_source_id')
        g = known.get(gid)
        decision = decisions.get(gid, {})
        if g and proposal.get('namespace') == g['namespace'] and proposal.get('candidate_key') == g['candidate_key'] and decision.get('decision') == 'PROPOSE_STAGING':
            recommended.add(gid)
        else:
            warnings.append('外部候选建议未能与服务端重建内容对应，未默认选中')
    for g in analysis['sources']:
        external = decisions.get(g['id'], {})
        g['external_decision'] = external if isinstance(external, dict) else {}
        if any(not isinstance(field(v['payload'],'candidate_key'),str) or not field(v['payload'],'candidate_key').strip() for v in g['versions']):
            g['blocking']=True
            g['issue_codes']=sorted(set(g['issue_codes']+['INVALID_CANDIDATE_ID']))
        g['suggested'] = g['id'] in recommended if format_name == FORMAT else not g['blocking']
        if g['external_decision'].get('primary_seed') not in g['seed_urls']:
            g['external_decision'] = {**g['external_decision'], 'primary_seed':None}
        # External proposals do not change these server-owned state values.
        g['system_source_id'] = None
        g['collection_enabled'] = None
    analysis.pop('analyzed_at', None)  # excluded from idempotent preview fingerprints
    return {'format':format_name, 'bundle_id':bundle_id, 'analysis':analysis, 'runs':runs,
            'readiness':handoff.get('readiness', 'RAW_RESEARCH_NOT_APPROVED'),
            'review_revision':handoff.get('review_revision'), 'warnings':warnings,
            'archive_files':archived, 'external_metadata':handoff}
