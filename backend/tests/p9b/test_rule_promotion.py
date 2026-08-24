from datetime import UTC, datetime
from uuid import UUID

import pytest

from deepaha.contracts.phase9b import RuleCandidateSchemaV08, UnitRuleSetSchemaV08
from deepaha.p9b.rules import (
    P9BRuleCompileError,
    compile_dormant_unit_rule_set,
    compile_legacy_opportunity_rule,
)

NOW = datetime(2026, 8, 24, 15, 30, tzinfo=UTC)


def uuid7(index: int) -> UUID:
    return UUID(f"019c0000-0000-7000-8000-{index:012x}")


def rule_candidate_values(*, target_scope: str) -> dict[str, object]:
    is_unit = target_scope == "UNIT"
    return {
        "rule_candidate_id": uuid7(1),
        "target_scope": target_scope,
        "opportunity_id": uuid7(2),
        "opportunity_version": 3,
        "opportunity_unit_id": uuid7(3) if is_unit else None,
        "opportunity_unit_version_id": uuid7(4) if is_unit else None,
        "verified_fact_ids": [uuid7(5)],
        "rule_type": "ATOMIC_QUALIFICATION",
        "proposed_rule_payload": {
            "code": "education-minimum",
            "operator": "GTE",
            "field": "education_level",
            "value_type": "STRING",
            "value": "BACHELOR",
            "required": True,
            "reason_template": "学历至少为本科",
        },
        "evidence_ref_ids": [uuid7(6)],
        "compiler_version": "p9b-rule-candidate-compiler/0.8.0",
        "producer_identity": "component:verified-fact-to-rule/0.8.0",
        "status": "PROPOSED",
        "created_at": NOW,
    }


def test_unit_candidate_cannot_compile_to_legacy_opportunity_rule() -> None:
    candidate = RuleCandidateSchemaV08.model_validate(rule_candidate_values(target_scope="UNIT"))

    with pytest.raises(P9BRuleCompileError, match="Unit"):
        compile_legacy_opportunity_rule(candidate)


def test_approved_unit_candidate_compiles_only_to_dormant_unit_rule_set() -> None:
    candidate = RuleCandidateSchemaV08.model_validate(rule_candidate_values(target_scope="UNIT"))

    compiled = compile_dormant_unit_rule_set(
        candidate,
        rule_approval_decision_id=uuid7(7),
        approval_decision="APPROVE",
        unit_rule_set_id=uuid7(8),
        created_at=NOW,
    )

    rule_set = UnitRuleSetSchemaV08.model_validate(compiled)
    assert rule_set.activation_status == "DORMANT"
    assert rule_set.opportunity_unit_id == candidate.opportunity_unit_id
    assert "rule_set_id" not in compiled


def test_rejected_or_opportunity_candidate_cannot_materialize_unit_rule_set() -> None:
    unit = RuleCandidateSchemaV08.model_validate(rule_candidate_values(target_scope="UNIT"))
    opportunity = RuleCandidateSchemaV08.model_validate(
        rule_candidate_values(target_scope="OPPORTUNITY")
    )

    with pytest.raises(P9BRuleCompileError, match="approved"):
        compile_dormant_unit_rule_set(
            unit,
            rule_approval_decision_id=uuid7(9),
            approval_decision="REJECT",
            unit_rule_set_id=uuid7(10),
            created_at=NOW,
        )
    with pytest.raises(P9BRuleCompileError, match="UNIT"):
        compile_dormant_unit_rule_set(
            opportunity,
            rule_approval_decision_id=uuid7(11),
            approval_decision="APPROVE",
            unit_rule_set_id=uuid7(12),
            created_at=NOW,
        )
