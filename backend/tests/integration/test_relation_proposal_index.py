"""Private navigation index is not an approval or qualification projection."""

from pathlib import Path
from typing import cast
from uuid import uuid7

import pytest
from fastapi import FastAPI

from deepaha.api.investigations import get_investigation_store
from deepaha.api.local_human_test import require_local_test_principal
from deepaha.investigations.relation_proposals import save_relation_proposal
from tests.api.test_investigations import make_client
from tests.integration.test_investigation_store import StoreHarness, harness
from tests.integration.test_relation_proposals import setup

__all__ = ["harness"]
pytestmark = pytest.mark.integration


def test_plan_index_reopens_saved_proposals(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    h = harness
    task, command = setup(h, monkeypatch)
    client, _ = make_client(tmp_path)
    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_investigation_store] = lambda: h.store
    app.dependency_overrides[require_local_test_principal] = lambda: h.principal
    base = f"/api/v1/local-human-test/investigations/{task}"
    url = f"{base}/unit-plans/{command.target_plan_id}/relation-proposals"
    with client:
        empty = client.get(url)
        assert empty.status_code == 200, empty.text
        assert empty.json() == {
            "task_id": str(task),
            "target_plan_id": str(command.target_plan_id),
            "proposals": [],
        }
        first = save_relation_proposal(h.store, task, command, h.principal, "first")
        second = save_relation_proposal(h.store, task, command, h.principal, "second")
        result = client.get(url)
        assert result.status_code == 200
        assert result.headers["cache-control"] == "private, no-store"
        rows = result.json()["proposals"]
        assert [r["proposal_id"] for r in rows] == [first["proposal_id"], second["proposal_id"]]
        assert set(rows[0]) == {"proposal_id", "producer_id", "created_at"}
        for row in rows:
            opened = client.get(
                f"/api/v1/local-human-test/investigations/{task}/relation-proposals/{row['proposal_id']}"
            )
            assert opened.status_code == 200
            assert opened.json()["review"]["status"] == "UNREVIEWED"
        assert client.get(url.replace(str(task), str(uuid7()))).status_code == 404
        assert client.get(url.replace(str(command.target_plan_id), str(uuid7()))).status_code == 404
