"""Shared REST/MCP authorization, audit and submission boundary."""

import asyncio
import hashlib
import json

from fastapi import HTTPException

from .audit import AuditEvent, AuditLog, now_iso
from .runner import OperationRunner
from .store import OperationStore


def require(principal, environment, action):
    if f"{environment}:{action}" not in principal.scopes:
        raise HTTPException(403, {"code": "SCOPE_REQUIRED"})


class GatewayCore:
    def __init__(self, settings):
        self.settings = settings
        self.audit = AuditLog(settings.audit_log)
        self.store = OperationStore(settings.state_dir / "state.sqlite3")
        self.runner = OperationRunner(settings, self.store, self.audit)
        self._submit_lock = asyncio.Lock()

    def event(self, name, principal, request_id, details):
        try:
            self.audit.append(
                AuditEvent(now_iso(), name, request_id, principal.token_fingerprint, details)
            )
        except (OSError, ValueError, KeyError):
            raise HTTPException(503, {"code": "AUDIT_UNAVAILABLE"}) from None

    async def status(self, principal, environment, request_id):
        require(principal, environment, "read")
        self.event("status_read", principal, request_id, {"environment": environment})
        code, output = await self.runner.direct(["status", environment])
        if code:
            raise HTTPException(503, {"code": "ADAPTER_STATUS_FAILED"})
        return {
            "environment": environment,
            "adapter_status": output,
            "recent_operations": self.operations(principal, environment, 5)["operations"],
        }

    async def logs(self, principal, environment, service, lines, request_id):
        require(principal, environment, "read")
        if not 20 <= lines <= self.settings.max_log_lines:
            raise HTTPException(422, {"code": "LOG_LIMIT"})
        self.event(
            "logs_read",
            principal,
            request_id,
            {"environment": environment, "service": service, "lines": lines},
        )
        code, output = await self.runner.direct(["logs", environment, service, str(lines)])
        if code:
            raise HTTPException(503, {"code": "LOG_READ_FAILED"})
        return {"environment": environment, "service": service, "output": output}

    def operations(self, principal, environment, limit):
        require(principal, environment, "read")
        return {"operations": [op.public() for op in self.store.list_recent(limit, environment)]}

    def operation(self, principal, operation_id):
        item = self.store.get(operation_id)
        if item is None or f"{item.environment}:read" not in principal.scopes:
            raise HTTPException(404, {"code": "OPERATION_NOT_FOUND"})
        return item.public()

    async def submit(self, action, payload, principal, request_id):
        environment = payload["environment"]
        require(principal, environment, action)
        if not self.settings.mutations_enabled or (
            environment == "staging" and not self.settings.staging_mutations_enabled
        ):
            raise HTTPException(503, {"code": "MUTATIONS_DISABLED"})
        if environment == "production" and not payload.get("approval_id"):
            raise HTTPException(403, {"code": "PER_OPERATION_HUMAN_AUTH_REQUIRED"})
        params = {k: v for k, v in payload.items() if k != "idempotency_key"}
        key = hashlib.sha256(
            json.dumps(
                [principal.token_fingerprint, action, environment, payload["idempotency_key"]]
            ).encode()
        ).hexdigest()
        async with self._submit_lock:
            existing = self.store.by_idempotency(key)
            if existing:
                if existing.params != params:
                    raise HTTPException(409, {"code": "IDEMPOTENCY_CONFLICT"})
                return {**existing.public(), "idempotent_replay": True}
            if self.runner.failed or self.runner.queue.full():
                raise HTTPException(503, {"code": "RUNNER_UNAVAILABLE"})
            self.event(
                "operation_requested", principal, request_id, {"action": action, "params": params}
            )
            item, _ = self.store.create(
                action=action,
                environment=environment,
                target=params.get("commit_sha") or params.get("target"),
                idempotency_key=key,
                requested_by=principal.token_fingerprint,
                request_id=request_id,
                params=params,
            )
            await self.runner.enqueue(item.id)
            return {**item.public(), "idempotent_replay": False}
