"""Current read-only queue uses real synthetic proposal and decision records."""

import json
from pathlib import Path
from typing import cast
from uuid import uuid7

import pytest
from fastapi import FastAPI

from deepaha.api.investigations import get_investigation_store
from deepaha.api.local_human_test import require_local_test_principal
from deepaha.investigations.group_applicability_decisions import (
    DecideGroupApplicability,
    save_group_applicability,
)
from deepaha.investigations.relation_decisions import save_relation_decision
from deepaha.investigations.relation_proposals import save_relation_proposal
from tests.api.test_investigations import make_client
from tests.integration.test_investigation_store import StoreHarness, harness
from tests.integration.test_relation_decisions import request, reviewer
from tests.integration.test_relation_proposals import setup

__all__ = ["harness"]
pytestmark = pytest.mark.integration


def test_queue_tracks_current_decisions_and_stale_source(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    h = harness
    task, command = setup(h, monkeypatch)
    client, _ = make_client(tmp_path)
    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_investigation_store] = lambda: h.store
    app.dependency_overrides[require_local_test_principal] = lambda: h.principal
    base = f"/api/v1/local-human-test/investigations/{task}/unit-plans/{command.target_plan_id}"
    url = f"{base}/relation-queue"
    with client:
        empty = client.get(url)
        assert empty.status_code == 200, empty.text
        assert empty.json()["proposals"] == []
        first = save_relation_proposal(h.store, task, command, h.principal, "first")
        second = save_relation_proposal(h.store, task, command, h.principal, "second")
        independent = reviewer(h)
        save_relation_decision(h.store, task, request(first), independent, "approve")
        queue = client.get(url)
        assert queue.status_code == 200, queue.text
        assert queue.headers["cache-control"] == "private, no-store"
        value = queue.json()
        assert [p["status"] for p in value["proposals"]] == ["APPROVED", "UNREVIEWED"]
        assert all(p["is_own_proposal"] for p in value["proposals"])
        assert value["executable"] is False and value["overall_qualification"] == "UNCERTAIN"
        assert value["proposals"][0]["condition_ids"] == list(command.condition_ids)
        assert value["proposals"][0]["reason"] == command.reason
        assert (
            client.get(url, params={"after": first["proposal_id"]}).json()["proposals"]
            == value["proposals"][1:]
        )
        assert client.get(url.replace(str(task), str(uuid7()))).status_code == 404
        assert client.get(url.replace(str(command.target_plan_id), str(uuid7()))).status_code == 404
        app.dependency_overrides[require_local_test_principal] = lambda: independent
        assert not any(p["is_own_proposal"] for p in client.get(url).json()["proposals"])
        group = second["package"]["proposal"]["source_review"]["dependencies"]["group"][
            "dependencies"
        ]["group_source"]
        latest = next(iter(group["applicability_histories"].values()))[-1]
        revised = DecideGroupApplicability.model_validate(
            latest["request"]
            | {"previous_decision_id": latest["decision_id"], "outcome": "DOES_NOT_APPLY"}
        )
        save_group_applicability(h.store, task, revised, h.principal, "exclude")
        stale = client.get(url).json()
        assert [p["status"] for p in stale["proposals"]] == ["STALE", "STALE"]
        assert stale["source_review_hash"] != value["source_review_hash"]
        (tmp_path / "relation-queue-fixture.json").write_text(
            json.dumps({"current": value, "stale": stale}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
