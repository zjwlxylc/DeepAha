"""Synthetic human decisions, not qualification inheritance."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from threading import Barrier
from typing import Any
from uuid import UUID, uuid7

import pytest
from alembic import command as migration_command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import Engine, event, select, text
from sqlalchemy.exc import DBAPIError

from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.group_applicability import read_group_rule_applicability
from deepaha.investigations.group_applicability_decisions import (
    DecideGroupApplicability,
    load_group_applicability_decisions,
    save_group_applicability,
)
from deepaha.investigations.models import InvestigationGroupApplicability
from deepaha.investigations.unit_snapshots import load_unit_plan
from tests.integration.test_group_rule_applicability import position_plan, prepared
from tests.integration.test_investigation_store import StoreHarness, harness

__all__ = ["harness"]
pytestmark = pytest.mark.integration


def command(
    view: dict[str, Any], outcome: str = "APPLIES", previous: UUID | None = None
) -> DecideGroupApplicability:
    c, e = view["context"], view["evidence_options"][0]
    return DecideGroupApplicability.model_validate(
        {
            "target_plan_id": c["target_plan_id"],
            "source_rule_preparation_id": c["source_rule_preparation_id"],
            "source_rule_candidate_id": c["source_rule_candidate_id"],
            "context_hash": view["context_hash"],
            "previous_decision_id": previous,
            "outcome": outcome,
            "reason": "Synthetic scope review",
            "evidence": [
                {"member_id": e["member_id"], "block_id": e["block_id"], "quote": e["text"]}
            ],
        }
    )


def test_append_retry_and_history_do_not_change_plan(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, plan, source, candidate = prepared(h, monkeypatch)
    view = read_group_rule_applicability(h.store, task, plan, source, candidate, h.principal)
    before = load_unit_plan(h.store, task, plan, h.principal)
    request = command(view)
    first = save_group_applicability(h.store, task, request, h.principal, "first")
    assert save_group_applicability(h.store, task, request, h.principal, "first") == first
    next_request = command(view, "DOES_NOT_APPLY", UUID(first["decision_id"]))
    second = save_group_applicability(h.store, task, next_request, h.principal, "second")
    result = load_group_applicability_decisions(h.store, task, plan, source, candidate, h.principal)
    assert result["history"] == [first, second] and result["latest"] == second
    assert result["scope"] == "GROUP_APPLICABILITY_REVIEW_ONLY"
    assert second["sequence"] == 2
    assert load_unit_plan(h.store, task, plan, h.principal) == before


@pytest.mark.parametrize("case", ["context", "quote", "member", "predecessor", "idempotency"])
def test_failed_request_never_appends(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    h = harness
    args = prepared(h, monkeypatch)
    view = read_group_rule_applicability(h.store, *args, h.principal)
    request = command(view)
    first = save_group_applicability(h.store, args[0], request, h.principal, "first")
    changed = command(view, previous=UUID(first["decision_id"])).model_dump(mode="json")
    if case == "context":
        changed["context_hash"] = "f" * 64
    if case == "quote":
        changed["evidence"][0]["quote"] = "The agent paraphrased this sentence."
    if case == "member":
        changed["evidence"][0]["member_id"] = str(uuid7())
    if case == "predecessor":
        changed["previous_decision_id"] = None
    if case == "idempotency":
        changed["reason"] = "Different request with the same key"
    with pytest.raises(InvestigationError):
        save_group_applicability(
            h.store,
            args[0],
            DecideGroupApplicability.model_validate(changed),
            h.principal,
            "first" if case == "idempotency" else "next",
        )
    assert load_group_applicability_decisions(h.store, *args, h.principal)["history"] == [first]


def test_pending_may_have_no_quote_but_resolved_must_have_exact_evidence(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    args = prepared(h, monkeypatch)
    view = read_group_rule_applicability(h.store, *args, h.principal)
    payload = command(view, "NEEDS_ADJUDICATION").model_dump(mode="json") | {"evidence": []}
    result = save_group_applicability(
        h.store, args[0], DecideGroupApplicability.model_validate(payload), h.principal, "pending"
    )
    assert result["evidence_snapshot"] == []
    for outcome in ["APPLIES", "DOES_NOT_APPLY"]:
        with pytest.raises(ValidationError):
            DecideGroupApplicability.model_validate(payload | {"outcome": outcome})


@pytest.mark.parametrize(
    "case",
    [
        "member",
        "target",
        "quote",
        "material",
        "url",
        "locator",
        "duplicate",
        "extra",
        "reason",
        "approval_hash",
        "review_hash",
        "context_extra",
        "reason_number",
        "unicode_reason",
        "missing_previous",
    ],
)
def test_database_rejects_rehashed_forgery(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    h = harness
    args = prepared(h, monkeypatch)
    view = read_group_rule_applicability(h.store, *args, h.principal)
    first = save_group_applicability(h.store, args[0], command(view), h.principal, "first")
    with h.factory() as session:
        row = session.get(InvestigationGroupApplicability, UUID(first["decision_id"]))
        assert row is not None
        data = {c.name: deepcopy(getattr(row, c.name)) for c in row.__table__.columns}
    data.update(
        decision_id=uuid7(),
        previous_decision_id=UUID(first["decision_id"]),
        sequence=2,
        request_key_hash="f" * 64,
    )
    data["request"]["previous_decision_id"] = first["decision_id"]
    if case == "member":
        data["context"]["member"]["entity_id"] = "other-position"
    if case == "target":
        data["context"]["target"]["unit_version_id"] = str(uuid7())
    if case == "quote":
        data["request"]["evidence"][0]["quote"] = "Rewritten"
        data["evidence_snapshot"][0]["quote"] = "Rewritten"
    if case == "material":
        data["evidence_snapshot"][0]["material_id"] = "other-original"
    if case == "url":
        data["evidence_snapshot"][0]["source_url"] = "https://example.org/unrelated"
    if case == "locator":
        data["evidence_snapshot"][0]["locator"] = {"paragraph": 999}
    if case == "duplicate":
        data["request"]["evidence"] *= 2
        data["evidence_snapshot"] *= 2
    if case == "extra":
        data["request"]["automatic_eligibility"] = True
    if case == "reason":
        data["request"]["reason"] = "\t\n\u00a0"
    if case == "approval_hash":
        data["context"]["source_rule_approval_hash"] = "f" * 64
    if case == "review_hash":
        data["context"]["source_review_hash"] = "f" * 64
    if case == "context_extra":
        data["context"]["auto_approve"] = True
    if case == "reason_number":
        data["request"]["reason"] = 123
    if case == "unicode_reason":
        data["request"]["reason"] = "\u2003"
    if case == "missing_previous":
        data["request"].pop("previous_decision_id")
    data["context_hash"] = digest(data["context"])
    data["request"]["context_hash"] = data["context_hash"]
    data["request_hash"] = digest(data["request"])
    data["evidence_hash"] = digest(data["evidence_snapshot"])
    with pytest.raises(DBAPIError), h.factory.begin() as session:
        session.add(InvestigationGroupApplicability(**data))
        session.flush()
    with h.factory() as session:
        assert len(list(session.scalars(select(InvestigationGroupApplicability)))) == 1


@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_database_history_is_immutable(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    h = harness
    args = prepared(h, monkeypatch)
    view = read_group_rule_applicability(h.store, *args, h.principal)
    save_group_applicability(h.store, args[0], command(view), h.principal, "first")
    sql = (
        "UPDATE investigation_group_applicability SET sequence=sequence"
        if operation == "UPDATE"
        else "DELETE FROM investigation_group_applicability"
    )
    with (
        pytest.raises(DBAPIError, match="GROUP_APPLICABILITY_IMMUTABLE"),
        h.factory.begin() as session,
    ):
        session.execute(text(sql))


@pytest.mark.parametrize("same_key", [True, False])
def test_two_connections_serialize_retry_or_predecessor(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, same_key: bool
) -> None:
    h = harness
    args = prepared(h, monkeypatch)
    request = command(read_group_rule_applicability(h.store, *args, h.principal))
    barrier = Barrier(2)

    def save(index: int) -> dict[str, Any] | str:
        barrier.wait(timeout=10)
        try:
            return save_group_applicability(
                h.store, args[0], request, h.principal, "same" if same_key else str(index)
            )
        except InvestigationError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(save, [0, 1]))
    if same_key:
        assert outcomes[0] == outcomes[1] and isinstance(outcomes[0], dict)
    else:
        assert sum(isinstance(o, dict) for o in outcomes) == 1
        assert "GROUP_APPLICABILITY_PREDECESSOR_CHANGED" in outcomes
    assert len(load_group_applicability_decisions(h.store, *args, h.principal)["history"]) == 1


def test_migration_empty_roundtrip_and_models(migrated_engine: Engine) -> None:
    config = Config("alembic.ini")
    migration_command.downgrade(config, "20260910_0048")
    migration_command.upgrade(config, "head")
    migration_command.check(config)


def test_migration_refuses_existing_history(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    args = prepared(h, monkeypatch)
    view = read_group_rule_applicability(h.store, *args, h.principal)
    save_group_applicability(h.store, args[0], command(view), h.principal, "first")
    with pytest.raises(RuntimeError, match="GROUP_APPLICABILITY_HISTORY_DOWNGRADE_REFUSED"):
        migration_command.downgrade(Config("alembic.ini"), "20260910_0048")


def test_policy_change_during_quote_binding_rolls_back(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deepaha.investigations import group_applicability_decisions
    from deepaha.investigations.applicability import _bound_evidence
    from deepaha.sources.models import SourceEndpoint

    h = harness
    args = prepared(h, monkeypatch)
    request = command(read_group_rule_applicability(h.store, *args, h.principal))
    changed = False

    def interleave(*params: Any) -> list[dict[str, Any]]:
        nonlocal changed
        result = _bound_evidence(*params)
        if not changed:
            with h.factory.begin() as session:
                endpoint = session.scalar(select(SourceEndpoint))
                assert endpoint is not None
                endpoint.policy_version = "changed-during-write"
            changed = True
        return result

    monkeypatch.setattr(group_applicability_decisions, "_bound_evidence", interleave)
    with pytest.raises(InvestigationError):
        save_group_applicability(h.store, args[0], request, h.principal, "first")
    assert changed
    with h.factory() as session:
        assert not list(session.scalars(select(InvestigationGroupApplicability)))


def test_sibling_rule_approval_preserves_old_context_and_allows_new_decision(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deepaha.investigations.group_rule_review import (
        decide_group_rule,
        prepare_group_rule_review,
    )
    from deepaha.investigations.group_rule_review_contracts import PrepareGroupRules
    from deepaha.investigations.group_rules import preview_group_rules
    from tests.integration.test_group_rule_preview import prepared as prepare_group
    from tests.integration.test_group_rule_preview import promote
    from tests.integration.test_group_rule_review import command as approval_command

    h = harness
    task, facts = prepare_group(
        h,
        monkeypatch,
        two=True,
        other_field="户籍要求",
        other_status="CONFIRMED",
        other_value='{"allowed_regions":["浙江"]}',
    )
    promote(h, task, facts, "APPROVE", "APPROVE")
    fact_id = UUID(facts["preparation_id"])
    preview = preview_group_rules(h.store, task, fact_id, h.principal)
    review = prepare_group_rule_review(
        h.store,
        task,
        fact_id,
        PrepareGroupRules(expected_preview_hash=preview["result_hash"]),
        h.principal,
    )
    source = UUID(review["preparation_id"])
    a = approval_command(review)
    h.clock.value += timedelta(seconds=2)
    decide_group_rule(h.store, task, source, a, h.principal, "rule-a")
    plan = position_plan(h, task, review)
    args = (task, plan, source, a.rule_candidate_id)
    before = read_group_rule_applicability(h.store, *args, h.principal)
    first = save_group_applicability(h.store, task, command(before), h.principal, "first")
    b = next(
        UUID(r["rule_candidate_id"])
        for r in review["result"]["rows"]
        if r["rule_candidate_id"] != str(a.rule_candidate_id)
    )
    b_command = approval_command(
        review
        | {
            "result": review["result"]
            | {"rows": [r for r in review["result"]["rows"] if r["rule_candidate_id"] == str(b)]}
        }
    )
    from deepaha.investigations.models import InvestigationGroupRuleDecision
    from deepaha.p9b.models import RuleApprovalDecisionModel

    def backdate(_mapper: Any, _connection: Any, target: Any) -> None:
        timestamp = h.clock.value - timedelta(seconds=1)
        if isinstance(target, InvestigationGroupRuleDecision):
            target.created_at = timestamp
        else:
            target.decided_at = timestamp

    event.listen(InvestigationGroupRuleDecision, "before_insert", backdate)
    event.listen(RuleApprovalDecisionModel, "before_insert", backdate)
    try:
        with pytest.raises(DBAPIError, match="GROUP_APPLICABILITY_REVIEW_ORDER_INVALID"):
            decide_group_rule(h.store, task, source, b_command, h.principal, "rule-b-backdated")
    finally:
        event.remove(InvestigationGroupRuleDecision, "before_insert", backdate)
        event.remove(RuleApprovalDecisionModel, "before_insert", backdate)
    h.clock.value += timedelta(seconds=1)
    assert load_group_applicability_decisions(h.store, *args, h.principal)["history"] == [first]
    decide_group_rule(h.store, task, source, b_command, h.principal, "rule-b")
    after = read_group_rule_applicability(h.store, *args, h.principal)
    assert after["context_hash"] != before["context_hash"]
    assert load_group_applicability_decisions(h.store, *args, h.principal)["history"] == [first]
    second = save_group_applicability(
        h.store,
        task,
        command(after, "DOES_NOT_APPLY", UUID(first["decision_id"])),
        h.principal,
        "second",
    )
    assert second["context_hash"] == after["context_hash"]
    assert load_group_applicability_decisions(h.store, *args, h.principal)["history"] == [
        first,
        second,
    ]


@pytest.mark.parametrize("zone", ["UTC", "Asia/Shanghai"])
def test_database_timezone_preserves_review_hash_and_insert(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, zone: str
) -> None:
    h = harness
    args = prepared(h, monkeypatch)
    before = read_group_rule_applicability(h.store, *args, h.principal)
    first = save_group_applicability(h.store, args[0], command(before), h.principal, "first")
    with h.factory() as session:
        row = session.get(InvestigationGroupApplicability, UUID(first["decision_id"]))
        assert row is not None
        data = {c.name: deepcopy(getattr(row, c.name)) for c in row.__table__.columns}
    data.update(
        decision_id=uuid7(),
        previous_decision_id=UUID(first["decision_id"]),
        sequence=2,
        request_key_hash="f" * 64,
    )
    data["request"]["previous_decision_id"] = first["decision_id"]
    data["request_hash"] = digest(data["request"])

    def set_zone(_session: Any, _transaction: Any, connection: Any) -> None:
        connection.execute(text("SELECT set_config('TimeZone', :zone, true)"), {"zone": zone})

    event.listen(h.factory, "after_begin", set_zone)
    try:
        with h.factory() as session:
            assert (
                session.scalar(
                    text(
                        "SELECT group_applicability_iso('2026-09-10T01:02:03.123456Z'::timestamptz)"
                    )
                )
                == "2026-09-10T01:02:03.123456Z"
            )
            review = session.scalar(text("SELECT group_applicability_review(:id)"), {"id": args[2]})
            assert digest(review) == before["context"]["source_review_hash"]
        with h.factory.begin() as session:
            session.add(InvestigationGroupApplicability(**data))
            session.flush()
    finally:
        event.remove(h.factory, "after_begin", set_zone)
    history = load_group_applicability_decisions(h.store, *args, h.principal)["history"]
    assert history[0] == first and history[1]["decision_id"] == str(data["decision_id"])
