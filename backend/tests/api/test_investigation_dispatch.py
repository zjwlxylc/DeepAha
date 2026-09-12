from pathlib import Path
from typing import cast
from unittest.mock import Mock
from uuid import uuid7

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from deepaha.api.investigation_runtime import get_wma_config
from deepaha.api.investigations import get_investigation_store
from deepaha.api.local_human_test import require_local_test_principal
from deepaha.core.settings import Settings, get_settings
from deepaha.investigations.contracts import InvestigationError
from deepaha.main import create_app
from deepaha.review.auth import (
    OPPORTUNITY_FACT_VALIDATION_PURPOSE,
    ReviewerPrincipal,
    ReviewerRole,
)

DISPATCH_PATH = "/api/v1/local-human-test/investigation-runtime/tasks/{task_id}/dispatch"


def make_operator_client(
    tmp_path: Path,
    *,
    roles: frozenset[ReviewerRole] | None = None,
    synthetic: bool = False,
    enabled: bool = True,
) -> tuple[TestClient, Mock]:
    app = create_app()
    store = Mock()
    config = Mock()
    config.status.return_value = {"state": "CONNECTION_VERIFIED", "revision": str(uuid7())}
    app.dependency_overrides[get_wma_config] = lambda: config
    app.dependency_overrides[get_settings] = lambda: Settings(
        local_human_test_enabled=enabled, local_human_test_root=tmp_path
    )
    app.dependency_overrides[get_investigation_store] = lambda: store
    app.dependency_overrides[require_local_test_principal] = lambda: ReviewerPrincipal(
        uuid7(),
        roles if roles is not None else frozenset({ReviewerRole.LOCAL_TEST_OPERATOR}),
        frozenset({OPPORTUNITY_FACT_VALIDATION_PURPOSE}),
        synthetic,
    )
    return TestClient(
        app, base_url="http://127.0.0.1", headers={"idempotency-key": "dispatch-test"}
    ), store


def test_synthetic_operator_is_rejected_before_any_store_call(tmp_path: Path) -> None:
    client, store = make_operator_client(tmp_path, synthetic=True)
    with client:
        response = client.post(DISPATCH_PATH.format(task_id=uuid7()))
    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "REAL_OPERATOR_REQUIRED"}}
    assert not store.mock_calls


@pytest.mark.parametrize(
    ("roles", "code"),
    [
        (frozenset({ReviewerRole.VALIDATION_REVIEWER}), "REAL_OPERATOR_REQUIRED"),
        (frozenset({ReviewerRole.FEEDBACK_REVIEWER}), "INVESTIGATION_ROLE_REQUIRED"),
    ],
)
def test_non_operator_roles_cannot_request_dispatch(
    tmp_path: Path, roles: frozenset[ReviewerRole], code: str
) -> None:
    client, store = make_operator_client(tmp_path, roles=roles)
    with client:
        response = client.post(DISPATCH_PATH.format(task_id=uuid7()))
    assert response.status_code == 403
    assert response.json() == {"detail": {"code": code}}
    assert not store.mock_calls


def test_missing_session_is_not_public(tmp_path: Path) -> None:
    client, _ = make_operator_client(tmp_path)
    cast(FastAPI, client.app).dependency_overrides.pop(require_local_test_principal)
    with client:
        response = client.post(DISPATCH_PATH.format(task_id=uuid7()))
    assert response.status_code == 401


def test_disabled_intake_hides_dispatch(tmp_path: Path) -> None:
    client, store = make_operator_client(tmp_path, enabled=False)
    with client:
        response = client.post(DISPATCH_PATH.format(task_id=uuid7()))
    assert response.status_code == 404
    assert not store.mock_calls


def test_operator_receives_only_the_persisted_intent_view(tmp_path: Path) -> None:
    client, store = make_operator_client(tmp_path)
    task_id = uuid7()
    store.request_dispatch.return_value = {
        "task_id": str(task_id),
        "status": "QUEUED",
        "dispatch_requested_at": "2026-09-11T00:00:00+00:00",
    }
    with client:
        response = client.post(DISPATCH_PATH.format(task_id=task_id))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json()["status"] == "QUEUED"
    assert response.json()["dispatch_requested_at"] == "2026-09-11T00:00:00+00:00"
    assert store.request_dispatch.call_args.args[0] == task_id
    assert "api_key" not in response.text and "secret" not in response.text


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("INVESTIGATION_NOT_FOUND", 404),
        ("TASK_NOT_DISPATCHABLE", 409),
        ("TASK_ALREADY_RUNNING", 409),
        ("REAL_OPERATOR_REQUIRED", 403),
    ],
)
def test_domain_failure_exposes_only_a_stable_code(tmp_path: Path, code: str, status: int) -> None:
    client, store = make_operator_client(tmp_path)
    store.request_dispatch.side_effect = InvestigationError(code)
    with client:
        response = client.post(DISPATCH_PATH.format(task_id=uuid7()))
    assert response.status_code == status
    assert response.json() == {"detail": {"code": code}}
    assert response.headers["cache-control"] == "private, no-store"
