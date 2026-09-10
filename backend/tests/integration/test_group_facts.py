"""Synthetic human accounts exercise mechanics, never actual human acceptance."""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid7

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError

from deepaha.artifacts.models import RawArtifact
from deepaha.investigations.contracts import InvestigationError, PromoteInvestigationFacts, digest
from deepaha.investigations.facts import act_on_facts
from deepaha.investigations.group_bindings import preview_group_source, register_group_source
from deepaha.investigations.group_fact_contracts import (
    DecideGroupFact,
    PrepareGroupFacts,
    PromoteGroupFacts,
)
from deepaha.investigations.group_facts import (
    act_on_group_facts,
    load_group_facts,
    prepare_group_facts,
)
from deepaha.investigations.models import (
    InvestigationGroupFactAction,
    InvestigationGroupFactPreparation,
)
from deepaha.p9b.identity import OpportunityUnitService
from deepaha.p9b.models import (
    ExtractionCandidate,
    ExtractionCandidateEvidence,
    FactVerificationDecisionModel,
    VerifiedFact,
    VersionedVerifiedFactSet,
)
from deepaha.review.models import ReviewerAccountModel
from deepaha.sources.models import SourceEndpoint
from tests.integration.test_investigation_facts import _ready
from tests.integration.test_investigation_store import StoreHarness, harness
from tests.investigations.test_delivery import _sample

pytestmark = pytest.mark.integration
__all__ = ["harness"]


def ready_group(
    h: StoreHarness, monkeypatch: pytest.MonkeyPatch, **options: Any
) -> tuple[UUID, UUID, PrepareGroupFacts]:
    def group_sample() -> tuple[dict[str, Any], dict[str, Any], dict[str, bytes]]:
        opportunities, evidence, artifacts = _sample()
        if options.get("empty"):
            return opportunities, evidence, artifacts
        fact = deepcopy(opportunities["units"][0]["positions"][0]["facts"][0])
        fact.update(
            field=options.get("field", "学历要求"),
            value="硕士及以上",
            status=options.get("status", "CONFIRMED"),
        )
        fact["evidence"][0]["quote"] = "学历要求：硕士及以上"
        if options.get("unverified"):
            fact["evidence"][0]["locator"]["human_verify"] = True
        if fact["status"] == "UNKNOWN":
            fact["value"] = None
        opportunities["units"][0]["unit_level"] = [fact]
        evidence["facts_flat"].append(
            {
                "entity_id": "unit",
                "entity_kind": "unit",
                "level": "unit",
                "opportunity_id": "announcement",
                **deepcopy(fact),
            }
        )
        if options.get("two") or options.get("two_evidence"):
            other = deepcopy(fact) | {
                "field": "另一未能确认的学历条件",
                "status": "UNKNOWN",
                "value": None,
            }
            # A supported alias deliberately produces a second candidate; both need decisions.
            other["field"] = options.get("other_field", "学历")
            if options.get("two_evidence"):
                other["evidence"][0]["artifact_id"] = "a_attachment"
                other["evidence"][0]["quote"] = "Additional official material"
                other["evidence"][0]["locator"] = {"selector": "p"}
            opportunities["units"][0]["unit_level"].append(other)
            evidence["facts_flat"].append(
                {
                    "entity_id": "unit",
                    "entity_kind": "unit",
                    "level": "unit",
                    "opportunity_id": "announcement",
                    **deepcopy(other),
                }
            )
        return opportunities, evidence, artifacts

    monkeypatch.setattr("tests.integration.test_investigation_store._sample", group_sample)
    task, command = _ready(h, two_materials=bool(options.get("two_evidence")))
    source = preview_group_source(h.store, task, "unit", h.principal)
    registered = register_group_source(h.store, task, "unit", source["source_hash"], h.principal)
    return (
        task,
        UUID(registered["group_binding_id"]),
        PrepareGroupFacts(check_id=command.check_id, expected_source_hash=source["source_hash"]),
    )


def test_group_candidates_use_own_identity_and_keep_other_scope_exclusions(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, group_id, command = ready_group(h, monkeypatch)
    original = h.store.get(task)
    result = prepare_group_facts(h.store, task, group_id, command, h.principal)
    assert result["result"]["source_row_count"] == 2
    row = result["result"]["rows"][0]
    assert row["entity_id"] == "unit"
    assert original["facts"][row["source_index"]]["entity_id"] == "unit"
    assert row["normalized_value_candidate"] == {"minimum_level": "MASTER"}
    assert result["result"]["excluded_rows"][0]["entity_id"] == "position"
    assert prepare_group_facts(h.store, task, group_id, command, h.principal) == result
    assert load_group_facts(h.store, task, UUID(result["preparation_id"]), h.principal) == result
    assert h.store.get(task) == original
    with h.factory() as session:
        candidate = session.get(ExtractionCandidate, UUID(row["candidate_id"]))
        assert candidate is not None
        assert (
            str(candidate.opportunity_unit_id)
            == result["result"]["group_source"]["group_identity"]["unit_id"]
        )
        assert not list(session.scalars(select(VerifiedFact)))


def test_group_fact_requires_explicit_supported_review(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, group_id, command = ready_group(h, monkeypatch)
    prep = prepare_group_facts(h.store, task, group_id, command, h.principal)
    prep_id = UUID(prep["preparation_id"])
    promotion = PromoteGroupFacts(
        expected_preparation_hash=prep["result_hash"], reason="Synthetic independent review"
    )
    with pytest.raises(InvestigationError, match="ALL_CANDIDATES_REQUIRE_DECISION"):
        act_on_group_facts(h.store, task, prep_id, promotion, h.principal, "premature")
    decision = DecideGroupFact(
        expected_preparation_hash=prep["result_hash"],
        candidate_id=prep["result"]["rows"][0]["candidate_id"],
        decision="APPROVE",
        evidence_support="SUPPORTED",
        precedence_check="PASSED",
        reason="Synthetic original verified",
    )
    act_on_group_facts(h.store, task, prep_id, decision, h.principal, "approve")
    result = act_on_group_facts(h.store, task, prep_id, promotion, h.principal, "promote")
    assert act_on_group_facts(h.store, task, prep_id, promotion, h.principal, "promote") == result
    assert result["fact_set"]["status"] == "ACTIVE"


@pytest.mark.parametrize("options", [{"field": "尚不支持的组字段"}, {"unverified": True}])
def test_group_unprocessed_or_unverified_never_becomes_approvable(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, options: dict[str, Any]
) -> None:
    task, group_id, command = ready_group(harness, monkeypatch, **options)
    result = prepare_group_facts(harness.store, task, group_id, command, harness.principal)
    assert len(result["result"]["rows"]) == 1
    assert result["result"]["rows"][0]["candidate_id"] is None


def test_group_unknown_cannot_be_approved_as_known(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, group_id, command = ready_group(h, monkeypatch, status="UNKNOWN")
    prep = prepare_group_facts(h.store, task, group_id, command, h.principal)
    cmd = DecideGroupFact(
        expected_preparation_hash=prep["result_hash"],
        candidate_id=prep["result"]["rows"][0]["candidate_id"],
        decision="APPROVE",
        evidence_support="SUPPORTED",
        precedence_check="PASSED",
        reason="Synthetic",
    )
    with pytest.raises(InvestigationError, match="DECISION_OR_PROMOTION_INVALID"):
        act_on_group_facts(
            h.store, task, UUID(prep["preparation_id"]), cmd, h.principal, "cannot-approve"
        )


def decision_for(
    prep: dict[str, Any], decision: str = "APPROVE", index: int = 0
) -> DecideGroupFact:
    return DecideGroupFact.model_validate(
        {
            "expected_preparation_hash": prep["result_hash"],
            "candidate_id": prep["result"]["rows"][index]["candidate_id"],
            "decision": decision,
            "evidence_support": "SUPPORTED",
            "precedence_check": "PASSED",
            "reason": "Synthetic independent field review",
        }
    )


def promote_for(prep: dict[str, Any]) -> PromoteGroupFacts:
    return PromoteGroupFacts(
        expected_preparation_hash=prep["result_hash"], reason="Synthetic review"
    )


def test_group_unknown_promotes_only_as_unknown(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, group_id, command = ready_group(h, monkeypatch, status="UNKNOWN")
    prep = prepare_group_facts(h.store, task, group_id, command, h.principal)
    prep_id = UUID(prep["preparation_id"])
    act_on_group_facts(
        h.store, task, prep_id, decision_for(prep, "UNKNOWN"), h.principal, "unknown"
    )
    act_on_group_facts(h.store, task, prep_id, promote_for(prep), h.principal, "promote")
    with h.factory() as session:
        fact = session.scalar(select(VerifiedFact))
        assert fact is not None and fact.fact_state == "UNKNOWN" and fact.normalized_value is None


def test_all_candidates_need_final_decisions(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, group_id, command = ready_group(h, monkeypatch, two=True)
    prep = prepare_group_facts(h.store, task, group_id, command, h.principal)
    assert len(prep["result"]["rows"]) == 2
    prep_id = UUID(prep["preparation_id"])
    act_on_group_facts(h.store, task, prep_id, decision_for(prep), h.principal, "approve")
    with pytest.raises(InvestigationError, match="ALL_CANDIDATES_REQUIRE_DECISION"):
        act_on_group_facts(h.store, task, prep_id, promote_for(prep), h.principal, "incomplete")
    act_on_group_facts(
        h.store, task, prep_id, decision_for(prep, "NEEDS_ADJUDICATION", 1), h.principal, "pending"
    )
    with pytest.raises(InvestigationError, match="ALL_CANDIDATES_REQUIRE_DECISION"):
        act_on_group_facts(
            h.store, task, prep_id, promote_for(prep), h.principal, "pending-promote"
        )
    act_on_group_facts(
        h.store, task, prep_id, decision_for(prep, "REJECT", 1), h.principal, "reject"
    )
    result = act_on_group_facts(h.store, task, prep_id, promote_for(prep), h.principal, "complete")
    assert result["fact_set"] is not None
    assert len(result["decisions"]) == 2 and len(result["history"]) == 3
    with h.factory() as session:
        assert len(list(session.scalars(select(VerifiedFact)))) == 1


def test_empty_group_preserves_denominator_without_fact_set(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, group_id, command = ready_group(h, monkeypatch, empty=True)
    prep = prepare_group_facts(h.store, task, group_id, command, h.principal)
    assert prep["result"]["rows"] == [] and prep["result"]["extraction_run_id"] is None
    assert len(prep["result"]["excluded_rows"]) == prep["result"]["source_row_count"] == 1
    with pytest.raises(InvestigationError, match="ALL_CANDIDATES_REQUIRE_DECISION"):
        act_on_group_facts(
            h.store, task, UUID(prep["preparation_id"]), promote_for(prep), h.principal, "empty"
        )


def test_foreign_candidate_and_changed_idempotent_request_rejected(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, group_id, command = ready_group(h, monkeypatch)
    prep = prepare_group_facts(h.store, task, group_id, command, h.principal)
    prep_id = UUID(prep["preparation_id"])
    cmd = decision_for(prep)
    with pytest.raises(InvestigationError, match="CANDIDATE_INVALID"):
        act_on_group_facts(
            h.store,
            task,
            prep_id,
            cmd.model_copy(update={"candidate_id": uuid7()}),
            h.principal,
            "foreign",
        )
    act_on_group_facts(h.store, task, prep_id, cmd, h.principal, "decision")
    with pytest.raises(InvestigationError, match="IDEMPOTENCY_CONFLICT"):
        act_on_group_facts(
            h.store,
            task,
            prep_id,
            cmd.model_copy(update={"reason": "Changed reason"}),
            h.principal,
            "decision",
        )
    with pytest.raises(InvestigationError, match="ALREADY_DECIDED"):
        act_on_group_facts(h.store, task, prep_id, cmd, h.principal, "another-key")


@pytest.mark.parametrize("change", ["authority", "policy", "original", "clock"])
def test_cached_preparation_read_and_action_recheck_current_context(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    h = harness
    task, group_id, command = ready_group(h, monkeypatch)
    prep = prepare_group_facts(h.store, task, group_id, command, h.principal)
    prep_id = UUID(prep["preparation_id"])
    decision = decision_for(prep)
    act_on_group_facts(h.store, task, prep_id, decision, h.principal, "approve")
    if change == "original":
        with h.factory() as session:
            original = session.scalar(select(RawArtifact))
            assert original is not None
            key = original.object_key
        h.objects.delete_if_matches(key=key, sha256=h.objects.stat(key=key).sha256)
        code = "STORED_MATERIAL_INTEGRITY_FAILED"
    elif change == "clock":
        h.clock.value -= timedelta(seconds=1)
        code = "GROUP_FACT_PREPARATION_CONFLICT"
    else:
        with h.factory.begin() as session:
            if change == "authority":
                reviewer = session.get(ReviewerAccountModel, h.principal.reviewer_id)
                assert reviewer is not None
                reviewer.active = False
            else:
                endpoint = session.get(SourceEndpoint, h.command.endpoint_id)
                assert endpoint is not None
                endpoint.policy_version = "changed"
        code = (
            "HUMAN_VALIDATION_AUTHORITY_REQUIRED"
            if change == "authority"
            else "SOURCE_POLICY_CHANGED"
        )
    operations: tuple[Callable[[], dict[str, Any]], ...] = (
        lambda: prepare_group_facts(h.store, task, group_id, command, h.principal),
        lambda: load_group_facts(h.store, task, prep_id, h.principal),
        lambda: act_on_group_facts(h.store, task, prep_id, decision, h.principal, "approve"),
    )
    for operation in operations:
        with pytest.raises(InvestigationError, match=code):
            operation()


@pytest.mark.parametrize(
    "change", ["original", "drop_row", "excluded", "quote", "block_text", "locator", "candidate"]
)
def test_sql_rejects_rehashed_false_receipts(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    h = harness
    task, group_id, command = ready_group(h, monkeypatch)

    def corrupt(_mapper: Any, _connection: Any, prep: InvestigationGroupFactPreparation) -> None:
        row = prep.result["rows"][0]
        if change == "original":
            row["original"]["value"] = "博士"
        elif change == "drop_row":
            prep.result["rows"] = []
        elif change == "excluded":
            prep.result["excluded_rows"] = []
        elif change == "quote":
            row["evidence"][0]["reference"]["quote"] = "博士"
        elif change == "block_text":
            row["evidence"][0]["binding"]["block_text"] = "博士"
        elif change == "locator":
            row["evidence"][0]["binding"]["structural_locator"] = {}
        else:
            row["candidate_id"] = str(uuid7())
        prep.result_hash = digest(prep.result)

    event.listen(InvestigationGroupFactPreparation, "before_insert", corrupt)
    try:
        with pytest.raises(DBAPIError):
            prepare_group_facts(h.store, task, group_id, command, h.principal)
    finally:
        event.remove(InvestigationGroupFactPreparation, "before_insert", corrupt)
    with h.factory() as session:
        assert not list(session.scalars(select(InvestigationGroupFactPreparation)))
        assert not list(session.scalars(select(ExtractionCandidate)))


def test_sql_rejects_future_decision_and_rolls_back(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, group_id, command = ready_group(h, monkeypatch)
    prep = prepare_group_facts(h.store, task, group_id, command, h.principal)

    def future(_mapper: Any, _connection: Any, decision: FactVerificationDecisionModel) -> None:
        decision.decided_at += timedelta(days=1)

    event.listen(FactVerificationDecisionModel, "before_insert", future)
    try:
        with pytest.raises(DBAPIError, match="GROUP_FACT_DECISION_INVALID"):
            act_on_group_facts(
                h.store,
                task,
                UUID(prep["preparation_id"]),
                decision_for(prep),
                h.principal,
                "future",
            )
    finally:
        event.remove(FactVerificationDecisionModel, "before_insert", future)
    with h.factory() as session:
        assert not list(session.scalars(select(FactVerificationDecisionModel)))
        assert not list(session.scalars(select(InvestigationGroupFactAction)))


def test_concurrent_prepare_and_promotion_share_one_receipt(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, group_id, command = ready_group(h, monkeypatch)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: prepare_group_facts(h.store, task, group_id, command, h.principal),
                range(2),
            )
        )
    assert results[0] == results[1]
    prep = results[0]
    prep_id = UUID(prep["preparation_id"])
    act_on_group_facts(h.store, task, prep_id, decision_for(prep), h.principal, "approve")
    with ThreadPoolExecutor(max_workers=2) as executor:
        promoted = list(
            executor.map(
                lambda _: act_on_group_facts(
                    h.store, task, prep_id, promote_for(prep), h.principal, "promote"
                ),
                range(2),
            )
        )
    assert promoted[0] == promoted[1]
    with h.factory() as session:
        assert len(list(session.scalars(select(VerifiedFact)))) == 1
    with pytest.raises(DBAPIError, match="GROUP_FACT_IMMUTABLE"), h.factory.begin() as session:
        session.execute(text("DELETE FROM investigation_group_fact_actions"))


@pytest.mark.parametrize("change", ["value", "raw", "fingerprint", "fact_time", "set_time"])
def test_promotion_rejects_changed_materialized_facts(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    h = harness
    task, group_id, command = ready_group(h, monkeypatch)
    prep = prepare_group_facts(h.store, task, group_id, command, h.principal)
    prep_id = UUID(prep["preparation_id"])
    act_on_group_facts(h.store, task, prep_id, decision_for(prep), h.principal, "approve")

    def tamper(_mapper: Any, _connection: Any, target: Any) -> None:
        if change == "value":
            target.normalized_value = {"minimum_level": "BACHELOR"}
        elif change == "raw":
            target.raw_value = "博士"
        elif change == "fingerprint":
            target.dependency_fingerprint = "a" * 64
        else:
            target.created_at += timedelta(days=1)
            if change == "set_time":
                target.updated_at = target.created_at

    model = VersionedVerifiedFactSet if change == "set_time" else VerifiedFact
    event.listen(model, "before_insert", tamper)
    try:
        with pytest.raises(
            (DBAPIError, InvestigationError), match="GROUP_FACT_.*INVALID|GROUP_FACT_.*INTEGRITY"
        ):
            act_on_group_facts(h.store, task, prep_id, promote_for(prep), h.principal, "tampered")
    finally:
        event.remove(model, "before_insert", tamper)
    with h.factory() as session:
        assert not list(session.scalars(select(VersionedVerifiedFactSet)))


def test_future_candidate_cannot_enter_review(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, group_id, command = ready_group(h, monkeypatch)

    def future(_mapper: Any, _connection: Any, target: ExtractionCandidate) -> None:
        target.created_at += timedelta(days=1)

    event.listen(ExtractionCandidate, "before_insert", future)
    try:
        with pytest.raises(
            (DBAPIError, InvestigationError), match="GROUP_FACT_.*INVALID|GROUP_FACT_.*INTEGRITY"
        ):
            prepare_group_facts(h.store, task, group_id, command, h.principal)
    finally:
        event.remove(ExtractionCandidate, "before_insert", future)


def test_appended_candidate_evidence_invalidates_read_and_cached_decision(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, group_id, command = ready_group(h, monkeypatch, two_evidence=True)
    prep = prepare_group_facts(h.store, task, group_id, command, h.principal)
    first, second = [UUID(row["candidate_id"]) for row in prep["result"]["rows"]]
    prep_id = UUID(prep["preparation_id"])
    cmd = decision_for(prep)
    act_on_group_facts(h.store, task, prep_id, cmd, h.principal, "approve")
    with h.factory.begin() as session:
        source = session.scalar(
            select(ExtractionCandidateEvidence).where(
                ExtractionCandidateEvidence.candidate_id == second
            )
        )
        assert source is not None
        session.add(
            ExtractionCandidateEvidence(
                candidate_id=first,
                block_id=source.block_id,
                evidence_ref_id=source.evidence_ref_id,
                extraction_run_id=source.extraction_run_id,
                document_id=source.document_id,
            )
        )
    with pytest.raises(InvestigationError, match="MATERIALIZATION_INTEGRITY_FAILED"):
        load_group_facts(h.store, task, prep_id, h.principal)
    with pytest.raises(InvestigationError, match="MATERIALIZATION_INTEGRITY_FAILED"):
        act_on_group_facts(h.store, task, prep_id, cmd, h.principal, "approve")


def test_new_group_version_invalidates_preparation(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, group_id, command = ready_group(h, monkeypatch)
    prep = prepare_group_facts(h.store, task, group_id, command, h.principal)
    identity = prep["result"]["group_source"]["group_identity"]
    source = prep["result"]["group_source"]["source"]
    h.clock.value += timedelta(seconds=1)
    with h.factory.begin() as session:
        OpportunityUnitService(session).append_version_cas(
            opportunity_unit_id=UUID(identity["unit_id"]),
            expected_current_version_id=UUID(identity["unit_version_id"]),
            opportunity_version=source["opportunity_version"],
            source_bundle_revision_id=UUID(source["source_bundle_revision_id"]),
            effective_from=h.clock.value,
            canonical_label="Changed group",
            identity_fingerprint="d" * 64,
        )
    with pytest.raises(InvestigationError, match="GROUP_IDENTITY_INTEGRITY_FAILED"):
        load_group_facts(h.store, task, UUID(prep["preparation_id"]), h.principal)


def test_group_preparation_cannot_enter_old_position_fact_bridge(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, group_id, command = ready_group(h, monkeypatch)
    prep = prepare_group_facts(h.store, task, group_id, command, h.principal)
    source = prep["result"]["group_source"]["source"]
    request = PromoteInvestigationFacts.model_validate(
        {
            "delivery_hash": source["delivery_hash"],
            "binding_id": source["binding_id"],
            "check_id": str(command.check_id),
            "preparation_id": prep["preparation_id"],
            "reason": "Synthetic cross bridge attempt",
            "entity_id": "unit",
        }
    )
    with pytest.raises(InvestigationError, match="FACT_PREPARATION_CONFLICT"):
        act_on_facts(h.store, task, request, h.principal, "wrong-bridge")


def test_group_preparation_rejects_cross_task_and_source_hash(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, group_id, command = ready_group(h, monkeypatch)
    with pytest.raises(InvestigationError, match="GROUP_FACT_SOURCE_CHANGED"):
        prepare_group_facts(
            h.store,
            task,
            group_id,
            command.model_copy(update={"expected_source_hash": "a" * 64}),
            h.principal,
        )
    prep = prepare_group_facts(h.store, task, group_id, command, h.principal)
    other_task = h.store.create(h.command, h.principal, "another-task")
    with pytest.raises(InvestigationError, match="GROUP_FACT_SOURCE_NOT_FOUND"):
        load_group_facts(h.store, other_task, UUID(prep["preparation_id"]), h.principal)
