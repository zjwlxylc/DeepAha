"""Append complete source associations without replacing existing position bindings."""

from typing import Any
from uuid import UUID, uuid7

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from deepaha.investigations.bindings import _authorize
from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.group_contracts import GroupSourcePreview, GroupSourceRecord
from deepaha.investigations.group_sources import (
    GROUP_CONTRACT_VERSION,
    GROUP_SCOPE,
    build_group_source,
)
from deepaha.investigations.models import InvestigationGroupBinding
from deepaha.investigations.store import InvestigationStore
from deepaha.local_human_test.review import require_human_fact_reviewer
from deepaha.p9b.identity import OpportunityUnitService, UnitSeed
from deepaha.p9b.models import OpportunityUnit, OpportunityUnitVersion
from deepaha.review.auth import ReviewerPrincipal


def _key(task_id: UUID, entity_id: str) -> str:
    return "group:" + digest([str(task_id), entity_id])


def _fingerprint(source_hash: str) -> str:
    return digest({"contract_version": GROUP_CONTRACT_VERSION, "group_source_hash": source_hash})


def _latest_group(
    session: Session, task_id: UUID, entity_id: str
) -> InvestigationGroupBinding | None:
    return session.scalar(
        select(InvestigationGroupBinding)
        .where(
            InvestigationGroupBinding.task_id == task_id,
            InvestigationGroupBinding.source_entity_id == entity_id,
        )
        .order_by(InvestigationGroupBinding.sequence.desc())
        .limit(1)
    )


def _identity(session: Session, row: InvestigationGroupBinding) -> dict[str, Any]:
    other_owner = session.scalar(
        select(InvestigationGroupBinding.group_binding_id)
        .where(
            InvestigationGroupBinding.unit_id == row.unit_id,
            or_(
                InvestigationGroupBinding.task_id != row.task_id,
                InvestigationGroupBinding.source_entity_id != row.source_entity_id,
            ),
        )
        .limit(1)
    )
    if other_owner is not None:
        raise InvestigationError("GROUP_SOURCE_IDENTITY_OWNERSHIP_CONFLICT")
    unit = session.scalar(
        select(OpportunityUnit)
        .where(OpportunityUnit.opportunity_unit_id == row.unit_id)
        .with_for_update()
    )
    version = session.get(OpportunityUnitVersion, row.unit_version_id)
    source = row.source
    if (
        unit is None
        or version is None
        or unit.unit_kind != "GROUP"
        or unit.current_version_id != row.unit_version_id
        or unit.lifecycle_status != "ACTIVE"
        or version.opportunity_unit_id != row.unit_id
        or version.status != "ACTIVE"
        or str(unit.opportunity_id) != source["opportunity_id"]
        or unit.opportunity_version != source["opportunity_version"]
        or version.opportunity_id != unit.opportunity_id
        or version.opportunity_version != unit.opportunity_version
        or str(version.source_bundle_revision_id) != source["source_bundle_revision_id"]
        or unit.current_unit_key != _key(row.task_id, row.source_entity_id)
        or unit.normalized_current_unit_key != unit.current_unit_key
        or version.identity_fingerprint != _fingerprint(row.source_hash)
        or version.canonical_label != source["source_group"]["name"]
        or row.source_hash != digest(source)
        or str(row.task_id) != source["task_id"]
        or str(row.binding_id) != source["binding_id"]
        or row.source_entity_id != source["source_group"]["id"]
        or source["contract_version"] != GROUP_CONTRACT_VERSION
        or source["scope"] != GROUP_SCOPE
    ):
        raise InvestigationError("GROUP_IDENTITY_INTEGRITY_FAILED")
    return {
        "unit_kind": "GROUP",
        "unit_id": str(unit.opportunity_unit_id),
        "public_id": unit.public_id,
        "unit_version_id": str(version.opportunity_unit_version_id),
        "version": version.version,
        "key": unit.current_unit_key,
        "label": version.canonical_label,
    }


def _view(
    session: Session, row: InvestigationGroupBinding, source: dict[str, Any]
) -> dict[str, Any]:
    if row.source != source or row.source_hash != digest(source):
        raise InvestigationError("GROUP_SOURCE_STALE")
    return GroupSourceRecord.model_validate(
        {
            "contract_version": GROUP_CONTRACT_VERSION,
            "scope": GROUP_SCOPE,
            "group_binding_id": str(row.group_binding_id),
            "group_identity": _identity(session, row),
            "source": source,
            "source_hash": row.source_hash,
            "reviewer_id": str(row.reviewer_id),
            "created_at": row.created_at,
        }
    ).model_dump(mode="json")


def preview_group_source(
    store: InvestigationStore, task_id: UUID, entity_id: str, principal: ReviewerPrincipal
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        source = build_group_source(store, session, task_id, entity_id)
        previous = _latest_group(session, task_id, entity_id)
        identity = _identity(session, previous) if previous else None
        if previous and previous.source["opportunity_id"] != source["opportunity_id"]:
            raise InvestigationError("GROUP_OPPORTUNITY_CONFLICT")
        return GroupSourcePreview.model_validate(
            {
                "source": source,
                "source_hash": digest(source),
                "existing_group_id": identity["unit_id"] if identity else None,
                "registration": _view(session, previous, source)
                if previous and previous.source == source
                else None,
            }
        ).model_dump(mode="json")


def register_group_source(
    store: InvestigationStore,
    task_id: UUID,
    entity_id: str,
    expected_source_hash: str,
    principal: ReviewerPrincipal,
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        source = build_group_source(store, session, task_id, entity_id)
        source_hash = digest(source)
        if expected_source_hash != source_hash:
            raise InvestigationError("GROUP_SOURCE_INPUT_CHANGED")
        previous = _latest_group(session, task_id, entity_id)
        if previous and previous.source == source:
            return _view(session, previous, source)
        now = store.clock()
        service = OpportunityUnitService(session)
        if previous:
            _identity(session, previous)
            if previous.source["opportunity_id"] != source["opportunity_id"]:
                raise InvestigationError("GROUP_OPPORTUNITY_CONFLICT")
            version = service.append_version_cas(
                opportunity_unit_id=previous.unit_id,
                expected_current_version_id=previous.unit_version_id,
                opportunity_version=source["opportunity_version"],
                source_bundle_revision_id=UUID(source["source_bundle_revision_id"]),
                effective_from=now,
                canonical_label=source["source_group"]["name"],
                identity_fingerprint=_fingerprint(source_hash),
            )
            unit_id, version_id = previous.unit_id, version.opportunity_unit_version_id
        else:
            unit = service.create_unit(
                opportunity_id=UUID(source["opportunity_id"]),
                opportunity_version=source["opportunity_version"],
                source_bundle_revision_id=UUID(source["source_bundle_revision_id"]),
                effective_from=now,
                seed=UnitSeed(
                    _key(task_id, entity_id),
                    "GROUP",
                    source["source_group"]["name"],
                    _fingerprint(source_hash),
                ),
            )
            assert unit.current_version_id is not None
            unit_id, version_id = unit.opportunity_unit_id, unit.current_version_id
        row = InvestigationGroupBinding(
            group_binding_id=uuid7(),
            task_id=task_id,
            binding_id=UUID(source["binding_id"]),
            source_entity_id=entity_id,
            sequence=previous.sequence + 1 if previous else 1,
            unit_id=unit_id,
            unit_version_id=version_id,
            source=source,
            source_hash=source_hash,
            reviewer_id=principal.reviewer_id,
            created_at=now,
        )
        session.add(row)
        session.flush()
        return _view(session, row, source)


def load_group_source(
    store: InvestigationStore, task_id: UUID, group_binding_id: UUID, principal: ReviewerPrincipal
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        row = session.get(InvestigationGroupBinding, group_binding_id)
        if row is None or row.task_id != task_id:
            raise InvestigationError("GROUP_SOURCE_NOT_FOUND")
        source = build_group_source(store, session, task_id, row.source_entity_id)
        return _view(session, row, source)
