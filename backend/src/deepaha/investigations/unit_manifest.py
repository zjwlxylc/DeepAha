"""Preserve every source row, without inheriting parent or peer qualifications."""

from typing import Any

from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.unit_qualification.contracts import CoverageCondition, UnitIdentity


def source_conditions(
    target: UnitIdentity,
    entity_id: str,
    delivery: dict[str, Any],
    sources: list[dict[str, Any]],
    facts: dict[str, dict[str, Any]],
    fact_decisions: dict[str, str],
    rule_decisions: dict[str, str],
) -> tuple[list[CoverageCondition], list[dict[str, Any]], list[dict[str, Any]]]:
    entities = {entity["id"]: entity for entity in delivery["evidence"]["entities"]}
    groups = {
        group["id"]
        for group in delivery["opportunities"]["units"]
        if any(position["id"] == entity_id for position in group["positions"])
    }
    if len(groups) != 1 or len(sources) != len(delivery["facts"]):
        raise InvestigationError("UNIT_SOURCE_DENOMINATOR_INVALID")
    conditions, excluded, notes = [], [], []
    for index, source in enumerate(sources):
        original = source["original"]
        if source["source_index"] != index or original != delivery["facts"][index]:
            raise InvestigationError("UNIT_SOURCE_DENOMINATOR_INVALID")
        entity = entities[source["entity_id"]]
        scope = {"announcement": "ANNOUNCEMENT", "unit": "EMPLOYER_GROUP", "position": "UNIT"}.get(
            entity["kind"]
        )
        if source["entity_id"] != entity_id and not (
            scope == "ANNOUNCEMENT" or scope == "EMPLOYER_GROUP" and entity["id"] in groups
        ):
            excluded.append(
                {
                    "source_index": index,
                    "entity_id": entity["id"],
                    "source_sha256": digest(source),
                    "reason": "DIFFERENT_ENTITY_SCOPE",
                }
            )
            continue
        if scope is None:
            raise InvestigationError("UNIT_SOURCE_SCOPE_INVALID")
        fact = facts.get(source["candidate_id"]) if source["entity_id"] == entity_id else None
        condition_id = f"source:{index}"
        conditions.append(
            CoverageCondition.model_validate(
                {
                    "condition_id": condition_id,
                    "scope": scope,
                    "source_entity_id": entity["id"],
                    "source_index": index,
                    "source_unit_id": target.unit_id if scope == "UNIT" else None,
                    "source_unit_version": target.unit_version if scope == "UNIT" else None,
                    "source_unit_version_id": target.unit_version_id if scope == "UNIT" else None,
                    "field_name": source["field_name"] or original["field"],
                    "source_sha256": digest(source),
                    "state": _state(source, fact, fact_decisions, rule_decisions),
                    "fact_id": fact["verified_fact_id"] if fact else None,
                    "evidence_ref_ids": list(
                        dict.fromkeys(
                            e["binding"]["evidence_ref_id"]
                            for e in source["evidence"]
                            if e["binding"]
                        )
                    ),
                }
            )
        )
        if original.get("note"):
            notes.append({"condition_id": condition_id, "note": original["note"]})
    if {c.source_index for c in conditions} | {r["source_index"] for r in excluded} != set(
        range(len(sources))
    ):
        raise InvestigationError("UNIT_SOURCE_DENOMINATOR_INVALID")
    return conditions, excluded, notes


def _state(
    source: dict[str, Any],
    fact: dict[str, Any] | None,
    fact_decisions: dict[str, str],
    rule_decisions: dict[str, str],
) -> str:
    # Human rejection is retained; it never means the condition does not apply.
    if fact_decisions.get(source["candidate_id"]) == "REJECT" or (
        fact and rule_decisions.get(fact["rule_candidate_id"]) == "REJECT"
    ):
        return "REJECTED"
    original_status = source["original"]["status"]
    if original_status == "UNPROCESSED":
        return "UNPROCESSED"
    if original_status == "CONFLICT":
        return "CONFLICT"
    if original_status in {"UNKNOWN", "INSUFFICIENT"}:
        return "UNKNOWN"
    if not source["evidence"] or any(not e["binding"] for e in source["evidence"]):
        return "UNLOCATED"
    if fact:
        return "KNOWN" if fact["fact_state"] == "KNOWN" else "UNKNOWN"
    if source["field_name"] is None or "UNKNOWN_NORMALIZATION_UNSUPPORTED" in source["issue_codes"]:
        return "UNSUPPORTED"
    return "UNPROCESSED"
