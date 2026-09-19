from __future__ import annotations

import re
from contextlib import asynccontextmanager
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, field_validator

from deepaha_ops import __version__
from deepaha_ops.audit import AuditEvent, AuditLog, now_iso
from deepaha_ops.auth import Principal, require_scope
from deepaha_ops.config import Settings, get_settings
from deepaha_ops.runner import OperationRunner
from deepaha_ops.store import OperationStore

COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")

EnvironmentName = Literal["staging", "production"]
RestartTarget = Literal["api", "web", "worker", "all"]
LogTarget = Literal["gateway", "api", "web", "worker"]


class DeployRequest(BaseModel):
    environment: EnvironmentName
    commit_sha: str
    confirmation: str | None = None

    @field_validator("commit_sha")
    @classmethod
    def validate_sha(cls, value: str) -> str:
        value = value.lower()
        if not COMMIT_RE.fullmatch(value):
            raise ValueError(
                "commit_sha must be a full 40-character lowercase hexadecimal SHA"
            )
        return value


class BackupRequest(BaseModel):
    environment: EnvironmentName = "production"


class RollbackRequest(BaseModel):
    environment: EnvironmentName
    target: str = "previous"
    confirmation: str | None = None

    @field_validator("target")
    @classmethod
    def validate_target(cls, value: str) -> str:
        value = value.lower()
        if value != "previous" and not COMMIT_RE.fullmatch(value):
            raise ValueError(
                "target must be 'previous' or a full 40-character commit SHA"
            )
        return value


class RestartRequest(BaseModel):
    target: RestartTarget


class BetaUserRequest(BaseModel):
    username: str
    email: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        if not USERNAME_RE.fullmatch(value):
            raise ValueError("invalid username")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if len(value) > 254 or value.count("@") != 1:
            raise ValueError("invalid email")
        local, domain = value.split("@", 1)
        if (
            not local
            or not domain
            or "." not in domain
            or any(char.isspace() for char in value)
        ):
            raise ValueError("invalid email")
        return value


def _components(
    settings: Settings,
) -> tuple[OperationStore, AuditLog, OperationRunner]:
    store = OperationStore(settings.state_dir / "state.sqlite3")
    audit = AuditLog(settings.audit_log)
    runner = OperationRunner(settings, store, audit)
    return store, audit, runner


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    store, audit, runner = _components(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await runner.start()
        try:
            yield
        finally:
            await runner.stop()

    app = FastAPI(
        title="DeepAha Ops Gateway",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.store = store
    app.state.audit = audit
    app.state.runner = runner
    if settings.trusted_hosts:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.trusted_hosts,
        )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        request.state.request_id = request_id[:128]
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "deepaha-ops-gateway",
            "version": __version__,
        }

    @app.get("/v1/capabilities")
    async def capabilities(
        _principal: Principal = Depends(require_scope("read")),
    ) -> dict[str, object]:
        return {
            "version": __version__,
            "mutations_enabled": settings.mutations_enabled,
            "actions": [
                "deploy",
                "backup",
                "rollback",
                "restart",
                "create_beta_user",
            ],
            "read_actions": ["status", "logs", "operations"],
            "safety": {
                "arbitrary_shell": False,
                "arbitrary_paths": False,
                "git_refs": "full_commit_sha_only",
                "mutations_serialized": True,
            },
        }

    @app.get("/v1/status")
    async def gateway_status(
        request: Request,
        principal: Principal = Depends(require_scope("read")),
    ) -> dict[str, object]:
        code, output = await runner.direct(["status"])
        audit.append(
            AuditEvent(
                timestamp=now_iso(),
                event="status_read",
                request_id=request.state.request_id,
                principal=principal.token_fingerprint,
                details={"exit_code": code},
            )
        )
        if code != 0:
            raise HTTPException(
                status_code=503,
                detail={"code": "ADAPTER_STATUS_FAILED"},
            )
        return {
            "adapter_status": output,
            "recent_operations": [
                op.public() for op in store.list_recent(5)
            ],
        }

    @app.get("/v1/logs")
    async def logs(
        request: Request,
        service: LogTarget,
        lines: Annotated[int, Query(ge=20, le=2000)] = 200,
        principal: Principal = Depends(require_scope("read")),
    ) -> dict[str, object]:
        if lines > settings.max_log_lines:
            raise HTTPException(
                status_code=422,
                detail={"code": "LOG_LINE_LIMIT_EXCEEDED"},
            )
        code, output = await runner.direct(
            ["logs", service, str(lines)]
        )
        audit.append(
            AuditEvent(
                timestamp=now_iso(),
                event="logs_read",
                request_id=request.state.request_id,
                principal=principal.token_fingerprint,
                details={
                    "service": service,
                    "lines": lines,
                    "exit_code": code,
                },
            )
        )
        if code != 0:
            raise HTTPException(
                status_code=503,
                detail={"code": "LOG_READ_FAILED"},
            )
        return {
            "service": service,
            "lines": lines,
            "output": output,
        }

    @app.get("/v1/operations")
    async def operations(
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        _principal: Principal = Depends(require_scope("read")),
    ) -> dict[str, object]:
        return {
            "operations": [
                op.public() for op in store.list_recent(limit)
            ]
        }

    @app.get("/v1/operations/{operation_id}")
    async def operation(
        operation_id: str,
        _principal: Principal = Depends(require_scope("read")),
    ) -> dict[str, object]:
        item = store.get(operation_id)
        if item is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "OPERATION_NOT_FOUND"},
            )
        return item.public()

    async def submit(
        *,
        action: str,
        payload: dict[str, object],
        principal: Principal,
        request: Request,
        idempotency_key: str | None,
    ) -> dict[str, object]:
        if not settings.mutations_enabled:
            raise HTTPException(
                status_code=503,
                detail={"code": "MUTATIONS_DISABLED"},
            )
        if (
            idempotency_key is None
            or not IDEMPOTENCY_RE.fullmatch(idempotency_key)
        ):
            raise HTTPException(
                status_code=400,
                detail={"code": "IDEMPOTENCY_KEY_REQUIRED"},
            )
        environment = payload.get("environment")
        target = (
            payload.get("target")
            or payload.get("commit_sha")
            or payload.get("username")
        )
        item, created = store.create(
            action=action,
            environment=str(environment) if environment else None,
            target=str(target) if target else None,
            idempotency_key=idempotency_key,
            requested_by=principal.token_fingerprint,
            request_id=request.state.request_id,
            params=payload,
        )
        if created:
            audit.append(
                AuditEvent(
                    timestamp=now_iso(),
                    event="operation_queued",
                    request_id=request.state.request_id,
                    principal=principal.token_fingerprint,
                    details={
                        "operation_id": item.id,
                        "action": action,
                        "params": payload,
                    },
                )
            )
            await runner.enqueue(item.id)
        return {
            **item.public(),
            "idempotent_replay": not created,
        }

    @app.post(
        "/v1/deploy",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def deploy(
        body: DeployRequest,
        request: Request,
        principal: Principal = Depends(require_scope("deploy")),
        idempotency_key: Annotated[
            str | None,
            Header(alias="Idempotency-Key"),
        ] = None,
    ) -> dict[str, object]:
        if (
            body.environment == "production"
            and body.confirmation != "DEPLOY_PRODUCTION"
        ):
            raise HTTPException(
                status_code=400,
                detail={"code": "PRODUCTION_CONFIRMATION_REQUIRED"},
            )
        return await submit(
            action="deploy",
            payload={
                "environment": body.environment,
                "commit_sha": body.commit_sha,
            },
            principal=principal,
            request=request,
            idempotency_key=idempotency_key,
        )

    @app.post(
        "/v1/backup",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def backup(
        body: BackupRequest,
        request: Request,
        principal: Principal = Depends(require_scope("backup")),
        idempotency_key: Annotated[
            str | None,
            Header(alias="Idempotency-Key"),
        ] = None,
    ) -> dict[str, object]:
        return await submit(
            action="backup",
            payload={"environment": body.environment},
            principal=principal,
            request=request,
            idempotency_key=idempotency_key,
        )

    @app.post(
        "/v1/rollback",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def rollback(
        body: RollbackRequest,
        request: Request,
        principal: Principal = Depends(require_scope("rollback")),
        idempotency_key: Annotated[
            str | None,
            Header(alias="Idempotency-Key"),
        ] = None,
    ) -> dict[str, object]:
        required = (
            "ROLLBACK_PRODUCTION"
            if body.environment == "production"
            else "ROLLBACK_STAGING"
        )
        if body.confirmation != required:
            raise HTTPException(
                status_code=400,
                detail={"code": "ROLLBACK_CONFIRMATION_REQUIRED"},
            )
        return await submit(
            action="rollback",
            payload={
                "environment": body.environment,
                "target": body.target,
            },
            principal=principal,
            request=request,
            idempotency_key=idempotency_key,
        )

    @app.post(
        "/v1/restart",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def restart(
        body: RestartRequest,
        request: Request,
        principal: Principal = Depends(require_scope("restart")),
        idempotency_key: Annotated[
            str | None,
            Header(alias="Idempotency-Key"),
        ] = None,
    ) -> dict[str, object]:
        return await submit(
            action="restart",
            payload={"target": body.target},
            principal=principal,
            request=request,
            idempotency_key=idempotency_key,
        )

    @app.post(
        "/v1/beta-users",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_beta_user(
        body: BetaUserRequest,
        request: Request,
        principal: Principal = Depends(
            require_scope("user_admin")
        ),
        idempotency_key: Annotated[
            str | None,
            Header(alias="Idempotency-Key"),
        ] = None,
    ) -> dict[str, object]:
        return await submit(
            action="create_beta_user",
            payload={
                "username": body.username,
                "email": body.email,
            },
            principal=principal,
            request=request,
            idempotency_key=idempotency_key,
        )

    return app


app = create_app()
