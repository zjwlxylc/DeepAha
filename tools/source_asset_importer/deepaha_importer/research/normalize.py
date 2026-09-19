"""Conservative, explicit normalization. Original fields remain in the package."""
from __future__ import annotations
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit
from ..contract import canonical_url, canonical_json, digest
from ..errors import ImporterError


def text(value):
    return value.strip() if isinstance(value, str) else ''


def items(value):
    if value is None: return []
    return value if isinstance(value, list) else [value]


def reference(value):
    if isinstance(value, str): return value
    if isinstance(value, dict):
        for key in ('candidate_key', 'evidence_key', 'brief_key', 'source_ref', 'ref', 'id'):
            if isinstance(value.get(key), str): return value[key]
    return None


def field(record, *names, default=None):
    for name in names:
        if name in record: return record[name]
    # Only spelling/space aliases; never choose between conflicting aliases.
    normalized = {re.sub(r'[^a-z0-9]', '', k.lower()): v for k, v in record.items() if k.isascii()}
    for name in names:
        k = re.sub(r'[^a-z0-9]', '', name.lower())
        if k in normalized: return normalized[k]
    return default


def url_key(value):
    """No www/scheme/path/route folding; drop only known tracking parameters.

    Signed URLs retain their whole query. Query order and hash routes survive.
    This is an endpoint comparison key, not proof of institution identity.
    """
    normalized = canonical_url(value)
    u = urlsplit(normalized)
    if re.search(r'(?i)(?:^|&)(?:.*signature|.*token|x-amz-.*|expires|sig)=', u.query):
        return normalized
    query = '&'.join(part for part in u.query.split('&') if part and not re.match(r'(?i)^(?:utm_[^=]*|gclid|fbclid)=', part))
    return urlunsplit((u.scheme, u.netloc, u.path, query, u.fragment))


def seed_urls(value):
    values = value if isinstance(value, list) else [value]
    found = []
    for raw in values:
        if not isinstance(raw, str): continue
        raw = raw.strip()
        # URL-like prose must be separated before validation; validators accept Unicode paths.
        # Never infer a scheme for bare domains or expand <province> templates.
        candidates = re.findall(r'https?://[^\s<>"\[\]{}，；、（）]+', raw)
        for candidate in candidates:
            candidate = candidate.rstrip('.,;。；，）)')
            try: key = url_key(candidate)
            except ImporterError: continue
            if key not in found: found.append(key)
    return found


def name_key(value):
    return re.sub(r'[\s·•—\-_/（）()]+', '', unicodedata.normalize('NFKC', text(value))).casefold()


def infer_namespace(run_key, override='AUTO'):
    if override != 'AUTO':
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', override):
            raise ImporterError('BAD_NAMESPACE', '来源标识只允许字母、数字、点、横线和下划线。')
        return override
    if re.match(r'^\d{8}T\d{6}_', run_key): return 'chatgpt-scout'
    if re.match(r'^\d{8}-\d{4}-\d{4}', run_key): return 'wb-scout'
    # Explicitly unknown producer: avoid pretending the filename proves a model.
    return 'unassigned'


def score_check(record):
    breakdown = field(record, 'score_breakdown', default={})
    declared = field(record, 'score_total')
    components = []
    if isinstance(breakdown, dict):
        totals = [(k, v) for k, v in breakdown.items() if 'total' in k.lower() or '总' in k]
        if declared is None and totals: declared = totals[0][1]
        for k, v in breakdown.items():
            if 'total' in k.lower() or '总' in k or k in {'note', 'reason'}: continue
            if isinstance(v, dict): v = field(v, 'score', '得分')
            components.append(v)
    elif isinstance(breakdown, list):
        components = [field(x, 'score', '得分') for x in breakdown if isinstance(x, dict)]
    numeric = lambda x: type(x) in (float, int)
    complete = bool(components) and all(numeric(x) for x in components)
    computed = sum(components) if complete else None
    mismatch = computed is not None and numeric(declared) and abs(computed - declared) > 1e-8
    nested_conflict = isinstance(breakdown, dict) and any(numeric(v) and numeric(declared) and v != declared for k,v in breakdown.items() if 'total' in k.lower() or '总' in k)
    return {'declared_total': declared, 'calculated_total': computed, 'component_count': len(components),
            'complete': complete, 'arithmetic_mismatch': mismatch or nested_conflict,
            'meaning': '研究者评分的算术检查；不是来源真实性或生产价值评分。'}


def semantic_hash(record):
    ignored = {'last_checked_at','first_seen_at','first_observed_this_run_at','base_revision','revision',
               'system_revision','run_focus','proposed_operation'}
    return digest(canonical_json({k:v for k,v in record.items() if k not in ignored}))


def evidence_references(value, known_keys):
    """Resolve explicit IDs in prose, without inventing or prefix-matching IDs.

    The raw prose is retained separately. Known exact keys are authoritative for
    linking only, not for truth. Unrecognized EV-... tokens remain visible gaps.
    """
    raw = reference(value)
    if not raw:
        return []
    raw = raw.strip()
    if raw in known_keys:
        return [raw]
    matches = []
    boundary = r'[A-Za-z0-9_.:\-]'
    for key in known_keys:
        for match in re.finditer(r'(?<!' + boundary + ')' + re.escape(key) + r'(?!' + boundary + ')', raw):
            matches.append((match.start(), key))
    for match in re.finditer(r'(?<![A-Za-z0-9_.:\-])EV-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+(?![A-Za-z0-9_.:\-])', raw):
        matches.append((match.start(), match.group()))
    if not matches:
        return [raw]
    return list(dict.fromkeys(key for _, key in sorted(matches)))
