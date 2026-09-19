from contextlib import asynccontextmanager
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, ConfigDict, Field

from .auth import Principal, authenticate
from .config import Settings, get_settings
from .core import GatewayCore

Environment = Literal["staging", "production"]
SHA = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]


class Mutation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: Environment
    expected_current: SHA
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9._:-]{8,128}$")
    approval_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")


class DeployRequest(Mutation):
    commit_sha: SHA


class RollbackRequest(Mutation):
    target: SHA


class RestartRequest(Mutation):
    target: Literal["api", "worker", "all"]


class BackupRequest(Mutation):
    pass


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    core = GatewayCore(settings)
    mcp = None
    if settings.oauth_issuer:
        from .mcp_server import build_mcp

        mcp = build_mcp(core, settings)
        mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app):
        await core.runner.start()
        try:
            if mcp:
                async with mcp.session_manager.run():
                    yield
            else:
                yield
        finally:
            await core.runner.stop()

    app = FastAPI(
        title="DeepAha Ops Gateway",
        version="1.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.core = core
    app.state.store, app.state.audit, app.state.runner = core.store, core.audit, core.runner
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)

    @app.middleware("http")
    async def context(request: Request, call_next):
        request.state.request_id = uuid4().hex
        response = await call_next(request)
        response.headers.update(
            {
                "X-Request-ID": request.state.request_id,
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
            }
        )
        return response

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "deepaha-ops-gateway", "version": "1.1.0"}

    @app.get("/v1/capabilities")
    async def capabilities(principal: Principal = Depends(authenticate)):
        return {
            "scopes": sorted(principal.scopes),
            "mutations_enabled": settings.mutations_enabled,
            "staging_mutations_enabled": settings.staging_mutations_enabled,
            "production": "PER_OPERATION_HUMAN_AUTH_REQUIRED",
            "schema_policy": "NO_SCHEMA_CHANGE",
        }

    @app.get("/v1/status")
    async def status(
        request: Request, environment: Environment, principal: Principal = Depends(authenticate)
    ):
        return await core.status(principal, environment, request.state.request_id)

    @app.get("/v1/logs")
    async def logs(
        request: Request,
        environment: Environment,
        service: Literal["api", "worker"],
        lines: Annotated[int, Query(ge=20, le=500)] = 100,
        principal: Principal = Depends(authenticate),
    ):
        return await core.logs(principal, environment, service, lines, request.state.request_id)

    @app.get("/v1/gateway/logs")
    async def gateway_logs(
        request: Request,
        lines: Annotated[int, Query(ge=20, le=500)] = 100,
        principal: Principal = Depends(authenticate),
    ):
        return await core.logs(principal, "gateway", "gateway", lines, request.state.request_id)

    @app.get("/v1/operations")
    async def operations(
        environment: Environment,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        principal: Principal = Depends(authenticate),
    ):
        return core.operations(principal, environment, limit)

    @app.get("/v1/operations/{operation_id}")
    async def operation(operation_id: str, principal: Principal = Depends(authenticate)):
        return core.operation(principal, operation_id)

    @app.post("/v1/deploy", status_code=202, openapi_extra={"x-openai-isConsequential": True})
    async def deploy(
        body: DeployRequest, request: Request, principal: Principal = Depends(authenticate)
    ):
        return await core.submit(
            "deploy", body.model_dump(exclude_none=True), principal, request.state.request_id
        )

    @app.post("/v1/backup", status_code=202, openapi_extra={"x-openai-isConsequential": True})
    async def backup(
        body: BackupRequest, request: Request, principal: Principal = Depends(authenticate)
    ):
        return await core.submit(
            "backup", body.model_dump(exclude_none=True), principal, request.state.request_id
        )

    @app.post("/v1/rollback", status_code=202, openapi_extra={"x-openai-isConsequential": True})
    async def rollback(
        body: RollbackRequest, request: Request, principal: Principal = Depends(authenticate)
    ):
        return await core.submit(
            "rollback", body.model_dump(exclude_none=True), principal, request.state.request_id
        )

    @app.post("/v1/restart", status_code=202, openapi_extra={"x-openai-isConsequential": True})
    async def restart(
        body: RestartRequest, request: Request, principal: Principal = Depends(authenticate)
    ):
        return await core.submit(
            "restart", body.model_dump(exclude_none=True), principal, request.state.request_id
        )

    if mcp:

        @app.get("/.well-known/oauth-protected-resource/mcp")
        async def protected_resource():
            return {
                "resource": settings.oauth_resource,
                "authorization_servers": [settings.oauth_issuer],
                "scopes_supported": [
                    "openid",
                    "offline_access",
                    "staging:read",
                    "staging:deploy",
                    "staging:backup",
                    "staging:rollback",
                    "staging:restart",
                ],
                "bearer_methods_supported": ["header"],
            }

        app.mount("/", mcp_app)
    return app
