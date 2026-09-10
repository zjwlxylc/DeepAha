"""Synthetic scope projections never grant inherited eligibility."""

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid7

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError

from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.group_applicability import read_group_rule_applicability
from deepaha.investigations.group_applicability_decisions import save_group_applicability
from deepaha.investigations.group_bindings import load_group_source, preview_group_source
from deepaha.investigations.group_facts import act_on_group_facts, prepare_group_facts
from deepaha.investigations.group_inheritance import preview_group_inheritance
from deepaha.investigations.unit_snapshots import load_unit_plan
from deepaha.p9b.identity import OpportunityUnitService
from deepaha.review.models import ReviewerAccountModel
from deepaha.sources.models import SourceEndpoint
from tests.integration.test_group_applicability_decisions import command
from tests.integration.test_group_facts import decision_for, ready_group
from tests.integration.test_group_rule_applicability import position_plan, prepared
from tests.integration.test_group_rule_preview import promote
from tests.integration.test_investigation_store import StoreHarness, harness

__all__ = ["harness"]
pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "outcome,expected",
    [
        ("APPLIES", "INHERIT"),
        ("DOES_NOT_APPLY", "EXCLUDE"),
        ("NEEDS_ADJUDICATION", "UNRESOLVED"),
    ],
)
def test_current_decisions_preserve_denominator_and_base(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, outcome: str, expected: str
) -> None:
    h = harness
    args = prepared(h, monkeypatch)
    before = preview_group_inheritance(h.store, args[0], args[1], h.principal)
    base = load_unit_plan(h.store, args[0], args[1], h.principal)
    assert before["snapshot"]["base_v2"] == base
    assert [r["disposition"] for r in before["snapshot"]["group_conditions"]] == [
        "UNRESOLVED",
        "UNRESOLVED",
    ]
    view = read_group_rule_applicability(h.store, *args, h.principal)
    receipt = save_group_applicability(h.store, args[0], command(view, outcome), h.principal, "one")
    after = preview_group_inheritance(h.store, args[0], args[1], h.principal)
    rows = after["snapshot"]["group_conditions"]
    assert len(rows) == 2 and rows[0]["disposition"] == expected
    assert rows[0]["applicability"]["decision_id"] == receipt["decision_id"]
    assert rows[1]["disposition"] == "UNRESOLVED"
    assert rows[1]["reason"] == "GROUP_FIELD_UNPROCESSED"
    assert after["snapshot"]["overall_qualification"] == "UNCERTAIN"
    assert after["snapshot"]["base_v2"] == base
    assert after["dependencies_hash"] != before["dependencies_hash"]
    assert after["dependencies_hash"] == digest(after["dependencies"])
    assert preview_group_inheritance(h.store, args[0], args[1], h.principal) == after
    correction = command(view, "NEEDS_ADJUDICATION", UUID(receipt["decision_id"]))
    save_group_applicability(h.store, args[0], correction, h.principal, "two")
    revised = preview_group_inheritance(h.store, args[0], args[1], h.principal)
    assert revised["dependencies_hash"] != after["dependencies_hash"]
    assert revised["snapshot"]["group_conditions"][0]["disposition"] == "UNRESOLVED"


@pytest.mark.parametrize("decision", ["REJECT", "NEEDS_ADJUDICATION"])
def test_unapproved_group_rule_is_not_an_exclusion(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, decision: str
) -> None:
    h = harness
    task, plan, _, _ = prepared(h, monkeypatch, decision=decision)
    preview = preview_group_inheritance(h.store, task, plan, h.principal)
    row = preview["snapshot"]["group_conditions"][0]
    assert row["disposition"] == "UNRESOLVED"
    assert row["reason"] == f"GROUP_RULE_{decision}"


def test_projection_does_not_write(harness: StoreHarness, monkeypatch: pytest.MonkeyPatch) -> None:
    h = harness
    task, plan, _, _ = prepared(h, monkeypatch)
    statements: list[str] = []

    def capture(_conn: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        statements.append(statement.lstrip().split()[0].upper())

    with h.factory() as session:
        engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", capture)
    try:
        preview_group_inheritance(h.store, task, plan, h.principal)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert not set(statements).intersection(
        {"INSERT", "UPDATE", "DELETE", "ALTER", "CREATE", "DROP", "TRUNCATE"}
    )


@pytest.mark.parametrize(
    "stage,expected",
    [
        ("registered", "GROUP_FACTS_NOT_PREPARED"),
        ("prepared", "FACT_SET_NOT_SAVED"),
        ("APPROVE", "GROUP_RULE_REVIEW_NOT_PREPARED"),
        ("UNKNOWN", "FACT_UNKNOWN"),
        ("REJECT", "FACT_REJECTED"),
    ],
)
def test_incomplete_group_pipeline_preserves_every_condition(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, stage: str, expected: str
) -> None:
    h = harness
    task, group, cmd = ready_group(
        h,
        monkeypatch,
        two=True,
        other_field="尚未处理条件",
        status="UNKNOWN" if stage == "UNKNOWN" else "CONFIRMED",
    )
    source = load_group_source(h.store, task, group, h.principal)
    facts: dict[str, Any] = {"result": {"group_source": source, "check_id": str(cmd.check_id)}}
    if stage != "registered":
        facts = prepare_group_facts(h.store, task, group, cmd, h.principal)
        if stage == "REJECT":
            act_on_group_facts(
                h.store,
                task,
                UUID(facts["preparation_id"]),
                decision_for(facts, "REJECT"),
                h.principal,
                "rejected-fact",
            )
        elif stage != "prepared":
            promote(h, task, facts, stage)
    # position_plan consumes only the frozen source/check; the position's actual
    # fact, rule and snapshot pipeline is independent of GROUP preparation.
    plan = position_plan(h, task, {"result": {"preview": {"result": {"fact_review": facts}}}})
    view = preview_group_inheritance(h.store, task, plan, h.principal)
    rows = view["snapshot"]["group_conditions"]
    assert len(rows) == 2
    assert rows[0]["reason"] == expected
    assert rows[1]["reason"] == (
        "GROUP_FACTS_NOT_PREPARED" if stage == "registered" else "GROUP_FIELD_UNPROCESSED"
    )
    assert all(row["disposition"] == "UNRESOLVED" for row in rows)
    assert view["snapshot"]["base_v2"] == load_unit_plan(h.store, task, plan, h.principal)


@pytest.mark.parametrize("change", ["policy", "authority"])
def test_changes_during_read_are_rejected_or_serialized(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    from deepaha.investigations import group_inheritance

    h = harness
    task, plan, _, _ = prepared(h, monkeypatch)
    original = group_inheritance._source
    changed = False

    def interleave(*params: Any) -> dict[str, Any]:
        nonlocal changed
        result = original(*params)
        if not changed:
            changed = True
            if change == "policy":
                with h.factory.begin() as session:
                    endpoint = session.scalar(select(SourceEndpoint))
                    assert endpoint is not None
                    endpoint.policy_version = "changed-during-projection"
            else:
                # Authorization holds the account row lock until the preview
                # transaction ends. A bounded concurrent update must wait.
                with pytest.raises(DBAPIError) as error, h.factory.begin() as session:
                    session.execute(text("SET LOCAL lock_timeout = '100ms'"))
                    account = session.get(ReviewerAccountModel, h.principal.reviewer_id)
                    assert account is not None
                    account.active = False
                    session.flush()
                assert getattr(error.value.orig, "sqlstate", None) == "55P03"
        return result

    monkeypatch.setattr(group_inheritance, "_source", interleave)
    if change == "policy":
        with pytest.raises(InvestigationError, match="SOURCE_POLICY_CHANGED"):
            preview_group_inheritance(h.store, task, plan, h.principal)
    else:
        preview_group_inheritance(h.store, task, plan, h.principal)
        with h.factory.begin() as session:
            account = session.get(ReviewerAccountModel, h.principal.reviewer_id)
            assert account is not None
            account.active = False
        with pytest.raises(InvestigationError, match="HUMAN_VALIDATION_AUTHORITY_REQUIRED"):
            preview_group_inheritance(h.store, task, plan, h.principal)
    assert changed


@pytest.mark.parametrize("empty", [False, True])
def test_unregistered_group_preserves_the_frozen_scope(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, empty: bool
) -> None:
    h = harness
    # Leave registration undone while reusing the fixture's frozen GROUP facts.
    monkeypatch.setattr(
        "tests.integration.test_group_facts.register_group_source",
        lambda *args: {"group_binding_id": str(uuid7())},
    )
    task, _, cmd = ready_group(h, monkeypatch, empty=empty)
    source = preview_group_source(h.store, task, "unit", h.principal)
    facts = {"result": {"group_source": source, "check_id": str(cmd.check_id)}}
    plan = position_plan(h, task, {"result": {"preview": {"result": {"fact_review": facts}}}})
    view = preview_group_inheritance(h.store, task, plan, h.principal)
    assert view["dependencies"]["group_source"]["registration"] is None
    rows = view["snapshot"]["group_conditions"]
    assert len(rows) == (0 if empty else 1)
    assert all(row["reason"] == "GROUP_SOURCE_NOT_REGISTERED" for row in rows)
    assert all(row["disposition"] == "UNRESOLVED" for row in rows)
    assert view["snapshot"]["overall_qualification"] == "UNCERTAIN"


def test_changed_group_version_rejects_previous_approval_and_applicability(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    args = prepared(h, monkeypatch)
    view = read_group_rule_applicability(h.store, *args, h.principal)
    save_group_applicability(h.store, args[0], command(view), h.principal, "old-version")
    before = preview_group_inheritance(h.store, args[0], args[1], h.principal)
    group = before["dependencies"]["group_source"]["registration"]
    identity, source = group["group_identity"], group["source"]
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
        preview_group_inheritance(h.store, args[0], args[1], h.principal)
