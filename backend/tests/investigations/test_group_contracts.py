from typing import Any
from uuid import uuid7

import pytest
from pydantic import ValidationError

from deepaha.investigations.contracts import digest
from deepaha.investigations.group_contracts import (
    GroupSourceContext,
    GroupSourceRecord,
    RegisterGroupSource,
)
from tests.investigations.test_delivery import _sample


def source_fixture() -> dict[str, Any]:
    opportunities, evidence, _ = _sample()
    return {
        "contract_version": "group-identity/1.0.0",
        "scope": "GROUP_SOURCE_ASSOCIATION_ONLY",
        "task_id": str(uuid7()),
        "delivery_hash": "a" * 64,
        "binding_id": str(uuid7()),
        "binding_hash": "b" * 64,
        "opportunity_id": str(uuid7()),
        "opportunity_version": 1,
        "source_bundle_revision_id": str(uuid7()),
        "canonical_bundle_hash": "c" * 64,
        "source_snapshot_hash": "d" * 64,
        "source_group": opportunities["units"][0],
        "source_entity": next(e for e in evidence["entities"] if e["id"] == "unit"),
        "members": [{"entity_id": "position", "state": "UNPROCESSED", "position_binding": None}],
        "membership_status": "UNPROCESSED_MEMBERS",
    }


def record_fixture() -> dict[str, Any]:
    source = source_fixture()
    unit_id = uuid7()
    return GroupSourceRecord.model_validate(
        {
            "contract_version": "group-identity/1.0.0",
            "scope": "GROUP_SOURCE_ASSOCIATION_ONLY",
            "group_binding_id": str(uuid7()),
            "group_identity": {
                "unit_kind": "GROUP",
                "unit_id": str(unit_id),
                "public_id": f"unit_{unit_id.hex}",
                "unit_version_id": str(uuid7()),
                "version": 1,
                "key": "group:example",
                "label": "Unit",
            },
            "source": source,
            "source_hash": digest(source),
            "reviewer_id": str(uuid7()),
            "created_at": "2026-09-10T00:00:00Z",
        }
    ).model_dump(mode="json")


@pytest.mark.parametrize("extra", [{"members": []}, {"group_id": str(uuid7())}, {"complete": True}])
def test_registration_request_cannot_choose_members_or_identity(extra: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        RegisterGroupSource.model_validate(
            {"entity_id": "unit", "expected_source_hash": "a" * 64, **extra}
        )


@pytest.mark.parametrize(
    "mutation",
    ["missing_member", "false_state", "false_complete", "wrong_entity", "other_contract"],
)
def test_source_contract_preserves_denominator_and_uncertainty(mutation: str) -> None:
    source = source_fixture()
    if mutation == "missing_member":
        source["members"] = []
    elif mutation == "false_state":
        source["members"][0]["state"] = "BOUND"
    elif mutation == "false_complete":
        source["membership_status"] = "ALL_MEMBERS_BOUND"
    elif mutation == "wrong_entity":
        source["source_entity"]["id"] = "other"
    else:
        source["contract_version"] = "0.8.0"
    with pytest.raises(ValidationError):
        GroupSourceContext.model_validate(source)


def test_record_contract_is_group_only() -> None:
    record = record_fixture()
    record["group_identity"]["unit_kind"] = "POSITION"
    with pytest.raises(ValidationError):
        GroupSourceRecord.model_validate(record)
