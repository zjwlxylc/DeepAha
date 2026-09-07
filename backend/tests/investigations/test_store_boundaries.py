"""Exercise persistence decisions with in-memory sessions, never a database."""

import asyncio
import copy
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from deepaha.artifacts.object_store import ObjectStore
from deepaha.investigations.contracts import CreateInvestigation, InvestigationError, digest
from deepaha.investigations.models import InvestigationTask
from deepaha.investigations.prompt import frozen_contract
from deepaha.investigations.runner import InvestigationClient, execute_investigation
from deepaha.investigations.store import InvestigationStore
from deepaha.investigations.wma import WmaSessionRef

TASK = UUID(int=101)
OWNER = UUID(int=102)
SOURCE = {"allowed_hosts": ["example.gov"]}


class SessionBoundary:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def __enter__(self) -> SessionBoundary:
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def begin(self) -> nullcontext[None]:
        return nullcontext()

    def scalar(self, statement: object) -> int:
        return len(self.events)

    def scalars(self, statement: object) -> list[Any]:
        return []

    def add(self, value: object) -> None:
        self.events.append(value)

    def flush(self) -> None:
        pass


class StoreBoundary(InvestigationStore):
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 7, tzinfo=UTC)
        self.session = SessionBoundary()
        command = CreateInvestigation(
            source_id=UUID(int=103),
            endpoint_id=UUID(int=104),
            notice_url="https://example.gov/notice",
            brief="Synthetic deadline boundary",
            wall_time_seconds=60,
        )
        contract = frozen_contract()
        self.task = InvestigationTask(
            task_id=TASK,
            source_id=command.source_id,
            endpoint_id=command.endpoint_id,
            created_by=UUID(int=105),
            request_key_hash="a" * 64,
            request_hash="b" * 64,
            request=command.model_dump(mode="json"),
            source_snapshot=copy.deepcopy(SOURCE),
            contract=contract,
            contract_hash=digest(contract),
            status="CREATING",
            execution={},
            runtime_id=None,
            remote_session_id=None,
            lease_owner=OWNER,
            deadline_at=self.now + timedelta(seconds=60),
            lease_until=self.now + timedelta(seconds=65),
            created_at=self.now,
            updated_at=self.now,
            result_objects={},
        )
        super().__init__(
            lambda: cast(Session, self.session), cast(ObjectStore, None), lambda: self.now
        )

    def _get(self, session: Session, task_id: UUID, *, lock: bool = False) -> InvestigationTask:
        assert task_id == TASK
        return self.task

    def _source(self, session: Session, command: CreateInvestigation) -> dict[str, Any]:
        return copy.deepcopy(SOURCE)


def test_view_timestamps_are_stable_across_database_session_timezones() -> None:
    store = StoreBoundary()
    first = store.get(TASK)
    local = timezone(timedelta(hours=8))
    store.task.created_at = store.task.created_at.astimezone(local)
    store.task.updated_at = store.task.updated_at.astimezone(local)
    assert store.task.deadline_at is not None
    store.task.deadline_at = store.task.deadline_at.astimezone(local)

    assert store.get(TASK) == first
    assert store.task.created_at.utcoffset() == timedelta(hours=8)
    assert not store.session.events


def test_legacy_view_recovers_notes_by_entity_and_field_without_rewriting_delivery() -> None:
    store = StoreBoundary()
    store.task.delivery_hash = "e" * 64
    store.task.delivery = {
        "facts": [
            {"entity_id": "a", "field": "degree", "value": "doctorate", "status": "CONFIRMED"},
            {"entity_id": "b", "field": "degree", "value": None, "status": "UNKNOWN"},
        ],
        "evidence": {
            "facts_flat": [
                {"entity_id": "a", "field": "degree", "note": "Candidate A exception."},
                {"entity_id": "b", "field": "degree", "note": "Candidate B missing evidence."},
            ]
        },
    }
    before = copy.deepcopy(store.task.delivery)
    result = store.get(TASK)
    assert [fact["note"] for fact in result["facts"]] == [
        "Candidate A exception.",
        "Candidate B missing evidence.",
    ]
    assert store.task.delivery == before
    assert result["delivery_hash"] == store.task.delivery_hash == "e" * 64
    assert not store.session.events


@pytest.mark.parametrize("note", [None, "Frozen candidate note."])
def test_view_preserves_explicit_frozen_note(note: str | None) -> None:
    store = StoreBoundary()
    store.task.delivery = {
        "facts": [{"entity_id": "a", "field": "degree", "note": note}],
        "evidence": {"facts_flat": [{"entity_id": "a", "field": "degree", "note": "Other"}]},
    }
    assert store.get(TASK)["facts"][0]["note"] == note


def test_expired_creation_checkpoint_keeps_ids_without_extending_execution() -> None:
    store = StoreBoundary()
    deadline, lease = store.task.deadline_at, store.task.lease_until
    store.now += timedelta(seconds=61)
    store.checkpoint_remote(TASK, OWNER, "runtime-1", None)
    store.checkpoint_remote(TASK, OWNER, "runtime-1", "session-1")
    assert (store.task.runtime_id, store.task.remote_session_id) == ("runtime-1", "session-1")
    assert (store.task.deadline_at, store.task.lease_until) == (deadline, lease)
    assert store.task.status == "CREATING" and store.task.lease_owner == OWNER
    with pytest.raises(InvestigationError, match="TASK_DEADLINE_EXCEEDED"):
        store.transition(TASK, OWNER, "PREPARING")


@pytest.mark.parametrize("fault", ["owner", "preparing", "uncertain", "runtime", "session"])
def test_checkpoint_refuses_stale_owner_wrong_state_and_replacement(fault: str) -> None:
    store = StoreBoundary()
    store.task.runtime_id, store.task.remote_session_id = "runtime-1", "session-1"
    owner = OWNER
    runtime, session = "runtime-1", "session-1"
    if fault == "owner":
        owner = UUID(int=999)
    elif fault == "preparing":
        store.task.status = "PREPARING"
    elif fault == "uncertain":
        store.task.status = "EXECUTION_UNCERTAIN"
    elif fault == "runtime":
        runtime = "replacement-runtime"
    else:
        session = "replacement-session"
    with pytest.raises(InvestigationError):
        store.checkpoint_remote(TASK, owner, runtime, session)
    assert (store.task.runtime_id, store.task.remote_session_id) == ("runtime-1", "session-1")


def test_checkpoint_replay_does_not_clear_session_or_append_events() -> None:
    store = StoreBoundary()
    store.checkpoint_remote(TASK, OWNER, "runtime-1", None)
    store.checkpoint_remote(TASK, OWNER, "runtime-1", "session-1")
    count = len(store.session.events)
    store.checkpoint_remote(TASK, OWNER, "runtime-1", None)
    store.checkpoint_remote(TASK, OWNER, "runtime-1", "session-1")
    assert store.task.remote_session_id == "session-1"
    assert len(store.session.events) == count


@pytest.mark.parametrize("expires_after", ["runtime", "session"])
def test_runner_stops_immediately_after_saving_expired_creation(expires_after: str) -> None:
    store = StoreBoundary()
    store.task.status = "QUEUED"
    store.task.lease_owner = store.task.lease_until = None
    continued = False

    class LateClient:
        async def create(self, task_key: str, *, checkpoint: Any) -> WmaSessionRef:
            nonlocal continued
            if expires_after == "runtime":
                store.now += timedelta(seconds=61)
            checkpoint("runtime-1", None)
            store.now += timedelta(seconds=61)
            checkpoint("runtime-1", "session-1")
            continued = True
            return WmaSessionRef("runtime-1", "session-1")

        async def aclose(self) -> None:
            pass

    with pytest.raises(TimeoutError):
        asyncio.run(execute_investigation(store, cast(InvestigationClient, LateClient()), TASK, {}))
    assert store.task.runtime_id == "runtime-1"
    assert store.task.remote_session_id == ("session-1" if expires_after == "session" else None)
    assert store.task.status == "EXECUTION_UNCERTAIN"
    assert not continued
    assert all(event.status != "PREPARING" for event in store.session.events)


def _recoverable(store: StoreBoundary, version: str = "direct-wma-intake/1") -> None:
    contract = copy.deepcopy(frozen_contract())
    contract["version"] = version
    contract["prompt_sha256"] = "c" * 64
    files = cast(dict[str, object], contract["files"])
    files["investigator-sop.md"] = "d" * 64
    store.task.contract = contract
    store.task.contract_hash = digest(contract)
    store.task.status = "COLLECTION_RETRYABLE"
    store.task.runtime_id, store.task.remote_session_id = "runtime-1", "session-1"
    store.task.lease_owner = store.task.lease_until = None
    store.task.execution = {"published_release": {"release_id": "original-release"}}


@pytest.mark.parametrize("version", ["direct-wma-intake/1", "direct-wma-intake/2"])
def test_recovery_accepts_supported_old_input_contract_with_unchanged_output_schema(
    version: str,
) -> None:
    store = StoreBoundary()
    _recoverable(store, version)
    original_contract = copy.deepcopy(store.task.contract)
    task = store.claim(TASK, OWNER, {"prompt_limit": 0}, recover=True)
    assert task["status"] == "COLLECTING"
    assert (task["runtime_id"], task["remote_session_id"]) == ("runtime-1", "session-1")
    assert store.task.contract == original_contract
    assert store.task.execution["published_release"] == {"release_id": "original-release"}


@pytest.mark.parametrize("fault", ["version", "scope", "schema", "missing_schema", "forged_hash"])
def test_recovery_rejects_unknown_or_unverifiable_contracts(fault: str) -> None:
    store = StoreBoundary()
    _recoverable(store)
    contract = store.task.contract
    if fault == "version":
        contract["version"] = "direct-wma-intake/999"
    elif fault == "scope":
        contract["scope"] = "OTHER_SCOPE"
    elif fault == "schema":
        cast(dict[str, object], contract["files"])["schemas/evidence.schema.json"] = "e" * 64
    elif fault == "missing_schema":
        cast(dict[str, object], contract["files"]).pop("schemas/opportunities.schema.json")
    else:
        contract["prompt_sha256"] = "f" * 64
    if fault != "forged_hash":
        store.task.contract_hash = digest(contract)
    with pytest.raises(InvestigationError, match="TASK_CONTRACT_CHANGED"):
        store.claim(TASK, OWNER, {}, recover=True)
    assert store.task.status == "COLLECTION_RETRYABLE"


def test_new_execution_still_requires_complete_current_contract() -> None:
    store = StoreBoundary()
    _recoverable(store)
    store.task.status = "QUEUED"
    store.task.runtime_id = store.task.remote_session_id = None
    with pytest.raises(InvestigationError, match="TASK_CONTRACT_CHANGED"):
        store.claim(TASK, OWNER, {})
