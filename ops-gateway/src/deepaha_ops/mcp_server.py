"""Streamable HTTP tools; no generic execution tool or caller-supplied path."""

import hashlib
from uuid import uuid4

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from .auth import Principal
from .oauth import IntrospectionVerifier


def build_mcp(core, settings):
    from .main import BackupRequest, DeployRequest, Environment, RestartRequest, RollbackRequest

    server = FastMCP(
        "DeepAha Ops",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/mcp",
        token_verifier=IntrospectionVerifier(settings),
        auth=AuthSettings(
            issuer_url=settings.oauth_issuer,
            resource_server_url=settings.oauth_resource,
            validate_token_resource=True,
            required_scopes=["staging:read"],
        ),
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=settings.trusted_hosts,
            allowed_origins=["https://ops.deepaha.com", "https://chatgpt.com"],
        ),
    )

    def principal():
        token = get_access_token()
        if token is None:
            raise ValueError("AUTH_REQUIRED")
        identity = "|".join([settings.oauth_issuer, token.client_id, token.subject or ""])
        return Principal(hashlib.sha256(identity.encode()).hexdigest(), frozenset(token.scopes))

    read = ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    )
    write = ToolAnnotations(
        readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False
    )

    @server.tool(annotations=read)
    async def status(environment: Environment):
        """Read the explicitly selected environment's current version and services."""
        return await core.status(principal(), environment, uuid4().hex)

    @server.tool(annotations=read)
    async def logs(environment: Environment, service: str, lines: int = 100):
        """Read bounded, redacted API or Worker logs. No path arguments."""
        if service not in ("api", "worker"):
            raise ValueError("INVALID_SERVICE")
        return await core.logs(principal(), environment, service, lines, uuid4().hex)

    @server.tool(annotations=read)
    async def operation(operation_id: str):
        """Read an asynchronous operation receipt within your environment scope."""
        return core.operation(principal(), operation_id)

    @server.tool(annotations=write)
    async def deploy(request: DeployRequest):
        """Deploy an approved SHA without schema change; returns operation id.

        Production requires independent one-use human approval.
        """
        return await core.submit(
            "deploy", request.model_dump(exclude_none=True), principal(), uuid4().hex
        )

    @server.tool(annotations=write)
    async def backup(request: BackupRequest):
        """Back up DB/objects consistently with a brief service pause; returns operation id."""
        return await core.submit(
            "backup", request.model_dump(exclude_none=True), principal(), uuid4().hex
        )

    @server.tool(annotations=write)
    async def rollback(request: RollbackRequest):
        """Switch to an approved compatible historical SHA; never restore a database."""
        return await core.submit(
            "rollback", request.model_dump(exclude_none=True), principal(), uuid4().hex
        )

    @server.tool(annotations=write)
    async def restart(request: RestartRequest):
        """Restart a fixed API/Worker target in the explicit environment; returns operation id."""
        return await core.submit(
            "restart", request.model_dump(exclude_none=True), principal(), uuid4().hex
        )

    return server
