"""Trusted snapshot assembly from synthetic PG facts and separate human rule records."""

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid7

import pytest
from sqlalchemy import event, insert, select, text
from sqlalchemy.exc import DBAPIError

from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.models import InvestigationUnitPlan
from deepaha.investigations.rule_contracts import MaterializeInvestigationUnitPlan
from deepaha.investigations.rules import decide_rule, prepare_rules
from deepaha.investigations.unit_snapshots import load_unit_plan, materialize_unit_plan
from tests.integration.test_investigation_rules import _decision, _facts
from tests.integration.test_investigation_store import StoreHarness, harness

__all__ = ["harness"]
pytestmark = pytest.mark.integration


def ready(
    h: StoreHarness, *, unknown: bool = False
) -> tuple[UUID, MaterializeInvestigationUnitPlan, dict[str, Any]]:
    task, command = _facts(h, unknown=unknown)
    prep = prepare_rules(h.store, task, command, h.principal)
    return (
        task,
        MaterializeInvestigationUnitPlan.model_validate(
            command.model_dump() | {"rule_preparation_id": prep["rule_preparation_id"]}
        ),
        prep,
    )


def test_requires_final_rule_decisions_then_reuses_exact_current_snapshot(
    harness: StoreHarness,
) -> None:
    h = harness
    task, command, prep = ready(h)
    with pytest.raises(InvestigationError, match="ALL_RULES_REQUIRE_FINAL_DECISION"):
        materialize_unit_plan(h.store, task, command, h.principal)
    decide_rule(
        h.store,
        task,
        _decision(command, prep, decision="NEEDS_ADJUDICATION", evidence=[]),
        h.principal,
        "pending",
    )
    with pytest.raises(InvestigationError, match="ALL_RULES_REQUIRE_FINAL_DECISION"):
        materialize_unit_plan(h.store, task, command, h.principal)
    decide_rule(h.store, task, _decision(command, prep), h.principal, "final")
    first = materialize_unit_plan(h.store, task, command, h.principal)
    assert materialize_unit_plan(h.store, task, command, h.principal) == first
    assert load_unit_plan(h.store, task, UUID(first["plan_id"]), h.principal) == first
    assert (
        first["plan"]["target"]["unit_version_id"] == prep["target"]["opportunity_unit_version_id"]
    )
    assert first["context"]["source_row_count"] == len(prep["source_rows"])
    assert len(first["plan"]["rules"]) == len(first["plan"]["admissions"]) == 1
    with h.factory() as session:
        assert len(list(session.scalars(select(InvestigationUnitPlan)))) == 1


def test_unknown_fact_stays_in_manifest_without_invented_rule(harness: StoreHarness) -> None:
    h = harness
    task, command, _ = ready(h, unknown=True)
    result = materialize_unit_plan(h.store, task, command, h.principal)
    assert result["plan"]["rules"] == []
    assert result["plan"]["manifest"]["conditions"][0]["state"] == "UNKNOWN"


@pytest.mark.parametrize("operation", ["create", "read"])
def test_current_verifier_is_replayed_before_cache_or_read(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    h = harness
    task, command, prep = ready(h)
    decide_rule(h.store, task, _decision(command, prep), h.principal, "final")
    first = materialize_unit_plan(h.store, task, command, h.principal)
    monkeypatch.setattr("deepaha.investigations.evidence_checks.VERIFIER_VERSION", "synthetic-next")
    with pytest.raises(InvestigationError, match="EVIDENCE_CHECK_REFRESH_REQUIRED"):
        if operation == "create":
            materialize_unit_plan(h.store, task, command, h.principal)
        else:
            load_unit_plan(h.store, task, UUID(first["plan_id"]), h.principal)


def approved(h: StoreHarness) -> tuple[UUID, MaterializeInvestigationUnitPlan]:
    task, command, prep = ready(h)
    decide_rule(h.store, task, _decision(command, prep), h.principal, "final")
    return task, command


def test_rejection_is_an_unresolved_condition_not_nonqualification(harness: StoreHarness) -> None:
    h = harness
    task, command, prep = ready(h)
    decide_rule(
        h.store,
        task,
        _decision(command, prep, decision="REJECT", evidence=[]),
        h.principal,
        "reject",
    )
    result = materialize_unit_plan(h.store, task, command, h.principal)
    assert result["plan"]["rules"] == []
    assert result["plan"]["manifest"]["conditions"][0]["state"] == "REJECTED"
    assert result["plan"]["dispositions"][0]["kind"] == "UNRESOLVED"


def test_real_clock_distinguishes_approval_time_from_receipt_creation(
    harness: StoreHarness,
) -> None:
    from datetime import timedelta
    from itertools import count

    from deepaha.p9b.models import RuleApprovalDecisionModel

    h = harness
    ticks = count()
    h.store.clock = lambda: h.clock() + timedelta(microseconds=next(ticks))
    task, command = approved(h)
    result = materialize_unit_plan(h.store, task, command, h.principal)
    assert load_unit_plan(h.store, task, UUID(result["plan_id"]), h.principal) == result
    admission = result["plan"]["admissions"][0]
    with h.factory() as session:
        approval = session.get(RuleApprovalDecisionModel, UUID(admission["approval_decision_id"]))
        assert approval is not None
        from datetime import datetime

        assert datetime.fromisoformat(admission["reviewed_at"]) == approval.decided_at


def test_concurrent_materialization_returns_one_immutable_plan(harness: StoreHarness) -> None:
    from concurrent.futures import ThreadPoolExecutor

    h = harness
    task, command = approved(h)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: materialize_unit_plan(h.store, task, command, h.principal), range(2))
        )
    assert results[0] == results[1]
    with h.factory() as session:
        assert len(list(session.scalars(select(InvestigationUnitPlan)))) == 1


@pytest.mark.parametrize(
    "attack", ["plan_hash", "context_hash", "target", "manifest", "check", "contract"]
)
def test_database_rejects_invalid_snapshot_identity_and_hashes(
    harness: StoreHarness, attack: str
) -> None:
    h = harness
    task, command = approved(h)

    def corrupt(_mapper: Any, _connection: Any, record: InvestigationUnitPlan) -> None:
        plan: Any = record.plan
        if attack in {"plan_hash", "context_hash"}:
            setattr(record, attack, "0" * 64)
            return
        if attack == "target":
            plan["target"]["unit_version_id"] = str(uuid7())
        elif attack == "manifest":
            plan["manifest"]["preparation_id"] = str(uuid7())
        elif attack == "check":
            record.context["check_id"] = str(uuid7())
        else:
            plan["contract_version"] = "unit-qualification/1.0.0"
        record.plan_hash, record.context_hash = digest(record.plan), digest(record.context)

    event.listen(InvestigationUnitPlan, "before_insert", corrupt)
    try:
        with pytest.raises(DBAPIError, match="UNIT_PLAN_CONTEXT_MISMATCH"):
            materialize_unit_plan(h.store, task, command, h.principal)
    finally:
        event.remove(InvestigationUnitPlan, "before_insert", corrupt)


@pytest.mark.parametrize("attack", ["rule_value", "scope", "source_notes", "root", "decision"])
def test_rehashed_payload_cannot_pass_trusted_reconstruction(
    harness: StoreHarness, attack: str
) -> None:
    h = harness
    task, command = approved(h)

    def corrupt(_mapper: Any, _connection: Any, record: InvestigationUnitPlan) -> None:
        plan: Any = record.plan
        if attack == "rule_value":
            plan["rules"][0]["value"] = "BACHELOR"
        elif attack == "scope":
            plan["manifest"]["conditions"] = []
        elif attack == "source_notes":
            record.context["source_notes"] = [{"note": "forged"}]
        elif attack == "root":
            plan["root_rule_ids"] = []
        else:
            plan["admissions"][0]["approval_decision_id"] = str(uuid7())
        record.plan_hash, record.context_hash = digest(record.plan), digest(record.context)

    event.listen(InvestigationUnitPlan, "before_insert", corrupt)
    try:
        with pytest.raises(InvestigationError, match="UNIT_PLAN_INTEGRITY_FAILED"):
            materialize_unit_plan(h.store, task, command, h.principal)
    finally:
        event.remove(InvestigationUnitPlan, "before_insert", corrupt)
    with h.factory() as session:
        assert not list(session.scalars(select(InvestigationUnitPlan)))


@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_snapshot_history_is_immutable(harness: StoreHarness, operation: str) -> None:
    h = harness
    task, command = approved(h)
    materialize_unit_plan(h.store, task, command, h.principal)
    with pytest.raises(DBAPIError, match="UNIT_PLAN_IMMUTABLE"), h.factory.begin() as session:
        session.execute(
            text(
                "UPDATE investigation_unit_plans SET created_at = now()"
                if operation == "UPDATE"
                else "DELETE FROM investigation_unit_plans"
            )
        )


def test_snapshot_history_refuses_destructive_downgrade(harness: StoreHarness) -> None:
    from alembic import command as alembic_command
    from alembic.config import Config

    h = harness
    task, command = approved(h)
    result = materialize_unit_plan(h.store, task, command, h.principal)
    with pytest.raises(RuntimeError, match="UNIT_PLAN_HISTORY_DOWNGRADE_REFUSED"):
        alembic_command.downgrade(Config("alembic.ini"), "20260908_0041")
    assert load_unit_plan(h.store, task, UUID(result["plan_id"]), h.principal) == result


def test_untrusted_direct_insert_remains_unusable_even_with_valid_hashes(
    harness: StoreHarness,
) -> None:
    from copy import deepcopy

    from deepaha.investigations.unit_snapshots import ADAPTER_VERSION, _build
    from deepaha.unit_qualification.contracts import CONTRACT_VERSION

    h = harness
    task, command = approved(h)
    plan_id = uuid7()
    with h.factory.begin() as session:
        plan, context = _build(h.store, session, task, command, plan_id)
        malicious = deepcopy(plan.model_dump(mode="json"))
        malicious["rules"] = []
        malicious["admissions"] = []
        malicious["root_rule_ids"] = []
        malicious["dispositions"] = []
        session.execute(
            insert(InvestigationUnitPlan).values(
                plan_id=plan_id,
                rule_preparation_id=command.rule_preparation_id,
                unit_version_id=plan.target.unit_version_id,
                contract_version=CONTRACT_VERSION,
                adapter_version=ADAPTER_VERSION,
                plan=malicious,
                plan_hash=digest(malicious),
                context=context,
                context_hash=digest(context),
                reviewer_id=h.principal.reviewer_id,
                created_at=h.clock(),
            )
        )
    operations: tuple[Callable[[], dict[str, Any]], ...] = (
        lambda: load_unit_plan(h.store, task, plan_id, h.principal),
        lambda: materialize_unit_plan(h.store, task, command, h.principal),
    )
    for operation in operations:
        with pytest.raises(InvestigationError, match="UNIT_PLAN_INTEGRITY_FAILED"):
            operation()


def test_stale_fact_dependency_blocks_cached_and_loaded_snapshot(harness: StoreHarness) -> None:
    from deepaha.p9b.facts import FactLifecycleService
    from deepaha.p9b.models import VerifiedFactSetDependency

    h = harness
    task, command = approved(h)
    result = materialize_unit_plan(h.store, task, command, h.principal)
    with h.factory.begin() as session:
        dependency = session.scalar(
            select(VerifiedFactSetDependency).where(
                VerifiedFactSetDependency.verified_fact_set_id == command.fact_set_id
            )
        )
        assert dependency is not None
        FactLifecycleService(session).invalidate_dependency(
            verified_fact_set_id=command.fact_set_id,
            dependency_id=dependency.dependency_id,
            observed_dependency_fingerprint="f" * 64,
            reason_code="SYNTHETIC_CHANGED_INPUT",
            actor_identity=f"human:{h.principal.reviewer_id}",
            created_at=h.clock(),
        )
    with pytest.raises(InvestigationError, match="RULE_FACT_SET_CONFLICT"):
        materialize_unit_plan(h.store, task, command, h.principal)
    with pytest.raises(InvestigationError, match="RULE_FACT_SET_CONFLICT"):
        load_unit_plan(h.store, task, UUID(result["plan_id"]), h.principal)


def test_reviewer_revocation_is_checked_on_read_and_cache(harness: StoreHarness) -> None:
    from deepaha.review.models import ReviewerAccountModel

    h = harness
    task, command = approved(h)
    result = materialize_unit_plan(h.store, task, command, h.principal)
    with h.factory.begin() as session:
        account = session.get(ReviewerAccountModel, h.principal.reviewer_id)
        assert account is not None
        account.active = False
    with pytest.raises(InvestigationError):
        materialize_unit_plan(h.store, task, command, h.principal)
    with pytest.raises(InvestigationError):
        load_unit_plan(h.store, task, UUID(result["plan_id"]), h.principal)


def test_plan_cannot_be_read_through_another_task(harness: StoreHarness) -> None:
    h = harness
    task, command = approved(h)
    result = materialize_unit_plan(h.store, task, command, h.principal)
    with pytest.raises(InvestigationError, match="UNIT_PLAN_NOT_FOUND"):
        load_unit_plan(h.store, uuid7(), UUID(result["plan_id"]), h.principal)
