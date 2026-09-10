"""Synthetic exact GROUP-to-POSITION context, not inherited eligibility."""

from copy import deepcopy
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid7

import pytest
from sqlalchemy import event, select

from deepaha.investigations.contracts import (
    DecideInvestigationFact,
    InvestigationError,
    PrepareInvestigationFacts,
    PromoteInvestigationFacts,
    digest,
)
from deepaha.investigations.facts import act_on_facts, prepare_facts
from deepaha.investigations.group_applicability import read_group_rule_applicability
from deepaha.investigations.group_rule_review import decide_group_rule, prepare_group_rule_review
from deepaha.investigations.models import InvestigationRuleApplicability
from deepaha.investigations.rule_contracts import MaterializeInvestigationUnitPlan
from deepaha.investigations.rules import decide_rule, prepare_rules
from deepaha.investigations.unit_snapshots import load_unit_plan, materialize_unit_plan
from deepaha.p9b.identity import OpportunityUnitService
from tests.integration.test_group_rule_review import command as group_decision
from tests.integration.test_group_rule_review import ready
from tests.integration.test_investigation_rules import _decision
from tests.integration.test_investigation_store import StoreHarness, harness

pytestmark = pytest.mark.integration
__all__ = ["harness"]


def prepared(
    h: StoreHarness, monkeypatch: pytest.MonkeyPatch, *, decision: str = "APPROVE"
) -> tuple[UUID, UUID, UUID, UUID]:
    task, fact_id, cmd = ready(h, monkeypatch, two=True, other_field="尚未处理条件")
    group = prepare_group_rule_review(h.store, task, fact_id, cmd, h.principal)
    source_id = UUID(group["preparation_id"])
    source_cmd = group_decision(group, decision)
    decide_group_rule(h.store, task, source_id, source_cmd, h.principal, "group-rule")
    review = group["result"]["preview"]["result"]["fact_review"]
    source = review["result"]["group_source"]["source"]
    base = PrepareInvestigationFacts(
        delivery_hash=source["delivery_hash"],
        binding_id=source["binding_id"],
        check_id=review["result"]["check_id"],
    )
    facts = prepare_facts(h.store, task, base, h.principal)["current"]
    row = next(r for r in facts["rows"] if r["entity_id"] == "position")
    common = base.model_dump() | {"preparation_id": facts["preparation_id"], "reason": "Synthetic"}
    act_on_facts(
        h.store,
        task,
        DecideInvestigationFact.model_validate(
            common
            | {
                "candidate_id": row["candidate_id"],
                "decision": "APPROVE",
                "evidence_support": "SUPPORTED",
                "precedence_check": "PASSED",
            }
        ),
        h.principal,
        "position-fact",
    )
    promoted = act_on_facts(
        h.store,
        task,
        PromoteInvestigationFacts.model_validate(common | {"entity_id": "position"}),
        h.principal,
        "position-promote",
    )
    rules_cmd = MaterializeInvestigationUnitPlan.model_validate(
        base.model_dump()
        | {
            "fact_preparation_id": facts["preparation_id"],
            "entity_id": "position",
            "fact_set_id": promoted["current"]["promotions"]["position"]["fact_set_id"],
            "rule_preparation_id": uuid7(),
        }
    )
    rules = prepare_rules(h.store, task, rules_cmd, h.principal)
    rules_cmd = rules_cmd.model_copy(
        update={"rule_preparation_id": UUID(rules["rule_preparation_id"])}
    )
    decide_rule(h.store, task, _decision(rules_cmd, rules), h.principal, "position-rule")
    plan = materialize_unit_plan(h.store, task, rules_cmd, h.principal)
    return task, UUID(plan["plan_id"]), source_id, source_cmd.rule_candidate_id


def test_exact_group_member_context_is_stable_read_only_and_preserves_denominator(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, plan, source, candidate = prepared(h, monkeypatch)
    before = load_unit_plan(h.store, task, plan, h.principal)
    statements: list[str] = []

    def capture(
        _conn: Any, _cursor: Any, statement: str, _params: Any, _context: Any, _many: bool
    ) -> None:
        statements.append(statement.lstrip().split()[0].upper())

    with h.factory() as session:
        engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", capture)
    try:
        result = read_group_rule_applicability(h.store, task, plan, source, candidate, h.principal)
        assert (
            read_group_rule_applicability(h.store, task, plan, source, candidate, h.principal)
            == result
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert not set(statements) & {"INSERT", "UPDATE", "DELETE", "CREATE", "ALTER"}
    assert result["context_hash"] == digest(result["context"])
    assert result["context"]["target_entity_id"] == "position"
    assert result["context"]["member"]["entity_id"] == "position"
    assert result["context"]["source_group"]["unit_id"] != result["context"]["target"]["unit_id"]
    assert len(result["source_review"]["result"]["rows"]) == 2
    assert result["source_review"]["result"]["rows"][1]["rule_candidate_id"] is None
    assert result["evidence_options"] and result["outcome"] == "UNDECIDED"
    assert load_unit_plan(h.store, task, plan, h.principal) == before
    with h.factory() as session:
        assert not list(session.scalars(select(InvestigationRuleApplicability)))


@pytest.mark.parametrize("decision", ["REJECT", "NEEDS_ADJUDICATION"])
def test_source_requires_actual_group_rule_approval(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, decision: str
) -> None:
    h = harness
    args = prepared(h, monkeypatch, decision=decision)
    with pytest.raises(InvestigationError, match="GROUP_APPLICABILITY_SOURCE_NOT_APPROVED"):
        read_group_rule_applicability(h.store, *args, h.principal)


@pytest.mark.parametrize("index", [0, 1, 2, 3])
def test_wrong_task_plan_preparation_or_candidate_is_rejected(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, index: int
) -> None:
    h = harness
    args = list(prepared(h, monkeypatch))
    args[index] = uuid7()
    with pytest.raises(InvestigationError):
        read_group_rule_applicability(h.store, args[0], args[1], args[2], args[3], h.principal)


@pytest.mark.parametrize("target", ["source_group", "target"])
def test_new_group_or_position_version_invalidates_context(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    h = harness
    args = prepared(h, monkeypatch)
    context = read_group_rule_applicability(h.store, *args, h.principal)["context"]
    identity = context[target]
    h.clock.value += timedelta(seconds=1)
    with h.factory.begin() as session:
        OpportunityUnitService(session).append_version_cas(
            opportunity_unit_id=UUID(identity["unit_id"]),
            expected_current_version_id=UUID(identity["unit_version_id"]),
            opportunity_version=context["target"]["opportunity_version"],
            source_bundle_revision_id=UUID(context["source_bundle_revision_id"]),
            effective_from=h.clock.value,
            canonical_label="Changed synthetic identity",
            identity_fingerprint="d" * 64,
        )
    with pytest.raises(InvestigationError):
        read_group_rule_applicability(h.store, *args, h.principal)


def test_cursor_is_strict_and_page_does_not_change_context(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    args = prepared(h, monkeypatch)
    first = read_group_rule_applicability(h.store, *args, h.principal)
    last = first["evidence_options"][-1]
    following = read_group_rule_applicability(
        h.store, *args, h.principal, after=f"{last['block_id']}:{last['member_id']}"
    )
    assert following["context_hash"] == first["context_hash"]
    assert not following["evidence_options"]
    for cursor in ["", str(uuid7()), f"{uuid7()}:{uuid7()}:{uuid7()}"]:
        with pytest.raises(InvestigationError, match="GROUP_APPLICABILITY_CURSOR_INVALID"):
            read_group_rule_applicability(h.store, *args, h.principal, after=cursor)


def test_policy_changed_during_evidence_read_cannot_return_old_context(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deepaha.investigations import group_applicability
    from deepaha.investigations.applicability import _material_url
    from deepaha.sources.models import SourceEndpoint

    h = harness
    args = prepared(h, monkeypatch)
    original = _material_url
    changed = False

    def interleave(*params: Any) -> str:
        nonlocal changed
        result = original(*params)
        if not changed:
            changed = True
            with h.factory.begin() as session:
                endpoint = session.scalar(select(SourceEndpoint))
                assert endpoint is not None
                endpoint.policy_version = "changed-after-evidence-read"
        return result

    monkeypatch.setattr(group_applicability, "_material_url", interleave)
    with pytest.raises(InvestigationError):
        read_group_rule_applicability(h.store, *args, h.principal)
    assert changed


@pytest.mark.parametrize("nonmember", [False, True])
def test_actual_source_membership_not_shared_opportunity_controls_context(
    harness: StoreHarness,
    monkeypatch: pytest.MonkeyPatch,
    nonmember: bool,
) -> None:
    from tests.integration import test_group_facts
    from tests.investigations.test_delivery import _sample

    def sample() -> tuple[dict[str, Any], dict[str, Any], dict[str, bytes]]:
        opportunities, evidence, artifacts = _sample()
        unit = opportunities["units"][0]
        position = unit["positions"][0]
        # All synthetic rows refer to the same literal paragraph written by _ready.
        position["facts"][0].update(field="学历要求", value="硕士及以上")
        position["facts"][0]["evidence"][0]["quote"] = "学历要求：硕士及以上"
        evidence["facts_flat"][0].update(deepcopy(position["facts"][0]))
        pending = deepcopy(position) | {"id": "pending", "name": "Pending", "code": "P2"}
        pending_entity = deepcopy(evidence["entities"][-1]) | {
            "id": "pending",
            "name": "Pending",
            "code": "P2",
        }
        pending_fact = deepcopy(evidence["facts_flat"][0]) | {"entity_id": "pending"}
        if nonmember:
            unit["positions"] = [pending]
            opportunities["units"].append(
                {
                    "id": "other",
                    "name": "Other group",
                    "parent_id": "announcement",
                    "unit_level": [],
                    "positions": [position],
                }
            )
            evidence["entities"][-1]["parent_id"] = "other"
            evidence["entities"].append(
                {"id": "other", "name": "Other group", "kind": "unit", "parent_id": "announcement"}
            )
            evidence["facts_flat"].insert(0, pending_fact)
        else:
            unit["positions"].append(pending)
            evidence["facts_flat"].append(pending_fact)
        evidence["entities"].append(pending_entity)
        return opportunities, evidence, artifacts

    monkeypatch.setattr(test_group_facts, "_sample", sample)
    args = prepared(harness, monkeypatch)
    if nonmember:
        with pytest.raises(InvestigationError, match="GROUP_APPLICABILITY_SOURCE_CONFLICT"):
            read_group_rule_applicability(harness.store, *args, harness.principal)
    else:
        result = read_group_rule_applicability(harness.store, *args, harness.principal)
        members = result["source_review"]["result"]["preview"]["result"]["fact_review"]["result"][
            "group_source"
        ]["source"]["members"]
        assert [(m["entity_id"], m["state"]) for m in members] == [
            ("position", "BOUND"),
            ("pending", "UNPROCESSED"),
        ]
