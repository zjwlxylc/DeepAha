"""Synthetic projections expose gaps; they cannot approve complete qualification."""

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest

from deepaha.investigations.scope_preflight import project_scope_preflight
from tests.investigations.test_cross_level_adjudication import source

NOW = datetime(2026, 9, 11, tzinfo=UTC)


def test_preserves_denominator_unknowns_and_time_policy() -> None:
    current = source()
    original = deepcopy(current)
    result = project_scope_preflight(current, [], as_of=NOW)
    assert current == original
    assert [r["condition_id"] for r in result["conditions"]] == [
        "source:0",
        "source:1",
        "source:2",
        "source:3",
    ]
    assert result["source_row_count"] == 4
    assert result["executable"] is False
    assert result["overall_qualification"] == "UNCERTAIN"
    assert "HUMAN_SCOPE_REVIEW_UNVERIFIED" in result["blockers"]
    assert "EVIDENCE_TIME_BOUNDARIES_NOT_ESTABLISHED" in result["blockers"]
    assert result["local_evidence_validity"][0]["status"] == "END_NOT_ESTABLISHED"
    assert set(current["snapshot"]["blockers"]) <= set(result["blockers"])
    assert result["unresolved_source_references"]
    assert any(r["issues"] for r in result["conditions"])
    assert result["uncovered_condition_pairs"]


def relation(
    status: str = "APPROVED", kind: str = "CUMULATIVE", key: str = "one"
) -> dict[str, Any]:
    return {
        "proposal_id": key,
        "status": status,
        "relation": kind,
        "condition_ids": ["source:0", "source:3"],
        "payload_sha256": "a" * 64,
    }


@pytest.mark.parametrize("status", ["STALE", "UNREVIEWED", "REJECTED", "NEEDS_ADJUDICATION"])
def test_only_current_approved_relations_cover_pairs(status: str) -> None:
    result = project_scope_preflight(source(), [relation(status)], as_of=NOW)
    assert ["source:0", "source:3"] in result["uncovered_condition_pairs"]


def test_approved_relation_is_review_coverage_not_execution() -> None:
    result = project_scope_preflight(source(), [relation()], as_of=NOW)
    assert ["source:0", "source:3"] not in result["uncovered_condition_pairs"]
    assert result["executable"] is False
    assert "CROSS_LEVEL_SEMANTICS_NOT_REVIEWED" in result["blockers"]


@pytest.mark.parametrize(
    "kind,code",
    [
        ("CONFLICT", "CROSS_LEVEL_CONFLICT_RECORDED"),
        ("EXCEPTION", "EXCEPTION_EXECUTION_NOT_IMPLEMENTED"),
    ],
)
def test_approval_cannot_hide_conflicts_or_execute_exceptions(kind: str, code: str) -> None:
    result = project_scope_preflight(source(), [relation(kind=kind)], as_of=NOW)
    assert code in result["blockers"]
    assert result["executable"] is False


def test_overlapping_approvals_need_joint_review() -> None:
    result = project_scope_preflight(source(), [relation(), relation(key="two")], as_of=NOW)
    assert result["overlapping_relation_pairs"] == [["one", "two"]]
    assert "OVERLAPPING_RELATIONS_REQUIRE_REVIEW" in result["blockers"]


@pytest.mark.parametrize(
    "clock,status",
    [
        (datetime(2025, 1, 1, tzinfo=UTC), "NOT_YET_VALID"),
        (datetime(2026, 9, 11, tzinfo=UTC), "EXPIRED"),
        (datetime(2025, 12, 31, 16, tzinfo=UTC), "WITHIN_RECORDED_INTERVAL"),
    ],
)
def test_time_intervals_are_start_inclusive_end_exclusive(clock: datetime, status: str) -> None:
    # Internal projection consumes an already trusted reconstruction. Exercise its
    # clock logic without representing this mutated fixture as a valid DB export.
    current = source()
    base = current["dependencies"]["group"]["snapshot"]["base_v2"]
    base["plan"]["admissions"][0]["evidence_validity"][0].update(valid_until="2026-09-11T00:00:00Z")
    result = project_scope_preflight(current, [], as_of=clock)
    assert result["local_evidence_validity"][0]["status"] == status


def test_naive_clock_is_rejected() -> None:
    with pytest.raises(ValueError):
        project_scope_preflight(source(), [], as_of=NOW.replace(tzinfo=None))


@pytest.mark.parametrize("attack", ["omitted", "duplicate", "count"])
def test_incomplete_denominator_is_rejected(attack: str) -> None:
    current = source()
    if attack == "omitted":
        current["snapshot"]["conditions"].pop()
    elif attack == "duplicate":
        current["snapshot"]["conditions"].append(current["snapshot"]["conditions"][0])
    else:
        current["dependencies"]["group"]["snapshot"]["base_v2"]["context"]["source_row_count"] += 1
    with pytest.raises(ValueError, match="denominator"):
        project_scope_preflight(current, [], as_of=NOW)
