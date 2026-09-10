"""Synthetic structural review records are not authenticated human decisions."""

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from deepaha.investigations.announcement_sources import _assemble
from deepaha.investigations.contracts import digest
from deepaha.investigations.cross_level_adjudication import (
    AdjudicationPackage,
    replay_adjudication,
)
from deepaha.investigations.cross_level_review import _compose_cross_level

AS_OF = datetime(2026, 9, 11, tzinfo=UTC)


def uid(number: int) -> str:
    return f"019a0000-0000-7000-8000-{number:012x}"


def source() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(
            (Path(__file__).parents[3] / "web/tests/cross-level-fixture.json").read_text(
                encoding="utf-8"
            )
        ),
    )


def package(relation: str = "CUMULATIVE") -> dict[str, Any]:
    review = source()
    bound = review["dependencies"]["announcement"]["snapshot"]["announcement_conditions"][0][
        "applicability"
    ]["evidence_snapshot"][0]
    selected = ["source:0", "source:3"]
    # Reuse a real synthetic bound block only to test shape and exact binding;
    # it does not semantically prove any of these relationship interpretations.
    proposal = {
        "contract_version": "cross-level-adjudication/1.0.0",
        "scope": "CROSS_LEVEL_ADJUDICATION_REVIEW_ONLY",
        "proposal_id": uid(1),
        "producer_id": uid(2),
        "created_at": "2026-09-10T14:00:00Z",
        "source_review": review,
        "source_review_hash": digest(review),
        "condition_ids": selected,
        "relation": relation,
        "displaced_condition_ids": ["source:0"] if relation == "EXCEPTION" else [],
        "reason": "Synthetic interpretation, not an actual human finding",
        "evidence": [
            deepcopy(bound) | {"purpose": purpose, "condition_ids": selected.copy()}
            for purpose in ("CONDITION", "RELATION")
        ],
    }
    result = {"proposal": proposal, "decisions": []}
    # Hash the canonical proposal export, including canonical Instant spelling.
    normalized = AdjudicationPackage.model_validate(result).model_dump(mode="json")
    add_decision(normalized, "NEEDS_ADJUDICATION" if relation == "UNRESOLVED" else "APPROVE")
    return normalized


def add_decision(value: dict[str, Any], outcome: str) -> None:
    history = value["decisions"]
    history.append(
        {
            "decision_id": uid(10 + len(history)),
            "proposal_id": value["proposal"]["proposal_id"],
            "proposal_hash": digest(value["proposal"]),
            "sequence": len(history) + 1,
            "previous_decision_id": history[-1]["decision_id"] if history else None,
            "reviewer_id": uid(3),
            "created_at": "2026-09-10T15:00:00Z",
            "decision": outcome,
            "reason": "Synthetic independent review fixture",
        }
    )


def replay(value: dict[str, Any], current: dict[str, Any] | None = None) -> dict[str, Any]:
    return replay_adjudication(
        value,
        expected_package_hash=digest(value),
        current_source_review=current or source(),
        as_of=AS_OF,
    )


@pytest.mark.parametrize("relation", ["CUMULATIVE", "EXCEPTION", "CONFLICT", "UNRESOLVED"])
def test_all_relations_keep_full_sources_and_never_execute(relation: str) -> None:
    value = package(relation)
    original = deepcopy(value)
    result = replay(value)
    assert value == original
    assert result["source_snapshot"] == value["proposal"]["source_review"]["snapshot"]
    assert result["selected_condition_ids"] == ["source:0", "source:3"]
    assert result["unselected_condition_ids"] == ["source:1", "source:2"]
    assert result["executable"] is False
    assert result["overall_qualification"] == "UNCERTAIN"
    assert set(result["source_snapshot"]["blockers"]) <= set(result["blockers"])
    assert result["status"] == ("NEEDS_ADJUDICATION" if relation == "UNRESOLVED" else "APPROVED")
    if relation == "CONFLICT":
        assert "CROSS_LEVEL_CONFLICT_RECORDED" in result["blockers"]


@pytest.mark.parametrize("attack", ["empty", "all", "foreign", "duplicate", "wrong-relation"])
def test_exception_requires_explicit_nonempty_proper_subset(attack: str) -> None:
    v = package("EXCEPTION")
    p = v["proposal"]
    p["displaced_condition_ids"] = {
        "empty": [],
        "all": p["condition_ids"],
        "foreign": ["source:2"],
        "duplicate": ["source:0", "source:0"],
        "wrong-relation": ["source:0"],
    }[attack]
    if attack == "wrong-relation":
        p["relation"] = "CUMULATIVE"
    v["decisions"] = []
    with pytest.raises(ValueError, match="displaced"):
        replay(v)


@pytest.mark.parametrize(
    "selected",
    [
        [],
        ["source:0"],
        ["source:0", "source:0"],
        ["source:3", "source:0"],
        ["source:0", "other"],
        ["source:0", "source:1"],
        ["source:0", "source:2"],
    ],
)
def test_invalid_missing_or_inactive_condition_selection_is_rejected(selected: list[str]) -> None:
    v = package()
    v["decisions"] = []
    v["proposal"]["condition_ids"] = selected
    with pytest.raises(ValueError):
        replay(v)


def test_different_fields_and_unknown_rows_remain_an_unresolved_diagnostic() -> None:
    v = package("UNRESOLVED")
    p = v["proposal"]
    p["condition_ids"] = ["source:2", "source:3"]
    p["evidence"] = []
    v["decisions"] = []
    assert replay(v)["status"] == "UNREVIEWED"
    add_decision(v, "APPROVE")
    with pytest.raises(ValueError, match="unresolved"):
        replay(v)


@pytest.mark.parametrize(
    "attack",
    [
        "no-relation",
        "missing-condition",
        "foreign",
        "blank",
        "locator",
        "duplicate",
        "partial-relation",
    ],
)
def test_evidence_must_bind_every_condition_and_explicit_relation(attack: str) -> None:
    v = package()
    p = v["proposal"]
    v["decisions"] = []
    if attack == "no-relation":
        p["evidence"].pop()
    elif attack == "missing-condition":
        p["evidence"][0]["condition_ids"] = ["source:0"]
    elif attack == "foreign":
        p["evidence"][0]["condition_ids"] = ["source:0", "source:2"]
    elif attack == "blank":
        p["evidence"][0]["quote"] = " \t\n "
    elif attack == "locator":
        p["evidence"][0]["locator"] = {}
    elif attack == "duplicate":
        p["evidence"].append(deepcopy(p["evidence"][0]))
    else:
        p["evidence"][1]["condition_ids"] = ["source:0"]
    with pytest.raises(ValueError):
        replay(v)


@pytest.mark.parametrize(
    "attack",
    [
        "self",
        "proposal",
        "hash",
        "sequence",
        "previous",
        "past",
        "future",
        "reason",
        "duplicate-id",
    ],
)
def test_decision_history_rejects_invalid_identity_order_and_time(attack: str) -> None:
    v = package()
    if attack == "duplicate-id":
        add_decision(v, "REJECT")
        v["decisions"][-1]["decision_id"] = v["decisions"][0]["decision_id"]
    else:
        key, invalid = {
            "self": ("reviewer_id", uid(2)),
            "proposal": ("proposal_id", uid(99)),
            "hash": ("proposal_hash", "0" * 64),
            "sequence": ("sequence", 2),
            "previous": ("previous_decision_id", uid(99)),
            "past": ("created_at", "2026-09-09T00:00:00Z"),
            "future": ("created_at", "2026-09-12T00:00:00Z"),
            "reason": ("reason", "   "),
        }[attack]
        v["decisions"][0][key] = invalid
    with pytest.raises(ValueError):
        replay(v)


def test_review_revision_and_source_change_do_not_leave_old_approval_active() -> None:
    v = package()
    add_decision(v, "REJECT")
    assert replay(v)["status"] == "REJECTED"
    assert replay(v)["latest"]["decision_id"] == v["decisions"][-1]["decision_id"]
    # A subsequent immutable proposal identity cannot be swapped into this history.
    v["proposal"]["proposal_id"] = uid(99)
    with pytest.raises(ValueError):
        replay(v)


@pytest.mark.parametrize("attack", ["tail", "reviewer", "proposal", "source-hash", "extra"])
def test_independent_whole_package_anchor_rejects_rehashed_tampering(attack: str) -> None:
    v = package()
    add_decision(v, "REJECT")
    anchor = digest(v)
    if attack == "tail":
        v["decisions"].pop()
    elif attack == "reviewer":
        v["decisions"][0]["reviewer_id"] = uid(90)
    elif attack == "proposal":
        v["proposal"]["reason"] = "forged"
        for d in v["decisions"]:
            d["proposal_hash"] = digest(v["proposal"])
    elif attack == "source-hash":
        v["proposal"]["source_review_hash"] = "0" * 64
    else:
        v["grant_eligibility"] = True
    with pytest.raises(ValueError, match="trusted package"):
        replay_adjudication(
            v, expected_package_hash=anchor, current_source_review=source(), as_of=AS_OF
        )


def test_contract_rejects_extra_fields_even_with_a_matching_anchor() -> None:
    v = package()
    v["proposal"]["grant_eligibility"] = True
    with pytest.raises(ValueError):
        replay(v)


@pytest.mark.parametrize("change", ["reason", "scope"])
def test_changed_upstream_review_makes_old_approval_stale(change: str) -> None:
    v = package()
    original = deepcopy(v)
    current = source()
    ann = current["dependencies"]["announcement"]
    group = current["dependencies"]["group"]
    sources = ann["dependencies"]["announcement_sources"]
    history = next(iter(sources[0]["applicability_histories"].values()))
    successor = deepcopy(history[-1])
    successor["sequence"] += 1
    successor["decision_id"] = uid(91)
    successor["request"]["previous_decision_id"] = history[-1]["decision_id"]
    successor["request"]["reason"] = "Synthetic immutable successor scope review"
    if change == "scope":
        successor["request"]["outcome"] = "DOES_NOT_APPLY"
    successor["request_hash"] = digest(successor["request"])
    history.append(successor)
    updated = _compose_cross_level(_assemble(ann["snapshot"]["base_v2"], sources), group)
    result = replay(v, updated)
    assert v == original
    assert result["status"] == "STALE"
    assert result["latest"]["decision"] == "APPROVE"  # history only, never current approval
    assert "CROSS_LEVEL_ADJUDICATION_STALE" in result["blockers"]
    assert result["current_source_review_hash"] == digest(updated)
    assert not result["executable"]


def test_other_valid_task_and_plan_cannot_be_used_as_current_context() -> None:
    from tests.investigations.test_cross_level_review import inputs

    other = _compose_cross_level(*inputs())
    with pytest.raises(ValueError, match="another task or plan"):
        replay(package(), other)


def test_rejected_conflict_proposal_does_not_assert_an_approved_conflict() -> None:
    v = package("CONFLICT")
    add_decision(v, "REJECT")
    result = replay(v)
    assert result["status"] == "REJECTED"
    assert "CROSS_LEVEL_CONFLICT_RECORDED" not in result["blockers"]


def test_unreviewed_proposal_cannot_be_dated_after_trusted_clock() -> None:
    v = package()
    v["decisions"] = []
    v["proposal"]["created_at"] = "2026-09-12T00:00:00Z"
    with pytest.raises(ValueError, match="future"):
        replay(v)


def test_reordered_review_times_are_rejected_even_with_valid_predecessor() -> None:
    v = package()
    add_decision(v, "REJECT")
    v["decisions"][-1]["created_at"] = "2026-09-10T14:30:00Z"
    with pytest.raises(ValueError, match="history"):
        replay(v)


def test_raw_quote_is_not_trimmed_and_missing_trusted_clock_is_rejected() -> None:
    v = package()
    v["decisions"] = []
    v["proposal"]["evidence"][0]["quote"] = "  原文\n引文  "
    assert AdjudicationPackage.model_validate(v).proposal.evidence[0].quote == "  原文\n引文  "
    with pytest.raises(ValueError, match="timezone"):
        replay_adjudication(
            v,
            expected_package_hash=digest(v),
            current_source_review=source(),
            as_of=datetime(2026, 9, 11),
        )
