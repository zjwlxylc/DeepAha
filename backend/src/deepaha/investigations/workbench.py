"""Bounded read projection; no inferred identity or human decision."""

from typing import Any

from deepaha.investigations.contracts import InvestigationError


def select_workbench(view: dict[str, Any], entity_id: str | None, offset: int) -> dict[str, Any]:
    entities = view["binding_entities"]
    if entity_id is not None and entity_id not in {entity["id"] for entity in entities}:
        raise InvestigationError("WORKBENCH_OBJECT_NOT_FOUND")
    original = view["opportunities"] or {}
    view["opportunities"] = {
        key: original[key] for key in ("opportunity_name", "publish_unit") if key in original
    }
    view["opportunities"]["units"] = [
        {
            "id": unit.get("id"),
            "name": unit.get("name"),
            "positions": [
                {key: position[key] for key in ("id", "name", "code") if key in position}
                for position in unit.get("positions", [])
            ],
        }
        for unit in original.get("units", [])
    ]
    selected = [
        (index, fact) for index, fact in enumerate(view["facts"]) if fact["entity_id"] == entity_id
    ]
    view["workbench"] = {"entity_id": entity_id, "offset": offset, "total": len(selected)}
    page = selected[offset : offset + 1]
    view["facts"] = [fact for _, fact in page]
    index_map = {old: new for new, (old, _) in enumerate(page)}
    for check in view["evidence_check_history"]:
        check["references"] = [
            dict(ref, fact_index=index_map[ref["fact_index"]])
            for ref in check["references"]
            if ref["fact_index"] in index_map
        ]
        # Inputs retain the original whole-delivery hash but are not needed by the UI.
        check.pop("inputs", None)
    view["rule_review"]["current"] = [
        prep for prep in view["rule_review"]["current"] if prep["entity_id"] == entity_id
    ]
    for prep in view["rule_review"]["current"]:
        prep["slice"] = {"offset": offset, "total": len(prep["rows"])}
        prep["rows"] = prep["rows"][offset : offset + 1]
        candidates = {row["candidate_id"] for row in prep["rows"]}
        prep["source_rows"] = [
            row for row in prep["source_rows"] if row["candidate_id"] in candidates
        ]
        rule_ids = {row["rule_candidate_id"] for row in prep["rows"]}
        prep["decisions"] = {
            key: value for key, value in prep["decisions"].items() if key in rule_ids
        }
        prep["decision_history"] = []
    view.pop("report", None)
    view.pop("execution", None)
    return view
