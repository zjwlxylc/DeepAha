"""Synthetic queue traversal; no human acceptance claims."""

import json
from datetime import timedelta

import pytest
from sqlalchemy import event

from deepaha.investigations.queue_query import QueueQuery, read_queue
from tests.integration.test_investigation_store import StoreHarness, harness

__all__ = ["harness"]
pytestmark = pytest.mark.integration


@pytest.mark.parametrize("count", [101, 250])
def test_complete_stable_summary_traversal(harness: StoreHarness, count: int) -> None:
    ids = [
        harness.store.create(harness.command, harness.principal, f"queue-{i}") for i in range(count)
    ]
    seen: list[str] = []
    cursor = None
    while True:
        statements = []
        engine = harness.factory.kw["bind"]

        def capture(*args: object) -> None:
            statements.append(args[2])

        event.listen(engine, "before_cursor_execute", capture)
        try:
            page = read_queue(harness.store, QueueQuery(cursor=cursor))
        finally:
            event.remove(engine, "before_cursor_execute", capture)
        assert len(statements) == 1
        for row in page["tasks"]:
            assert not {"facts", "delivery", "materials", "report", "execution"} & row.keys()
            assert row["material_count"] == 0
        seen.extend(row["task_id"] for row in page["tasks"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == [str(value) for value in sorted(ids, reverse=True)]


def test_filter_boundaries(harness: StoreHarness) -> None:
    for i in range(3):
        harness.store.create(harness.command, harness.principal, f"filter-{i}")
    page = read_queue(harness.store, QueueQuery(limit=1))
    with pytest.raises(ValueError):
        read_queue(harness.store, QueueQuery(cursor=page["next_cursor"], q="changed"))
    assert read_queue(harness.store, QueueQuery(q="no-match"))["tasks"] == []
    assert read_queue(harness.store, QueueQuery(status="EXPIRED"))["tasks"] == []


def test_insert_after_first_page_and_measure(harness: StoreHarness) -> None:
    ids = [
        harness.store.create(harness.command, harness.principal, f"measure-{i}") for i in range(3)
    ]
    first = read_queue(harness.store, QueueQuery(limit=1))
    harness.clock.value += timedelta(seconds=1)
    later = harness.store.create(harness.command, harness.principal, "later")
    rest = read_queue(harness.store, QueueQuery(cursor=first["next_cursor"]))
    assert [row["task_id"] for row in rest["tasks"]] == [
        str(x) for x in sorted(ids, reverse=True)[1:]
    ]
    assert str(later) not in [row["task_id"] for row in rest["tasks"]]
    assert (
        len(read_queue(harness.store, QueueQuery(source=harness.command.source_id))["tasks"]) == 4
    )
    new = read_queue(harness.store, QueueQuery())
    old = {"tasks": harness.store.list_tasks()}
    print(
        f"synthetic queued tasks=4 summary_bytes={len(json.dumps(new).encode())} "
        f"legacy_bytes={len(json.dumps(old).encode())}"
    )
