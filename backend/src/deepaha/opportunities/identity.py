from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from unicodedata import normalize
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from deepaha.contracts.phase2 import OpportunityTypeV02
from deepaha.contracts.phase3 import (
    OpportunityIdentityActionType,
    OpportunityIdentityMemberRole,
)
from deepaha.opportunities.types import UNSET, OpportunityPatch


class IdentityReplayError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class IdentityMemberRecord:
    opportunity_id: UUID
    role: OpportunityIdentityMemberRole


@dataclass(frozen=True, slots=True)
class IdentityActionRecord:
    action_id: UUID
    action_type: OpportunityIdentityActionType
    members: tuple[IdentityMemberRecord, ...]
    reversal_of_action_id: UUID | None
    actor: str
    reason: str
    source_document_id: UUID | None
    source_evidence_ref_id: UUID | None
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class IdentityState:
    canonical_by_opportunity: dict[UUID, UUID]
    split_children_by_parent: dict[UUID, tuple[UUID, ...]]
    active_action_ids: frozenset[UUID]


_REVERSAL_TYPES = {
    OpportunityIdentityActionType.MERGE_REVERSAL,
    OpportunityIdentityActionType.SPLIT_REVERSAL,
}


def _validate_action_shape(action: IdentityActionRecord) -> None:
    if not action.actor.strip():
        raise IdentityReplayError("identity action actor must be non-empty")
    if not action.reason.strip():
        raise IdentityReplayError("identity action reason must be non-empty")
    if (action.source_document_id is None) != (action.source_evidence_ref_id is None):
        raise IdentityReplayError("source document and evidence must both be set or absent")
    if len({member.opportunity_id for member in action.members}) != len(action.members):
        raise IdentityReplayError("identity action members must have unique opportunity IDs")

    roles = [member.role for member in action.members]
    merge_shape = (
        roles.count(OpportunityIdentityMemberRole.TARGET) == 1
        and roles.count(OpportunityIdentityMemberRole.SOURCE) >= 1
        and not any(
            role
            in {
                OpportunityIdentityMemberRole.PARENT,
                OpportunityIdentityMemberRole.CHILD,
            }
            for role in roles
        )
    )
    split_shape = (
        roles.count(OpportunityIdentityMemberRole.PARENT) == 1
        and roles.count(OpportunityIdentityMemberRole.CHILD) >= 2
        and not any(
            role
            in {
                OpportunityIdentityMemberRole.SOURCE,
                OpportunityIdentityMemberRole.TARGET,
            }
            for role in roles
        )
    )
    if (
        action.action_type
        in {
            OpportunityIdentityActionType.MERGE,
            OpportunityIdentityActionType.MERGE_REVERSAL,
        }
        and not merge_shape
    ):
        raise IdentityReplayError("MERGE identity action has invalid members")
    if (
        action.action_type
        in {
            OpportunityIdentityActionType.SPLIT,
            OpportunityIdentityActionType.SPLIT_REVERSAL,
        }
        and not split_shape
    ):
        raise IdentityReplayError("SPLIT identity action has invalid members")

    is_reversal = action.action_type in _REVERSAL_TYPES
    if is_reversal and action.reversal_of_action_id is None:
        raise IdentityReplayError("reversal action must reference an original action")
    if not is_reversal and action.reversal_of_action_id is not None:
        raise IdentityReplayError("non-reversal action cannot reference another action")


def _follow_target(direct_targets: dict[UUID, UUID], opportunity_id: UUID) -> UUID:
    current = opportunity_id
    visited: set[UUID] = set()
    while current in direct_targets:
        if current in visited:
            raise IdentityReplayError("merge cycle detected")
        visited.add(current)
        current = direct_targets[current]
    return current


def replay_identity_state(actions: tuple[IdentityActionRecord, ...]) -> IdentityState:
    ordered = sorted(actions, key=lambda item: (item.occurred_at, item.action_id.hex))
    by_id: dict[UUID, IdentityActionRecord] = {}
    order_by_id: dict[UUID, int] = {}
    for index, action in enumerate(ordered):
        if action.action_id in by_id:
            raise IdentityReplayError(f"duplicate action ID: {action.action_id}")
        _validate_action_shape(action)
        by_id[action.action_id] = action
        order_by_id[action.action_id] = index

    reversal_by_original: dict[UUID, UUID] = {}
    for action in ordered:
        if action.action_type not in _REVERSAL_TYPES:
            continue
        original_id = action.reversal_of_action_id
        assert original_id is not None
        original = by_id.get(original_id)
        if original is None:
            raise IdentityReplayError("reversal references a missing original action")
        if original.action_type in _REVERSAL_TYPES:
            raise IdentityReplayError("reversal of a reversal is forbidden")
        if order_by_id[action.action_id] <= order_by_id[original_id]:
            raise IdentityReplayError("reversal must be ordered after original action")
        expected_type = (
            OpportunityIdentityActionType.MERGE_REVERSAL
            if original.action_type is OpportunityIdentityActionType.MERGE
            else OpportunityIdentityActionType.SPLIT_REVERSAL
        )
        if action.action_type is not expected_type:
            raise IdentityReplayError("reversal type does not match original action")
        if action.members != original.members:
            raise IdentityReplayError("reversal members must exactly copy original members")
        if original_id in reversal_by_original:
            raise IdentityReplayError("identity action is already reversed")
        reversal_by_original[original_id] = action.action_id

    active = tuple(
        action
        for action in ordered
        if action.action_type not in _REVERSAL_TYPES
        and action.action_id not in reversal_by_original
    )
    all_opportunity_ids = {member.opportunity_id for action in ordered for member in action.members}
    direct_targets: dict[UUID, UUID] = {}
    split_children: dict[UUID, tuple[UUID, ...]] = {}
    for action in active:
        if action.action_type is OpportunityIdentityActionType.MERGE:
            target = next(
                member.opportunity_id
                for member in action.members
                if member.role is OpportunityIdentityMemberRole.TARGET
            )
            sources = sorted(
                (
                    member.opportunity_id
                    for member in action.members
                    if member.role is OpportunityIdentityMemberRole.SOURCE
                ),
                key=lambda item: item.hex,
            )
            for source in sources:
                if source in direct_targets:
                    raise IdentityReplayError(f"opportunity {source} has multiple active targets")
                if source == target or _follow_target(direct_targets, target) == source:
                    raise IdentityReplayError("merge cycle detected")
                direct_targets[source] = target
        elif action.action_type is OpportunityIdentityActionType.SPLIT:
            parent = next(
                member.opportunity_id
                for member in action.members
                if member.role is OpportunityIdentityMemberRole.PARENT
            )
            if parent in split_children:
                raise IdentityReplayError(f"opportunity {parent} has multiple active splits")
            split_children[parent] = tuple(
                sorted(
                    (
                        member.opportunity_id
                        for member in action.members
                        if member.role is OpportunityIdentityMemberRole.CHILD
                    ),
                    key=lambda item: item.hex,
                )
            )

    canonical = {
        opportunity_id: _follow_target(direct_targets, opportunity_id)
        for opportunity_id in sorted(all_opportunity_ids, key=lambda item: item.hex)
    }
    return IdentityState(
        canonical_by_opportunity=canonical,
        split_children_by_parent=split_children,
        active_action_ids=frozenset(action.action_id for action in active),
    )


def resolve_canonical_opportunity_id(
    state: IdentityState,
    opportunity_id: UUID,
) -> UUID:
    return state.canonical_by_opportunity.get(opportunity_id, opportunity_id)


def normalize_identity_text(value: str) -> str:
    return " ".join(normalize("NFC", value).strip().casefold().split())


def normalize_official_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https"} or parsed.hostname is None:
        raise ValueError("official URL must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("official URL must not contain credentials")

    host = parsed.hostname.casefold().rstrip(".")
    if ":" in host:
        host = f"[{host}]"
    port = parsed.port
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        host = f"{host}:{port}"
    path = parsed.path or "/"
    return urlunsplit((scheme, host, path, parsed.query, ""))


def stable_public_id_for_key(identity_key: str) -> str:
    digest = sha256(f"deepaha:opportunity:v0.3:{identity_key}".encode()).hexdigest()
    return f"opp_{digest[:32]}"


def weak_fingerprint(facts: OpportunityPatch) -> str | None:
    if (
        facts.type is UNSET
        or facts.canonical_title is UNSET
        or facts.issuer_name is UNSET
        or not isinstance(facts.type, OpportunityTypeV02)
        or not isinstance(facts.canonical_title, str)
        or not isinstance(facts.issuer_name, str)
        or not normalize_identity_text(facts.canonical_title)
        or not normalize_identity_text(facts.issuer_name)
    ):
        return None
    jurisdiction = (
        normalize_identity_text(facts.jurisdiction) if isinstance(facts.jurisdiction, str) else ""
    )
    components = (
        facts.type.value,
        normalize_identity_text(facts.issuer_name),
        normalize_identity_text(facts.canonical_title),
        jurisdiction,
    )
    return f"weak:{sha256(chr(31).join(components).encode()).hexdigest()}"


__all__ = [
    "IdentityActionRecord",
    "IdentityMemberRecord",
    "IdentityReplayError",
    "IdentityState",
    "normalize_identity_text",
    "normalize_official_url",
    "replay_identity_state",
    "resolve_canonical_opportunity_id",
    "stable_public_id_for_key",
    "weak_fingerprint",
]
