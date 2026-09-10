from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid7

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError

from deepaha.artifacts.models import RawArtifact
from deepaha.investigations.contracts import (
    InvestigationError,
    RegisterInvestigationPositions,
    digest,
)
from deepaha.investigations.group_bindings import (
    _fingerprint,
    _key,
    load_group_source,
    preview_group_source,
    register_group_source,
)
from deepaha.investigations.models import InvestigationGroupBinding
from deepaha.investigations.registration import register_identity, register_positions
from deepaha.p9b.identity import OpportunityUnitService
from deepaha.p9b.models import (
    OpportunityUnit,
    OpportunityUnitAlias,
    OpportunityUnitVersion,
    VerifiedFact,
)
from deepaha.review.models import ReviewerAccountModel
from deepaha.sources.models import SourceEndpoint
from tests.integration.test_investigation_registration import _command, _ready
from tests.integration.test_investigation_store import StoreHarness, _count, harness
from tests.investigations.test_delivery import _sample

pytestmark = pytest.mark.integration
__all__ = ["harness"]


def _registered(h: StoreHarness) -> tuple[UUID, dict[str, Any]]:
    task, delivery = _ready(h)
    binding = register_identity(h.store, task, _command(delivery), h.principal, "initial")[
        "entity_binding"
    ]
    return task, binding


@pytest.mark.parametrize("nested_parent_null", [False, True])
def test_group_source_preserves_unbound_members_and_does_not_create_facts(
    harness: StoreHarness,
    monkeypatch: pytest.MonkeyPatch,
    nested_parent_null: bool,
) -> None:
    if nested_parent_null:

        def null_parent() -> tuple[dict[str, Any], dict[str, Any], dict[str, bytes]]:
            opportunities, evidence, artifacts = _sample()
            opportunities["units"][0]["parent_id"] = None
            return opportunities, evidence, artifacts

        monkeypatch.setattr("tests.integration.test_investigation_store._sample", null_parent)
    h = harness
    task, binding = _registered(h)
    original_task = h.store.get(task)
    preview = preview_group_source(h.store, task, "unit", h.principal)
    assert preview["source"]["members"] == [
        {"entity_id": "position", "state": "UNPROCESSED", "position_binding": None}
    ]
    record = register_group_source(h.store, task, "unit", preview["source_hash"], h.principal)
    assert record["scope"] == "GROUP_SOURCE_ASSOCIATION_ONLY"
    assert record["source"]["binding_id"] == binding["binding_id"]
    assert record["group_identity"]["unit_kind"] == "GROUP"
    assert load_group_source(h.store, task, UUID(record["group_binding_id"]), h.principal) == record
    assert (
        register_group_source(h.store, task, "unit", preview["source_hash"], h.principal) == record
    )
    assert h.store.get(task) == original_task
    with h.factory() as session:
        assert _count(session, OpportunityUnit) == 1
        assert _count(session, OpportunityUnitVersion) == 1
        assert _count(session, VerifiedFact) == 0


def test_changed_binding_keeps_group_id_and_appends_version(harness: StoreHarness) -> None:
    h = harness
    task, binding = _registered(h)
    old_source = preview_group_source(h.store, task, "unit", h.principal)
    old = register_group_source(h.store, task, "unit", old_source["source_hash"], h.principal)
    h.clock.value += timedelta(seconds=1)
    new_binding = register_positions(
        h.store,
        task,
        RegisterInvestigationPositions.model_validate(
            {
                "delivery_hash": binding["delivery_hash"],
                "previous_binding_id": binding["binding_id"],
                "positions": [{"entity_id": "position", "unit_key": "01", "label": "Position"}],
                "reason": "Synthetic position registration",
            }
        ),
        h.principal,
        "position",
    )["entity_binding"]
    with pytest.raises(InvestigationError, match="GROUP_SOURCE_STALE"):
        load_group_source(h.store, task, UUID(old["group_binding_id"]), h.principal)
    with pytest.raises(InvestigationError, match="GROUP_SOURCE_INPUT_CHANGED"):
        register_group_source(h.store, task, "unit", old_source["source_hash"], h.principal)
    h.clock.value += timedelta(seconds=1)
    current = preview_group_source(h.store, task, "unit", h.principal)
    new = register_group_source(h.store, task, "unit", current["source_hash"], h.principal)
    assert new["group_binding_id"] != old["group_binding_id"]
    assert new["group_identity"]["unit_id"] == old["group_identity"]["unit_id"]
    assert new["group_identity"]["version"] == 2
    assert new["source"]["members"][0]["position_binding"] == new_binding["positions"][0]
    with h.factory() as session:
        rows = list(
            session.scalars(select(OpportunityUnit).where(OpportunityUnit.unit_kind == "GROUP"))
        )
        assert len(rows) == 1
        assert session.scalar(text("SELECT count(*) FROM investigation_group_bindings")) == 2


def test_concurrent_group_registration_is_idempotent(harness: StoreHarness) -> None:
    h = harness
    task, _ = _registered(h)
    preview = preview_group_source(h.store, task, "unit", h.principal)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: register_group_source(
                    h.store, task, "unit", preview["source_hash"], h.principal
                ),
                range(2),
            )
        )
    assert results[0] == results[1]
    with h.factory() as session:
        assert _count(session, OpportunityUnit) == 1
        assert session.scalar(text("SELECT count(*) FROM investigation_group_bindings")) == 1


@pytest.mark.parametrize("operation", ["preview", "register", "read"])
def test_group_operations_recheck_revoked_authority(harness: StoreHarness, operation: str) -> None:
    h = harness
    task, _ = _registered(h)
    preview = preview_group_source(h.store, task, "unit", h.principal)
    record = register_group_source(h.store, task, "unit", preview["source_hash"], h.principal)
    with h.factory.begin() as session:
        reviewer = session.get(ReviewerAccountModel, h.principal.reviewer_id)
        assert reviewer is not None
        reviewer.active = False
    with pytest.raises(InvestigationError, match="HUMAN_VALIDATION_AUTHORITY_REQUIRED"):
        if operation == "preview":
            preview_group_source(h.store, task, "unit", h.principal)
        elif operation == "register":
            register_group_source(h.store, task, "unit", preview["source_hash"], h.principal)
        else:
            load_group_source(h.store, task, UUID(record["group_binding_id"]), h.principal)


@pytest.mark.parametrize("operation", ["preview", "register", "read"])
def test_group_operations_recheck_original_bytes(harness: StoreHarness, operation: str) -> None:
    h = harness
    task, _ = _registered(h)
    preview = preview_group_source(h.store, task, "unit", h.principal)
    record = register_group_source(h.store, task, "unit", preview["source_hash"], h.principal)
    with h.factory() as session:
        original = session.scalar(select(RawArtifact))
        assert original is not None
        key = original.object_key
    metadata = h.objects.stat(key=key)
    h.objects.delete_if_matches(key=key, sha256=metadata.sha256)
    with pytest.raises(InvestigationError, match="STORED_MATERIAL_INTEGRITY_FAILED"):
        if operation == "preview":
            preview_group_source(h.store, task, "unit", h.principal)
        elif operation == "register":
            register_group_source(h.store, task, "unit", preview["source_hash"], h.principal)
        else:
            load_group_source(h.store, task, UUID(record["group_binding_id"]), h.principal)


def test_changed_source_policy_and_cross_task_read_are_rejected(harness: StoreHarness) -> None:
    h = harness
    task, _ = _registered(h)
    preview = preview_group_source(h.store, task, "unit", h.principal)
    record = register_group_source(h.store, task, "unit", preview["source_hash"], h.principal)
    with pytest.raises(InvestigationError, match="GROUP_SOURCE_NOT_FOUND"):
        load_group_source(h.store, uuid7(), UUID(record["group_binding_id"]), h.principal)
    with h.factory.begin() as session:
        endpoint = session.get(SourceEndpoint, h.command.endpoint_id)
        assert endpoint is not None
        endpoint.policy_version = "changed-policy"
    with pytest.raises(InvestigationError, match="SOURCE_POLICY_CHANGED"):
        register_group_source(h.store, task, "unit", preview["source_hash"], h.principal)


def test_external_group_version_cannot_reuse_old_receipt(harness: StoreHarness) -> None:
    h = harness
    task, binding = _registered(h)
    preview = preview_group_source(h.store, task, "unit", h.principal)
    record = register_group_source(h.store, task, "unit", preview["source_hash"], h.principal)
    h.clock.value += timedelta(seconds=1)
    with h.factory.begin() as session:
        OpportunityUnitService(session).append_version_cas(
            opportunity_unit_id=UUID(record["group_identity"]["unit_id"]),
            expected_current_version_id=UUID(record["group_identity"]["unit_version_id"]),
            opportunity_version=1,
            source_bundle_revision_id=UUID(binding["source_bundle_revision_id"]),
            effective_from=h.clock.value,
            canonical_label="External changed group",
            identity_fingerprint="d" * 64,
        )
    with pytest.raises(InvestigationError, match="GROUP_IDENTITY_INTEGRITY_FAILED"):
        register_group_source(h.store, task, "unit", preview["source_hash"], h.principal)


@pytest.mark.parametrize("mutation", ["drop_member", "hide_unknown", "change_source_group"])
def test_sql_rejects_rehashed_false_source_and_rolls_back_group(
    harness: StoreHarness, mutation: str
) -> None:
    h = harness
    task, _ = _registered(h)
    preview = preview_group_source(h.store, task, "unit", h.principal)

    def tamper(mapper: Any, connection: Any, target: InvestigationGroupBinding) -> None:
        if mutation == "drop_member":
            target.source["members"] = []
        elif mutation == "hide_unknown":
            target.source["membership_status"] = "ALL_MEMBERS_BOUND"
        else:
            target.source["source_group"]["name"] = "Another group"
        target.source_hash = digest(target.source)

    event.listen(InvestigationGroupBinding, "before_insert", tamper)
    try:
        with pytest.raises(DBAPIError, match="GROUP_SOURCE_CONTENT_INVALID"):
            register_group_source(h.store, task, "unit", preview["source_hash"], h.principal)
    finally:
        event.remove(InvestigationGroupBinding, "before_insert", tamper)
    with h.factory() as session:
        assert _count(session, OpportunityUnit) == 0
        assert _count(session, InvestigationGroupBinding) == 0


@pytest.mark.parametrize(
    "operation",
    [
        "UPDATE investigation_group_bindings SET source_hash='" + "b" * 64 + "'",
        "DELETE FROM investigation_group_bindings",
    ],
)
def test_group_source_history_is_immutable(harness: StoreHarness, operation: str) -> None:
    h = harness
    task, _ = _registered(h)
    preview = preview_group_source(h.store, task, "unit", h.principal)
    record = register_group_source(h.store, task, "unit", preview["source_hash"], h.principal)
    with pytest.raises(DBAPIError, match="GROUP_SOURCE_IMMUTABLE"), h.factory.begin() as session:
        session.execute(
            text(operation + " WHERE group_binding_id=:id"),
            {"id": UUID(record["group_binding_id"])},
        )
    assert load_group_source(h.store, task, UUID(record["group_binding_id"]), h.principal) == record


def test_sql_cannot_borrow_another_groups_identity_with_valid_key_and_version(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    def two_groups() -> tuple[dict[str, Any], dict[str, Any], dict[str, bytes]]:
        opportunities, evidence, artifacts = _sample()
        opportunities["units"].append(
            {
                "id": "other-unit",
                "name": "Other group",
                "parent_id": "announcement",
                "unit_level": [],
                "positions": [],
            }
        )
        evidence["entities"].append(
            {"id": "other-unit", "name": "Other group", "kind": "unit", "parent_id": "announcement"}
        )
        return opportunities, evidence, artifacts

    monkeypatch.setattr("tests.integration.test_investigation_store._sample", two_groups)
    h = harness
    task, binding = _registered(h)
    preview = preview_group_source(h.store, task, "unit", h.principal)
    original = register_group_source(h.store, task, "unit", preview["source_hash"], h.principal)
    other = preview_group_source(h.store, task, "other-unit", h.principal)
    h.clock.value += timedelta(seconds=1)
    with (
        pytest.raises(DBAPIError, match="GROUP_SOURCE_IDENTITY_OWNERSHIP_CONFLICT"),
        h.factory.begin() as session,
    ):
        unit_id = UUID(original["group_identity"]["unit_id"])
        alias = session.scalar(
            select(OpportunityUnitAlias).where(
                OpportunityUnitAlias.opportunity_unit_id == unit_id,
                OpportunityUnitAlias.alias_kind == "CURRENT",
            )
        )
        assert alias is not None
        alias.alias_kind, alias.valid_to = "HISTORICAL", h.clock.value
        session.flush()
        version = OpportunityUnitService(session).append_version_cas(
            opportunity_unit_id=unit_id,
            expected_current_version_id=UUID(original["group_identity"]["unit_version_id"]),
            opportunity_version=1,
            source_bundle_revision_id=UUID(binding["source_bundle_revision_id"]),
            effective_from=h.clock.value,
            canonical_label="Other group",
            identity_fingerprint=_fingerprint(other["source_hash"]),
        )
        unit = session.get(OpportunityUnit, unit_id)
        assert unit is not None
        unit.current_unit_key = unit.normalized_current_unit_key = _key(task, "other-unit")
        session.add(
            OpportunityUnitAlias(
                alias_id=uuid7(),
                opportunity_id=unit.opportunity_id,
                opportunity_unit_id=unit_id,
                normalized_alias_key=unit.current_unit_key,
                display_alias_key=unit.current_unit_key,
                alias_kind="CURRENT",
                valid_from=h.clock.value,
                valid_to=None,
                evidence_ref_id=alias.evidence_ref_id,
                source_bundle_revision_id=alias.source_bundle_revision_id,
                created_at=h.clock.value,
            )
        )
        session.flush()
        session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        session.add(
            InvestigationGroupBinding(
                group_binding_id=uuid7(),
                task_id=task,
                binding_id=UUID(binding["binding_id"]),
                source_entity_id="other-unit",
                sequence=1,
                unit_id=unit_id,
                unit_version_id=version.opportunity_unit_version_id,
                source=other["source"],
                source_hash=other["source_hash"],
                reviewer_id=h.principal.reviewer_id,
                created_at=h.clock.value,
            )
        )
        session.flush()
    assert (
        load_group_source(h.store, task, UUID(original["group_binding_id"]), h.principal)
        == original
    )
