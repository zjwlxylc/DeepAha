"""Synthetic review mechanics, not actual human acceptance or inherited eligibility."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid7

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import DBAPIError

from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.group_rule_review import (
    decide_group_rule,
    load_group_rule_review,
    prepare_group_rule_review,
)
from deepaha.investigations.group_rule_review_contracts import DecideGroupRule, PrepareGroupRules
from deepaha.investigations.group_rules import preview_group_rules
from deepaha.investigations.models import (
    InvestigationGroupRuleDecision,
    InvestigationGroupRulePreparation,
)
from deepaha.p9b.identity import OpportunityUnitService
from deepaha.p9b.models import (
    RuleApprovalDecisionModel,
    RuleCandidateEvidence,
    RuleCandidateFact,
    RuleCandidateModel,
    UnitRuleSet,
    VerifiedFact,
    VerifiedFactEvidence,
)
from deepaha.review.models import ReviewerAccountModel
from tests.integration.test_group_rule_preview import prepared, promote
from tests.integration.test_investigation_store import StoreHarness, harness

pytestmark = pytest.mark.integration
__all__ = ["harness"]


def ready(
    h: StoreHarness, monkeypatch: pytest.MonkeyPatch, **options: Any
) -> tuple[UUID, UUID, PrepareGroupRules]:
    task, facts = prepared(h, monkeypatch, **options)
    promote(h, task, facts, "UNKNOWN" if options.get("status") else "APPROVE")
    fact_id = UUID(facts["preparation_id"])
    preview = preview_group_rules(h.store, task, fact_id, h.principal)
    return task, fact_id, PrepareGroupRules(expected_preview_hash=preview["result_hash"])


def command(record: dict[str, Any], decision: str = "APPROVE") -> DecideGroupRule:
    row = next(r for r in record["result"]["rows"] if r["rule_candidate_id"])
    return DecideGroupRule.model_validate(
        {
            "expected_preparation_hash": record["result_hash"],
            "rule_candidate_id": row["rule_candidate_id"],
            "decision": decision,
            "reason": "Synthetic independent rule review",
            "evidence": [
                {
                    "evidence_ref_id": ref,
                    "authority": "FORMAL_OFFICIAL_ATTACHMENT",
                    "relation": "SUPPORTS",
                    "effective_at": "2026-09-01T00:00:00Z",
                    "applicability": "APPLIES_TO_EXACT_TARGET",
                    "reason": "Synthetic original assessed",
                }
                for ref in row["evidence_ref_ids"]
            ],
        }
    )


def test_preparation_keeps_full_denominator_and_does_not_approve(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, fact_id, cmd = ready(h, monkeypatch, two=True, other_field="未支持组条件")
    record = prepare_group_rule_review(h.store, task, fact_id, cmd, h.principal)
    assert prepare_group_rule_review(h.store, task, fact_id, cmd, h.principal) == record
    assert (
        load_group_rule_review(h.store, task, UUID(record["preparation_id"]), h.principal) == record
    )
    assert len(record["result"]["rows"]) == 2
    assert record["result"]["rows"][1]["rule_candidate_id"] is None
    assert record["result"]["preview"]["result"]["fact_review"]["result"]["excluded_rows"]
    with h.factory() as session:
        candidate = session.scalar(select(RuleCandidateModel))
        assert candidate is not None and candidate.target_scope == "UNIT"
        assert (
            str(candidate.opportunity_unit_id)
            == record["result"]["preview"]["result"]["target"]["unit_id"]
        )
        assert not list(session.scalars(select(RuleApprovalDecisionModel)))
        assert not list(session.scalars(select(UnitRuleSet)))


@pytest.mark.parametrize("status", ["UNKNOWN", "CONFLICT"])
def test_unknown_does_not_create_rule_candidate(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    task, fact_id, cmd = ready(harness, monkeypatch, status=status)
    result = prepare_group_rule_review(harness.store, task, fact_id, cmd, harness.principal)
    assert result["result"]["rows"][0]["rule_candidate_id"] is None
    assert result["result"]["rows"][0]["proposed_rule_payload"] is None


def test_independent_approval_is_idempotent_but_not_inheritance(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, fact_id, cmd = ready(h, monkeypatch)
    record = prepare_group_rule_review(h.store, task, fact_id, cmd, h.principal)
    prep_id = UUID(record["preparation_id"])
    request = command(record)
    result = decide_group_rule(h.store, task, prep_id, request, h.principal, "approve")
    assert decide_group_rule(h.store, task, prep_id, request, h.principal, "approve") == result
    assert len(result["history"]) == 1
    assert result["decisions"][str(request.rule_candidate_id)]["decision"] == "APPROVE"
    with h.factory() as session:
        assert not list(session.scalars(select(UnitRuleSet)))
    with pytest.raises(InvestigationError, match="ALREADY_DECIDED"):
        decide_group_rule(h.store, task, prep_id, request, h.principal, "another")
    with pytest.raises(InvestigationError, match="IDEMPOTENCY_CONFLICT"):
        decide_group_rule(
            h.store,
            task,
            prep_id,
            request.model_copy(update={"reason": "Changed"}),
            h.principal,
            "approve",
        )


@pytest.mark.parametrize("change", ["no_evidence", "unresolved", "foreign", "future", "wrong_hash"])
def test_approval_rejects_missing_or_foreign_evidence(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    h = harness
    task, fact_id, cmd = ready(h, monkeypatch)
    record = prepare_group_rule_review(h.store, task, fact_id, cmd, h.principal)
    request = command(record).model_dump(mode="json")
    if change == "no_evidence":
        request["evidence"] = []
    elif change == "unresolved":
        request["evidence"][0]["applicability"] = "UNRESOLVED"
    elif change == "foreign":
        request["evidence"][0]["evidence_ref_id"] = str(uuid7())
    elif change == "future":
        request["evidence"][0]["effective_at"] = (h.clock.value + timedelta(days=1)).isoformat()
    else:
        request["expected_preparation_hash"] = "f" * 64
    with pytest.raises(InvestigationError):
        decide_group_rule(
            h.store,
            task,
            UUID(record["preparation_id"]),
            DecideGroupRule.model_validate(request),
            h.principal,
            "bad",
        )
    with h.factory() as session:
        assert not list(session.scalars(select(RuleApprovalDecisionModel)))


def test_concurrent_prepare_and_same_key_approval_are_single_receipts(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, fact, cmd = ready(h, monkeypatch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(
            pool.map(
                lambda _: prepare_group_rule_review(h.store, task, fact, cmd, h.principal), range(2)
            )
        )
    assert records[0] == records[1]
    prep_id = UUID(records[0]["preparation_id"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        decisions = list(
            pool.map(
                lambda _: decide_group_rule(
                    h.store, task, prep_id, command(records[0]), h.principal, "same-key"
                ),
                range(2),
            )
        )
    assert decisions[0] == decisions[1] and len(decisions[0]["history"]) == 1


def test_database_rejects_approval_without_paired_assessment(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, fact, cmd = ready(h, monkeypatch)
    record = prepare_group_rule_review(h.store, task, fact, cmd, h.principal)
    with (
        pytest.raises(DBAPIError, match="GROUP_RULE_DECISION_RECEIPT_REQUIRED"),
        h.factory.begin() as session,
    ):
        session.add(
            RuleApprovalDecisionModel(
                rule_approval_decision_id=uuid7(),
                rule_candidate_id=command(record).rule_candidate_id,
                decision="APPROVE",
                approver_identity=f"human:{h.principal.reviewer_id}",
                approval_method="HUMAN",
                reason_code="HUMAN_APPROVE",
                policy_version=record["result"]["contract_version"],
                decided_at=h.clock.value,
            )
        )


@pytest.mark.parametrize("child", ["fact", "evidence"])
def test_candidate_child_append_cannot_change_frozen_materialization(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, child: str
) -> None:
    h = harness
    task, facts = prepared(h, monkeypatch, two_evidence=True, other_field="户籍要求")
    promote(h, task, facts, "APPROVE", "UNKNOWN")
    fact_id = UUID(facts["preparation_id"])
    preview = preview_group_rules(h.store, task, fact_id, h.principal)
    record = prepare_group_rule_review(
        h.store,
        task,
        fact_id,
        PrepareGroupRules(expected_preview_hash=preview["result_hash"]),
        h.principal,
    )
    with (
        pytest.raises(DBAPIError, match="GROUP_RULE_RECEIPT_REQUIRED"),
        h.factory.begin() as session,
    ):
        other = session.scalar(
            select(VerifiedFact).where(
                VerifiedFact.field_name == "household_registration_requirements"
            )
        )
        assert other is not None
        candidate_id = command(record).rule_candidate_id
        if child == "fact":
            session.add(
                RuleCandidateFact(
                    rule_candidate_id=candidate_id,
                    verified_fact_id=other.verified_fact_id,
                    verified_fact_set_id=other.verified_fact_set_id,
                )
            )
        else:
            ref = session.scalar(
                select(VerifiedFactEvidence).where(
                    VerifiedFactEvidence.verified_fact_id == other.verified_fact_id
                )
            )
            assert ref is not None
            session.add(
                RuleCandidateEvidence(
                    rule_candidate_id=candidate_id,
                    evidence_ref_id=ref.evidence_ref_id,
                )
            )

    assert (
        load_group_rule_review(h.store, task, UUID(record["preparation_id"]), h.principal) == record
    )


def test_adjudication_can_be_followed_by_rejection(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, fact_id, cmd = ready(h, monkeypatch)
    record = prepare_group_rule_review(h.store, task, fact_id, cmd, h.principal)
    prep_id = UUID(record["preparation_id"])
    decide_group_rule(
        h.store, task, prep_id, command(record, "NEEDS_ADJUDICATION"), h.principal, "pending"
    )
    result = decide_group_rule(
        h.store, task, prep_id, command(record, "REJECT"), h.principal, "reject"
    )
    assert [r["decision"] for r in result["history"]] == ["NEEDS_ADJUDICATION", "REJECT"]


def test_revoked_authority_rejects_cached_read_and_write(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, fact_id, cmd = ready(h, monkeypatch)
    record = prepare_group_rule_review(h.store, task, fact_id, cmd, h.principal)
    with h.factory.begin() as session:
        account = session.get(ReviewerAccountModel, h.principal.reviewer_id)
        assert account is not None
        account.active = False
    with pytest.raises(InvestigationError):
        load_group_rule_review(h.store, task, UUID(record["preparation_id"]), h.principal)
    with pytest.raises(InvestigationError):
        prepare_group_rule_review(h.store, task, fact_id, cmd, h.principal)


@pytest.mark.parametrize("change", ["task", "clock", "group_version"])
def test_saved_review_rechecks_current_context_before_read_or_retry(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    h = harness
    task, fact_id, cmd = ready(h, monkeypatch)
    record = prepare_group_rule_review(h.store, task, fact_id, cmd, h.principal)
    prep_id = UUID(record["preparation_id"])
    request = command(record)
    decide_group_rule(h.store, task, prep_id, request, h.principal, "approved")
    if change == "task":
        task = uuid7()
    elif change == "clock":
        h.clock.value -= timedelta(seconds=1)
    else:
        source = record["result"]["preview"]["result"]["fact_review"]["result"]["group_source"]
        identity, original = source["group_identity"], source["source"]
        h.clock.value += timedelta(seconds=1)
        with h.factory.begin() as session:
            OpportunityUnitService(session).append_version_cas(
                opportunity_unit_id=UUID(identity["unit_id"]),
                expected_current_version_id=UUID(identity["unit_version_id"]),
                opportunity_version=original["opportunity_version"],
                source_bundle_revision_id=UUID(original["source_bundle_revision_id"]),
                effective_from=h.clock.value,
                canonical_label="Changed group",
                identity_fingerprint="d" * 64,
            )
    with pytest.raises(InvestigationError):
        load_group_rule_review(h.store, task, prep_id, h.principal)
    with pytest.raises(InvestigationError):
        prepare_group_rule_review(h.store, task, fact_id, cmd, h.principal)
    with pytest.raises(InvestigationError):
        decide_group_rule(h.store, task, prep_id, request, h.principal, "approved")


@pytest.mark.parametrize("change", ["payload", "row", "candidate", "evidence", "target"])
def test_sql_rejects_rehashed_forged_preparation(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    h = harness
    task, fact_id, cmd = ready(h, monkeypatch)

    def tamper(_mapper: Any, _connection: Any, row: InvestigationGroupRulePreparation) -> None:
        result = deepcopy(row.result)
        if change == "payload":
            result["rows"][0]["proposed_rule_payload"]["value"] = "DOCTORATE"
        elif change == "row":
            result["rows"] = []
        elif change == "candidate":
            result["rows"][0]["rule_candidate_id"] = str(uuid7())
        elif change == "evidence":
            result["rows"][0]["evidence_ref_ids"] = []
        else:
            result["preview"]["result"]["target"]["unit_id"] = str(uuid7())
        row.result, row.result_hash = result, digest(result)

    event.listen(InvestigationGroupRulePreparation, "before_insert", tamper)
    try:
        with pytest.raises(DBAPIError):
            prepare_group_rule_review(h.store, task, fact_id, cmd, h.principal)
    finally:
        event.remove(InvestigationGroupRulePreparation, "before_insert", tamper)
    with h.factory() as session:
        assert not list(session.scalars(select(RuleCandidateModel)))


@pytest.mark.parametrize("change", ["missing", "infinity", "naive"])
def test_sql_rejects_unreviewed_approval_receipt(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    h = harness
    task, fact_id, cmd = ready(h, monkeypatch)
    record = prepare_group_rule_review(h.store, task, fact_id, cmd, h.principal)

    def tamper(_mapper: Any, _connection: Any, row: InvestigationGroupRuleDecision) -> None:
        row.request = deepcopy(row.request)
        if change == "missing":
            row.request["evidence"] = []
        else:
            row.request["evidence"][0]["effective_at"] = (
                "-infinity" if change == "infinity" else "2026-09-01"
            )
        row.request_hash = digest(row.request)

    event.listen(InvestigationGroupRuleDecision, "before_insert", tamper)
    try:
        with pytest.raises(DBAPIError):
            decide_group_rule(
                h.store, task, UUID(record["preparation_id"]), command(record), h.principal, "bad"
            )
    finally:
        event.remove(InvestigationGroupRuleDecision, "before_insert", tamper)
    with h.factory() as session:
        assert not list(session.scalars(select(RuleApprovalDecisionModel)))
