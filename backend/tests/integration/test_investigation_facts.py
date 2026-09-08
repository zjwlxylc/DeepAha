"""Synthetic independent review mechanics; never real human acceptance evidence."""

import json
from hashlib import sha256
from typing import Any, cast
from uuid import UUID, uuid7

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import DBAPIError

from deepaha.investigations.contracts import (
    DecideInvestigationFact,
    InvestigationError,
    PrepareInvestigationFacts,
    PromoteInvestigationFacts,
    digest,
)
from deepaha.investigations.delivery import validate_delivery
from deepaha.investigations.facts import act_on_facts, prepare_facts
from deepaha.investigations.models import (
    InvestigationFactAction,
    InvestigationFactPreparation,
    InvestigationMaterial,
)
from deepaha.investigations.registration import register_identity
from deepaha.p9b.models import ExtractionCandidate, FactVerificationDecisionModel, VerifiedFact
from tests.integration.test_investigation_registration import _command
from tests.integration.test_investigation_store import (
    StoreHarness,
    _collecting,
    _files,
    _review,
    harness,
)

__all__ = ["harness"]
pytestmark = pytest.mark.integration


def _ready(
    h: StoreHarness,
    *,
    human_verify: bool = False,
    two_materials: bool = False,
    field: str = "学历要求",
    status: str = "CONFIRMED",
    announcement: bool = False,
    duplicate_materials: int = 0,
) -> tuple[UUID, PrepareInvestigationFacts]:
    task_id, owner = _collecting(h)
    files, artifacts = _files(task_id)
    opportunities, evidence = (
        json.loads(files["opportunities.json"]),
        json.loads(files["evidence.json"]),
    )
    content = '<html><body><p id="terms">学历要求：硕士及以上</p></body></html>'.encode()
    artifacts["notice"] = content
    evidence["artifacts"][0]["sha256"] = sha256(content).hexdigest()
    for item in [opportunities["units"][0]["positions"][0]["facts"][0], evidence["facts_flat"][0]]:
        item.update(field=field, value="硕士及以上", status=status)
        item["evidence"][0]["quote"] = "学历要求：硕士及以上"
        if human_verify:
            item["evidence"][0]["locator"]["human_verify"] = True
    if announcement:
        from copy import deepcopy

        parent = deepcopy(opportunities["units"][0]["positions"][0]["facts"][0])
        opportunities["announcement_level"] = [parent]
        evidence["facts_flat"].append(
            deepcopy(evidence["facts_flat"][0])
            | {"entity_id": "announcement", "entity_kind": "announcement", "level": "announcement"}
        )
    if two_materials:
        opportunities = json.loads(json.dumps(opportunities).replace('"notice"', '"z_notice"'))
        evidence = json.loads(json.dumps(evidence).replace('"notice"', '"z_notice"'))
        artifacts = {"z_notice": content, "a_attachment": b"<p>Additional official material</p>"}
        evidence["artifacts"].append(
            evidence["artifacts"][0]
            | {
                "artifact_id": "a_attachment",
                "source_url": "https://example.gov/attachment",
                "local_path": "artifacts/attachment.html",
                "file_name": "attachment.html",
                "remote_path": "/workspace/task/artifacts/attachment.html",
                "sha256": sha256(artifacts["a_attachment"]).hexdigest(),
            }
        )
    for copy_index in range(duplicate_materials):
        from copy import deepcopy

        material_id = f"notice-copy-{copy_index}"
        artifacts[material_id] = content
        evidence["artifacts"].append(
            deepcopy(evidence["artifacts"][0])
            | {
                "artifact_id": material_id,
                "source_url": f"https://example.gov/notice?copy={copy_index}",
                "local_path": f"artifacts/{material_id}.html",
                "file_name": f"{material_id}.html",
                "remote_path": f"/workspace/task/artifacts/{material_id}.html",
            }
        )
    files["opportunities.json"] = json.dumps(opportunities).encode()
    files["evidence.json"] = json.dumps(evidence).encode()
    delivery = validate_delivery(files, artifacts)
    h.store.freeze_manifest(task_id, owner, files)
    h.store.finish(task_id, owner, delivery, files)
    prepared = h.store.prepare_documents(task_id, delivery.sha256, h.principal)
    h.store.review(task_id, _review(delivery), h.principal, "synthetic-intake")
    bound = register_identity(
        h.store,
        task_id,
        _command(
            delivery,
            positions=[
                {
                    "entity_id": "position",
                    "unit_key": "P1",
                    "label": "Synthetic position",
                }
            ],
        ),
        h.principal,
        "synthetic-identity",
    )
    return task_id, PrepareInvestigationFacts(
        delivery_hash=delivery.sha256,
        binding_id=UUID(bound["entity_binding"]["binding_id"]),
        check_id=UUID(prepared["evidence_check"]["check_id"]),
    )


def test_preparation_reuses_common_anchors_without_approving(harness: StoreHarness) -> None:
    h = harness
    task_id, command = _ready(h)
    original = h.store.get(task_id)
    result = prepare_facts(h.store, task_id, command, h.principal)
    current: dict[str, Any] = result["current"]
    row = current["rows"][0]
    assert current["check_id"] == str(command.check_id)
    assert row["normalized_value_candidate"] == {"minimum_level": "MASTER"}
    assert row["ready_for_persistence"] and not row["abstained"]
    assert row["evidence"][0]["binding"]["structural_locator"]["kind"] == "reader_anchor"
    assert row["evidence"][0]["check_reference"] == original["evidence_check"]["references"][0]
    assert prepare_facts(h.store, task_id, command, h.principal) == result
    assert h.store.get(task_id)["facts"] == original["facts"]
    with h.factory() as session:
        assert len(list(session.scalars(select(ExtractionCandidate)))) == 1
        assert not list(session.scalars(select(FactVerificationDecisionModel)))
        assert not list(session.scalars(select(VerifiedFact)))


def test_multiple_materials_replay_in_canonical_raw_identity_order(harness: StoreHarness) -> None:
    h = harness
    task_id, command = _ready(h, two_materials=True)
    with h.factory() as session:
        ordered = list(
            session.scalars(
                select(InvestigationMaterial).order_by(
                    InvestigationMaterial.raw_artifact_id, InvestigationMaterial.material_id
                )
            )
        )
        assert [m.material_id for m in ordered] == ["z_notice", "a_attachment"]
    prepared = prepare_facts(h.store, task_id, command, h.principal)
    assert prepared["current"]["rows"][0]["candidate_id"] is not None
    assert prepare_facts(h.store, task_id, command, h.principal) == prepared


@pytest.mark.parametrize("change", ["block_text", "structural_locator", "material_id"])
def test_non_candidate_evidence_enrichment_is_checked_by_database(
    harness: StoreHarness, change: str
) -> None:
    h = harness
    task_id, command = _ready(h, field="Synthetic unsupported field")

    def corrupt(_mapper: Any, _connection: Any, prep: InvestigationFactPreparation) -> None:
        row = cast(list[dict[str, Any]], prep.result["rows"])[0]
        assert row["candidate_id"] is None
        assert row["evidence"][0]["check_reference"]["verdict"] == "PASS"
        row["evidence"][0]["binding"][change] = {} if change == "structural_locator" else "Forged"
        prep.result_hash = digest(prep.result)

    event.listen(InvestigationFactPreparation, "before_insert", corrupt)
    try:
        with pytest.raises(DBAPIError, match="INVESTIGATION_FACT_CHECK_MISMATCH"):
            prepare_facts(h.store, task_id, command, h.principal)
    finally:
        event.remove(InvestigationFactPreparation, "before_insert", corrupt)


def test_human_verify_remains_unprocessed_and_cannot_create_a_candidate(
    harness: StoreHarness,
) -> None:
    h = harness
    task_id, command = _ready(h, human_verify=True)
    current = prepare_facts(h.store, task_id, command, h.principal)["current"]
    row = current["rows"][0]
    assert row["source_index"] == 0 and row["candidate_id"] is None
    assert row["evidence"][0]["check_reference"]["verdict"] == "UNVERIFIED"
    assert row["evidence"][0]["binding"] is None
    assert "UNKNOWN_EVIDENCE_UNVERIFIED" in row["issue_codes"]
    with h.factory() as session:
        assert not list(session.scalars(select(ExtractionCandidate)))


def test_investigated_unknown_requires_explicit_unknown_decision(harness: StoreHarness) -> None:
    h = harness
    task_id, command = _ready(h, status="UNKNOWN")
    prep = prepare_facts(h.store, task_id, command, h.principal)["current"]
    row = prep["rows"][0]
    assert row["original_status"] == "UNKNOWN" and row["candidate_id"] is not None
    assert row["abstained"] and row["normalized_value_candidate"] is None
    assert row["evidence"][0]["check_reference"]["verdict"] == "PASS"
    base = command.model_dump() | {
        "preparation_id": prep["preparation_id"],
        "reason": "Synthetic unknown",
    }
    decision = DecideInvestigationFact.model_validate(
        base
        | {
            "candidate_id": row["candidate_id"],
            "decision": "APPROVE",
            "evidence_support": "SUPPORTED",
            "precedence_check": "PASSED",
        }
    )
    with pytest.raises(InvestigationError, match="DECISION_OR_PROMOTION_INVALID"):
        act_on_facts(h.store, task_id, decision, h.principal, "cannot-approve-unknown")
    act_on_facts(
        h.store,
        task_id,
        decision.model_copy(update={"decision": "UNKNOWN"}),
        h.principal,
        "explicit-unknown",
    )
    act_on_facts(
        h.store,
        task_id,
        PromoteInvestigationFacts.model_validate(base | {"entity_id": "position"}),
        h.principal,
        "save-unknown",
    )
    with h.factory() as session:
        verified = list(session.scalars(select(VerifiedFact)))
        assert len(verified) == 1 and verified[0].normalized_value is None


def test_only_explicit_independent_decision_can_create_a_fact(harness: StoreHarness) -> None:
    h = harness
    task_id, command = _ready(h)
    current = prepare_facts(h.store, task_id, command, h.principal)["current"]
    base = command.model_dump() | {
        "preparation_id": UUID(current["preparation_id"]),
        "reason": "Synthetic review",
    }
    promotion = PromoteInvestigationFacts.model_validate(base | {"entity_id": "position"})
    with pytest.raises(InvestigationError, match="ALL_CANDIDATES_REQUIRE_DECISION"):
        act_on_facts(h.store, task_id, promotion, h.principal, "premature")
    decision = DecideInvestigationFact.model_validate(
        base
        | {
            "candidate_id": current["rows"][0]["candidate_id"],
            "decision": "APPROVE",
            "evidence_support": "UNKNOWN",
            "precedence_check": "UNKNOWN",
        }
    )
    with pytest.raises(InvestigationError, match="DECISION_OR_PROMOTION_INVALID"):
        act_on_facts(h.store, task_id, decision, h.principal, "unsupported")
    decision = decision.model_copy(
        update={"evidence_support": "SUPPORTED", "precedence_check": "PASSED"}
    )
    act_on_facts(h.store, task_id, decision, h.principal, "explicit")
    promoted = act_on_facts(h.store, task_id, promotion, h.principal, "save")
    assert act_on_facts(h.store, task_id, promotion, h.principal, "save") == promoted
    with h.factory() as session:
        verified = list(session.scalars(select(VerifiedFact)))
        assert len(verified) == 1 and verified[0].normalized_value == {"minimum_level": "MASTER"}


def test_pending_adjudication_can_be_resolved_without_overwriting_history(
    harness: StoreHarness,
) -> None:
    h = harness
    task_id, command = _ready(h)
    prep = prepare_facts(h.store, task_id, command, h.principal)["current"]
    base = command.model_dump() | {"preparation_id": prep["preparation_id"], "reason": "Synthetic"}
    pending = DecideInvestigationFact.model_validate(
        base
        | {
            "candidate_id": prep["rows"][0]["candidate_id"],
            "decision": "NEEDS_ADJUDICATION",
            "evidence_support": "UNKNOWN",
            "precedence_check": "UNKNOWN",
        }
    )
    act_on_facts(h.store, task_id, pending, h.principal, "pending")
    promotion = PromoteInvestigationFacts.model_validate(base | {"entity_id": "position"})
    with pytest.raises(InvestigationError, match="ALL_CANDIDATES_REQUIRE_DECISION"):
        act_on_facts(h.store, task_id, promotion, h.principal, "premature")
    final = pending.model_copy(
        update={
            "decision": "APPROVE",
            "evidence_support": "SUPPORTED",
            "precedence_check": "PASSED",
        }
    )
    decided = act_on_facts(h.store, task_id, final, h.principal, "resolved")
    assert act_on_facts(h.store, task_id, final, h.principal, "resolved") == decided
    with (
        h.factory.begin() as session,
        pytest.raises(DBAPIError, match="uq_investigation_fact_action_decision"),
    ):
        action = session.scalar(
            select(InvestigationFactAction).order_by(InvestigationFactAction.action_id.desc())
        )
        assert action is not None
        values = {
            column.name: getattr(action, column.name)
            for column in InvestigationFactAction.__table__.columns
        }
        values.update(
            action_id=uuid7(), request_key_hash=sha256(b"duplicate-audit-receipt").hexdigest()
        )
        session.add(InvestigationFactAction(**values))
        session.flush()
    with pytest.raises(InvestigationError, match="ALREADY_DECIDED"):
        act_on_facts(h.store, task_id, pending, h.principal, "cannot-reopen-final")
    act_on_facts(h.store, task_id, promotion, h.principal, "save-resolved")
    with h.factory() as session:
        assert len(list(session.scalars(select(FactVerificationDecisionModel)))) == 2
        assert len(list(session.scalars(select(VerifiedFact)))) == 1


@pytest.mark.parametrize("operation", ["prepare", "decide", "promote"])
def test_new_verifier_version_rejects_stale_preparation(
    harness: StoreHarness,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    h = harness
    task_id, command = _ready(h)
    current = prepare_facts(h.store, task_id, command, h.principal)["current"]
    monkeypatch.setattr("deepaha.investigations.evidence_checks.VERIFIER_VERSION", "synthetic-next")
    with pytest.raises(InvestigationError, match="EVIDENCE_CHECK_REFRESH_REQUIRED"):
        if operation == "prepare":
            prepare_facts(h.store, task_id, command, h.principal)
        elif operation == "decide":
            decision = DecideInvestigationFact.model_validate(
                command.model_dump()
                | {
                    "preparation_id": current["preparation_id"],
                    "candidate_id": current["rows"][0]["candidate_id"],
                    "decision": "APPROVE",
                    "evidence_support": "SUPPORTED",
                    "precedence_check": "PASSED",
                    "reason": "Synthetic",
                }
            )
            act_on_facts(h.store, task_id, decision, h.principal, "stale")
        else:
            promotion = PromoteInvestigationFacts.model_validate(
                command.model_dump()
                | {
                    "preparation_id": current["preparation_id"],
                    "entity_id": "position",
                    "reason": "Synthetic",
                }
            )
            act_on_facts(h.store, task_id, promotion, h.principal, "stale")


@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_preparation_is_immutable(harness: StoreHarness, operation: str) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    h = harness
    task_id, command = _ready(h)
    prepare_facts(h.store, task_id, command, h.principal)
    statement = (
        "DELETE FROM investigation_fact_preparations"
        if operation == "DELETE"
        else "UPDATE investigation_fact_preparations SET result = '{}'::jsonb"
    )
    with h.factory.begin() as session, pytest.raises(DBAPIError, match="IMMUTABLE"):
        session.execute(text(statement))


@pytest.mark.parametrize("change", ["check_id", "decision", "evidence_support"])
def test_database_rejects_action_not_matching_recorded_decision(
    harness: StoreHarness, change: str
) -> None:
    h = harness
    task_id, command = _ready(h)
    prep = prepare_facts(h.store, task_id, command, h.principal)["current"]
    decision = DecideInvestigationFact.model_validate(
        command.model_dump()
        | {
            "preparation_id": prep["preparation_id"],
            "candidate_id": prep["rows"][0]["candidate_id"],
            "decision": "APPROVE",
            "evidence_support": "SUPPORTED",
            "precedence_check": "PASSED",
            "reason": "Synthetic",
        }
    )

    def corrupt(_mapper: Any, _connection: Any, action: InvestigationFactAction) -> None:
        action.request[change] = {
            "check_id": str(task_id),
            "decision": "REJECT",
            "evidence_support": "UNSUPPORTED",
        }[change]
        action.request_hash = digest(action.request)

    event.listen(InvestigationFactAction, "before_insert", corrupt)
    try:
        with pytest.raises(DBAPIError, match="INVESTIGATION_FACT_(REQUEST|DECISION)_MISMATCH"):
            act_on_facts(h.store, task_id, decision, h.principal, "tampered")
    finally:
        event.remove(InvestigationFactAction, "before_insert", corrupt)
    with h.factory() as session:
        assert not list(session.scalars(select(FactVerificationDecisionModel)))
        assert not list(session.scalars(select(InvestigationFactAction)))


def test_history_prevents_migration_rollback(harness: StoreHarness) -> None:
    from alembic import command as alembic_command
    from alembic.config import Config

    h = harness
    task_id, command = _ready(h)
    prepare_facts(h.store, task_id, command, h.principal)
    with pytest.raises(RuntimeError, match="INVESTIGATION_FACT_HISTORY_DOWNGRADE_REFUSED"):
        alembic_command.downgrade(Config("alembic.ini"), "20260908_0039")
    assert h.store.get(task_id)["fact_review"]["current"] is not None
