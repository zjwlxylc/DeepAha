from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock

import pytest
from fastapi import FastAPI

from deepaha.api import investigation_runtime as runtime_api
from deepaha.api.investigation_runtime import get_wma_config
from deepaha.investigations.contracts import InvestigationError
from deepaha.investigations.local_config import inspect_configuration
from deepaha.investigations.wma import DirectWmaError
from deepaha.review.auth import OPPORTUNITY_FACT_VALIDATION_PURPOSE, ReviewerRole
from tests.api.test_investigations import make_client

RUNTIME = "/api/v1/local-human-test/investigation-runtime"
CONFIGURATION = f"{RUNTIME}/configuration"
CHECK = f"{RUNTIME}/check"
PAYLOAD: dict[str, str] = {
    "api_key": "secret-value",
    "agent_id": "test-agent",
    "source_app": "cloud-agent",
}


def _override_config(client: Any, config: Mock) -> None:
    cast(FastAPI, client.app).dependency_overrides[get_wma_config] = lambda: config


@pytest.mark.parametrize(
    "roles",
    [frozenset({ReviewerRole.VALIDATION_REVIEWER}), frozenset({ReviewerRole.LOCAL_TEST_OPERATOR})],
)
def test_only_real_operator_can_save_wma_configuration(
    tmp_path: Path, roles: frozenset[ReviewerRole]
) -> None:
    client, _ = make_client(tmp_path, roles=roles)
    config = Mock()
    _override_config(client, config)
    with client:
        response = client.post(CONFIGURATION, json=PAYLOAD)
    assert response.status_code == 403
    assert not config.mock_calls
    assert "secret-value" not in response.text


@pytest.mark.parametrize(
    ("roles", "purposes", "expected_code"),
    [
        # Wrong role: the intake dependency admits the principal, then the
        # endpoint's own operator guard rejects it.
        (
            frozenset({ReviewerRole.VALIDATION_REVIEWER}),
            frozenset({OPPORTUNITY_FACT_VALIDATION_PURPOSE}),
            "REAL_OPERATOR_REQUIRED",
        ),
        # Right role but missing purpose: rejected earlier by the intake
        # dependency, so the code comes from that layer instead.
        (
            frozenset({ReviewerRole.LOCAL_TEST_OPERATOR}),
            frozenset(),
            "INVESTIGATION_ROLE_REQUIRED",
        ),
    ],
)
def test_real_operator_without_full_authority_is_denied(
    tmp_path: Path,
    roles: frozenset[ReviewerRole],
    purposes: frozenset[str],
    expected_code: str,
) -> None:
    client, _ = make_client(tmp_path, roles=roles, purposes=purposes, synthetic=False)
    config = Mock()
    _override_config(client, config)
    with client:
        response = client.post(CONFIGURATION, json=PAYLOAD)
    assert response.status_code == 403
    assert response.json() == {"detail": {"code": expected_code}}
    assert not config.mock_calls


def test_full_real_operator_can_save_wma_configuration(tmp_path: Path) -> None:
    client, _ = make_client(
        tmp_path,
        roles=frozenset({ReviewerRole.LOCAL_TEST_OPERATOR}),
        purposes=frozenset({OPPORTUNITY_FACT_VALIDATION_PURPOSE}),
        synthetic=False,
    )
    config = Mock()
    config.save.return_value = {
        "revision": "01a08f03-991f-7368-8d87-ca813a1b267b",
        "agent_id": "test-agent",
        "source_app": "cloud-agent",
        "state": "SAVED",
    }
    _override_config(client, config)
    with client:
        response = client.post(CONFIGURATION, json=PAYLOAD)
    assert response.status_code == 200
    assert response.json()["state"] == "SAVED"
    assert "api_key" not in response.text
    assert "secret-value" not in response.text
    config.save.assert_called_once()


class _ReleaseClient:
    def __init__(self, release: dict[str, object] | None = None, error: str | None = None) -> None:
        self._release = release
        self._error = error
        self.closed = False

    async def inspect_release(self) -> dict[str, object]:
        if self._error is not None:
            raise DirectWmaError(self._error)
        return self._release if self._release is not None else {}

    async def aclose(self) -> None:
        self.closed = True


def _operator_client(tmp_path: Path) -> Any:
    client, _ = make_client(
        tmp_path,
        roles=frozenset({ReviewerRole.LOCAL_TEST_OPERATOR}),
        purposes=frozenset({OPPORTUNITY_FACT_VALIDATION_PURPOSE}),
        synthetic=False,
    )
    return client


def _override_check(monkeypatch: pytest.MonkeyPatch, client: _ReleaseClient) -> None:
    monkeypatch.setattr(
        runtime_api,
        "inspect_configuration",
        partial(inspect_configuration, client_factory=lambda binding: client),
    )


def _check_store() -> Mock:
    """Mirror the real store: ``status()`` reflects the last ``record_check``."""
    store = Mock()
    store.load.return_value = ("rev-1", Mock())
    recorded: dict[str, Any] = {"state": "CONNECTION_VERIFIED", "revision": "rev-1"}

    def _record_check(revision: str, release: object, error: str | None) -> None:
        recorded["state"] = "CHECK_FAILED" if error else "CONNECTION_VERIFIED"
        recorded.pop("error_code", None)
        if error:
            recorded["error_code"] = error

    store.record_check.side_effect = _record_check
    store.status.side_effect = lambda: dict(recorded)
    return store


def test_check_reports_verified_when_release_inspection_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _operator_client(tmp_path)
    store = _check_store()
    _override_config(client, store)
    fake = _ReleaseClient(release={"published_model": "server-model"})
    _override_check(monkeypatch, fake)
    with client:
        response = client.post(CHECK)
    assert response.status_code == 200
    assert response.json()["state"] == "CONNECTION_VERIFIED"
    store.record_check.assert_called_once_with("rev-1", {"published_model": "server-model"}, None)
    assert fake.closed
    assert "api_key" not in response.text


def test_check_reports_stable_code_when_wma_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _operator_client(tmp_path)
    store = _check_store()
    _override_config(client, store)
    fake = _ReleaseClient(error="WMA_RELEASE_INSPECTION_FAILED")
    _override_check(monkeypatch, fake)
    with client:
        response = client.post(CHECK)
    assert response.status_code == 200
    store.record_check.assert_called_once_with("rev-1", None, "WMA_RELEASE_INSPECTION_FAILED")
    assert "WMA_RELEASE_INSPECTION_FAILED" in response.text


def test_wma_config_missing_session_is_not_public(tmp_path: Path) -> None:
    from deepaha.api.local_human_test import require_local_test_principal

    client, _ = make_client(tmp_path)
    cast(FastAPI, client.app).dependency_overrides.pop(require_local_test_principal)
    with client:
        response = client.get(RUNTIME)
    assert response.status_code == 401


def _sources_returning(count: int) -> Callable[[object, object, object], dict[str, list[object]]]:
    def _inner(store: object, principal: object, response: object) -> dict[str, list[object]]:
        return {"sources": [object() for _ in range(count)]}

    return _inner


def _worker_returning(state: str) -> Callable[[object, object, object], dict[str, Any]]:
    def _inner(root: object, database_url: object, now: object) -> dict[str, Any]:
        return {"state": state, "updated_at": None}

    return _inner


@pytest.mark.parametrize(
    ("worker_state", "wma_state", "source_count", "expected"),
    [
        ("RUNNING", "CONNECTION_VERIFIED", 2, True),
        ("OFFLINE", "CONNECTION_VERIFIED", 2, False),
        ("RUNNING", "SAVED", 2, False),
        ("RUNNING", "CONNECTION_VERIFIED", 0, False),
    ],
)
def test_dispatch_enabled_requires_running_worker_verified_wma_and_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    worker_state: str,
    wma_state: str,
    source_count: int,
    expected: bool,
) -> None:
    client, _ = make_client(tmp_path)
    config = Mock()
    config.status.return_value = {"state": wma_state}
    _override_config(client, config)
    monkeypatch.setattr(runtime_api, "list_sources", _sources_returning(source_count))
    monkeypatch.setattr(runtime_api, "worker_status", _worker_returning(worker_state))
    with client:
        response = client.get(RUNTIME)
    assert response.status_code == 200
    body = response.json()
    assert body["dispatch_enabled"] is expected
    assert body["source_count"] == source_count
    assert body["worker"]["state"] == worker_state
    assert "api_key" not in response.text


def test_readiness_reports_unreadable_config_without_leaking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = make_client(tmp_path)
    config = Mock()
    config.status.side_effect = InvestigationError("WMA_CONFIG_UNREADABLE")
    _override_config(client, config)
    monkeypatch.setattr(runtime_api, "list_sources", _sources_returning(1))
    monkeypatch.setattr(runtime_api, "worker_status", _worker_returning("RUNNING"))
    with client:
        response = client.get(RUNTIME)
    assert response.status_code == 200
    body = response.json()
    assert body["wma"] == {"state": "UNREADABLE", "error_code": "WMA_CONFIG_UNREADABLE"}
    assert body["dispatch_enabled"] is False
    assert str(tmp_path) not in response.text
    assert "Traceback" not in response.text
