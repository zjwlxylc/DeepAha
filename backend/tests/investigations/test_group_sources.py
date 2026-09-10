from copy import deepcopy
from typing import Any

import pytest

from deepaha.investigations.contracts import InvestigationError
from deepaha.investigations.group_sources import group_membership
from tests.investigations.test_delivery import _sample


def _source() -> dict[str, Any]:
    opportunities, evidence, _ = _sample()
    opportunities["units"][0]["positions"].append(
        {"id": "unprocessed", "name": "Second", "facts": []}
    )
    evidence["entities"].append(
        {"id": "unprocessed", "name": "Second", "kind": "position", "parent_id": "unit"}
    )
    opportunities["units"].append(
        {
            "id": "other-group",
            "name": "Other",
            "parent_id": "announcement",
            "unit_level": [],
            "positions": [{"id": "other-position", "name": "Other position", "facts": []}],
        }
    )
    evidence["entities"].extend(
        [
            {"id": "other-group", "name": "Other", "kind": "unit", "parent_id": "announcement"},
            {
                "id": "other-position",
                "name": "Other position",
                "kind": "position",
                "parent_id": "other-group",
            },
        ]
    )
    return {"opportunities": opportunities, "evidence": evidence}


def test_members_preserve_all_source_rows_and_unprocessed_identity() -> None:
    delivery = _source()
    before = deepcopy(delivery)
    binding = {
        "entity_id": "position",
        "opportunity_unit_id": "position-uuid",
        "opportunity_unit_version_id": "version-uuid",
    }
    result = group_membership(delivery, "unit", [binding, {"entity_id": "other-position"}])
    assert result["source_group"] == delivery["opportunities"]["units"][0]
    assert result["members"] == [
        {"entity_id": "position", "state": "BOUND", "position_binding": binding},
        {"entity_id": "unprocessed", "state": "UNPROCESSED", "position_binding": None},
    ]
    assert result["membership_status"] == "UNPROCESSED_MEMBERS"
    assert delivery == before
    result["source_group"]["name"] = "Changed copy"
    assert delivery == before


@pytest.mark.parametrize("entity_id", ["missing", "position", "announcement"])
def test_only_actual_group_can_be_target(entity_id: str) -> None:
    with pytest.raises(InvestigationError, match="GROUP_SOURCE_INVALID"):
        group_membership(_source(), entity_id, [])


@pytest.mark.parametrize(
    "change",
    [
        "duplicate_group",
        "duplicate_position",
        "wrong_parent",
        "duplicate_entity",
        "wrong_kind",
        "duplicate_binding",
        "missing_entity",
    ],
)
def test_ambiguous_source_membership_is_rejected(change: str) -> None:
    delivery = _source()
    groups = delivery["opportunities"]["units"]
    entities = delivery["evidence"]["entities"]
    positions: list[dict[str, Any]] = []
    if change == "duplicate_group":
        groups.append(deepcopy(groups[0]))
    elif change == "duplicate_position":
        groups[1]["positions"].append(deepcopy(groups[0]["positions"][0]))
    elif change == "wrong_parent":
        next(e for e in entities if e["id"] == "position")["parent_id"] = "other-group"
    elif change == "duplicate_entity":
        entities.append(deepcopy(entities[0]))
    elif change == "wrong_kind":
        next(e for e in entities if e["id"] == "unit")["kind"] = "position"
    elif change == "missing_entity":
        entities[:] = [e for e in entities if e["id"] != "unprocessed"]
    else:
        positions = [{"entity_id": "position"}, {"entity_id": "position"}]
    with pytest.raises(InvestigationError, match="GROUP_SOURCE_INVALID"):
        group_membership(delivery, "unit", positions)


def test_empty_group_does_not_claim_full_membership() -> None:
    delivery = _source()
    delivery["opportunities"]["units"][0]["positions"] = []
    delivery["evidence"]["entities"] = [
        e for e in delivery["evidence"]["entities"] if e["parent_id"] != "unit"
    ]
    result = group_membership(delivery, "unit", [])
    assert result["members"] == []
    assert result["membership_status"] == "NO_MEMBERS"


def test_nested_null_parent_preserves_existing_delivery_contract() -> None:
    delivery = _source()
    delivery["opportunities"]["units"][0]["parent_id"] = None
    result = group_membership(delivery, "unit", [])
    assert result["source_group"]["parent_id"] is None
    assert result["source_entity"]["parent_id"] == "announcement"
    assert [row["entity_id"] for row in result["members"]] == ["position", "unprocessed"]
