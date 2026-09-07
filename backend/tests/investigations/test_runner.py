import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from threading import Event
from typing import Any, cast
from uuid import UUID

import pytest

from deepaha.investigations import runner
from deepaha.investigations.contracts import RESULT_NAMES, CreateInvestigation, InvestigationError
from deepaha.investigations.delivery import DeliveryValidationError, ValidatedDelivery
from deepaha.investigations.prompt import task_root
from deepaha.investigations.store import InvestigationStore
from deepaha.investigations.wma import DirectWmaError, WmaSessionRef

TASK_ID = UUID("019c0000-0000-7000-8000-000000000201")
REMOTE = WmaSessionRef("synthetic-runtime", "synthetic-session")
ROOT = task_root(TASK_ID)
ORIGINAL = b"\x00\xff\x80synthetic-original\r\n"
VALIDATED = ValidatedDelivery({}, {}, "Synthetic report", (), (), (), "a" * 64)


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 7, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class StateStore:
    """Stateful persistence boundary; no database or remote operations."""

    def __init__(self, *, budget: float = 10.0) -> None:
        self.clock = Clock()
        self.budget = budget
        self.events: list[str] = []
        self.owner: UUID | None = None
        self.frozen: dict[str, str] | None = None
        self.failure: tuple[str, str] | None = None
        self.finished: ValidatedDelivery | None = None
        command = CreateInvestigation(
            source_id=UUID("019c0000-0000-7000-8000-000000000202"),
            endpoint_id=UUID("019c0000-0000-7000-8000-000000000203"),
            notice_url="https://example.gov/notice",
            brief="Synthetic investigation for runner boundary tests",
        )
        self.task: dict[str, Any] = command.model_dump(mode="json") | {
            "status": "QUEUED",
            "runtime_id": None,
            "remote_session_id": None,
            "source_snapshot": {"allowed_hosts": ["example.gov"]},
        }

    def claim(
        self, task_id: UUID, owner: UUID, execution: dict[str, object], *, recover: bool = False
    ) -> dict[str, Any]:
        assert task_id == TASK_ID
        self.events.append("claim:recover" if recover else "claim:create")
        if self.task["status"] in ("PENDING_REVIEW", "APPROVED", "REJECTED"):
            return dict(self.task)
        if recover:
            assert self.task["runtime_id"] and self.task["remote_session_id"]
        else:
            assert self.task["status"] == "QUEUED"
        self.owner = owner
        self.task["status"] = "COLLECTING" if recover else "CREATING"
        self.task["deadline_at"] = (self.clock() + timedelta(seconds=self.budget)).isoformat()
        return dict(self.task)

    def transition(
        self,
        task_id: UUID,
        owner: UUID,
        status: str,
        remote: tuple[str, str | None] | None = None,
    ) -> None:
        self._owned(task_id, owner)
        if remote is not None:
            self.task["runtime_id"], self.task["remote_session_id"] = remote
        self.task["status"] = status
        self.events.append(f"persist:{status}")

    def checkpoint_remote(
        self, task_id: UUID, owner: UUID, runtime_id: str, session_id: str | None
    ) -> None:
        assert task_id == TASK_ID and owner == self.owner and self.task["status"] == "CREATING"
        self.task["runtime_id"] = runtime_id
        if session_id is not None:
            self.task["remote_session_id"] = session_id
        self.events.append("persist:CREATING")

    def record_binding(self, task_id: UUID, owner: UUID, evidence: dict[str, object]) -> None:
        self._owned(task_id, owner)
        self.task["binding"] = evidence
        self.events.append("persist:binding")

    def freeze_manifest(self, task_id: UUID, owner: UUID, files: dict[str, bytes]) -> None:
        self._owned(task_id, owner)
        fingerprints = {name: sha256(content).hexdigest() for name, content in files.items()}
        if self.frozen is not None and fingerprints != self.frozen:
            raise InvestigationError("RECOVERED_MANIFEST_CHANGED")
        self.frozen = fingerprints
        self.events.append("freeze_manifest")

    def finish(
        self,
        task_id: UUID,
        owner: UUID,
        validated: ValidatedDelivery,
        files: dict[str, bytes],
    ) -> None:
        self._owned(task_id, owner)
        assert set(files) == set(RESULT_NAMES)
        self.finished = validated
        self.task["status"] = "PENDING_REVIEW"
        self.events.append("finish")

    def fail(self, task_id: UUID, owner: UUID, status: str, code: str) -> None:
        assert task_id == TASK_ID and owner == self.owner
        self.failure = status, code
        self.task["status"] = status
        self.events.append(f"fail:{status}")

    def _owned(self, task_id: UUID, owner: UUID) -> None:
        assert task_id == TASK_ID and owner == self.owner
        if self.clock() >= datetime.fromisoformat(self.task["deadline_at"]):
            raise InvestigationError("TASK_DEADLINE_EXCEEDED")


def _result_files() -> dict[str, bytes]:
    # Preflight uses the real JSON schemas and path checks; semantic validation is
    # independently tested in test_delivery and replaced at that boundary here.
    opportunities = {
        "opportunity_name": "Synthetic notice",
        "publish_unit": "Synthetic issuer",
        "opportunity_type": "recruitment",
        "announcement_level": [],
        "units": [],
    }
    evidence = {
        "artifacts": [
            {
                "artifact_id": "notice",
                "source_url": "https://example.gov/notice",
                "local_path": "artifacts/notice.bin",
                "remote_path": f"{ROOT}/artifacts/notice.bin",
                "file_name": "notice.bin",
                "media_type": "application/octet-stream",
                "sha256": sha256(ORIGINAL).hexdigest(),
            }
        ],
        "entities": [],
        "facts_flat": [],
    }
    return {
        "opportunities.json": json.dumps(opportunities).encode(),
        "evidence.json": json.dumps(evidence).encode(),
        "report.md": b"# Synthetic report",
    }


class Client:
    def __init__(self, store: StateStore) -> None:
        self.store = store
        self.files = {f"{ROOT}/result/{name}": data for name, data in _result_files().items()}
        self.files[f"{ROOT}/artifacts/notice.bin"] = ORIGINAL
        self.errors: dict[str, BaseException] = {}
        self.delays: dict[str, float] = {}
        self.advances: dict[str, float] = {}
        self.reason = "end_turn"
        self.prompt_timeouts: list[float] = []
        self.downloads: list[str] = []
        self.close_error: BaseException | None = None

    async def _step(self, stage: str) -> None:
        self.store.events.append(stage)
        if stage in self.advances:
            self.store.clock.advance(self.advances.pop(stage))
        if stage in self.delays:
            await asyncio.sleep(self.delays.pop(stage))
        if stage in self.errors:
            raise self.errors.pop(stage)

    async def create(
        self, task_key: str, *, checkpoint: Callable[[str, str | None], None] | None = None
    ) -> WmaSessionRef:
        assert task_key == str(TASK_ID)
        await self._step("create")
        if checkpoint:
            checkpoint(REMOTE.runtime_id, None)
        await self._step("bind_session")
        if checkpoint:
            checkpoint(REMOTE.runtime_id, REMOTE.session_id)
        await self._step("verify_binding")
        return REMOTE

    def binding_evidence(self) -> dict[str, object]:
        return {"session_binding": "SYNTHETIC_TEST"}

    async def resume(self, ref: WmaSessionRef) -> None:
        assert ref == REMOTE
        await self._step("resume")

    async def upload(self, remote_path: str, content: bytes) -> None:
        assert remote_path.startswith(f"{ROOT}/") and isinstance(content, bytes)
        await self._step("upload")

    async def prompt(self, text: str, timeout_seconds: float) -> str:
        assert text
        self.prompt_timeouts.append(timeout_seconds)
        await self._step("prompt")
        return self.reason

    async def download(self, remote_path: str, max_bytes: int) -> bytes:
        self.downloads.append(remote_path)
        await self._step("download")
        await self._step(f"download:{remote_path}")
        if remote_path not in self.files:
            raise DirectWmaError("WMA_ARTIFACT_NOT_FOUND")
        assert len(self.files[remote_path]) <= max_bytes
        return self.files[remote_path]

    async def aclose(self) -> None:
        self.store.events.append("close")
        if self.close_error is not None:
            raise self.close_error


@pytest.fixture(autouse=True)
def validation_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    def validate(files: dict[str, bytes], originals: dict[str, bytes]) -> ValidatedDelivery:
        assert files == _result_files()
        assert originals == {"notice": ORIGINAL}
        return VALIDATED

    monkeypatch.setattr(runner, "validate_delivery", validate)


def _run(store: StateStore, client: Client, *, recover: bool = False) -> None:
    asyncio.run(
        runner.execute_investigation(
            cast(InvestigationStore, store), client, TASK_ID, {}, recover=recover
        )
    )


def test_first_upload_failure_never_starts_investigation() -> None:
    store = StateStore()
    client = Client(store)
    client.errors["upload"] = DirectWmaError("WMA_UPLOAD_FAILED")
    with pytest.raises(DirectWmaError, match="WMA_UPLOAD_FAILED"):
        _run(store, client)
    assert store.failure == ("FAILED_PREPARATION", "WMA_UPLOAD_FAILED")
    assert store.events.count("upload") == 1
    assert "prompt" not in store.events and client.downloads == []
    assert store.task["runtime_id"] == REMOTE.runtime_id
    assert store.finished is None and store.events[-1] == "close"


@pytest.mark.parametrize("failure_stage", ["bind_session", "verify_binding"])
def test_partial_remote_creation_is_saved_even_when_agent_binding_fails(failure_stage: str) -> None:
    store = StateStore()
    client = Client(store)
    client.errors[failure_stage] = DirectWmaError("WMA_PUBLISHED_BINDING_MISMATCH")
    with pytest.raises(DirectWmaError, match="WMA_PUBLISHED_BINDING_MISMATCH"):
        _run(store, client)
    assert store.task["runtime_id"] == REMOTE.runtime_id
    assert store.task["remote_session_id"] == (
        REMOTE.session_id if failure_stage == "verify_binding" else None
    )
    assert not {"upload", "prompt", "download"}.intersection(store.events)


def test_binding_evidence_is_persisted_before_any_investigation_input() -> None:
    store = StateStore()
    client = Client(store)
    _run(store, client)
    assert store.task["binding"]["session_binding"] == "SYNTHETIC_TEST"
    assert store.task["binding"]["input_prepared_at"]
    assert store.events.index("persist:binding") < store.events.index("upload")


@pytest.mark.parametrize(
    ("reason", "code"),
    [
        ("max_tokens", "WMA_OUTPUT_LIMIT_REACHED"),
        ("max_turn_requests", "WMA_REQUEST_LIMIT_REACHED"),
        ("refusal", "WMA_REMOTE_REFUSED"),
        ("cancelled", "WMA_REMOTE_CANCELLED"),
        ("", "WMA_NON_SUCCESS_STOP"),
        ("END_TURN", "WMA_NON_SUCCESS_STOP"),
    ],
)
def test_non_end_turn_retains_reason_without_collection_or_retry(reason: str, code: str) -> None:
    store = StateStore()
    client = Client(store)
    client.reason = reason
    with pytest.raises(InvestigationError, match=code):
        _run(store, client)
    assert store.failure == ("EXECUTION_UNCERTAIN", code)
    assert store.finished is None and client.downloads == []
    assert store.events.count("prompt") == 1
    assert store.task["runtime_id"] == REMOTE.runtime_id
    assert store.task["remote_session_id"] == REMOTE.session_id


def test_remote_reference_is_persisted_before_upload_and_prompt() -> None:
    store = StateStore()
    client = Client(store)
    client.advances = {"create": 1.0, "upload": 2.0}
    _run(store, client)
    assert store.events.index("persist:PREPARING") < store.events.index("upload")
    assert store.events.index("persist:PREPARING") < store.events.index("prompt")
    assert store.task["runtime_id"] == REMOTE.runtime_id
    assert store.task["remote_session_id"] == REMOTE.session_id
    assert client.prompt_timeouts == [7.0]
    assert store.finished is VALIDATED
    original_event = f"download:{ROOT}/artifacts/notice.bin"
    assert store.events.index("freeze_manifest") < store.events.index(original_event)


@pytest.mark.parametrize(
    ("stage", "status"),
    [
        ("create", "EXECUTION_UNCERTAIN"),
        ("upload", "EXPIRED"),
        ("prompt", "EXECUTION_UNCERTAIN"),
        ("download", "COLLECTION_RETRYABLE"),
    ],
)
def test_total_deadline_can_expire_in_every_remote_stage(stage: str, status: str) -> None:
    store = StateStore(budget=0.025)
    client = Client(store)
    client.delays[stage] = 0.1
    with pytest.raises(TimeoutError):
        _run(store, client)
    assert store.failure == (status, "TASK_DEADLINE_OR_CANCELLED")
    assert stage in store.events and store.finished is None
    assert store.events[-1] == "close"


def test_one_deadline_is_shared_across_create_upload_prompt_and_download() -> None:
    store = StateStore(budget=0.16)
    client = Client(store)
    # Each call fits individually; their sum cannot fit the one overall deadline.
    client.delays = {"create": 0.045, "upload": 0.045, "prompt": 0.045, "download": 0.045}
    with pytest.raises(TimeoutError):
        _run(store, client)
    assert store.finished is None
    assert store.failure is not None and store.failure[1] == "TASK_DEADLINE_OR_CANCELLED"
    assert store.events.count("create") == 1 and store.events.count("prompt") <= 1


def test_timed_out_validation_cannot_commit_when_background_work_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = Event()

    def slow_validation(files: dict[str, bytes], originals: dict[str, bytes]) -> ValidatedDelivery:
        completed.wait(timeout=0.08)
        completed.set()
        return VALIDATED

    monkeypatch.setattr(runner, "validate_delivery", slow_validation)
    store = StateStore(budget=0.025)
    client = Client(store)
    with pytest.raises(TimeoutError):
        _run(store, client)
    # asyncio.run waits for executor shutdown: validation has now returned, but
    # its cancelled caller must never proceed to persist a completed delivery.
    assert completed.is_set()
    assert store.failure == ("COLLECTION_RETRYABLE", "TASK_DEADLINE_OR_CANCELLED")
    assert store.finished is None and "finish" not in store.events


def test_unknown_execution_recovery_only_resumes_and_collects() -> None:
    store = StateStore()
    store.task.update(
        status="EXECUTION_UNCERTAIN",
        runtime_id=REMOTE.runtime_id,
        remote_session_id=REMOTE.session_id,
    )
    client = Client(store)
    _run(store, client, recover=True)
    assert "resume" in store.events and client.downloads
    assert not {"create", "upload", "prompt"}.intersection(store.events)
    assert store.task["status"] == "PENDING_REVIEW"


def test_recovery_resume_is_also_bounded_by_whole_deadline() -> None:
    store = StateStore(budget=0.025)
    store.task.update(
        status="EXECUTION_UNCERTAIN",
        runtime_id=REMOTE.runtime_id,
        remote_session_id=REMOTE.session_id,
    )
    client = Client(store)
    client.delays["resume"] = 0.1
    with pytest.raises(TimeoutError):
        _run(store, client, recover=True)
    assert store.failure == ("COLLECTION_RETRYABLE", "TASK_DEADLINE_OR_CANCELLED")
    assert client.downloads == [] and "prompt" not in store.events


def test_collection_failure_is_recoverable_without_another_prompt() -> None:
    store = StateStore()
    client = Client(store)
    original = f"{ROOT}/artifacts/notice.bin"
    client.errors[f"download:{original}"] = DirectWmaError("WMA_DOWNLOAD_FAILED")
    with pytest.raises(DirectWmaError, match="WMA_DOWNLOAD_FAILED"):
        _run(store, client)
    assert store.failure == ("COLLECTION_RETRYABLE", "WMA_DOWNLOAD_FAILED")
    assert store.frozen is not None and store.finished is None
    _run(store, client, recover=True)
    assert store.task["status"] == "PENDING_REVIEW"
    assert store.events.count("create") == store.events.count("prompt") == 1
    assert store.events.count("resume") == 1
    assert client.downloads.count(original) == 2


def test_changed_manifest_on_recovery_is_rejected_before_original_download() -> None:
    store = StateStore()
    client = Client(store)
    original = f"{ROOT}/artifacts/notice.bin"
    client.errors[f"download:{original}"] = DirectWmaError("WMA_DOWNLOAD_FAILED")
    with pytest.raises(DirectWmaError):
        _run(store, client)
    client.files[f"{ROOT}/result/report.md"] += b"\nChanged after first collection."
    with pytest.raises(InvestigationError, match="RECOVERED_MANIFEST_CHANGED"):
        _run(store, client, recover=True)
    assert store.failure == ("FAILED_VALIDATION", "RECOVERED_MANIFEST_CHANGED")
    assert client.downloads.count(original) == 1 and store.finished is None
    assert store.events.count("prompt") == 1


@pytest.mark.parametrize("name", RESULT_NAMES)
def test_missing_result_stops_before_any_original_download(name: str) -> None:
    store = StateStore()
    client = Client(store)
    del client.files[f"{ROOT}/result/{name}"]
    with pytest.raises(DirectWmaError, match="WMA_ARTIFACT_NOT_FOUND"):
        _run(store, client)
    assert store.failure == ("COLLECTION_RETRYABLE", "WMA_ARTIFACT_NOT_FOUND")
    assert all(path.startswith(f"{ROOT}/result/") for path in client.downloads)
    assert store.frozen is None and store.finished is None


@pytest.mark.parametrize("name", ["opportunities.json", "evidence.json"])
def test_preflight_missing_required_structure_cannot_download_originals(name: str) -> None:
    store = StateStore()
    client = Client(store)
    client.files[f"{ROOT}/result/{name}"] = b"{}"
    with pytest.raises(DeliveryValidationError):
        _run(store, client)
    assert store.task["status"] == "FAILED_VALIDATION"
    assert client.downloads == [f"{ROOT}/result/{item}" for item in RESULT_NAMES]
    assert store.frozen is None and store.finished is None


def test_missing_declared_original_is_retryable_and_never_commits() -> None:
    store = StateStore()
    client = Client(store)
    del client.files[f"{ROOT}/artifacts/notice.bin"]
    with pytest.raises(DirectWmaError, match="WMA_ARTIFACT_NOT_FOUND"):
        _run(store, client)
    assert store.failure == ("COLLECTION_RETRYABLE", "WMA_ARTIFACT_NOT_FOUND")
    assert store.frozen is not None and store.finished is None


def test_manifest_file_count_is_enforced_before_downloading_originals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runner, "MAX_FILES", 0)
    store = StateStore()
    client = Client(store)
    with pytest.raises(InvestigationError, match="DELIVERY_FILE_LIMIT"):
        _run(store, client)
    assert store.failure == ("FAILED_VALIDATION", "DELIVERY_FILE_LIMIT")
    assert client.downloads == [f"{ROOT}/result/{name}" for name in RESULT_NAMES]
    assert store.finished is None


def test_total_byte_limit_counts_results_and_original_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    combined_bytes = sum(map(len, _result_files().values())) + len(ORIGINAL)
    monkeypatch.setattr(runner, "MAX_TOTAL_BYTES", combined_bytes - 1)
    store = StateStore()
    client = Client(store)
    with pytest.raises(InvestigationError, match="DELIVERY_BYTE_LIMIT"):
        _run(store, client)
    assert store.failure == ("FAILED_VALIDATION", "DELIVERY_BYTE_LIMIT")
    assert store.finished is None


@pytest.mark.parametrize(
    "path", ["../other/notice.bin", "/workspace/other/notice.bin", "artifacts/../../notice.bin"]
)
def test_preflight_rejects_escape_before_downloading_untrusted_path(path: str) -> None:
    store = StateStore()
    client = Client(store)
    key = f"{ROOT}/result/evidence.json"
    evidence = json.loads(client.files[key])
    evidence["artifacts"][0]["local_path"] = path
    client.files[key] = json.dumps(evidence).encode()
    with pytest.raises(DeliveryValidationError):
        _run(store, client)
    assert store.task["status"] == "FAILED_VALIDATION"
    assert client.downloads == [f"{ROOT}/result/{name}" for name in RESULT_NAMES]
    assert store.frozen is None and store.finished is None


def test_repeated_pending_task_does_not_run_prompt_again() -> None:
    store = StateStore()
    client = Client(store)
    _run(store, client)
    completed_events = list(store.events)
    _run(store, client)
    assert store.events == [*completed_events, "claim:create", "close"]
    assert store.events.count("prompt") == 1 and store.finished is VALIDATED


@pytest.mark.parametrize(
    "close_error", [RuntimeError("synthetic cleanup"), asyncio.CancelledError()]
)
def test_cleanup_failure_cannot_mask_committed_success(close_error: BaseException) -> None:
    store = StateStore()
    client = Client(store)
    client.close_error = close_error
    _run(store, client)
    assert store.task["status"] == "PENDING_REVIEW" and store.finished is VALIDATED


@pytest.mark.parametrize(
    "close_error", [RuntimeError("synthetic cleanup"), asyncio.CancelledError()]
)
def test_cleanup_failure_cannot_replace_original_failure(close_error: BaseException) -> None:
    store = StateStore()
    client = Client(store)
    client.close_error = close_error
    client.errors["upload"] = DirectWmaError("WMA_UPLOAD_FAILED")
    with pytest.raises(DirectWmaError, match="WMA_UPLOAD_FAILED"):
        _run(store, client)
    assert store.failure == ("FAILED_PREPARATION", "WMA_UPLOAD_FAILED")
