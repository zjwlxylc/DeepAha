"""Synthetic object navigation: field decisions remain independent writes."""

import pytest

from deepaha.investigations.facts import prepare_facts
from tests.integration.test_investigation_facts import _ready
from tests.integration.test_investigation_store import StoreHarness, harness

__all__ = ["harness"]
pytestmark = pytest.mark.integration


@pytest.mark.parametrize("announcement", [False, True])
def test_workbench_requires_explicit_object_and_bounds_fields(
    harness: StoreHarness,
    announcement: bool,
) -> None:
    task_id, command = _ready(harness, announcement=announcement)
    prepare_facts(harness.store, task_id, command, harness.principal)
    full = harness.store.get(task_id)
    initial = harness.store.get_workbench(task_id)
    assert initial["facts"] == []
    assert initial["fact_review"]["current"]["rows"] == []
    entity = full["fact_review"]["current"]["rows"][0]["entity_id"]
    selected = harness.store.get_workbench(task_id, entity_id=entity)
    assert len(selected["fact_review"]["current"]["rows"]) == 1
    assert all(row["entity_id"] == entity for row in selected["facts"])
    assert "report" not in selected
    assert "execution" not in selected
    assert len(selected["facts"]) <= 1
    assert selected["fact_review"]["current"]["slice"]["can_promote"] is False
    with pytest.raises(ValueError):
        harness.store.get_workbench(task_id, entity_id="not-in-this-task")
    assert harness.store.get(task_id) == full
