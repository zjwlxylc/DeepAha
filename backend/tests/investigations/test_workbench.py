from deepaha.investigations.workbench import select_workbench


def test_large_synthetic_delivery_is_not_transferred_to_workbench() -> None:
    facts = [{"entity_id": f"position-{i % 2}", "field": f"field-{i}"} for i in range(2527)]
    view = {
        "binding_entities": [{"id": "position-0"}, {"id": "position-1"}],
        "opportunities": {
            "opportunity_name": "Synthetic",
            "units": [
                {
                    "id": "unit",
                    "name": "Synthetic unit",
                    "facts": facts,
                    "positions": [
                        {"id": "position-0", "name": "A", "facts": facts},
                        {"id": "position-1", "name": "B", "facts": facts},
                    ],
                },
            ],
        },
        "facts": facts,
        "evidence_check_history": [],
        "rule_review": {"current": []},
        "report": "large report",
        "execution": {"raw": "private"},
    }
    result = select_workbench(view, "position-1", 5)
    assert result["workbench"]["total"] == 1263
    assert result["facts"] == [{"entity_id": "position-1", "field": "field-11"}]
    assert "facts" not in result["opportunities"]["units"][0]
    assert "facts" not in result["opportunities"]["units"][0]["positions"][0]
    assert "report" not in result


def test_rule_pending_count_uses_whole_object_not_visible_page() -> None:
    view = {
        "binding_entities": [{"id": "position"}],
        "opportunities": {},
        "facts": [],
        "evidence_check_history": [],
        "rule_review": {
            "current": [
                {
                    "entity_id": "position",
                    "rows": [
                        {"candidate_id": "a", "rule_candidate_id": "r1"},
                        {"candidate_id": "b", "rule_candidate_id": None},
                        {"candidate_id": "c", "rule_candidate_id": "r3"},
                    ],
                    "source_rows": [],
                    "decisions": {
                        "r1": {"decision": "APPROVE"},
                        "r3": {"decision": "NEEDS_ADJUDICATION"},
                    },
                }
            ],
        },
    }
    prep = select_workbench(view, "position", 0)["rule_review"]["current"][0]
    assert len(prep["rows"]) == 1
    assert prep["slice"] == {"offset": 0, "total": 3, "unresolved_total": 2}
