"""Synthetic heterogeneous source coverage, not a real qualification/Gold result."""

import json
from copy import deepcopy
from typing import Any
from uuid import UUID

import pytest

from deepaha.investigations.contracts import (
    DecideInvestigationFact,
    PrepareInvestigationFacts,
    PromoteInvestigationFacts,
)
from deepaha.investigations.delivery import validate_delivery
from deepaha.investigations.facts import act_on_facts, prepare_facts
from deepaha.investigations.registration import register_identity
from deepaha.investigations.rule_contracts import (
    MaterializeInvestigationUnitPlan,
    PrepareInvestigationRules,
)
from deepaha.investigations.rules import decide_rule, prepare_rules
from deepaha.investigations.unit_snapshots import load_unit_plan, materialize_unit_plan
from deepaha.unit_qualification.compiler import compile_unit_qualification
from deepaha.unit_qualification.contracts import UnitQualificationPlan
from tests.integration.test_investigation_registration import _command
from tests.integration.test_investigation_rules import _decision
from tests.integration.test_investigation_store import (
    StoreHarness,
    _collecting,
    _files,
    _review,
    harness,
)

__all__ = ["harness"]
pytestmark = pytest.mark.integration


def _heterogeneous(
    h: StoreHarness,
) -> tuple[UUID, MaterializeInvestigationUnitPlan, dict[str, Any]]:
    task, owner = _collecting(h)
    files, artifacts = _files(task)
    o, e = json.loads(files["opportunities.json"]), json.loads(files["evidence.json"])
    base = deepcopy(o["units"][0]["positions"][0]["facts"][0])
    base.update(field="学历要求", value="博士研究生及以上")
    own = [
        base,
        deepcopy(base) | {"field": "报考对象", "value": None, "status": "UNKNOWN"},
        deepcopy(base) | {"field": "专业要求", "value": "专业代码：081200"},
        deepcopy(base)
        | {"field": "Synthetic unsupported condition", "value": "See formal attachment"},
        deepcopy(base) | {"field": "户籍要求", "value": '{"allowed_regions":["浙江"]}'},
    ]
    own[0]["note"] = "Synthetic exception requiring separate scope review."
    own[2]["evidence"][0]["locator"]["human_verify"] = True
    o["units"][0]["positions"][0]["facts"] = own
    o["announcement_level"] = [deepcopy(base) | {"field": "年龄要求", "value": "另见附件"}]
    o["units"][0]["unit_level"] = [
        deepcopy(base) | {"field": "户籍要求", "value": None, "status": "UNKNOWN"}
    ]
    o["units"][0]["positions"].append(
        {"id": "peer", "name": "Peer position", "code": "P2", "facts": [deepcopy(base)]}
    )
    o["units"].append(
        {
            "id": "other-group",
            "name": "Other group",
            "parent_id": "announcement",
            "unit_level": [deepcopy(base)],
            "positions": [],
        }
    )
    e["entities"].extend(
        [
            {
                "id": "peer",
                "name": "Peer position",
                "kind": "position",
                "code": "P2",
                "parent_id": "unit",
            },
            {
                "id": "other-group",
                "name": "Other group",
                "kind": "unit",
                "parent_id": "announcement",
            },
        ]
    )
    e["facts_flat"] = []
    for entity_id, kind, values in [
        ("announcement", "announcement", o["announcement_level"]),
        ("unit", "unit", o["units"][0]["unit_level"]),
        ("position", "position", own),
        ("peer", "position", o["units"][0]["positions"][1]["facts"]),
        ("other-group", "unit", o["units"][1]["unit_level"]),
    ]:
        e["facts_flat"].extend(
            {
                "entity_id": entity_id,
                "opportunity_id": "announcement",
                "entity_kind": kind,
                "level": kind,
                **deepcopy(f),
            }
            for f in values
        )
    files["opportunities.json"], files["evidence.json"] = (
        json.dumps(o).encode(),
        json.dumps(e).encode(),
    )
    delivery = validate_delivery(files, artifacts)
    h.store.freeze_manifest(task, owner, files)
    h.store.finish(task, owner, delivery, files)
    docs = h.store.prepare_documents(task, delivery.sha256, h.principal)
    h.store.review(task, _review(delivery), h.principal, "intake")
    bound = register_identity(
        h.store,
        task,
        _command(
            delivery,
            positions=[
                {"entity_id": "position", "unit_key": "P1", "label": "Position"},
                {"entity_id": "peer", "unit_key": "P2", "label": "Peer position"},
            ],
        ),
        h.principal,
        "identity",
    )
    fact_command = PrepareInvestigationFacts(
        delivery_hash=delivery.sha256,
        binding_id=UUID(bound["entity_binding"]["binding_id"]),
        check_id=UUID(docs["evidence_check"]["check_id"]),
    )
    prep = prepare_facts(h.store, task, fact_command, h.principal)["current"]
    common = fact_command.model_dump() | {
        "preparation_id": prep["preparation_id"],
        "reason": "Synthetic fixture only",
    }
    for row in prep["rows"]:
        if row["entity_id"] != "position" or not row["candidate_id"]:
            continue
        decision = (
            "REJECT"
            if row["field_name"] == "household_registration_requirements"
            else "UNKNOWN"
            if row["abstained"]
            else "APPROVE"
        )
        act_on_facts(
            h.store,
            task,
            DecideInvestigationFact.model_validate(
                common
                | {
                    "candidate_id": row["candidate_id"],
                    "decision": decision,
                    "evidence_support": "SUPPORTED",
                    "precedence_check": "PASSED",
                }
            ),
            h.principal,
            str(row["source_index"]),
        )
    promoted = act_on_facts(
        h.store,
        task,
        PromoteInvestigationFacts.model_validate(common | {"entity_id": "position"}),
        h.principal,
        "promote",
    )
    rule_command = PrepareInvestigationRules.model_validate(
        fact_command.model_dump()
        | {
            "fact_preparation_id": prep["preparation_id"],
            "entity_id": "position",
            "fact_set_id": promoted["current"]["promotions"]["position"]["fact_set_id"],
        }
    )
    rules = prepare_rules(h.store, task, rule_command, h.principal)
    decide_rule(h.store, task, _decision(rule_command, rules), h.principal, "rule")
    return (
        task,
        MaterializeInvestigationUnitPlan.model_validate(
            rule_command.model_dump() | {"rule_preparation_id": rules["rule_preparation_id"]}
        ),
        prep,
    )


def test_complete_source_denominator_preserves_unknowns_notes_and_excludes_peers(
    harness: StoreHarness,
) -> None:
    h = harness
    task, command, source = _heterogeneous(h)
    result = materialize_unit_plan(h.store, task, command, h.principal)
    assert load_unit_plan(h.store, task, UUID(result["plan_id"]), h.principal) == result
    plan = UnitQualificationPlan.model_validate(result["plan"])
    own = {c.field_name: c for c in plan.manifest.conditions if c.scope == "UNIT"}
    assert {name: c.state for name, c in own.items()} == {
        "education_requirements": "KNOWN",
        "applicant_scope": "UNKNOWN",
        "major_requirements": "UNLOCATED",
        "Synthetic unsupported condition": "UNSUPPORTED",
        "household_registration_requirements": "REJECTED",
    }
    assert len(plan.rules) == len(plan.admissions) == 1
    assert own["major_requirements"].evidence_ref_ids == ()
    parents = [c for c in plan.manifest.conditions if c.scope != "UNIT"]
    assert len(parents) == 2 and all(
        c.fact_id is None and c.source_unit_version_id is None for c in parents
    )
    assert all(
        d.kind == "UNRESOLVED"
        for d in plan.dispositions
        if d.condition_id in {c.condition_id for c in parents}
    )
    context = result["context"]
    assert context["source_row_count"] == len(source["rows"]) == 9
    assert {r["entity_id"] for r in context["excluded_source_rows"]} == {"peer", "other-group"}
    assert len(plan.manifest.conditions) + len(context["excluded_source_rows"]) == 9
    assert len(context["source_notes"]) == 3
    assert context["evidence_reference_counts"] == {"PASS": 8, "FAIL": 0, "UNVERIFIED": 1}
    assert len(context["unresolved_source_references"]) == 1
    assert "SOURCE_NOTES_UNREVIEWED" in plan.manifest.upstream_blockers
    compiled = compile_unit_qualification(plan, evidence_as_of=h.clock())
    assert "HUMAN_SCOPE_REVIEW_UNVERIFIED" in {b.code for b in compiled.coverage_blockers}
