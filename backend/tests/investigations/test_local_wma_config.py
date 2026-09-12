import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid7

import pytest
from pydantic import SecretStr, ValidationError

from deepaha.investigations.contracts import InvestigationError
from deepaha.investigations.local_config import LocalWmaConfigStore, SaveWmaConfig


def _saved_store(tmp_path: Path) -> LocalWmaConfigStore:
    """Return a store holding one saved revision, using fakes instead of real DPAPI."""
    protector = Mock()
    protector.protect.side_effect = lambda value: b"encrypted:" + value[::-1]
    protector.unprotect.side_effect = lambda value: value[len(b"encrypted:") :][::-1]
    store = LocalWmaConfigStore(tmp_path, protector, Mock())
    store.save(
        SaveWmaConfig(
            api_key=SecretStr("test-key"), agent_id="test-agent", source_app="cloud-agent"
        ),
        uuid7(),
    )
    return store


def _rewrite_checked_at(store: LocalWmaConfigStore, revision: str, checked_at: datetime) -> None:
    """Rewrite only ``checked_at`` of the recorded check, keeping the rest untouched."""
    check_path = store.root / f"{revision}.check.json"
    check: dict[str, object] = json.loads(check_path.read_text(encoding="utf-8"))
    check["checked_at"] = checked_at.isoformat()
    check_path.write_text(json.dumps(check), encoding="utf-8")


def test_status_reports_check_expired_after_fifteen_minutes(tmp_path: Path) -> None:
    store = _saved_store(tmp_path)
    revision, _ = store.load()
    store.record_check(revision, {"published_model": "server-model"}, None)
    assert store.status()["state"] == "CONNECTION_VERIFIED"
    _rewrite_checked_at(store, revision, datetime.now(UTC) - timedelta(minutes=16))
    status = store.status()
    assert status["state"] == "CHECK_EXPIRED"
    assert status["revision"] == revision


def test_status_reports_check_failed_for_a_recorded_error_code(tmp_path: Path) -> None:
    store = _saved_store(tmp_path)
    revision, _ = store.load()
    store.record_check(revision, None, "WMA_CONNECTION_CHECK_FAILED")
    status = store.status()
    assert status["state"] == "CHECK_FAILED"
    assert status["error_code"] == "WMA_CONNECTION_CHECK_FAILED"
    assert status["release"] is None


def test_status_reports_wma_check_unreadable_when_check_file_is_corrupt(tmp_path: Path) -> None:
    store = _saved_store(tmp_path)
    revision, _ = store.load()
    store.record_check(revision, {"published_model": "server-model"}, None)
    (store.root / f"{revision}.check.json").write_text("{not-json", encoding="utf-8")
    status = store.status()
    assert status["state"] == "CHECK_FAILED"
    assert status["error_code"] == "WMA_CHECK_UNREADABLE"
    assert status["revision"] == revision


def test_status_raises_wma_config_unreadable_when_revision_file_is_corrupt(tmp_path: Path) -> None:
    store = _saved_store(tmp_path)
    revision, _ = store.load()
    (store.root / f"{revision}.json").write_text("{not-json", encoding="utf-8")
    with pytest.raises(InvestigationError) as raised:
        store.status()
    assert raised.value.code == "WMA_CONFIG_UNREADABLE"


def test_saved_is_not_verified_and_replacement_invalidates_connection(tmp_path: Path) -> None:
    protector = Mock()
    protector.protect.side_effect = lambda value: b"encrypted:" + value[::-1]
    protector.unprotect.side_effect = lambda value: value[len(b"encrypted:") :][::-1]
    store = LocalWmaConfigStore(tmp_path, protector, Mock())
    assert store.status()["state"] == "NOT_CONFIGURED"
    command = SaveWmaConfig(
        api_key=SecretStr("test-key"), agent_id="test-agent", source_app="cloud-agent"
    )
    status = store.save(command, uuid7())
    assert status["state"] == "SAVED"
    assert "test-key" not in json.dumps(status)
    assert all("test-key" not in path.read_text() for path in tmp_path.rglob("*.json"))
    revision, binding = store.load()
    assert binding.api_key.get_secret_value() == "test-key"
    store.record_check(revision, {"published_model": "server-model"}, None)
    assert store.status()["state"] == "CONNECTION_VERIFIED"
    store.save(command, uuid7())
    store.record_check(revision, {"published_model": "stale-model"}, None)
    assert store.status()["state"] == "SAVED"


@pytest.mark.parametrize(
    "update", [{"model": "override"}, {"agent_id": ""}, {"api_key": "bad key"}]
)
def test_invalid_config_cannot_override_model(update: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        SaveWmaConfig.model_validate(
            {"api_key": "test-key", "agent_id": "test-agent", "source_app": "cloud-agent"} | update
        )


def test_inspection_failure_is_sanitized_and_client_closed(tmp_path: Path) -> None:
    from deepaha.investigations.local_config import inspect_configuration

    class Client:
        closed = False

        async def inspect_release(self) -> dict[str, object]:
            raise RuntimeError("secret-key and provider response")

        async def aclose(self) -> None:
            self.closed = True

    store = Mock()
    store.load.return_value = ("revision", object())
    client = Client()
    asyncio.run(inspect_configuration(store, lambda binding: client))
    store.record_check.assert_called_once_with("revision", None, "WMA_CONNECTION_CHECK_FAILED")
    assert client.closed


def test_loading_pinned_revision_does_not_follow_replacement(tmp_path: Path) -> None:
    store = _saved_store(tmp_path)
    revision, original = store.load()
    store.save(
        SaveWmaConfig(
            api_key=SecretStr("replacement-key"),
            agent_id="replacement-agent",
            source_app="other-app",
        ),
        uuid7(),
    )
    loaded_revision, binding = store.load(revision)
    assert loaded_revision == revision
    assert binding.agent_id == original.agent_id
    assert binding.source_app == original.source_app
    assert binding.api_key.get_secret_value() == original.api_key.get_secret_value()
    with pytest.raises(InvestigationError, match="WMA_CONFIG_UNREADABLE"):
        store.load("../current")
