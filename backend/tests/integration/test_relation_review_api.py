"""Synthetic reviewer identities exercising the real private API and database."""

import json
from pathlib import Path
from typing import cast
from uuid import UUID, uuid7

import pytest
from fastapi import FastAPI

from deepaha.api.investigations import get_investigation_store
from deepaha.api.local_human_test import require_local_test_principal
from deepaha.investigations.contracts import digest
from tests.api.test_investigations import make_client
from tests.integration.test_investigation_store import StoreHarness, _files, harness
from tests.integration.test_relation_decisions import request, reviewer
from tests.integration.test_relation_proposals import setup

__all__ = ["harness"]
pytestmark = pytest.mark.integration


@pytest.mark.parametrize("with_float", [False, True])
def test_private_relation_roundtrip(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, with_float: bool
) -> None:
    h = harness
    if with_float:

        def float_files(task_id: UUID) -> tuple[dict[str, bytes], dict[str, bytes]]:
            files, artifacts = _files(task_id)
            opportunities = json.loads(files["opportunities.json"])
            evidence = json.loads(files["evidence.json"])
            opportunities["units"][0]["unit_level"][1]["evidence"][0]["locator"]["weight"] = 1.0
            rows = [f for f in evidence["facts_flat"] if f["entity_id"] == "unit"]
            rows[1]["evidence"][0]["locator"]["weight"] = 1.0
            files["opportunities.json"] = json.dumps(opportunities).encode()
            files["evidence.json"] = json.dumps(evidence).encode()
            return files, artifacts

        monkeypatch.setattr("tests.integration.test_investigation_facts._files", float_files)
    task, proposal = setup(h, monkeypatch)
    client, _ = make_client(tmp_path)
    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_investigation_store] = lambda: h.store
    app.dependency_overrides[require_local_test_principal] = lambda: h.principal
    base = f"/api/v1/local-human-test/investigations/{task}"
    with client:
        body = proposal.model_dump(mode="json")
        assert client.post(f"{base}/relation-proposals", json=body).status_code == 400
        created = client.post(
            f"{base}/relation-proposals", json=body, headers={"Idempotency-Key": "proposal"}
        )
        assert created.status_code == 200, created.text
        saved = created.json()
        assert saved["payload_sha256"] == digest(saved["package"])
        url = f"{base}/relation-proposals/{saved['proposal_id']}"
        assert client.get(url).json() == saved
        decision_url = f"{base}/relation-decisions"
        command = request(saved).model_dump(mode="json")
        self_review = client.post(decision_url, json=command, headers={"Idempotency-Key": "self"})
        assert self_review.status_code == 403
        independent = reviewer(h)
        app.dependency_overrides[require_local_test_principal] = lambda: independent
        assert (
            client.post(
                decision_url,
                json=command | {"reviewer_id": str(uuid7())},
                headers={"Idempotency-Key": "spoof"},
            ).status_code
            == 400
        )
        first = client.post(decision_url, json=command, headers={"Idempotency-Key": "approve"})
        assert first.status_code == 200, first.text
        refreshed = client.get(url).json()
        assert refreshed["review"]["status"] == "APPROVED"
        assert refreshed["payload_sha256"] == digest(refreshed["package"])
        assert refreshed["proposal_payload_sha256"] == saved["payload_sha256"]
        revised = request(refreshed, first.json()["decision"]["decision_id"], "REJECT")
        second = client.post(
            decision_url,
            json=revised.model_dump(mode="json"),
            headers={"Idempotency-Key": "reject"},
        )
        assert second.status_code == 200, second.text
        retry = client.post(decision_url, json=command, headers={"Idempotency-Key": "approve"})
        assert retry.json()["decision"] == first.json()["decision"]
        assert retry.json()["review"]["status"] == "REJECTED"
        assert not retry.json()["review"]["executable"]
        assert retry.json()["review"]["overall_qualification"] == "UNCERTAIN"
        wrong_task = client.get(url.replace(str(task), str(uuid7())))
        missing = client.get(f"{base}/relation-proposals/{uuid7()}")
        for response in (created, first, second, retry, self_review, wrong_task, missing):
            assert response.headers["cache-control"] == "private, no-store"
        assert wrong_task.status_code == missing.status_code == 404
        (tmp_path / "relation-review-fixture.json").write_text(
            json.dumps(
                {
                    "task": str(task),
                    "plan": str(proposal.target_plan_id),
                    "saved": saved,
                    "approved": first.json(),
                    "rejected": second.json(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
