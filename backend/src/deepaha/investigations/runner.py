import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid7

from deepaha.investigations.contracts import (
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_TOTAL_BYTES,
    RESULT_NAMES,
    CreateInvestigation,
    InvestigationError,
)
from deepaha.investigations.delivery import (
    DeliveryValidationError,
    preflight_manifest,
    validate_delivery,
)
from deepaha.investigations.prompt import prepare_input, task_root
from deepaha.investigations.store import InvestigationStore
from deepaha.investigations.wma import DirectWmaError, WmaSessionRef


class InvestigationClient(Protocol):
    async def create(
        self, task_key: str, *, checkpoint: Callable[[str, str | None], None] | None = None
    ) -> WmaSessionRef: ...
    def binding_evidence(self) -> dict[str, object]: ...
    async def resume(self, ref: WmaSessionRef) -> None: ...
    async def upload(self, remote_path: str, content: bytes) -> None: ...
    async def prompt(self, text: str, timeout_seconds: float) -> str: ...
    async def download(self, remote_path: str, max_bytes: int) -> bytes: ...
    async def aclose(self) -> None: ...


async def execute_investigation(
    store: InvestigationStore,
    client: InvestigationClient,
    task_id: UUID,
    execution: dict[str, object],
    *,
    recover: bool = False,
) -> None:
    owner = uuid7()
    stage = "CREATING"
    claimed = False
    try:
        task = store.claim(task_id, owner, execution, recover=recover)
        if task["status"] in ("PENDING_REVIEW", "APPROVED", "REJECTED"):
            return
        claimed = True
        stage = task["status"]
        deadline = datetime.fromisoformat(task["deadline_at"])
        remaining = (deadline - store.clock()).total_seconds()
        if remaining <= 0:
            raise TimeoutError
        # One deadline includes SDK startup, every upload, execution, and all downloads.
        async with asyncio.timeout(remaining):
            command = CreateInvestigation.model_validate(
                {key: task[key] for key in CreateInvestigation.model_fields}
            )
            root = task_root(task_id)
            if recover:
                await client.resume(WmaSessionRef(task["runtime_id"], task["remote_session_id"]))
            else:

                def checkpoint(runtime_id: str, session_id: str | None) -> None:
                    store.checkpoint_remote(task_id, owner, runtime_id, session_id)
                    if store.clock() >= deadline:
                        raise TimeoutError

                ref = await client.create(str(task_id), checkpoint=checkpoint)
                store.transition(task_id, owner, "PREPARING", (ref.runtime_id, ref.session_id))
                stage = "PREPARING"
                prepared_at = store.clock()
                store.record_binding(
                    task_id,
                    owner,
                    client.binding_evidence() | {"input_prepared_at": prepared_at.isoformat()},
                )
                files, prompt = prepare_input(
                    task_id,
                    command,
                    task["source_snapshot"]["allowed_hosts"],
                    deadline_at=deadline,
                    prepared_at=prepared_at,
                )
                for path, content in files.items():
                    await client.upload(path, content)
                stage = "INVESTIGATING"
                store.transition(task_id, owner, stage)
                reason = await client.prompt(prompt, (deadline - store.clock()).total_seconds())
                if reason != "end_turn":
                    code = {
                        "refusal": "WMA_REMOTE_REFUSED",
                        "max_tokens": "WMA_OUTPUT_LIMIT_REACHED",
                        "max_turn_requests": "WMA_REQUEST_LIMIT_REACHED",
                        "cancelled": "WMA_REMOTE_CANCELLED",
                    }.get(reason, "WMA_NON_SUCCESS_STOP")
                    raise InvestigationError(code)
                stage = "COLLECTING"
                store.transition(task_id, owner, stage)
            results: dict[str, bytes] = {}
            for name in RESULT_NAMES:
                results[name] = await client.download(f"{root}/result/{name}", MAX_FILE_BYTES)
            manifest = preflight_manifest(results)
            if len(manifest) > MAX_FILES:
                raise InvestigationError("DELIVERY_FILE_LIMIT")
            store.freeze_manifest(task_id, owner, results)
            total = sum(len(data) for data in results.values())
            originals: dict[str, bytes] = {}
            for artifact_id, path in manifest:
                data = await client.download(f"{root}/{path}", MAX_FILE_BYTES)
                total += len(data)
                if total > MAX_TOTAL_BYTES:
                    raise InvestigationError("DELIVERY_BYTE_LIMIT")
                originals[artifact_id] = data
            validated = await asyncio.to_thread(validate_delivery, results, originals)
            # Synchronous validation/import must also finish before the persisted deadline.
            store.finish(task_id, owner, validated, results)
    except TimeoutError, asyncio.CancelledError:
        if claimed:
            status = (
                "EXECUTION_UNCERTAIN"
                if stage in ("CREATING", "INVESTIGATING")
                else "COLLECTION_RETRYABLE"
                if stage == "COLLECTING"
                else "EXPIRED"
            )
            store.fail(task_id, owner, status, "TASK_DEADLINE_OR_CANCELLED")
        raise
    except Exception as error:
        if claimed:
            code = (
                error.code
                if isinstance(error, (InvestigationError, DirectWmaError, DeliveryValidationError))
                else "INVESTIGATION_DEPENDENCY_FAILED"
            )
            status = (
                "FAILED_VALIDATION"
                if isinstance(error, DeliveryValidationError)
                or code
                in {
                    "DELIVERY_TASK_BINDING_MISMATCH",
                    "EXPECTED_MATERIAL_MISSING",
                    "EXPECTED_ENTITY_MISSING",
                    "MATERIAL_OUTSIDE_APPROVED_HOSTS",
                    "DELIVERY_FILE_LIMIT",
                    "DELIVERY_BYTE_LIMIT",
                    "RECOVERED_MANIFEST_CHANGED",
                }
                else "EXECUTION_UNCERTAIN"
                if stage in ("CREATING", "INVESTIGATING")
                else "COLLECTION_RETRYABLE"
                if stage == "COLLECTING"
                else "FAILED_PREPARATION"
            )
            store.fail(task_id, owner, status, code)
        raise
    finally:
        try:
            async with asyncio.timeout(5):
                await client.aclose()
        except Exception, asyncio.CancelledError:
            pass  # Cleanup never masks the durable task outcome or triggers another prompt.
