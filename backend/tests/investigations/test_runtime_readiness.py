import asyncio
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID

import pytest
from sqlalchemy import Engine

from deepaha.core.settings import Settings
from deepaha.investigations import runtime
from deepaha.investigations.runtime import heartbeat, worker_status

DATABASE_URL = "postgresql+psycopg://deepaha@127.0.0.1:55439/deepaha"


class _StopLoop(Exception):
    """Raised by the stubbed sleep to end a bounded run of an infinite loop."""


def test_heartbeat_is_scoped_to_database_and_expires(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    assert worker_status(tmp_path, "db-a", now)["state"] == "OFFLINE"
    heartbeat(tmp_path, "db-a", now)
    assert worker_status(tmp_path, "db-a", now)["state"] == "RUNNING"
    assert worker_status(tmp_path, "db-b", now)["state"] == "OFFLINE"
    assert worker_status(tmp_path, "db-a", now + timedelta(seconds=31))["state"] == "OFFLINE"
    assert "db-a" not in (tmp_path / "investigation-worker.json").read_text()


def _enabled_settings(root: Path) -> Settings:
    return Settings(
        environment="development",
        local_human_test_enabled=True,
        local_human_test_root=root,
        database_url=DATABASE_URL,
        local_human_test_bind_host="127.0.0.1",
    )


def _install_sleep(monkeypatch: pytest.MonkeyPatch, allowed: int) -> None:
    """Replace ``runtime.asyncio.sleep`` with a stopper that ends after N bodies."""
    state = {"count": 0}

    async def _sleep(seconds: float) -> None:
        state["count"] += 1
        if state["count"] > allowed:
            raise _StopLoop

    monkeypatch.setattr(runtime, "asyncio", types.SimpleNamespace(sleep=_sleep))


@pytest.mark.parametrize(
    "overrides",
    [
        {"environment": "production"},
        {"local_human_test_enabled": False},
        {"local_human_test_root": None},
        {"database_url": None},
    ],
)
def test_serve_refuses_any_incomplete_local_gate(tmp_path: Path, overrides: dict[str, Any]) -> None:
    settings = _enabled_settings(tmp_path).model_copy(update=overrides)
    with pytest.raises(RuntimeError, match="LOCAL_INVESTIGATION_RUNTIME_NOT_ENABLED"):
        asyncio.run(runtime.serve(settings))


def test_serve_runs_heartbeat_and_dispatch_then_disposes_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []

    async def _heartbeat(settings: Settings, engine: Engine) -> None:
        events.append("heartbeat")

    async def _dispatch(settings: Settings, engine: Engine) -> None:
        events.append("dispatch")

    class _Engine:
        def dispose(self) -> None:
            events.append("dispose")

    monkeypatch.setattr(runtime, "_heartbeat_loop", _heartbeat)
    monkeypatch.setattr(runtime, "_dispatch_loop", _dispatch)
    monkeypatch.setattr(runtime, "get_engine", lambda settings: _Engine())
    asyncio.run(runtime.serve(_enabled_settings(tmp_path)))
    assert {"heartbeat", "dispatch"}.issubset(set(events))
    assert events[-1] == "dispose"


class _DisposableEngine:
    def dispose(self) -> None:
        return None


def test_heartbeat_keeps_ticking_while_a_long_dispatch_is_in_flight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dispatch may await for minutes; liveness must not wait for it.

    The heartbeat loop here only stops once the dispatch has finished, so a
    sequential ``await heartbeat; await dispatch`` implementation would never
    reach the dispatch and would hang. ``wait_for`` turns that hang into a
    failure instead of stalling the suite.
    """
    ticks: list[int] = []
    finished: list[str] = []
    dispatch_done = asyncio.Event()

    async def _heartbeat(settings: Settings, engine: Engine) -> None:
        while not dispatch_done.is_set():
            ticks.append(len(ticks))
            await asyncio.sleep(0)

    async def _dispatch(settings: Settings, engine: Engine) -> None:
        await asyncio.sleep(0)
        finished.append("dispatch")
        dispatch_done.set()

    monkeypatch.setattr(runtime, "_heartbeat_loop", _heartbeat)
    monkeypatch.setattr(runtime, "_dispatch_loop", _dispatch)
    monkeypatch.setattr(runtime, "get_engine", lambda settings: cast(Engine, _DisposableEngine()))
    asyncio.run(asyncio.wait_for(runtime.serve(_enabled_settings(tmp_path)), timeout=5))
    assert finished == ["dispatch"]
    assert len(ticks) >= 2


class _Connection:
    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, *exc: object) -> Literal[False]:
        return False

    def execute(self, statement: object) -> None:
        return None


class _Engine:
    def __init__(self, *, reachable: bool) -> None:
        self.reachable = reachable

    def connect(self) -> _Connection:
        if not self.reachable:
            raise RuntimeError("synthetic database outage")
        return _Connection()


def test_heartbeat_loop_only_refreshes_liveness_when_database_is_reachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = _enabled_settings(tmp_path)
    _install_sleep(monkeypatch, allowed=1)
    with pytest.raises(_StopLoop):
        asyncio.run(runtime._heartbeat_loop(settings, cast(Engine, _Engine(reachable=True))))
    assert worker_status(tmp_path, DATABASE_URL, datetime.now(UTC))["state"] == "RUNNING"
    assert capsys.readouterr().out == ""

    offline_root = tmp_path / "offline"
    offline = _enabled_settings(offline_root)
    _install_sleep(monkeypatch, allowed=1)
    with pytest.raises(_StopLoop):
        asyncio.run(runtime._heartbeat_loop(offline, cast(Engine, _Engine(reachable=False))))
    assert not (offline_root / "investigation-worker.json").exists()
    assert "INVESTIGATION_RUNTIME_HEALTH_FAILED" in capsys.readouterr().out


class _ScriptedStore:
    def __init__(self, batches: list[list[dict[str, Any]]]) -> None:
        self.batches = batches
        self.index = 0
        self.listed = 0

    def clock(self) -> datetime:
        return datetime(2026, 9, 11, tzinfo=UTC)

    def list_dispatchable(self, now: datetime) -> list[dict[str, Any]]:
        self.listed += 1
        batch = self.batches[min(self.index, len(self.batches) - 1)]
        self.index += 1
        return batch


class _FakeConfig:
    def __init__(self, state: str) -> None:
        self.state = state

    def status(self) -> dict[str, Any]:
        return {"state": self.state}


def _install_dispatch_doubles(
    monkeypatch: pytest.MonkeyPatch,
    store: _ScriptedStore,
    config: _FakeConfig,
    dispatched: list[UUID],
) -> None:
    monkeypatch.setattr(runtime, "InvestigationStore", lambda factory, objects: store)
    monkeypatch.setattr(runtime, "LocalFileObjectStore", lambda **kwargs: None)
    monkeypatch.setattr(runtime, "LocalWmaConfigStore", lambda *args: config)
    monkeypatch.setattr(runtime, "WindowsDpapiProtector", lambda: None)
    monkeypatch.setattr(runtime, "WindowsDirectoryHardener", lambda: None)

    async def _dispatch(
        store_arg: object, config_arg: object, factory_arg: object, candidate: dict[str, Any]
    ) -> None:
        dispatched.append(candidate["task_id"])

    monkeypatch.setattr(runtime, "dispatch_candidate", _dispatch)


def test_dispatch_loop_ignores_candidates_without_a_pinned_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _ScriptedStore([[{"task_id": UUID(int=1), "kind": "NEW"}]])
    dispatched: list[UUID] = []
    _install_dispatch_doubles(monkeypatch, store, _FakeConfig("NOT_CONFIGURED"), dispatched)
    _install_sleep(monkeypatch, allowed=2)
    with pytest.raises(_StopLoop):
        asyncio.run(runtime._dispatch_loop(_enabled_settings(tmp_path), cast(Engine, object())))
    assert store.listed == 3
    assert dispatched == []


def test_dispatch_loop_runs_each_candidate_once_within_its_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = {
        "task_id": UUID(int=1),
        "kind": "NEW",
        "created_by": UUID(int=2),
        "dispatch_intent": {"configuration_revision": "revision", "intent_id": "intent"},
    }
    store = _ScriptedStore([[candidate], [candidate], [], [candidate]])
    dispatched: list[UUID] = []
    _install_dispatch_doubles(monkeypatch, store, _FakeConfig("CONNECTION_VERIFIED"), dispatched)
    _install_sleep(monkeypatch, allowed=4)
    with pytest.raises(_StopLoop):
        asyncio.run(runtime._dispatch_loop(_enabled_settings(tmp_path), cast(Engine, object())))
    # Not re-picked while it stays listed; re-picked only after it drops out and
    # reappears, which keeps ``attempted`` bounded.
    assert dispatched == [candidate["task_id"], candidate["task_id"]]


def test_worker_from_another_checkout_does_not_prove_this_checkout_ready(tmp_path: Path) -> None:
    import json

    now = datetime.now(UTC)
    heartbeat(tmp_path, DATABASE_URL, now)
    path = tmp_path / "investigation-worker.json"
    row = json.loads(path.read_text(encoding="utf-8"))
    row["codebase"] = "different-checkout"
    path.write_text(json.dumps(row), encoding="utf-8")
    assert worker_status(tmp_path, DATABASE_URL, now)["state"] == "OFFLINE"
