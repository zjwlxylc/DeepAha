"""Resolve WMA child structures into stable unit identities and actionable targets.

GROUP rows provide scope only.  Actionable rows become user-facing catalog targets.
No title-similarity merge is performed here.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

ACTIONABLE_KINDS = {'POSITION','TRACK','PROGRAM_TIER','REGION_VARIANT','DEFAULT_SINGLETON'}
KNOWN_KINDS = ACTIONABLE_KINDS | {'GROUP'}


@dataclass(frozen=True)
class UnitNode:
    source_id: str
    source_key: str
    stable_key: str
    name: str
    kind: str
    code: str
    parent_source_id: str | None
    identity_strength: str
    source_path: str
    fields: tuple[dict, ...]
    application_url: str | None = None
    official_url: str | None = None
    region: str = ''
    summary: str = ''
    lifecycle_status: str = 'ACTIVE'


@dataclass(frozen=True)
class ActionableTargetSeed:
    stable_key: str | None
    source_id: str | None
    kind: str
    title: str
    code: str
    singleton: bool = False


def _normalized_kind(value: object) -> str:
    kind = str(value or 'DEFAULT_SINGLETON').upper()
    return kind if kind in KNOWN_KINDS else 'DEFAULT_SINGLETON'


def resolve_units(root_item: dict) -> list[UnitNode]:
    """Resolve flattened children into stable identity candidates.

    Identity follows the SG1 contract rather than trusting run-local WMA order:
    stable source key -> parent semantic path + business code -> producer id ->
    weak path/name fallback.  Duplicate candidates are never similarity-merged.
    """
    children = root_item.get('children') if isinstance(root_item, dict) else []
    if not isinstance(children, list):
        return []
    rows = [c for c in children if isinstance(c, dict)]
    by_id = {str(c.get('id')): c for c in rows if c.get('id')}

    def norm(value: object) -> str:
        return ' '.join(str(value or '').strip().casefold().split())

    path_memo: dict[str, str] = {}
    def semantic_path(c: dict, stack: set[str] | None = None) -> str:
        cid = str(c.get('id') or '')
        if cid and cid in path_memo:
            return path_memo[cid]
        stack = set(stack or ())
        if cid:
            if cid in stack:
                return 'CYCLE'
            stack.add(cid)
        parent = by_id.get(str(c.get('parent_id') or ''))
        prefix = semantic_path(parent, stack) + '/' if parent else 'ROOT/'
        kind = _normalized_kind(c.get('kind'))
        code = norm(c.get('code'))
        name = norm(c.get('name')) or 'unnamed'
        token = f'CODE:{code}' if code else f'NAME:{name}'
        value = f'{prefix}{kind}:{token}'
        if cid:
            path_memo[cid] = value
        return value

    preliminary: list[tuple[dict, str, str]] = []
    for c in rows:
        kind = _normalized_kind(c.get('kind'))
        source_key = str(c.get('source_key') or '').strip()
        source_type = str(c.get('identity_source') or '')
        code = norm(c.get('code'))
        parent = by_id.get(str(c.get('parent_id') or ''))
        if source_key and source_type in {'SOURCE_RECORD_KEY','STABLE_SOURCE_ID'}:
            candidate = f'{kind}:SOURCE:{source_key}'
            strength = 'STRONG'
        elif code:
            # Business codes are meaningful only inside their parent scope.
            parent_path = semantic_path(parent) if parent else 'ROOT'
            candidate = f'{parent_path}/{kind}:CODE:{code}'
            strength = 'STRONG'
        elif source_key and source_type == 'PRODUCER_ID':
            # Producer ids are useful when no better business identity exists.
            candidate = f'{kind}:ID:{source_key}'
            strength = 'STRONG'
        else:
            candidate = semantic_path(c)
            strength = 'WEAK'
        preliminary.append((c, candidate, strength))

    counts = Counter(candidate for _, candidate, _ in preliminary)
    result = []
    for c, candidate, strength in preliminary:
        if counts[candidate] > 1:
            # Ambiguous identities must not be automatically merged across versions.
            discriminator = str(c.get('source_key') or c.get('source_path') or c.get('id') or '')
            candidate = f'{candidate}/AMBIG:{discriminator}'
            strength = 'WEAK'
        result.append(UnitNode(
            source_id=str(c.get('id') or ''),
            source_key=str(c.get('source_key') or '').strip(),
            stable_key=candidate,
            name=str(c.get('name') or '未命名条目'),
            kind=_normalized_kind(c.get('kind')),
            code=str(c.get('code') or ''),
            parent_source_id=str(c.get('parent_id')) if c.get('parent_id') else None,
            identity_strength=strength,
            source_path=str(c.get('source_path') or ''),
            fields=tuple(x for x in c.get('fields', []) if isinstance(x, dict)),
            application_url=c.get('application_url') if isinstance(c.get('application_url'), str) else None,
            official_url=c.get('official_url') if isinstance(c.get('official_url'), str) else None,
            region=str(c.get('region') or ''),
            summary=str(c.get('summary') or ''),
            lifecycle_status='WITHDRAWN' if str(c.get('lifecycle_status') or '').upper() == 'WITHDRAWN' else 'ACTIVE',
        ))
    return result


def resolve_actionable_targets(unit_graph: Iterable[UnitNode], root_item: dict) -> list[ActionableTargetSeed]:
    """Return the actionable frontier, not every actionable ancestor.

    A TRACK that contains actionable PROGRAM_TIER children is context rather than an
    additional action card. GROUP nodes are never cards but may sit between two
    actionable levels. This avoids duplicate cards such as "设计赛道" plus both
    "本科生组/研究生组" when registration actually happens at the group level.
    """
    graph = list(unit_graph)
    by_id = {n.source_id: n for n in graph if n.source_id}
    actionable_ids = {n.source_id for n in graph if n.kind in ACTIONABLE_KINDS and n.source_id}
    has_actionable_descendant: set[str] = set()
    for node in graph:
        if node.source_id not in actionable_ids:
            continue
        parent_id = node.parent_source_id
        seen: set[str] = set()
        while parent_id and parent_id not in seen:
            seen.add(parent_id)
            if parent_id in actionable_ids:
                has_actionable_descendant.add(parent_id)
            parent = by_id.get(parent_id)
            parent_id = parent.parent_source_id if parent else None
    targets = [
        ActionableTargetSeed(n.stable_key, n.source_id, n.kind, n.name, n.code)
        for n in graph if n.kind in ACTIONABLE_KINDS and n.source_id not in has_actionable_descendant
    ]
    if targets:
        return targets
    return [ActionableTargetSeed(None, None, 'DEFAULT_SINGLETON', str(root_item.get('title') or '未命名机会'), '', True)]
