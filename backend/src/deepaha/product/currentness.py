"""SG3 unit-level currentness analysis.

This module compares one pending WMA projection with the currently accepted
CatalogTarget frontier.  It never approves facts and never infers withdrawal
from absence.  CatalogTarget history remains the durable accepted version log.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from collections import Counter
from sqlalchemy import select

from .adapter import public_content
from .catalog_projection import build_target_content, _ancestors
from .granularity import resolve_units, resolve_actionable_targets, UnitNode
from .models import CatalogTarget, OpportunityUnit


@dataclass(frozen=True)
class CandidateTarget:
    public_id: str | None
    stable_key: str
    title: str
    code: str
    content: dict
    lifecycle_status: str


def _storage_key(node: UnitNode, revision_id: str) -> str:
    return node.stable_key if node.identity_strength == 'STRONG' else f'{node.stable_key}@REV:{revision_id}'


def project_candidate_targets(session, opportunity, item: dict, package_notes: list[str], revision_id: str) -> list[CandidateTarget]:
    """Project pending actionable targets without mutating unit identity rows."""
    root_content = public_content(item, package_notes)
    graph = resolve_units(item)
    node_by_source = {n.source_id: n for n in graph}
    existing = {
        row.stable_key: row
        for row in session.scalars(select(OpportunityUnit).where(OpportunityUnit.opportunity_id == opportunity.opportunity_id))
    }
    result: list[CandidateTarget] = []
    for seed in resolve_actionable_targets(graph, item):
        if seed.singleton:
            result.append(CandidateTarget(
                public_id=opportunity.public_id,
                stable_key='__ROOT_SINGLETON__',
                title=str(root_content.get('title') or seed.title),
                code='',
                content=build_target_content(root_content, opportunity.public_id, None, [], None),
                lifecycle_status='WITHDRAWN' if item.get('lifecycle_status') == 'WITHDRAWN' else 'ACTIVE',
            ))
            continue
        node = node_by_source[seed.source_id]
        key = _storage_key(node, revision_id)
        db_unit = existing.get(key)
        public_id = db_unit.public_id if db_unit else None
        ancestors = _ancestors(node, node_by_source)
        content = build_target_content(root_content, opportunity.public_id, node, ancestors, public_id)
        result.append(CandidateTarget(
            public_id=public_id,
            stable_key=key,
            title=node.name,
            code=node.code,
            content=content,
            lifecycle_status=node.lifecycle_status,
        ))
    return result


def _latest_current_targets(session, opportunity_id: str) -> dict[str, CatalogTarget]:
    rows = list(session.scalars(
        select(CatalogTarget)
        .where(CatalogTarget.opportunity_id == opportunity_id,
               CatalogTarget.status.in_(['CURRENT', 'UPDATE_PENDING']))
        .order_by(CatalogTarget.created_at.desc(), CatalogTarget.id.desc())
    ))
    result = {}
    for row in rows:
        result.setdefault(row.public_id, row)
    return result


def _artifact_map(content: dict) -> dict[str, dict]:
    out = {}
    for a in content.get('artifacts', []) if isinstance(content, dict) else []:
        if not isinstance(a, dict):
            continue
        aid = str(a.get('id') or '')
        if aid:
            out[aid] = {
                'sha256': a.get('sha256'),
                'integrity': a.get('integrity'),
                'name': a.get('name'),
                'path': a.get('path'),
            }
    return out


def replaced_artifacts(old_revision_content: dict, new_revision_content: dict) -> set[str]:
    old, new = _artifact_map(old_revision_content), _artifact_map(new_revision_content)
    return {aid for aid in old.keys() & new.keys() if old[aid] != new[aid]}


def _field_signature(field: dict) -> dict:
    refs = []
    for e in field.get('evidence', []) if isinstance(field.get('evidence'), list) else []:
        if not isinstance(e, dict):
            continue
        refs.append({
            'artifact_id': e.get('artifact_id'),
            'quote': e.get('quote'),
            'locator': e.get('locator'),
            'located': e.get('located'),
        })
    return {
        'value': field.get('value'),
        'state': field.get('state'),
        'quote_located': field.get('quote_located'),
        'usage': field.get('usage'),
        'evidence': refs,
    }


def _field_map(content: dict) -> tuple[dict[str, dict], dict[str, dict]]:
    values: dict[str, dict] = {}
    original: dict[str, dict] = {}
    for scope in ('fields', 'ancestor_fields', 'common_fields'):
        counts: Counter[str] = Counter()
        rows = content.get(scope, []) if isinstance(content.get(scope), list) else []
        for field in rows:
            if not isinstance(field, dict):
                continue
            label = str(field.get('label') or '未命名字段')
            counts[label] += 1
            key = f'{scope}:{label}#{counts[label]}'
            values[key] = _field_signature(field)
            original[key] = field
    return values, original


def _artifact_references(content: dict, artifact_ids: set[str]) -> list[tuple[str, str]]:
    refs = []
    _, original = _field_map(content)
    for key, field in original.items():
        for ref in field.get('evidence', []) if isinstance(field.get('evidence'), list) else []:
            if isinstance(ref, dict) and ref.get('artifact_id') in artifact_ids:
                refs.append((key, str(field.get('label') or '')))
                break
    return refs


def diff_target_content(before: dict, after: dict, changed_artifacts: set[str] | None = None) -> dict:
    affected: list[str] = []
    scalar = {}
    for key in ('title', 'issuer', 'region', 'summary', 'official_url', 'application_url', 'deadline', 'deadline_precision'):
        if before.get(key) != after.get(key):
            scalar[key] = {'before': before.get(key), 'after': after.get(key)}
            affected.append(key)
    before_fields, _ = _field_map(before)
    after_fields, _ = _field_map(after)
    field_changes = {}
    for key in sorted(before_fields.keys() | after_fields.keys()):
        if before_fields.get(key) != after_fields.get(key):
            field_changes[key] = {'before': before_fields.get(key), 'after': after_fields.get(key)}
            affected.append(key)
    changed_artifacts = set(changed_artifacts or ())
    evidence_refs = sorted(set(_artifact_references(before, changed_artifacts) + _artifact_references(after, changed_artifacts)))
    for key, label in evidence_refs:
        marker = 'evidence:' + next((str(ref.get('artifact_id')) for f in (before, after) for row in f.get(key.split(':',1)[0], []) if isinstance(row, dict) and row.get('label') == label for ref in row.get('evidence', []) if isinstance(ref, dict) and ref.get('artifact_id') in changed_artifacts), '')
        if marker != 'evidence:' and marker not in affected:
            affected.append(marker)
        if ('报名' in label or '申请' in label) and '截止' in label and 'deadline' not in affected:
            affected.append('deadline')
    return {
        'affected_fields': list(dict.fromkeys(affected)),
        'scalar': scalar,
        'fields': field_changes,
        'changed_artifacts': sorted(changed_artifacts),
    }


def analyze_changes(session, opportunity, current_publication, old_revision_content: dict, new_revision_content: dict,
                    item: dict, package_notes: list[str], pending_revision_id: str) -> dict:
    old_targets = _latest_current_targets(session, opportunity.opportunity_id)
    candidates = project_candidate_targets(session, opportunity, item, package_notes, pending_revision_id)
    by_public = {c.public_id: c for c in candidates if c.public_id}
    changed_artifacts = replaced_artifacts(old_revision_content, new_revision_content)
    root_withdrawn = item.get('lifecycle_status') == 'WITHDRAWN'
    target_changes = []
    counts = {'changed': 0, 'added': 0, 'missing': 0, 'withdrawn': 0, 'unchanged': 0}

    for public_id, old in old_targets.items():
        candidate = by_public.get(public_id)
        if root_withdrawn or (candidate and candidate.lifecycle_status == 'WITHDRAWN'):
            target_changes.append({
                'public_id': public_id, 'title': old.content.get('title', ''), 'code': old.content.get('code', ''),
                'change_kind': 'WITHDRAWAL_PENDING', 'affected_fields': ['all'],
                'before_deadline': old.content.get('deadline'), 'after_deadline': None,
                'summary': '官方返回明确标记此具体机会撤回，等待整体收录决定。',
            })
            counts['withdrawn'] += 1
            continue
        if candidate is None:
            target_changes.append({
                'public_id': public_id, 'title': old.content.get('title', ''), 'code': old.content.get('code', ''),
                'change_kind': 'MISSING_PENDING', 'affected_fields': ['coverage', 'deadline'],
                'before_deadline': old.content.get('deadline'), 'after_deadline': None,
                'summary': '最新返回未包含此分项，不能据此判断已撤回。',
            })
            counts['missing'] += 1
            continue
        diff = diff_target_content(old.content, candidate.content, changed_artifacts)
        if diff['affected_fields']:
            # Replacing an evidence artifact is its own currentness event when the
            # extracted business value did not change.  Evidence risk may also
            # invalidate date actions, but that must not mislabel the event as a
            # business-field correction.
            evidence_only_change = bool(diff['changed_artifacts']) and not diff['scalar'] and not diff['fields']
            kind = 'EVIDENCE_REPLACED' if evidence_only_change else ('DEADLINE_CHANGED' if set(diff['affected_fields']) <= {'deadline','deadline_precision'} else 'UPDATED')
            target_changes.append({
                'public_id': public_id, 'title': candidate.title, 'code': candidate.code,
                'change_kind': kind, 'affected_fields': diff['affected_fields'],
                'before_deadline': old.content.get('deadline'), 'after_deadline': candidate.content.get('deadline'),
                'summary': '；'.join(_human_change_summary(diff)) or '具体内容发生变化，等待收录。',
                'diff': diff,
            })
            counts['changed'] += 1
        else:
            counts['unchanged'] += 1

    for candidate in candidates:
        if candidate.public_id is None and candidate.lifecycle_status != 'WITHDRAWN':
            target_changes.append({
                'public_id': None, 'stable_key': candidate.stable_key, 'title': candidate.title, 'code': candidate.code,
                'change_kind': 'ADDED_PENDING', 'affected_fields': ['new_target'],
                'before_deadline': None, 'after_deadline': candidate.content.get('deadline'),
                'summary': '新增可行动分项，等待整体收录。',
            })
            counts['added'] += 1

    return {
        'has_changes': any(counts[k] for k in ('changed','added','missing','withdrawn')),
        'counts': counts,
        'targets': target_changes,
        'replaced_artifacts': sorted(changed_artifacts),
        'root_lifecycle_status': item.get('lifecycle_status', 'ACTIVE'),
        'pending_revision_id': pending_revision_id,
    }


def _human_change_summary(diff: dict) -> list[str]:
    out = []
    if 'deadline' in diff.get('scalar', {}):
        x = diff['scalar']['deadline']
        out.append(f'报名截止由{x["before"] or "未确定"}变为{x["after"] or "未确定"}')
    scalar_names = {'title':'名称','issuer':'机构','region':'地区','summary':'摘要','official_url':'官方入口','application_url':'申请入口'}
    for key, label in scalar_names.items():
        if key in diff.get('scalar', {}):
            out.append(label + '发生变化')
    if diff.get('fields'):
        labels = []
        for key in diff['fields']:
            label = key.split(':',1)[1].rsplit('#',1)[0]
            if label not in labels:
                labels.append(label)
        out.append('字段变化：' + '、'.join(labels[:5]))
    if diff.get('changed_artifacts'):
        out.append('关联原件已替换')
    return out


def apply_pending_currentness(session, opportunity, summary: dict, pending_revision_id: str) -> list[dict]:
    """Mark only affected accepted targets pending; never erase stored old values."""
    applied = []
    for change in summary.get('targets', []):
        public_id = change.get('public_id')
        if not public_id or change.get('change_kind') == 'ADDED_PENDING':
            continue
        target = session.scalar(
            select(CatalogTarget)
            .where(CatalogTarget.opportunity_id == opportunity.opportunity_id,
                   CatalogTarget.public_id == public_id,
                   CatalogTarget.status.in_(['CURRENT','UPDATE_PENDING']))
            .order_by(CatalogTarget.created_at.desc(), CatalogTarget.id.desc())
        )
        if not target:
            continue
        target.status = 'UPDATE_PENDING'
        body = copy.deepcopy(target.content)
        body['currentness'] = {
            'pending_revision_id': pending_revision_id,
            'change_kind': change['change_kind'],
            'affected_fields': change.get('affected_fields', []),
            'summary': change.get('summary', ''),
        }
        target.content = body
        applied.append(change)
    return applied


def affected_deadline(change: dict) -> bool:
    fields = set(change.get('affected_fields') or ())
    return 'deadline' in fields or change.get('change_kind') in {'MISSING_PENDING','WITHDRAWAL_PENDING'}
