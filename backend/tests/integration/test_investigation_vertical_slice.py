"""Real database/API/runner with synthetic transport and synthetic review action."""

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from deepaha.api.investigations import get_investigation_store
from deepaha.api.local_human_test import require_local_test_principal
from deepaha.core.settings import Settings, get_settings
from deepaha.investigations.delivery import preflight_manifest
from deepaha.investigations.models import InvestigationTask
from deepaha.investigations.prompt import task_root
from deepaha.investigations.runner import execute_investigation
from deepaha.investigations.wma import WmaSessionRef
from deepaha.main import create_app
from tests.integration import test_investigation_store as store_support
from tests.integration.test_investigation_store import (
    StoreHarness,
    _files,
    _pending,
)

harness = store_support.harness
pytestmark = pytest.mark.integration


class SyntheticClient:
    def __init__(self, task_id: UUID) -> None:
        results, artifacts = _files(task_id)
        for name in ("opportunities.json", "evidence.json"):
            document = json.loads(results[name])
            fact = (
                document["units"][0]["positions"][0]["facts"][0]
                if name == "opportunities.json"
                else document["facts_flat"][0]
            )
            fact["note"] = "Synthetic candidate note; the issuer must clarify the exception."
            results[name] = json.dumps(document).encode()
        root = task_root(task_id)
        self.files = {f"{root}/result/{name}": data for name, data in results.items()}
        self.files.update(
            {f"{root}/{path}": artifacts[key] for key, path in preflight_manifest(results)}
        )
        self.prompt_count = 0
        self.upload_count = 0

    async def create(
        self, task_key: str, *, checkpoint: Callable[[str, str | None], None] | None = None
    ) -> WmaSessionRef:
        if checkpoint:
            checkpoint("synthetic-runtime", None)
            checkpoint("synthetic-runtime", "synthetic-session")
        return WmaSessionRef("synthetic-runtime", "synthetic-session")

    def binding_evidence(self) -> dict[str, object]:
        return {"session_binding": "SYNTHETIC_TEST"}

    async def resume(self, ref: WmaSessionRef) -> None:
        pass

    async def upload(self, remote_path: str, content: bytes) -> None:
        assert remote_path.startswith("/workspace/deepaha/") and content
        self.upload_count += 1

    async def prompt(self, text: str, timeout_seconds: float) -> str:
        assert timeout_seconds > 0
        self.prompt_count += 1
        return "end_turn"

    async def download(self, remote_path: str, max_bytes: int) -> bytes:
        value = self.files[remote_path]
        assert len(value) <= max_bytes
        return value

    async def aclose(self) -> None:
        pass


def test_register_execute_download_and_internal_review_through_real_api(
    harness: StoreHarness,
    tmp_path: Path,
) -> None:
    h = harness
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        local_human_test_enabled=True, local_human_test_root=tmp_path
    )
    app.dependency_overrides[get_investigation_store] = lambda: h.store
    app.dependency_overrides[require_local_test_principal] = lambda: h.principal
    base = "/api/v1/local-human-test/investigations"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        created = client.post(
            base,
            json=h.command.model_dump(mode="json"),
            headers={"Idempotency-Key": "synthetic-vertical"},
        )
        assert created.status_code == 201
        assert created.json()["status"] == "QUEUED"
        task_id = UUID(created.json()["task_id"])
        transport = SyntheticClient(task_id)
        asyncio.run(execute_investigation(h.store, transport, task_id, {"mode": "SYNTHETIC_TEST"}))
        detail = client.get(f"{base}/{task_id}").json()
        assert detail["status"] == "PENDING_REVIEW"
        assert len(detail["facts"]) > 0 and detail["materials"]
        assert detail["facts"][0]["note"] == (
            "Synthetic candidate note; the issuer must clarify the exception."
        )
        with h.factory() as session:
            frozen = session.get(InvestigationTask, task_id)
            assert frozen is not None
            assert (
                cast(dict[str, Any], frozen.delivery)["facts"][0]["note"]
                == (detail["facts"][0]["note"])
            )
        material = detail["materials"][0]
        response = client.get(f"{base}/{task_id}/materials/{material['artifact_id']}")
        _, originals = _files(task_id)
        assert response.content == originals[material["artifact_id"]]
        assert response.headers["content-disposition"].startswith("attachment;")
        assert response.headers["content-type"] == "application/octet-stream"
        prepared = client.post(
            f"{base}/{task_id}/documents", json={"delivery_hash": detail["delivery_hash"]}
        )
        assert prepared.status_code == 200
        assert prepared.json()["document_preparation"]["status"] == "PREPARED"
        assert prepared.json()["facts"] == detail["facts"]
        assert prepared.json()["review"] is None
        repeated = client.post(
            f"{base}/{task_id}/documents", json={"delivery_hash": detail["delivery_hash"]}
        )
        assert repeated.json() == prepared.json()
        reviewed = client.post(
            f"{base}/{task_id}/review",
            json={
                "decision": "APPROVE",
                "delivery_hash": detail["delivery_hash"],
                "reason": "Synthetic test action; not human qualification.",
            },
            headers={"Idempotency-Key": "synthetic-internal-review"},
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["status"] == "APPROVED"
        asyncio.run(execute_investigation(h.store, transport, task_id, {"mode": "SYNTHETIC_TEST"}))
        assert transport.prompt_count == 1
        assert transport.upload_count == 4


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE investigation_tasks SET request = '{}'::jsonb WHERE task_id = :id",
        "UPDATE investigation_tasks SET delivery = '{}'::jsonb WHERE task_id = :id",
        "UPDATE investigation_tasks SET result_objects = '{}'::jsonb WHERE task_id = :id",
        "DELETE FROM investigation_events WHERE task_id = :id",
        "DELETE FROM investigation_materials WHERE task_id = :id",
    ],
)
def test_database_rejects_rewriting_frozen_intake_evidence(
    harness: StoreHarness,
    mutation: str,
) -> None:
    task_id, _, _ = _pending(harness)
    with pytest.raises(DBAPIError), harness.factory.begin() as session:
        session.execute(text(mutation), {"id": task_id})
