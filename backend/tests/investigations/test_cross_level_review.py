"""Replay checks use recorded synthetic inputs, never current human approval."""

from copy import deepcopy
from typing import Any

import pytest

from deepaha.investigations.announcement_sources import _assemble
from deepaha.investigations.contracts import digest
from deepaha.investigations.cross_level_review import _compose_cross_level, replay_cross_level
from tests.api.test_group_inheritance_contract import rehash, sample


def inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    group = sample()
    return _assemble(group["snapshot"]["base_v2"], []), group


def test_replay_keeps_every_condition_and_original_inputs_without_executing() -> None:
    ann, group = inputs()
    original = deepcopy((ann, group))
    result = _compose_cross_level(ann, group)
    assert (ann, group) == original
    assert (
        replay_cross_level(result, expected_dependencies_hash=result["dependencies_hash"]) == result
    )
    snap = result["snapshot"]
    base = group["snapshot"]["base_v2"]
    assert [r["condition"] for r in snap["conditions"]] == base["plan"]["manifest"]["conditions"]
    assert {r["disposition"] for r in snap["conditions"]} == {"LOCAL", "INHERITED", "UNRESOLVED"}
    assert not snap["executable"] and snap["overall_qualification"] == "UNCERTAIN"
    assert snap["semantic_review_groups"][0]["relation"] == "NOT_EVALUATED"
    assert result["dependencies"]["announcement"] == ann
    assert result["dependencies"]["group"] == group


@pytest.mark.parametrize("attack", ["drop", "override", "hide-group", "execute", "blocker"])
def test_rehashing_a_forged_projection_is_rejected(attack: str) -> None:
    result = _compose_cross_level(*inputs())
    snap = result["snapshot"]
    if attack == "drop":
        snap["conditions"].pop()
    elif attack == "override":
        snap["conditions"][0]["disposition"] = "EXCLUDED"
    elif attack == "hide-group":
        snap["semantic_review_groups"] = []
    elif attack == "execute":
        snap["executable"] = True
    else:
        snap["blockers"] = []
    result["snapshot_hash"] = digest(snap)
    with pytest.raises(ValueError):
        replay_cross_level(result, expected_dependencies_hash=result["dependencies_hash"])


@pytest.mark.parametrize("attack", ["base", "version", "extra", "hash", "denominator"])
def test_invalid_or_mixed_inputs_are_rejected(attack: str) -> None:
    ann, group = inputs()
    if attack == "base":
        ann["snapshot"]["base_v2"]["created_at"] = "2026-09-09T00:00:00Z"
    elif attack == "version":
        ann["snapshot"]["contract_version"] = "future/1"
    elif attack == "extra":
        ann["grant_approval"] = True
    elif attack == "hash":
        ann["dependencies_hash"] = "f" * 64
    else:
        group["snapshot"]["group_conditions"].pop()
        group["snapshot_hash"] = digest(group["snapshot"])
    with pytest.raises(ValueError):
        _compose_cross_level(ann, group)


def test_trusted_export_does_not_make_unknown_group_deriver_supported() -> None:
    ann, group = inputs()
    group["dependencies"]["group_source"]["rule_preview"]["result"]["derivation_version"] = (
        "future/2.0.0"
    )
    rehash(group)
    with pytest.raises(ValueError, match="unsupported group rule derivation"):
        _compose_cross_level(ann, group)
