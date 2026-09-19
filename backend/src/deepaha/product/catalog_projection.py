"""Materialize user-actionable catalog targets from one approved root publication."""
from __future__ import annotations

import copy
import re
from sqlalchemy import select

from .adapter import public_content, exact_day
from .granularity import resolve_units, resolve_actionable_targets, UnitNode
from .models import CatalogTarget, OpportunityUnit, now, uid
from .opportunity_core import presentation_for, summary_labels


def upsert_unit_identities(session, opportunity_id: str, revision_id: str, item: dict):
    graph = resolve_units(item)
    existing = {
        row.stable_key: row
        for row in session.scalars(select(OpportunityUnit).where(OpportunityUnit.opportunity_id == opportunity_id))
    }
    by_source: dict[str, OpportunityUnit] = {}
    # First pass creates all rows without parent references so ordering is irrelevant.
    for node in graph:
        storage_key = node.stable_key if node.identity_strength == 'STRONG' else f'{node.stable_key}@REV:{revision_id}'
        row = existing.get(storage_key)
        if row is None:
            iid = uid()
            row = OpportunityUnit(
                id=iid,
                opportunity_id=opportunity_id,
                public_id='unit_' + iid.replace('-', ''),
                stable_key=storage_key,
                kind=node.kind,
                name=node.name,
                code=node.code,
                identity_strength=node.identity_strength,
                source_path=node.source_path,
                first_revision_id=revision_id,
                current_revision_id=revision_id,
            )
            session.add(row)
            session.flush()
            existing[storage_key] = row
        else:
            row.kind = node.kind
            row.name = node.name
            row.code = node.code
            row.identity_strength = node.identity_strength
            row.source_path = node.source_path
            row.current_revision_id = revision_id
            row.updated_at = now()
        by_source[node.source_id] = row
    # Parent relations are identity metadata only; they do not approve applicability.
    for node in graph:
        row = by_source[node.source_id]
        parent = by_source.get(node.parent_source_id or '')
        row.parent_id = parent.id if parent else None
    return graph, by_source


def _field_values(fields, labels):
    for field in fields:
        label = str(field.get('label') or '')
        if any(token in label for token in labels) and field.get('value'):
            return str(field['value'])
    return ''


def _notes(fields):
    values = []
    for field in fields:
        for note in field.get('notes', []) if isinstance(field.get('notes'), list) else []:
            if note and note not in values:
                values.append(note)
    return values


def _ancestors(node: UnitNode, by_source_node: dict[str, UnitNode]):
    result = []
    current = node
    seen = set()
    while current.parent_source_id and current.parent_source_id not in seen:
        seen.add(current.parent_source_id)
        parent = by_source_node.get(current.parent_source_id)
        if not parent:
            break
        result.append(parent)
        current = parent
    result.reverse()
    return result



def _supported_deadline(fields: list[dict]) -> str | None:
    """Return one exact, quote-supported action deadline from this scope only."""
    values = set()
    for field in fields:
        label = str(field.get('label') or '')
        if not (('报名' in label or '申请' in label) and '截止' in label):
            continue
        if not field.get('usage', {}).get('date_action'):
            continue
        candidate = exact_day(str(field.get('value') or ''))
        if not candidate:
            continue
        supported = False
        for ref in field.get('evidence', []) if isinstance(field.get('evidence'), list) else []:
            if not ref.get('located'):
                continue
            quote = str(ref.get('quote') or '')
            for raw in re.findall(r'\d{4}[-年/]\d{1,2}[-月/]\d{1,2}日?', quote):
                if exact_day(raw) == candidate:
                    supported = True
                    break
            if supported:
                break
        if supported:
            values.add(candidate)
    return next(iter(values)) if len(values) == 1 else None

def _target_content(root_content: dict, root_public_id: str, node: UnitNode | None, unit_public_id: str | None):
    if node is None:
        content = copy.deepcopy(root_content)
        content.update({
            'target_kind': 'DEFAULT_SINGLETON',
            'code': '',
            'root_public_id': root_public_id,
            'unit_public_id': None,
            'parent_announcement': None,
            'common_fields': [],
            'ancestor_fields': [],
            'children': [],
            'scope_labels': [],
            'presentation': presentation_for(str(root_content.get('type') or ''), 'DEFAULT_SINGLETON', str(root_content.get('raw_type') or '')),
            'lifecycle_status': root_content.get('lifecycle_status', 'ACTIVE'),
        })
        return content

    # Caller injects ancestors temporarily into the node-compatible dict.
    ancestor_nodes = getattr(node, '_resolved_ancestors', ())  # pragma: no cover - frozen dataclass has no attr
    raise AssertionError('use build_target_content')


def build_target_content(root_content: dict, root_public_id: str, node: UnitNode | None, ancestors: list[UnitNode], unit_public_id: str | None):
    if node is None:
        return _target_content(root_content, root_public_id, None, None)
    own_fields = [copy.deepcopy(x) for x in node.fields]
    ancestor_fields = [copy.deepcopy(f) for a in ancestors for f in a.fields]
    common_fields = [copy.deepcopy(x) for x in root_content.get('fields', [])]
    all_scope_fields = ancestor_fields + own_fields
    type_code = str(root_content.get('type') or '')
    raw_type = str(root_content.get('raw_type') or '')
    presentation = presentation_for(type_code, node.kind, raw_type)
    nearest_group = next((a for a in reversed(ancestors) if a.kind == 'GROUP'), None)
    issuer = nearest_group.name if nearest_group and presentation['group_as_issuer'] else root_content.get('issuer', '')
    region = node.region or _field_values(all_scope_fields, ['工作地点', '工作地区', '岗位地点', '单位所在地', '所在地区', '地区', '赛区', '实施地区']) or root_content.get('region', '')
    summary = node.summary or _field_values(own_fields, summary_labels(type_code)) or root_content.get('summary', '')
    notes = list(root_content.get('notes', []))
    for value in _notes(ancestor_fields + own_fields):
        if value not in notes:
            notes.append(value)
    specific_deadline = _supported_deadline(own_fields)
    if specific_deadline is None:
        specific_deadline = _supported_deadline(ancestor_fields)
    deadline = specific_deadline or root_content.get('deadline')
    content = {
        k: copy.deepcopy(root_content.get(k))
        for k in ['type','source_name','eligibility','raw_type','qualification_coverage']
    }
    content.update({
        'official_url': node.official_url or root_content.get('official_url'),
        'application_url': node.application_url or root_content.get('application_url'),
        'deadline': deadline,
        'deadline_precision': 'day' if specific_deadline else root_content.get('deadline_precision'),
        'title': node.name,
        'issuer': issuer,
        'region': region,
        'summary': summary,
        'notes': notes,
        'fields': own_fields,
        'ancestor_fields': ancestor_fields,
        'common_fields': common_fields,
        'children': [],
        'target_kind': node.kind,
        'code': node.code,
        'root_public_id': root_public_id,
        'unit_public_id': unit_public_id,
        'parent_announcement': {
            'id': root_public_id,
            'title': root_content.get('title', ''),
            'issuer': root_content.get('issuer', ''),
        },
        'scope_labels': [a.name for a in ancestors],
        'unit_path': [{'kind': a.kind, 'name': a.name, 'code': a.code} for a in ancestors] + [{'kind': node.kind, 'name': node.name, 'code': node.code}],
        'presentation': presentation,
        'lifecycle_status': node.lifecycle_status,
    })
    return content


def materialize_catalog_targets(session, opportunity, publication, item: dict, package_notes: list[str], product=None):
    graph, db_by_source = upsert_unit_identities(session, opportunity.opportunity_id, publication.revision_id, item)
    root_content = public_content(item, package_notes)
    node_by_source = {n.source_id: n for n in graph}
    seeds = resolve_actionable_targets(graph, item)
    public_ids: list[str] = []
    seed_public_ids: set[str] = set()
    seed_rows = []
    root_withdrawn = item.get('lifecycle_status') == 'WITHDRAWN'
    for seed in seeds:
        if seed.singleton:
            public_id = opportunity.public_id
            db_unit = None
            node = None
            ancestors = []
            lifecycle = 'WITHDRAWN' if root_withdrawn else 'ACTIVE'
        else:
            db_unit = db_by_source[seed.source_id]
            public_id = db_unit.public_id
            node = node_by_source[seed.source_id]
            ancestors = _ancestors(node, node_by_source)
            lifecycle = node.lifecycle_status
        seed_public_ids.add(public_id)
        seed_rows.append((public_id, db_unit, node, ancestors, lifecycle))

    current = list(session.scalars(select(CatalogTarget).where(
        CatalogTarget.opportunity_id == opportunity.opportunity_id,
        CatalogTarget.status.in_(['CURRENT','UPDATE_PENDING']),
    )))
    lifecycle_by_public = {public_id: lifecycle for public_id, _, _, _, lifecycle in seed_rows}
    for old in current:
        lifecycle = lifecycle_by_public.get(old.public_id)
        if root_withdrawn or lifecycle == 'WITHDRAWN':
            old.status = 'WITHDRAWN'
        elif old.public_id in seed_public_ids or old.public_id == opportunity.public_id:
            old.status = 'SUPERSEDED'
        else:
            # Absence is not withdrawal. Keep the last accepted content reachable,
            # but its time-sensitive use remains pending until a scoped recheck or
            # later accepted version resolves the gap.
            old.status = 'UPDATE_PENDING'
            body = copy.deepcopy(old.content)
            currentness = dict(body.get('currentness') or {})
            currentness.update({
                'change_kind': 'MISSING_PENDING',
                'affected_fields': list(dict.fromkeys((currentness.get('affected_fields') or []) + ['coverage','deadline'])),
                'summary': '最新返回未包含此分项，尚不能据此判断该机会已撤回。',
                'pending_revision_id': publication.revision_id,
            })
            body['currentness'] = currentness
            old.content = body

    if root_withdrawn:
        return public_ids

    for public_id, db_unit, node, ancestors, lifecycle in seed_rows:
        if lifecycle == 'WITHDRAWN':
            # Explicitly withdrawn units remain in history through their previous
            # target row and this accepted root revision; no new active card is made.
            continue
        content = build_target_content(root_content, opportunity.public_id, node, ancestors, public_id if db_unit else None)
        content.pop('currentness', None)
        from .qualification_compiler import summarize_content
        content['qualification_compiler'] = summarize_content(content)
        target = CatalogTarget(
            public_id=public_id,
            opportunity_id=opportunity.opportunity_id,
            unit_id=db_unit.id if db_unit else None,
            publication_id=publication.id,
            revision_id=publication.revision_id,
            content=content,
            status='CURRENT',
        )
        session.add(target)
        session.flush()
        if product is not None:
            from .milestones import apply_target_milestones
            apply_target_milestones(product,session,target)
            if hasattr(product,'_reschedule_target_followers'):
                product._reschedule_target_followers(session,target)
        public_ids.append(public_id)
    return public_ids



def backfill_existing_catalog(session, product=None):
    """Create SG1 target projections for already-approved rc2 publications.

    Uses the saved Revision projection when available so old rc2 public JSON does not
    need to have exposed internal unit identity keys.
    """
    from .models import Publication, Opportunity, Identity, Revision
    created = 0
    current_publications = list(session.scalars(select(Publication).where(Publication.status.in_(['CURRENT','UPDATE_PENDING']))))
    for publication in current_publications:
        if session.scalar(select(CatalogTarget).where(CatalogTarget.publication_id == publication.id)):
            continue
        opportunity = session.get(Opportunity, publication.opportunity_id)
        if not opportunity:
            continue
        revision = session.get(Revision, publication.revision_id)
        ident = session.scalar(select(Identity).where(Identity.opportunity_id == opportunity.opportunity_id))
        item = None
        if revision and isinstance(revision.content, dict):
            for candidate in revision.content.get('opportunities', []):
                if not isinstance(candidate, dict):
                    continue
                if ident and candidate.get('identity_key') == ident.source_key:
                    item = candidate
                    break
                if candidate.get('title') == opportunity.canonical_title and item is None:
                    item = candidate
        if item is None:
            # Root-only legacy records remain readable as a singleton; no child identities are invented.
            content = copy.deepcopy(publication.content)
            item = {
                'identity_key': ident.source_key if ident else opportunity.public_id,
                'title': content.get('title', opportunity.canonical_title),
                'type': content.get('type', opportunity.type),
                'issuer': content.get('issuer', opportunity.issuer_name),
                'source_name': content.get('source_name', ''),
                'official_url': content.get('official_url'),
                'application_url': content.get('application_url'),
                'region': content.get('region', ''),
                'summary': content.get('summary', ''),
                'fields': content.get('fields', []),
                'children': [],
                'notes': content.get('notes', []),
                'deadline': content.get('deadline'),
                'deadline_precision': content.get('deadline_precision'),
                'eligibility': content.get('eligibility', 'UNCERTAIN'),
                'raw_type': content.get('raw_type', ''),
                'qualification_coverage': content.get('qualification_coverage', ''),
            }
        before = session.scalar(select(CatalogTarget).where(CatalogTarget.publication_id == publication.id))
        if not before:
            public_ids = materialize_catalog_targets(session, opportunity, publication, item, [], product=product)
            created += len(public_ids)
    return created
