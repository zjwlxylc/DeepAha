"""Synthetic independent rule review; no real human approval or qualification claim."""

from typing import Any, cast
from uuid import UUID, uuid7

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError

from deepaha.contracts.phase9b import RuleApprovalDecisionSchemaV08
from deepaha.investigations.contracts import (
    DecideInvestigationFact,
    InvestigationError,
    PromoteInvestigationFacts,
    digest,
)
from deepaha.investigations.facts import act_on_facts, prepare_facts
from deepaha.investigations.models import InvestigationRuleDecision, InvestigationRulePreparation
from deepaha.investigations.rule_contracts import DecideInvestigationRule, PrepareInvestigationRules
from deepaha.investigations.rules import RULE_BRIDGE_VERSION, decide_rule, prepare_rules
from deepaha.p9b.models import RuleApprovalDecisionModel, RuleCandidateModel, UnitRuleSet
from deepaha.p9b.rules import RulePromotionService
from tests.integration.test_investigation_facts import _ready
from tests.integration.test_investigation_store import StoreHarness, harness

__all__ = ["harness"]
pytestmark = pytest.mark.integration


def _facts(h: StoreHarness, *, unknown: bool = False) -> tuple[UUID, PrepareInvestigationRules]:
    task, base = _ready(h, status="UNKNOWN" if unknown else "CONFIRMED")
    prep = prepare_facts(h.store, task, base, h.principal)["current"]
    common = base.model_dump() | {
        "preparation_id": prep["preparation_id"],
        "reason": "Synthetic independent review",
    }
    act_on_facts(
        h.store,
        task,
        DecideInvestigationFact.model_validate(
            common
            | {
                "candidate_id": prep["rows"][0]["candidate_id"],
                "decision": "UNKNOWN" if unknown else "APPROVE",
                "evidence_support": "SUPPORTED",
                "precedence_check": "PASSED",
            }
        ),
        h.principal,
        "fact",
    )
    final = act_on_facts(
        h.store,
        task,
        PromoteInvestigationFacts.model_validate(
            common
            | {
                "entity_id": "position",
            }
        ),
        h.principal,
        "promote",
    )
    return task, PrepareInvestigationRules.model_validate(
        base.model_dump()
        | {
            "fact_preparation_id": prep["preparation_id"],
            "entity_id": "position",
            "fact_set_id": final["current"]["promotions"]["position"]["fact_set_id"],
        }
    )


def _decision(
    command: PrepareInvestigationRules, prep: dict[str, Any], **changes: Any
) -> DecideInvestigationRule:
    row = next(row for row in prep["rows"] if row["rule_candidate_id"])
    return DecideInvestigationRule.model_validate(
        command.model_dump()
        | {
            "rule_preparation_id": prep["rule_preparation_id"],
            "rule_candidate_id": row["rule_candidate_id"],
            "decision": "APPROVE",
            "reason": "Synthetic independent rule review",
            "evidence": [
                {
                    "evidence_ref_id": ref,
                    "authority": "ORIGINAL_OFFICIAL_NOTICE",
                    "relation": "SUPPORTS",
                    "effective_at": "2026-01-01T00:00:00+08:00",
                    "applicability": "APPLIES_TO_EXACT_TARGET",
                    "reason": "Synthetic exact scope",
                }
                for ref in row["evidence_ref_ids"]
            ],
            **changes,
        }
    )


def test_candidate_requires_independent_evidence_decision_and_keeps_unit_identity(
    harness: StoreHarness,
) -> None:
    h = harness
    task, command = _facts(h)
    prep = prepare_rules(h.store, task, command, h.principal)
    assert prepare_rules(h.store, task, command, h.principal) == prep
    assert len(prep["source_rows"]) == len(prep["rows"]) == 1
    assert prep["check_id"] == str(command.check_id)
    assert prep["target"]["target_scope"] == "UNIT"
    with h.factory() as session:
        candidate = session.scalar(select(RuleCandidateModel))
        assert (
            candidate is not None
            and candidate.target_scope == "UNIT"
            and candidate.status == "PROPOSED"
        )
        assert not list(session.scalars(select(RuleApprovalDecisionModel)))
    decided = decide_rule(h.store, task, _decision(command, prep), h.principal, "rule")
    assert decide_rule(h.store, task, _decision(command, prep), h.principal, "rule") == decided
    with pytest.raises(InvestigationError, match="IDEMPOTENCY"):
        decide_rule(h.store, task, _decision(command, prep, reason="Changed"), h.principal, "rule")
    with h.factory() as session:
        assert not list(session.scalars(select(UnitRuleSet)))


@pytest.mark.parametrize("attack", ["missing", "foreign", "scope", "date"])
def test_approval_requires_every_real_reference_and_explicit_assessment(
    harness: StoreHarness, attack: str
) -> None:
    h = harness
    task, command = _facts(h)
    prep = prepare_rules(h.store, task, command, h.principal)
    body = _decision(command, prep).model_dump(mode="json")
    if attack == "missing":
        body["evidence"] = []
    elif attack == "foreign":
        body["evidence"][0]["evidence_ref_id"] = str(uuid7())
    elif attack == "scope":
        body["evidence"][0]["applicability"] = "UNRESOLVED"
    else:
        body["evidence"][0]["effective_at"] = None
    with pytest.raises(InvestigationError, match="RULE_EVIDENCE_REVIEW_INCOMPLETE"):
        decide_rule(
            h.store, task, DecideInvestigationRule.model_validate(body), h.principal, "invalid"
        )


def test_unknown_fact_is_visible_but_never_executable(harness: StoreHarness) -> None:
    h = harness
    task, command = _facts(h, unknown=True)
    row = prepare_rules(h.store, task, command, h.principal)["rows"][0]
    assert row["rule_candidate_id"] is None and row["reason_code"] == "FACT_UNKNOWN"
    with h.factory() as session:
        assert not list(session.scalars(select(RuleCandidateModel)))


@pytest.mark.parametrize("action", ["prepare", "decide"])
def test_fresh_mechanical_check_is_required_even_on_cached_rules(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    h = harness
    task, command = _facts(h)
    prep = prepare_rules(h.store, task, command, h.principal)
    monkeypatch.setattr("deepaha.investigations.evidence_checks.VERIFIER_VERSION", "synthetic-next")
    with pytest.raises(InvestigationError, match="EVIDENCE_CHECK_REFRESH_REQUIRED"):
        if action == "prepare":
            prepare_rules(h.store, task, command, h.principal)
        else:
            decide_rule(h.store, task, _decision(command, prep), h.principal, "stale")


def test_pending_rule_review_can_append_a_final_decision(harness: StoreHarness) -> None:
    h = harness
    task, command = _facts(h)
    prep = prepare_rules(h.store, task, command, h.principal)
    decide_rule(
        h.store,
        task,
        _decision(command, prep, decision="NEEDS_ADJUDICATION", evidence=[]),
        h.principal,
        "pending",
    )
    decided = decide_rule(h.store, task, _decision(command, prep), h.principal, "resolved")
    assert decided["decisions"][prep["rows"][0]["rule_candidate_id"]]["decision"] == "APPROVE"
    with pytest.raises(InvestigationError, match="ALREADY_DECIDED"):
        decide_rule(
            h.store,
            task,
            _decision(command, prep, decision="REJECT"),
            h.principal,
            "cannot-change-final",
        )
    with h.factory() as session:
        assert len(list(session.scalars(select(RuleApprovalDecisionModel)))) == 2


@pytest.mark.parametrize("decision", ["REJECT", "NEEDS_ADJUDICATION"])
@pytest.mark.parametrize("attack", ["foreign", "duplicate"])
def test_nonapproval_cannot_record_foreign_or_duplicate_assessments(
    harness: StoreHarness, decision: str, attack: str
) -> None:
    h = harness
    task, command = _facts(h)
    prep = prepare_rules(h.store, task, command, h.principal)
    body = _decision(command, prep, decision=decision).model_dump(mode="json")
    if attack == "foreign":
        body["evidence"][0]["evidence_ref_id"] = str(uuid7())
    else:
        body["evidence"].append(dict(body["evidence"][0]))
    with pytest.raises(InvestigationError, match="EVIDENCE_REVIEW_INCOMPLETE"):
        decide_rule(
            h.store, task, DecideInvestigationRule.model_validate(body), h.principal, "invalid"
        )
    with h.factory() as session:
        assert not list(session.scalars(select(RuleApprovalDecisionModel)))


@pytest.mark.parametrize("unknown", [True, False])
def test_database_checks_displayed_evidence_even_without_rule_candidate(
    harness: StoreHarness, unknown: bool
) -> None:
    h = harness
    task, command = _facts(h, unknown=unknown)

    def corrupt(_mapper: Any, _connection: Any, prep: InvestigationRulePreparation) -> None:
        rows = cast(list[dict[str, Any]], prep.result["rows"])
        rows[0]["evidence"][0]["text"] = "Invented evidence"
        prep.result_hash = digest(prep.result)

    event.listen(InvestigationRulePreparation, "before_insert", corrupt)
    try:
        with pytest.raises(DBAPIError, match="INVESTIGATION_RULE_EVIDENCE_MISMATCH"):
            prepare_rules(h.store, task, command, h.principal)
    finally:
        event.remove(InvestigationRulePreparation, "before_insert", corrupt)


def test_p9b_decision_without_investigation_assessment_cannot_commit(harness: StoreHarness) -> None:
    h = harness
    task, command = _facts(h)
    prep = prepare_rules(h.store, task, command, h.principal)
    with (
        pytest.raises(DBAPIError, match="INVESTIGATION_RULE_DECISION_RECEIPT_REQUIRED"),
        h.factory.begin() as session,
    ):
        RulePromotionService(session).decide(
            RuleApprovalDecisionSchemaV08.model_validate(
                {
                    "rule_approval_decision_id": uuid7(),
                    "rule_candidate_id": prep["rows"][0]["rule_candidate_id"],
                    "decision": "APPROVE",
                    "approval_method": "HUMAN",
                    "approver_identity": f"human:{h.principal.reviewer_id}",
                    "reason_code": "SYNTHETIC_BYPASS",
                    "decided_at": h.clock(),
                    "policy_version": RULE_BRIDGE_VERSION,
                }
            )
        )


def test_concurrent_final_rule_decisions_have_one_winner(harness: StoreHarness) -> None:
    from concurrent.futures import ThreadPoolExecutor

    h = harness
    task, command = _facts(h)
    prep = prepare_rules(h.store, task, command, h.principal)

    def attempt(key: str) -> str:
        try:
            decide_rule(h.store, task, _decision(command, prep), h.principal, key)
            return "APPROVED"
        except InvestigationError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, ["first", "second"]))
    assert sorted(outcomes) == ["APPROVED", "RULE_CANDIDATE_ALREADY_DECIDED"]
    with h.factory() as session:
        assert len(list(session.scalars(select(RuleApprovalDecisionModel)))) == 1


@pytest.mark.parametrize("attack", ["foreign", "duplicate"])
def test_database_rejects_invalid_nonapproval_assessments(
    harness: StoreHarness, attack: str
) -> None:
    h = harness
    task, command = _facts(h)
    prep = prepare_rules(h.store, task, command, h.principal)

    def corrupt(_mapper: Any, _connection: Any, record: InvestigationRuleDecision) -> None:
        evidence = cast(list[dict[str, Any]], record.request["evidence"])
        if attack == "foreign":
            evidence[0]["evidence_ref_id"] = str(uuid7())
        else:
            evidence.append(dict(evidence[0]))
        record.request_hash = digest(record.request)

    event.listen(InvestigationRuleDecision, "before_insert", corrupt)
    try:
        with pytest.raises(DBAPIError, match="INVESTIGATION_RULE_EVIDENCE_INCOMPLETE"):
            decide_rule(
                h.store,
                task,
                _decision(command, prep, decision="REJECT"),
                h.principal,
                "invalid-sql",
            )
    finally:
        event.remove(InvestigationRuleDecision, "before_insert", corrupt)
    with h.factory() as session:
        assert not list(session.scalars(select(RuleApprovalDecisionModel)))


@pytest.mark.parametrize(
    "table", ["investigation_rule_preparations", "investigation_rule_decisions"]
)
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_rule_review_history_is_immutable(
    harness: StoreHarness, table: str, operation: str
) -> None:
    h = harness
    task, command = _facts(h)
    prep = prepare_rules(h.store, task, command, h.principal)
    decide_rule(h.store, task, _decision(command, prep), h.principal, "final")
    with (
        pytest.raises(DBAPIError, match="INVESTIGATION_RULE_RECEIPT_IMMUTABLE"),
        h.factory.begin() as session,
    ):
        # Both identifiers are fixed test parameters, never external input.
        session.execute(
            text(
                f"UPDATE {table} SET created_at = now()"
                if operation == "UPDATE"
                else f"DELETE FROM {table}"
            )
        )


def test_rule_review_history_refuses_destructive_downgrade(harness: StoreHarness) -> None:
    from alembic import command as alembic_command
    from alembic.config import Config

    task, command = _facts(harness)
    prepare_rules(harness.store, task, command, harness.principal)
    with pytest.raises(RuntimeError, match="INVESTIGATION_RULE_HISTORY_DOWNGRADE_REFUSED"):
        alembic_command.downgrade(Config("alembic.ini"), "20260908_0040")
    assert harness.store.get(task)["rule_review"]["current"]
