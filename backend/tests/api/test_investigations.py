from pathlib import Path
from typing import Any
from unittest.mock import Mock
from uuid import uuid7

import pytest
from fastapi.testclient import TestClient

from deepaha.api.investigations import get_investigation_store
from deepaha.api.local_human_test import require_local_test_principal
from deepaha.core.settings import Settings, get_settings
from deepaha.investigations.contracts import InvestigationError
from deepaha.main import create_app
from deepaha.review.auth import ReviewerPrincipal, ReviewerRole


def make_client(
    tmp_path: Path, *, enabled: bool = True, roles: frozenset[ReviewerRole] | None = None
) -> tuple[TestClient, Mock]:
    app = create_app()
    store = Mock()
    app.dependency_overrides[get_settings] = lambda: Settings(
        local_human_test_enabled=enabled, local_human_test_root=tmp_path
    )
    app.dependency_overrides[get_investigation_store] = lambda: store
    app.dependency_overrides[require_local_test_principal] = lambda: ReviewerPrincipal(
        uuid7(),
        roles if roles is not None else frozenset({ReviewerRole.LOCAL_TEST_OPERATOR}),
        frozenset({"OPPORTUNITY_FACT_VALIDATION"}),
        True,
    )
    return TestClient(app, base_url="http://127.0.0.1"), store


@pytest.mark.parametrize("suffix", ["", "/sources", "/" + str(uuid7())])
def test_disabled_intake_stays_hidden(tmp_path: Path, suffix: str) -> None:
    client, store = make_client(tmp_path, enabled=False)
    with client:
        response = client.get("/api/v1/local-human-test/investigations" + suffix)
    assert response.status_code == 404
    assert not store.mock_calls


def test_unrelated_reviewer_cannot_read_intake(tmp_path: Path) -> None:
    client, store = make_client(tmp_path, roles=frozenset({ReviewerRole.FEEDBACK_REVIEWER}))
    with client:
        response = client.get("/api/v1/local-human-test/investigations")
    assert response.status_code == 403
    assert not store.mock_calls


def test_registration_requires_idempotency_and_never_dispatches(tmp_path: Path) -> None:
    client, store = make_client(tmp_path)
    payload: dict[str, Any] = {
        "source_id": str(uuid7()),
        "endpoint_id": str(uuid7()),
        "notice_url": "https://official.example/a",
        "brief": "公开调查",
    }
    store.create.return_value = uuid7()
    store.get.return_value = {"status": "QUEUED"}
    with client:
        missing = client.post("/api/v1/local-human-test/investigations", json=payload)
        created = client.post(
            "/api/v1/local-human-test/investigations",
            json=payload,
            headers={"Idempotency-Key": "synthetic-request"},
        )
    assert missing.status_code == 400
    assert created.status_code == 201
    assert created.json()["status"] == "QUEUED"
    assert created.headers["cache-control"] == "private, no-store"
    assert [call[0] for call in store.mock_calls] == ["create", "get"]


def test_domain_failure_only_exposes_stable_code(tmp_path: Path) -> None:
    client, store = make_client(tmp_path)
    store.get.side_effect = InvestigationError("INVESTIGATION_NOT_FOUND")
    with client:
        response = client.get(f"/api/v1/local-human-test/investigations/{uuid7()}")
    assert response.status_code == 404
    assert response.json() == {"detail": {"code": "INVESTIGATION_NOT_FOUND"}}


def test_review_must_supply_current_delivery_hash(tmp_path: Path) -> None:
    client, store = make_client(tmp_path)
    with client:
        response = client.post(
            f"/api/v1/local-human-test/investigations/{uuid7()}/review",
            json={"decision": "APPROVE", "reason": "Synthetic"},
            headers={"Idempotency-Key": "synthetic-review"},
        )
    assert response.status_code == 400
    assert not store.mock_calls


def test_document_preparation_requires_frozen_delivery_and_returns_private_receipt(
    tmp_path: Path,
) -> None:
    client, store = make_client(tmp_path)
    task_id = uuid7()
    store.prepare_documents.return_value = {
        "status": "PENDING_REVIEW",
        "document_preparation": {"status": "PREPARED"},
    }
    with client:
        missing = client.post(
            f"/api/v1/local-human-test/investigations/{task_id}/documents", json={}
        )
        result = client.post(
            f"/api/v1/local-human-test/investigations/{task_id}/documents",
            json={"delivery_hash": "a" * 64},
        )
    assert missing.status_code == 400
    assert result.status_code == 200
    assert result.json()["document_preparation"]["status"] == "PREPARED"
    assert result.headers["cache-control"] == "private, no-store"
    store.prepare_documents.assert_called_once()
    assert store.prepare_documents.call_args.args[:2] == (task_id, "a" * 64)


def test_disabled_document_preparation_cannot_parse(tmp_path: Path) -> None:
    client, store = make_client(tmp_path, enabled=False)
    with client:
        result = client.post(
            f"/api/v1/local-human-test/investigations/{uuid7()}/documents",
            json={"delivery_hash": "a" * 64},
        )
    assert result.status_code == 404
    assert not store.mock_calls
