"""Current-state reconstruction of immutable announcement inheritance views."""

from copy import deepcopy
from typing import Any
from uuid import UUID, uuid7

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from deepaha.investigations.announcement_sources import (
    SNAPSHOT_ADAPTER_VERSION,
    SNAPSHOT_CONTRACT_VERSION,
    build_announcement_snapshot,
)
from deepaha.investigations.bindings import _authorize
from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.models import InvestigationAnnouncementSnapshot
from deepaha.investigations.store import InvestigationStore
from deepaha.local_human_test.review import require_human_fact_reviewer
from deepaha.review.auth import ReviewerPrincipal


class MaterializeAnnouncementSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    expected_dependencies_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


def _view(record: InvestigationAnnouncementSnapshot, current: dict[str, Any]) -> dict[str, Any]:
    if (
        record.contract_version != SNAPSHOT_CONTRACT_VERSION
        or record.adapter_version != SNAPSHOT_ADAPTER_VERSION
        or record.dependencies_hash != digest(record.dependencies)
        or record.snapshot_hash != digest(record.snapshot)
    ):
        raise InvestigationError("ANNOUNCEMENT_SNAPSHOT_INTEGRITY_FAILED")
    if record.dependencies != current["dependencies"]:
        raise InvestigationError("ANNOUNCEMENT_SNAPSHOT_STALE")
    base = current["snapshot"]["base_v2"]
    if (
        record.snapshot != current["snapshot"]
        or record.dependencies_hash != current["dependencies_hash"]
        or str(record.base_plan_id) != base["plan_id"]
        or str(record.unit_version_id) != base["plan"]["target"]["unit_version_id"]
    ):
        raise InvestigationError("ANNOUNCEMENT_SNAPSHOT_INTEGRITY_FAILED")
    return {
        "snapshot_id": str(record.snapshot_id),
        "base_plan_id": str(record.base_plan_id),
        "contract_version": record.contract_version,
        "adapter_version": record.adapter_version,
        "dependencies": deepcopy(record.dependencies),
        "dependencies_hash": record.dependencies_hash,
        "snapshot": deepcopy(record.snapshot),
        "snapshot_hash": record.snapshot_hash,
        "reviewer_id": str(record.reviewer_id),
        "created_at": record.created_at.isoformat(),
    }


def preview_announcement_snapshot(
    store: InvestigationStore, task_id: UUID, base_plan_id: UUID, principal: ReviewerPrincipal
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        return build_announcement_snapshot(store, session, task_id, base_plan_id)


def materialize_announcement_snapshot(
    store: InvestigationStore,
    task_id: UUID,
    base_plan_id: UUID,
    expected_dependencies_hash: str,
    principal: ReviewerPrincipal,
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        current = build_announcement_snapshot(store, session, task_id, base_plan_id)
        if current["dependencies_hash"] != expected_dependencies_hash:
            raise InvestigationError("ANNOUNCEMENT_SNAPSHOT_INPUT_CHANGED")
        existing = session.scalar(
            select(InvestigationAnnouncementSnapshot).where(
                InvestigationAnnouncementSnapshot.base_plan_id == base_plan_id,
                InvestigationAnnouncementSnapshot.contract_version == SNAPSHOT_CONTRACT_VERSION,
                InvestigationAnnouncementSnapshot.adapter_version == SNAPSHOT_ADAPTER_VERSION,
                InvestigationAnnouncementSnapshot.dependencies_hash == expected_dependencies_hash,
            )
        )
        if existing is not None:
            return _view(existing, current)
        record = InvestigationAnnouncementSnapshot(
            snapshot_id=uuid7(),
            base_plan_id=base_plan_id,
            unit_version_id=UUID(
                current["snapshot"]["base_v2"]["plan"]["target"]["unit_version_id"]
            ),
            contract_version=SNAPSHOT_CONTRACT_VERSION,
            adapter_version=SNAPSHOT_ADAPTER_VERSION,
            dependencies=deepcopy(current["dependencies"]),
            dependencies_hash=expected_dependencies_hash,
            snapshot=deepcopy(current["snapshot"]),
            snapshot_hash=digest(current["snapshot"]),
            reviewer_id=principal.reviewer_id,
            created_at=store.clock(),
        )
        session.add(record)
        session.flush()
        session.refresh(record)
        return _view(record, current)


def load_announcement_snapshot(
    store: InvestigationStore, task_id: UUID, snapshot_id: UUID, principal: ReviewerPrincipal
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        record = session.get(InvestigationAnnouncementSnapshot, snapshot_id)
        if record is None:
            raise InvestigationError("ANNOUNCEMENT_SNAPSHOT_NOT_FOUND")
        current = build_announcement_snapshot(store, session, task_id, record.base_plan_id)
        return _view(record, current)
