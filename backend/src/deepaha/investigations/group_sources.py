"""Complete source group membership; identity association is not fact approval."""

from copy import deepcopy
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from deepaha.investigations.bindings import _check_positions, _latest, _validated_members
from deepaha.investigations.contracts import (
    BindInvestigation,
    CreateInvestigation,
    InvestigationError,
    digest,
)
from deepaha.investigations.group_contracts import GroupSourceContext
from deepaha.opportunities.models import Opportunity
from deepaha.p9b.models import SourceBundleMember, SourceBundleRevision
from deepaha.p9b.wma_provenance import WmaBundleMemberSpec

if TYPE_CHECKING:
    from deepaha.investigations.store import InvestigationStore

GROUP_CONTRACT_VERSION = "group-identity/1.0.0"
GROUP_SCOPE = "GROUP_SOURCE_ASSOCIATION_ONLY"


def build_group_source(
    store: InvestigationStore, session: Session, task_id: UUID, entity_id: str
) -> dict[str, Any]:
    task = store._get(session, task_id, lock=True)
    binding = _latest(session, task_id)
    if task.status != "APPROVED" or binding is None or binding.delivery_hash != task.delivery_hash:
        raise InvestigationError("GROUP_BINDING_CONFLICT")
    if binding.request_hash != digest(binding.request):
        raise InvestigationError("GROUP_BINDING_INTEGRITY_FAILED")
    opportunity = session.scalar(
        select(Opportunity)
        .where(Opportunity.opportunity_id == binding.opportunity_id)
        .with_for_update()
    )
    bundle = session.scalar(
        select(SourceBundleRevision)
        .where(SourceBundleRevision.source_bundle_revision_id == binding.source_bundle_revision_id)
        .with_for_update()
    )
    if (
        opportunity is None
        or opportunity.current_version != binding.opportunity_version
        or bundle is None
        or bundle.status != "FROZEN"
    ):
        raise InvestigationError("GROUP_TARGET_VERSION_CONFLICT")
    command = BindInvestigation.model_validate(
        {k: v for k, v in binding.request.items() if k != "registration"}
    )
    _check_positions(session, task, command)
    if digest(store._source(session, CreateInvestigation.model_validate(task.request))) != digest(
        task.source_snapshot
    ):
        raise InvestigationError("SOURCE_POLICY_CHANGED")
    specs = _validated_members(store, session, task)
    members = list(
        session.scalars(
            select(SourceBundleMember).where(
                SourceBundleMember.source_bundle_revision_id == binding.source_bundle_revision_id
            )
        )
    )
    if any(not isinstance(spec, WmaBundleMemberSpec) for spec in specs):
        raise InvestigationError("GROUP_BINDING_DOCUMENTS_CHANGED")
    expected = {
        (s.material_id, s.document_id, s.evidence_ref_id, s.parse_attempt_id)
        for s in specs
        if isinstance(s, WmaBundleMemberSpec)
    }
    actual = {
        (m.wma_material_id, m.document_id, m.evidence_ref_id, m.parse_attempt_id) for m in members
    }
    if expected != actual or len(specs) != len(members):
        raise InvestigationError("GROUP_BINDING_DOCUMENTS_CHANGED")
    source = {
        "contract_version": GROUP_CONTRACT_VERSION,
        "scope": GROUP_SCOPE,
        "task_id": str(task_id),
        "delivery_hash": task.delivery_hash,
        "binding_id": str(binding.binding_id),
        "binding_hash": binding.request_hash,
        "opportunity_id": str(binding.opportunity_id),
        "opportunity_version": binding.opportunity_version,
        "source_bundle_revision_id": str(bundle.source_bundle_revision_id),
        "canonical_bundle_hash": bundle.canonical_bundle_hash,
        "source_snapshot_hash": digest(task.source_snapshot),
        **group_membership(
            task.delivery or {}, entity_id, [p.model_dump(mode="json") for p in command.positions]
        ),
    }
    return GroupSourceContext.model_validate(source).model_dump(mode="json")


def group_membership(
    delivery: dict[str, Any], entity_id: str, positions: list[dict[str, Any]]
) -> dict[str, Any]:
    """Use the frozen hierarchy, never a caller-selected subset of source children.

    ``positions`` is the current server-loaded binding, whose Unit/Version ownership
    is checked by the persistence boundary before calling this pure projection.
    """
    try:
        entity_rows = delivery["evidence"]["entities"]
        entities = {row["id"]: row for row in entity_rows}
        groups = delivery["opportunities"]["units"]
        group_ids = [group["id"] for group in groups]
        mapped = {row["entity_id"]: row for row in positions}
        if (
            len(entities) != len(entity_rows)
            or len(set(group_ids)) != len(group_ids)
            or len(mapped) != len(positions)
            or set(group_ids) != {row["id"] for row in entity_rows if row["kind"] == "unit"}
            or entity_id not in group_ids
        ):
            raise ValueError("invalid group identity")
        seen: set[str] = set()
        for group in groups:
            entity = entities[group["id"]]
            parent = entities[entity["parent_id"]]
            if parent["kind"] != "announcement" or group.get("parent_id") not in {
                None,
                parent["id"],
            }:
                raise ValueError("invalid group parent")
            for position in group["positions"]:
                child = entities[position["id"]]
                if (
                    child["kind"] != "position"
                    or child["parent_id"] != group["id"]
                    or child["id"] in seen
                ):
                    raise ValueError("invalid position parent")
                seen.add(child["id"])
        if seen != {row["id"] for row in entity_rows if row["kind"] == "position"}:
            raise ValueError("incomplete position denominator")
        if not set(mapped).issubset(seen):
            raise ValueError("binding contains unknown position")
        group = next(group for group in groups if group["id"] == entity_id)
        members = [
            {
                "entity_id": position["id"],
                "state": "BOUND" if position["id"] in mapped else "UNPROCESSED",
                "position_binding": deepcopy(mapped.get(position["id"])),
            }
            for position in group["positions"]
        ]
        return {
            "source_group": deepcopy(group),
            "source_entity": deepcopy(entities[entity_id]),
            "members": members,
            "membership_status": "NO_MEMBERS"
            if not members
            else (
                "UNPROCESSED_MEMBERS"
                if any(row["state"] == "UNPROCESSED" for row in members)
                else "ALL_MEMBERS_BOUND"
            ),
        }
    except (KeyError, TypeError, ValueError) as error:
        raise InvestigationError("GROUP_SOURCE_INVALID") from error
