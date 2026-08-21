import json
from pathlib import Path
from uuid import UUID

import pytest

import deepaha.sources.cli as cli

ENDPOINT_ID = UUID("0198d239-4b00-7000-8000-000000000403")


def test_collect_requires_explicit_live_permission(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DEEPAHA_ALLOW_LIVE_SOURCE_CHECK", raising=False)

    assert cli.main(["collect", "--endpoint-id", str(ENDPOINT_ID)]) == 2
    output = capsys.readouterr().out
    assert json.loads(output)["error_code"] == "LIVE_SOURCE_CHECK_NOT_ALLOWED"


def test_collect_manifest_requires_explicit_live_permission(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DEEPAHA_ALLOW_LIVE_SOURCE_CHECK", raising=False)

    assert cli.main(["collect-manifest", "--path", "registry.json"]) == 2
    assert "LIVE_SOURCE_CHECK_NOT_ALLOWED" in capsys.readouterr().out


def test_import_registry_does_not_require_live_permission(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DEEPAHA_ALLOW_LIVE_SOURCE_CHECK", raising=False)
    called: list[Path] = []

    def fake_import(path: Path) -> dict[str, object]:
        called.append(path)
        return {"created_sources": 1, "created_endpoints": 10}

    monkeypatch.setattr(cli, "_command_import_registry", fake_import)

    assert cli.main(["import-registry", "--path", "registry.json"]) == 0
    assert called == [Path("registry.json")]
    assert json.loads(capsys.readouterr().out)["created_endpoints"] == 10


def test_health_does_not_require_live_permission(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DEEPAHA_ALLOW_LIVE_SOURCE_CHECK", raising=False)
    called: list[UUID] = []

    def fake_health(endpoint_id: UUID, as_of: str | None) -> dict[str, object]:
        called.append(endpoint_id)
        assert as_of is None
        return {"endpoint_id": str(endpoint_id), "attempts_24h": 0}

    monkeypatch.setattr(cli, "_command_health", fake_health)

    assert cli.main(["health", "--endpoint-id", str(ENDPOINT_ID)]) == 0
    assert called == [ENDPOINT_ID]
    assert json.loads(capsys.readouterr().out)["attempts_24h"] == 0


def test_collect_output_never_contains_credentials_or_body(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DEEPAHA_ALLOW_LIVE_SOURCE_CHECK", "true")
    monkeypatch.setenv("DEEPAHA_OBJECT_STORE_SECRET_KEY", "super-secret-value")

    def fake_collect(endpoint_id: UUID) -> dict[str, object]:
        return {
            "endpoint_id": str(endpoint_id),
            "attempts": [{"outcome": "SUCCEEDED", "http_status": 200}],
        }

    monkeypatch.setattr(cli, "_command_collect", fake_collect)

    assert cli.main(["collect", "--endpoint-id", str(ENDPOINT_ID)]) == 0
    output = capsys.readouterr().out
    assert "super-secret-value" not in output
    assert "official response body" not in output
    assert set(json.loads(output)["attempts"][0]) == {"outcome", "http_status"}


@pytest.mark.parametrize("value", ["false", "0", "no"])
def test_false_live_permission_values_do_not_authorize_collection(
    value: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPAHA_ALLOW_LIVE_SOURCE_CHECK", value)

    assert cli.main(["collect", "--endpoint-id", str(ENDPOINT_ID)]) == 2
