"""Bounded dispatch decisions: no database, no remote SDK, and never a re-prompt."""

import asyncio
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest
from pydantic import SecretStr

from deepaha.investigations import dispatch
from deepaha.investigations.contracts import InvestigationError
from deepaha.investigations.dispatch import ClientFactory, build_execution, should_clear_intent
from deepaha.investigations.local_config import LocalWmaConfigStore
from deepaha.investigations.store import InvestigationStore
from deepaha.investigations.wma import DirectWmaClient, DirectWmaError, WmaBinding

TASK_ID = UUID("019c0000-0000-7000-8000-000000000901")
CREATED_BY = UUID("019c0000-0000-7000-8000-000000000902")
BINDING = WmaBinding(SecretStr("synthetic-key"), "test-agent", "cloud-agent", "1.0")
INTENT_AT = datetime(2026, 9, 11, tzinfo=UTC)


class _FakeClient:
    async def inspect_release(self) -> dict[str, object]:
        return {}

    async def aclose(self) -> None:
        return None


class _FakeStore:
    """Bookkeeping boundary: records cancels without touching persistence."""

    def __init__(self, *, status: str = "QUEUED") -> None:
        self.status = status
        self.cancelled: list[tuple[UUID, str]] = []
        self.get_calls = 0

    def get(self, task_id: UUID) -> dict[str, Any]:
        self.get_calls += 1
        return {"task_id": str(task_id), "status": self.status}

    def finish_dispatch(self, task_id: UUID, intent_id: str, code: str | None = None) -> None:
        pass

    def cancel_dispatch(self, task_id: UUID, code: str) -> None:
        self.cancelled.append((task_id, code))


class _FakeConfig:
    def __init__(self, *, error: str | None = None) -> None:
        self.error = error
        self.loaded = 0

    def load(self, revision: str) -> tuple[str, WmaBinding]:
        self.loaded += 1
        if self.error is not None:
            raise InvestigationError(self.error)
        return "revision", BINDING


def _candidate(kind: str) -> dict[str, Any]:
    return {
        "dispatch_intent": {
            "configuration_revision": "revision",
            "operator_id": str(CREATED_BY),
            "intent_id": "intent",
        },
        "task_id": TASK_ID,
        "status": "QUEUED" if kind == "NEW" else "EXECUTION_UNCERTAIN",
        "created_by": CREATED_BY,
        "dispatch_requested_at": INTENT_AT,
        "kind": kind,
    }


def _fake_factory(binding: WmaBinding) -> DirectWmaClient:
    return cast(DirectWmaClient, _FakeClient())


def _failing_factory(binding: WmaBinding) -> DirectWmaClient:
    raise DirectWmaError("WMA_SDK_UNAVAILABLE")


def _run(
    store: _FakeStore,
    config: _FakeConfig,
    factory: ClientFactory,
    candidate: dict[str, Any],
) -> None:
    asyncio.run(
        dispatch.dispatch_candidate(
            cast(InvestigationStore, store),
            cast(LocalWmaConfigStore, config),
            factory,
            candidate,
        )
    )


def test_build_execution_carries_persistent_intent_and_bounds_prompts() -> None:
    live = build_execution(BINDING, TASK_ID, CREATED_BY, recover=False)
    assert live["mode"] == "LIVE" and live["provider"] == "WMA"
    assert live["operator_id"] == str(CREATED_BY)
    assert live["authorization_reference"] == f"persistent-dispatch:{TASK_ID}"
    assert live["agent_id"] == "test-agent" and live["source_app"] == "cloud-agent"
    assert live["prompt_limit"] == 1
    assert live["agent_release_evidence"] == "PENDING"
    assert live["agent_release_reference"] is None

    recovery = build_execution(BINDING, TASK_ID, CREATED_BY, recover=True)
    assert recovery["prompt_limit"] == 0  # recovery only downloads (#11)
    assert recovery["agent_release_evidence"] == "RECOVERY_ONLY"


@pytest.mark.parametrize(
    ("status", "kind", "expected"),
    [
        ("QUEUED", "NEW", True),
        ("QUEUED", "RECOVER", False),
        ("EXECUTION_UNCERTAIN", "NEW", False),
        ("COLLECTING", "RECOVER", False),
        ("PENDING_REVIEW", "NEW", False),
    ],
)
def test_should_clear_intent_only_for_still_queued_new(
    status: str, kind: str, expected: bool
) -> None:
    assert should_clear_intent(status, kind) is expected


def test_unreadable_configuration_skips_client_and_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, config = _FakeStore(), _FakeConfig(error="WMA_CONFIG_UNREADABLE")
    built: list[WmaBinding] = []
    executed: list[object] = []

    def _factory(binding: WmaBinding) -> DirectWmaClient:
        built.append(binding)
        return cast(DirectWmaClient, _FakeClient())

    async def _spy(*args: object, **kwargs: object) -> None:
        executed.append(args)

    monkeypatch.setattr(dispatch, "execute_registered", _spy)
    _run(store, config, _factory, _candidate("NEW"))
    assert built == [] and executed == [] and store.cancelled == []


def test_client_construction_failure_clears_new_intent_with_its_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeStore(status="QUEUED")
    executed: list[object] = []

    async def _spy(*args: object, **kwargs: object) -> None:
        executed.append(args)

    monkeypatch.setattr(dispatch, "execute_registered", _spy)
    _run(store, _FakeConfig(), _failing_factory, _candidate("NEW"))
    assert store.cancelled == [(TASK_ID, "WMA_SDK_UNAVAILABLE")]
    assert executed == []


def test_client_construction_failure_leaves_recovery_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeStore(status="EXECUTION_UNCERTAIN")
    executed: list[object] = []

    async def _spy(*args: object, **kwargs: object) -> None:
        executed.append(args)

    monkeypatch.setattr(dispatch, "execute_registered", _spy)
    _run(store, _FakeConfig(), _failing_factory, _candidate("RECOVER"))
    assert store.cancelled == []
    assert executed == []


def test_pre_claim_failure_clears_new_intent_with_persisted_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeStore(status="QUEUED")

    async def _failing(*args: object, **kwargs: object) -> None:
        raise InvestigationError("WMA_RELEASE_INSPECTION_FAILED")

    monkeypatch.setattr(dispatch, "execute_registered", _failing)
    _run(store, _FakeConfig(), _fake_factory, _candidate("NEW"))
    assert store.cancelled == [(TASK_ID, "WMA_RELEASE_INSPECTION_FAILED")]


def test_pre_claim_failure_without_a_code_uses_a_stable_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeStore(status="QUEUED")

    async def _failing(*args: object, **kwargs: object) -> None:
        raise RuntimeError("synthetic unexpected failure")

    monkeypatch.setattr(dispatch, "execute_registered", _failing)
    _run(store, _FakeConfig(), _fake_factory, _candidate("NEW"))
    assert store.cancelled == [(TASK_ID, "INVESTIGATION_DEPENDENCY_FAILED")]


def test_post_claim_failure_never_clears_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeStore(status="EXECUTION_UNCERTAIN")

    async def _failing(*args: object, **kwargs: object) -> None:
        raise DirectWmaError("WMA_PROMPT_FAILED")

    monkeypatch.setattr(dispatch, "execute_registered", _failing)
    _run(store, _FakeConfig(), _fake_factory, _candidate("NEW"))
    assert store.cancelled == []
    assert store.get_calls == 1


def test_recovery_failure_is_not_cleared_here(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _FakeStore(status="COLLECTION_RETRYABLE")

    async def _failing(*args: object, **kwargs: object) -> None:
        raise InvestigationError("TASK_NOT_RECOVERABLE")

    monkeypatch.setattr(dispatch, "execute_registered", _failing)
    _run(store, _FakeConfig(), _fake_factory, _candidate("RECOVER"))
    assert store.cancelled == []
    # The persisted outcome is still inspected, it just never clears anything.
    assert store.get_calls == 1


@pytest.mark.parametrize("kind", ["NEW", "RECOVER"])
def test_dispatch_passes_the_matching_recovery_mode(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    store = _FakeStore(status="QUEUED" if kind == "NEW" else "COLLECTING")
    seen: list[dict[str, object]] = []
    recover_flags: list[bool] = []

    async def _record(
        store_arg: object,
        client_arg: object,
        task_id: object,
        execution: dict[str, object],
        *,
        recover: bool = False,
    ) -> None:
        seen.append(execution)
        recover_flags.append(recover)

    monkeypatch.setattr(dispatch, "execute_registered", _record)
    _run(store, _FakeConfig(), _fake_factory, _candidate(kind))
    assert recover_flags == [kind == "RECOVER"]
    assert seen[0]["prompt_limit"] == (0 if kind == "RECOVER" else 1)
    assert seen[0]["authorization_reference"] == f"persistent-dispatch:{TASK_ID}"
    assert store.cancelled == []
