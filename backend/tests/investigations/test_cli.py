import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from pydantic import SecretStr

from deepaha.core.settings import Settings
from deepaha.investigations.cli import WmaEnvironment, require_live_ready, require_local_ready
from deepaha.investigations.contracts import InvestigationError


@pytest.mark.parametrize("recover", [False, True])
def test_live_execution_records_provider_release_but_recovery_does_not_rebind(
    monkeypatch: pytest.MonkeyPatch, recover: bool
) -> None:
    from deepaha.investigations import cli

    calls: list[str] = []
    captured: list[dict[str, object]] = []

    class Client:
        async def inspect_release(self) -> dict[str, object]:
            calls.append("inspect")
            return {"source": "CONTROL_PLANE", "release_version": "v1"}

    async def execute(*args: Any, **kwargs: Any) -> None:
        calls.append("execute")
        captured.append(args[3])

    monkeypatch.setattr(cli, "execute_investigation", execute)
    asyncio.run(
        cli.execute_registered(
            None,  # type: ignore[arg-type]
            Client(),  # type: ignore[arg-type]
            UUID(int=1),
            {"authorization_reference": "test", "agent_release_evidence": "OPERATOR_DECLARED"},
            recover=recover,
        )
    )
    assert calls == (["execute"] if recover else ["inspect", "execute"])
    if not recover:
        assert captured[0]["agent_release_evidence"] == "CONTROL_PLANE"
        assert captured[0]["published_release"] == {
            "source": "CONTROL_PLANE",
            "release_version": "v1",
        }
    else:
        assert "published_release" not in captured[0]


def test_failed_release_inspection_closes_connection_without_claiming_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deepaha.investigations import cli

    calls: list[str] = []

    class Client:
        async def inspect_release(self) -> dict[str, object]:
            raise InvestigationError("SYNTHETIC_INSPECTION_FAILURE")

        async def aclose(self) -> None:
            calls.append("close")

    async def execute(*args: Any, **kwargs: Any) -> None:
        calls.append("execute")

    monkeypatch.setattr(cli, "execute_investigation", execute)
    with pytest.raises(InvestigationError, match="SYNTHETIC_INSPECTION_FAILURE"):
        asyncio.run(
            cli.execute_registered(
                None,  # type: ignore[arg-type]
                Client(),  # type: ignore[arg-type]
                UUID(int=1),
                {},
            )
        )
    assert calls == ["close"]


def test_live_start_requires_local_authority_before_cloud_binding(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    from deepaha.investigations import cli

    monkeypatch.setattr(
        cli,
        "Settings",
        lambda: Settings(local_human_test_enabled=True, local_human_test_root=tmp_path),
    )
    monkeypatch.setattr(
        cli,
        "WmaEnvironment",
        lambda: WmaEnvironment(
            live_enabled=True,
            reviewer_token=SecretStr("operator-secret"),
            api_key=SecretStr("api-secret"),
            agent_id="configured-agent",
            source_app="deepaha-test",
        ),
    )
    calls: list[str] = []

    def forbidden_database(*args: object) -> None:
        calls.append("database")
        raise AssertionError("must stop before claiming a task or creating a runtime")

    monkeypatch.setattr(cli, "get_engine", forbidden_database)
    monkeypatch.setattr(
        "sys.argv",
        [
            "investigations",
            "run",
            "00000000-0000-0000-0000-000000000001",
            "--authorization-reference",
            "user-authorized",
            "--agent-release-reference",
            "operator-declared-v1",
        ],
    )
    assert cli.main() == 1
    output = capsys.readouterr().out
    assert json.loads(output) == {"error_code": "INVESTIGATION_COMMAND_FAILED"}
    assert calls == ["database"]
    assert "secret" not in output


def test_preflight_exposes_binding_requirement_without_network_or_database(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from deepaha.investigations import cli

    monkeypatch.setattr("sys.argv", ["investigations", "preflight"])
    assert cli.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["published_binding_required"] is True
    assert "live_start_hold" not in result


@pytest.mark.parametrize("operation", ["show", "recover"])
def test_local_read_and_existing_runtime_recovery_reach_local_authority(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    operation: str,
) -> None:
    from deepaha.investigations import cli

    monkeypatch.setattr(
        cli,
        "Settings",
        lambda: Settings(local_human_test_enabled=True, local_human_test_root=tmp_path),
    )
    monkeypatch.setattr(
        cli, "WmaEnvironment", lambda: WmaEnvironment(reviewer_token=SecretStr("test-token"))
    )

    def database_boundary(*args: object) -> None:
        raise InvestigationError("LOCAL_DATABASE_BOUNDARY_REACHED")

    monkeypatch.setattr(cli, "get_engine", database_boundary)
    monkeypatch.setattr(
        "sys.argv", ["investigations", operation, "00000000-0000-0000-0000-000000000001"]
    )
    assert cli.main() == 1
    assert json.loads(capsys.readouterr().out) == {"error_code": "LOCAL_DATABASE_BOUNDARY_REACHED"}


def test_stored_task_can_be_read_with_local_auth_without_enabling_wma(tmp_path: Path) -> None:
    settings = Settings(local_human_test_enabled=True, local_human_test_root=tmp_path)
    config = WmaEnvironment(live_enabled=False, reviewer_token=SecretStr("synthetic-token"))
    require_local_ready(settings, config)
    with pytest.raises(InvestigationError, match="LIVE_WMA_PREFLIGHT_INCOMPLETE"):
        require_live_ready(settings, config)


@pytest.mark.parametrize("environment", ["production", "test"])
def test_live_entry_is_limited_to_explicit_local_development(
    tmp_path: Path,
    environment: str,
) -> None:
    settings = Settings(
        environment=environment, local_human_test_enabled=True, local_human_test_root=tmp_path
    )
    config = WmaEnvironment(
        live_enabled=True,
        reviewer_token=SecretStr("synthetic-token"),
        api_key=SecretStr("synthetic-key"),
        agent_id="test",
        source_app="test",
    )
    with pytest.raises(InvestigationError, match="LOCAL_WMA_PREFLIGHT_INCOMPLETE"):
        require_live_ready(settings, config)
