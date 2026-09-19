from __future__ import annotations

import asyncio
import os
import signal
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path

from deepaha_ops.audit import AuditEvent, AuditLog, now_iso, redact_text
from deepaha_ops.config import Settings
from deepaha_ops.store import OperationStore


class OperationRunner:
    def __init__(
        self,
        settings: Settings,
        store: OperationStore,
        audit: AuditLog,
    ) -> None:
        self.settings = settings
        self.store = store
        self.audit = audit
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=settings.queue_limit)
        self.failed = False
        self._direct_limit = asyncio.Semaphore(2)
        self._worker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(
                self._loop(),
                name="deepaha-ops-worker",
            )

    async def stop(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            with suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    async def enqueue(self, operation_id: str) -> None:
        await self.queue.put(operation_id)

    async def _loop(self) -> None:
        while True:
            operation_id = await self.queue.get()
            try:
                await self._execute(operation_id)
            except Exception:
                self.failed = True
                self.store._update(
                    operation_id,
                    status="UNKNOWN",
                    output="Reconciliation required; runner failed closed",
                )
                return
            finally:
                self.queue.task_done()

    async def _execute(self, operation_id: str) -> None:
        operation = self.store.get(operation_id)
        if operation is None:
            return
        args = self._adapter_args(operation.action, operation.params)
        self.audit.append(
            AuditEvent(
                timestamp=now_iso(),
                event="operation_started",
                request_id=operation.request_id,
                principal=operation.requested_by,
                details={
                    "operation_id": operation.id,
                    "action": operation.action,
                },
            )
        )
        self.store.mark_running(operation_id)
        exit_code, output = await self._run(args)
        self.audit.append(
            AuditEvent(
                timestamp=now_iso(),
                event="operation_finished",
                request_id=operation.request_id,
                principal=operation.requested_by,
                details={
                    "operation_id": operation.id,
                    "action": operation.action,
                    "exit_code": exit_code,
                },
            )
        )
        self.store.finish(operation_id, exit_code=exit_code, output=output)
        if exit_code in (124, 125):
            self.store._update(operation_id, status="UNKNOWN")

    async def direct(self, args: Sequence[str]) -> tuple[int, str]:
        async with self._direct_limit:
            try:
                return await asyncio.wait_for(self._run([*args]), timeout=25)
            except TimeoutError:
                return 124, "Read timed out"

    async def _run(self, adapter_args: Sequence[str]) -> tuple[int, str]:
        adapter = str(self.settings.adapter_path)
        if not Path(adapter).is_absolute():
            return 126, "adapter path must be absolute"
        try:
            command = [adapter, *adapter_args]
            if self.settings.adapter_use_sudo:
                command = ["sudo", "-n", *command]
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as exc:
            return 126, f"adapter unavailable: {exc.__class__.__name__}"
        output = bytearray()
        truncated = False

        async def drain():
            nonlocal truncated
            while chunk := await process.stdout.read(4096):
                remaining = self.settings.max_output_bytes - len(output)
                output.extend(chunk[:remaining])
                truncated |= len(chunk) > remaining
            await process.wait()

        try:
            await asyncio.wait_for(drain(), timeout=self.settings.command_timeout_seconds)
        except TimeoutError:
            os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
            return 124, "adapter timed out"
        except asyncio.CancelledError:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except TimeoutError:
                os.killpg(process.pid, signal.SIGKILL)
                await process.wait()
            raise
        raw = output.decode(
            "utf-8",
            errors="replace",
        )
        if truncated:
            raw += "\n[OUTPUT_TRUNCATED]"
        return int(process.returncode or 0), redact_text(raw)

    @staticmethod
    def _adapter_args(
        action: str,
        params: dict[str, object],
    ) -> list[str]:
        if action in ("deploy", "backup", "rollback", "restart"):
            return [
                action,
                str(params["environment"]),
                str(params["expected_current"]),
                str(params.get("commit_sha") or params.get("target") or "-"),
                str(params.get("approval_id") or "-"),
            ]
        raise ValueError(f"unsupported action: {action}")
