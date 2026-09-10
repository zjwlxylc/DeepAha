"""Actual DB records, synthetic evidence and human accounts; no release qualification."""

from copy import deepcopy
from typing import Any
from uuid import UUID, uuid7

import pytest
from sqlalchemy import event

from deepaha.investigations.announcement_sources import _assemble as announcement_projection
from deepaha.investigations.applicability import read_rule_applicability, save_rule_applicability
from deepaha.investigations.contracts import (
    DecideInvestigationFact,
    InvestigationError,
    PrepareInvestigationFacts,
    PromoteInvestigationFacts,
    digest,
)
from deepaha.investigations.cross_level_preview import preview_cross_level
from deepaha.investigations.cross_level_review import _compose_cross_level, replay_cross_level
from deepaha.investigations.facts import act_on_facts, prepare_facts
from deepaha.investigations.group_applicability import read_group_rule_applicability
from deepaha.investigations.group_applicability_decisions import save_group_applicability
from deepaha.investigations.rule_contracts import MaterializeInvestigationUnitPlan
from deepaha.investigations.rules import decide_rule, prepare_rules
from deepaha.investigations.unit_snapshots import load_unit_plan
from deepaha.review.models import ReviewerAccountModel
from deepaha.sources.models import SourceEndpoint
from tests.integration.test_group_applicability_decisions import command as group_command
from tests.integration.test_group_rule_applicability import prepared
from tests.integration.test_investigation_rule_applicability import command as ann_command
from tests.integration.test_investigation_rules import _decision
from tests.integration.test_investigation_store import StoreHarness, harness
from tests.investigations.test_delivery import _sample

__all__ = ["harness"]
pytestmark = pytest.mark.integration


def all_levels(h: StoreHarness, monkeypatch: pytest.MonkeyPatch) -> tuple[UUID, UUID, UUID, UUID]:
    def sample() -> tuple[dict[str, Any], dict[str, Any], dict[str, bytes]]:
        opportunities, evidence, artifacts = _sample()
        parent = deepcopy(opportunities["units"][0]["positions"][0]["facts"][0])
        parent.update(field="学历要求", value="硕士及以上")
        parent["evidence"][0]["quote"] = "学历要求：硕士及以上"
        opportunities["announcement_level"] = [parent]
        evidence["facts_flat"].append(
            deepcopy(evidence["facts_flat"][0])
            | parent
            | {"entity_id": "announcement", "entity_kind": "announcement", "level": "announcement"}
        )
        return opportunities, evidence, artifacts

    monkeypatch.setattr("tests.integration.test_group_facts._sample", sample)
    return prepared(h, monkeypatch)


def approve_announcement(h: StoreHarness, task: UUID, plan: UUID) -> tuple[UUID, UUID]:
    base = load_unit_plan(h.store, task, plan, h.principal)
    c = base["context"]
    command = PrepareInvestigationFacts(
        delivery_hash=c["delivery_hash"], binding_id=c["binding_id"], check_id=c["check_id"]
    )
    facts = prepare_facts(h.store, task, command, h.principal)["current"]
    row = next(r for r in facts["rows"] if r["entity_id"] == "announcement")
    common = command.model_dump() | {
        "preparation_id": facts["preparation_id"],
        "reason": "Synthetic review only",
    }
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
        "ann-fact",
    )
    promoted = act_on_facts(
        h.store,
        task,
        PromoteInvestigationFacts.model_validate(common | {"entity_id": "announcement"}),
        h.principal,
        "ann-promote",
    )
    rule_command = MaterializeInvestigationUnitPlan.model_validate(
        command.model_dump()
        | {
            "fact_preparation_id": facts["preparation_id"],
            "entity_id": "announcement",
            "fact_set_id": promoted["current"]["promotions"]["announcement"]["fact_set_id"],
            "rule_preparation_id": uuid7(),
        }
    )
    rules = prepare_rules(h.store, task, rule_command, h.principal)
    rule_command = rule_command.model_copy(
        update={"rule_preparation_id": UUID(rules["rule_preparation_id"])}
    )
    decision = _decision(rule_command, rules)
    decide_rule(h.store, task, decision, h.principal, "ann-rule")
    return rule_command.rule_preparation_id, decision.rule_candidate_id


def test_three_levels_keep_full_denominator_and_exact_exclusions(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, plan, group, candidate = all_levels(h, monkeypatch)
    before = load_unit_plan(h.store, task, plan, h.principal)
    initial = preview_cross_level(h.store, task, plan, h.principal)
    ann, ann_candidate = approve_announcement(h, task, plan)
    av = read_rule_applicability(h.store, task, plan, ann, ann_candidate, h.principal)
    save_rule_applicability(h.store, task, ann_command(av), h.principal, "ann-applies")
    gv = read_group_rule_applicability(h.store, task, plan, group, candidate, h.principal)
    applied = save_group_applicability(
        h.store, task, group_command(gv), h.principal, "group-applies"
    )
    inherited = preview_cross_level(h.store, task, plan, h.principal)
    assert inherited["dependencies_hash"] != initial["dependencies_hash"]
    assert {r["condition"]["scope"] for r in inherited["snapshot"]["conditions"]} == {
        "ANNOUNCEMENT",
        "EMPLOYER_GROUP",
        "UNIT",
    }
    assert [r["condition"] for r in inherited["snapshot"]["conditions"]] == before["plan"][
        "manifest"
    ]["conditions"]
    group_conditions = [
        r
        for r in inherited["snapshot"]["conditions"]
        if r["condition"]["scope"] == "EMPLOYER_GROUP"
    ]
    assert [r["disposition"] for r in group_conditions] == ["INHERITED", "UNRESOLVED"]
    save_group_applicability(
        h.store,
        task,
        group_command(gv, "DOES_NOT_APPLY", UUID(applied["decision_id"])),
        h.principal,
        "group-exclude",
    )
    excluded = preview_cross_level(h.store, task, plan, h.principal)
    rows = excluded["snapshot"]["conditions"]
    assert len(rows) == 4
    assert [r["disposition"] for r in rows].count("EXCLUDED") == 1
    assert (
        next(r for r in rows if r["condition"]["scope"] == "ANNOUNCEMENT")["disposition"]
        == "INHERITED"
    )
    review_group = excluded["snapshot"]["semantic_review_groups"][0]
    assert len(review_group["condition_ids"]) == 3
    assert review_group["excluded_condition_ids"] == [
        group_conditions[0]["condition"]["condition_id"]
    ]
    assert review_group["relation"] == "NOT_EVALUATED"
    assert (
        replay_cross_level(inherited, expected_dependencies_hash=inherited["dependencies_hash"])
        == inherited
    )  # Historical, not current-state approval.
    # Pin the digest from the actual authorized DB export before modifying any package bytes.
    trusted_hash = inherited["dependencies_hash"]
    for attack in ("original", "target", "receipt-hash", "approval", "compiler"):
        forged = deepcopy(inherited)
        ann_source = forged["dependencies"]["announcement"]["dependencies"]["announcement_sources"][
            0
        ]
        receipt = ann_source["applicability_histories"][str(ann_candidate)][0]
        if attack == "original":
            ann_source["source_rows"][0]["original"]["value"] = "伪造条件"
        elif attack == "target":
            receipt["request"]["target_plan_id"] = str(uuid7())
        elif attack == "receipt-hash":
            receipt["request_hash"] = "0" * 64
        elif attack == "approval":
            ann_source["approved_rule_decisions"] = {}
        else:
            ann_source["rule_preparation"]["compiler_version"] = "future/compiler"
        forged["dependencies_hash"] = digest(forged["dependencies"])
        with pytest.raises(ValueError, match="trusted export digest"):
            replay_cross_level(forged, expected_dependencies_hash=trusted_hash)
        if attack in {"original", "compiler"}:
            # Also reject invalid frozen rows or unsupported versions even with a newly
            # issued trusted digest; digest provenance cannot establish version support.
            ann_input = announcement_projection(before, [ann_source])
            with pytest.raises(ValueError, match="frozen full denominator|unsupported"):
                _compose_cross_level(ann_input, inherited["dependencies"]["group"])
    assert load_unit_plan(h.store, task, plan, h.principal) == before

    statements: list[str] = []

    def capture(_conn: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        statements.append(statement.lstrip().split()[0].upper())

    with h.factory() as session:
        engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", capture)
    try:
        assert preview_cross_level(h.store, task, plan, h.principal) == excluded
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert not set(statements) & {
        "INSERT",
        "UPDATE",
        "DELETE",
        "CREATE",
        "ALTER",
        "DROP",
        "TRUNCATE",
    }


@pytest.mark.parametrize("change", ["permission", "source", "projection"])
def test_change_during_read_is_rejected(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    from deepaha.investigations import cross_level_preview as module

    h = harness
    task, plan, _, _ = prepared(h, monkeypatch)
    original = module._build
    calls = 0

    def changed(*args: Any) -> dict[str, Any]:
        nonlocal calls
        result = original(*args)
        calls += 1
        if calls == 1 and change in {"permission", "source"}:
            # The service holds a shared account lock. Inject inside its own transaction,
            # rather than synchronously waiting on an external conflicting write.
            if change == "permission":
                session = args[1]
                account = session.get(ReviewerAccountModel, h.principal.reviewer_id)
                assert account is not None
                account.active = False
                session.flush()
            else:
                with h.factory.begin() as session:
                    endpoint = session.get(SourceEndpoint, h.command.endpoint_id)
                    assert endpoint is not None
                    endpoint.active = False
        if calls == 2 and change == "projection":
            result["snapshot"]["blockers"].append("CHANGED")
        return result

    monkeypatch.setattr(module, "_build", changed)
    with pytest.raises(InvestigationError):
        preview_cross_level(h.store, task, plan, h.principal)
