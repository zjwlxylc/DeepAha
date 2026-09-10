"""Offline assembly boundaries; persisted-source verification is covered by PG tests."""

from copy import deepcopy
from typing import Any

import pytest

from deepaha.investigations.announcement_sources import _assemble, _record
from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.models import InvestigationFactAction


def inputs() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    condition = {
        "condition_id": "source:1",
        "scope": "ANNOUNCEMENT",
        "source_index": 1,
        "source_entity_id": "announcement",
        "source_sha256": "a" * 64,
        "source_unit_id": None,
        "source_unit_version": None,
        "source_unit_version_id": None,
        "field_name": "education_level",
        "fact_id": None,
        "state": "UNPROCESSED",
        "evidence_ref_ids": ["official-source-reference"],
    }
    base = {
        "plan_id": "base-id",
        "plan_hash": "b" * 64,
        "context_hash": "c" * 64,
        "plan": {
            "manifest": {
                "conditions": [condition],
                "preparation_id": "preparation-id",
                "preparation_sha256": "d" * 64,
            }
        },
        "context": {
            "source_notes": [{"condition_id": "source:1", "note": "Word 尚未核验"}],
            "unresolved_source_references": ["word"],
        },
        "reviewer_id": "base-creator",
        "created_at": "2026-09-08T12:00:00Z",
    }
    group = {
        "entity_id": "announcement",
        "source_rows": [{"source_index": 1, "candidate_id": "fact-candidate"}],
        "fact_actions": [],
        "fact_set": {"verified_fact_set_id": "fact-set"},
        "facts": [
            {
                "candidate_id": "fact-candidate",
                "verified_fact_id": "parent-fact",
                "fact_state": "KNOWN",
            }
        ],
        "rule_preparation": {"rule_preparation_id": "parent-preparation"},
        "rule_rows": [{"verified_fact_id": "parent-fact", "rule_candidate_id": "parent-rule"}],
        "rule_decisions": [],
        "all_rules_final": True,
        "approved_rules": {"parent-rule": {"rule_id": "parent-rule", "value": "MASTER"}},
        "approved_rule_decisions": {
            "parent-rule": {"decision_id": "parent-approval", "approval": {"decision": "APPROVE"}}
        },
        "applicability_histories": {"parent-rule": []},
    }
    return base, [group]


@pytest.mark.parametrize(
    "outcome,expected",
    [
        (None, "UNRESOLVED"),
        ("NEEDS_ADJUDICATION", "UNRESOLVED"),
        ("APPLIES", "INHERITED"),
        ("DOES_NOT_APPLY", "EXCLUDED"),
    ],
)
def test_preserves_parent_condition_and_explicit_applicability(
    outcome: str | None, expected: str
) -> None:
    base, sources = inputs()
    original = deepcopy(base)
    if outcome:
        sources[0]["applicability_histories"]["parent-rule"] = [
            {
                "decision_id": "scope-decision",
                "request": {"outcome": outcome, "reason": "  scope evidence\n"},
            }
        ]
    result = _assemble(base, sources)
    row = result["snapshot"]["announcement_conditions"][0]
    assert row["disposition"] == expected
    assert row["condition"] == original["plan"]["manifest"]["conditions"][0]
    assert row["source_fact"]["verified_fact_id"] == "parent-fact"
    assert row["source_rule"]["rule_id"] == "parent-rule"
    assert row["source_rule_approval"]["decision_id"] == "parent-approval"
    assert result["snapshot"]["base_v2"] == original == base
    assert result["snapshot"]["overall_qualification"] == "UNCERTAIN"
    assert result["dependencies_hash"] == digest(result["dependencies"])


def test_new_nonapplicable_or_same_outcome_receipt_changes_dependency_hash() -> None:
    base, sources = inputs()
    before = _assemble(base, sources)
    history = sources[0]["applicability_histories"]["parent-rule"]
    history.append(
        {"decision_id": "one", "request": {"outcome": "DOES_NOT_APPLY", "reason": "first"}}
    )
    excluded = _assemble(base, sources)
    history.append(
        {"decision_id": "two", "request": {"outcome": "DOES_NOT_APPLY", "reason": "correction"}}
    )
    corrected = _assemble(base, sources)
    assert len({r["dependencies_hash"] for r in (before, excluded, corrected)}) == 3
    assert corrected == _assemble(base, deepcopy(sources))


@pytest.mark.parametrize("missing", ["fact", "preparation", "candidate", "approval", "group_final"])
def test_known_missing_source_stays_in_denominator(missing: str) -> None:
    base, sources = inputs()
    group = sources[0]
    if missing == "fact":
        group["facts"] = []
    elif missing == "preparation":
        group["rule_preparation"] = None
        group["rule_rows"] = []
    elif missing == "candidate":
        group["rule_rows"][0]["rule_candidate_id"] = None
    elif missing == "approval":
        group["approved_rules"] = {}
        group["approved_rule_decisions"] = {}
    else:
        group["all_rules_final"] = False
    result = _assemble(base, sources)
    assert len(result["snapshot"]["announcement_conditions"]) == 1
    row = result["snapshot"]["announcement_conditions"][0]
    assert row["disposition"] == "UNRESOLVED" and row["reasons"]


def test_missing_announcement_group_is_an_error_not_silently_dropped() -> None:
    base, _ = inputs()
    with pytest.raises(InvestigationError, match="ANNOUNCEMENT_SOURCE"):
        _assemble(base, [])


def test_all_decisions_participate_in_hash_and_result_does_not_alias_inputs() -> None:
    base, sources = inputs()
    first = _assemble(base, sources)
    sources[0]["fact_actions"].append(
        {"decision_id": "unpromoted-rejection", "request": {"decision": "REJECT"}}
    )
    second = _assemble(base, sources)
    assert first["dependencies_hash"] != second["dependencies_hash"]
    second["snapshot"]["base_v2"]["context"]["source_notes"] = []
    assert base["context"]["source_notes"]


@pytest.mark.parametrize(
    "state,reason",
    [
        ("UNLOCATED", "SOURCE_EVIDENCE_UNVERIFIED"),
        ("UNSUPPORTED", "SOURCE_FIELD_UNSUPPORTED"),
        ("CONFLICT", "SOURCE_CONDITION_CONFLICT"),
        ("UNKNOWN", "SOURCE_CONDITION_UNKNOWN"),
        ("UNPROCESSED", "SOURCE_CONDITION_UNPROCESSED"),
    ],
)
def test_distinguishes_unread_evidence_from_missing_review(state: str, reason: str) -> None:
    base, sources = inputs()
    base["plan"]["manifest"]["conditions"][0]["state"] = state
    sources[0]["facts"] = []
    sources[0]["source_rows"][0]["candidate_id"] = None
    row = _assemble(base, sources)["snapshot"]["announcement_conditions"][0]
    assert row["disposition"] == "UNRESOLVED"
    assert reason in row["reasons"]
    assert "SOURCE_FACT_CANDIDATE_MISSING" in row["reasons"]


def test_record_serializer_excludes_request_nonce_from_dependencies() -> None:
    action = InvestigationFactAction(
        request_key_hash="nonce-must-not-enter-dependency",
        request={"reason": "  exact source text\n"},
    )
    value = _record(action)
    assert "request_key_hash" not in value
    assert value["request"]["reason"] == "  exact source text\n"
