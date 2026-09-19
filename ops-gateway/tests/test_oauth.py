import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from deepaha_ops.oauth import IntrospectionVerifier


@pytest.mark.parametrize(
    "change",
    [
        {"active": False},
        {"exp": 0},
        {"aud": ["https://wrong.invalid"]},
        {"iss": "https://wrong.invalid"},
        {"scope": "unapproved"},
        {"client_id": ""},
        {"token_type": "refresh_token"},
    ],
)
def test_introspection_rejects_invalid_claims(tmp_path, monkeypatch, change):
    secret = tmp_path / "secret"
    secret.write_text("synthetic-client-secret")
    settings = SimpleNamespace(
        oauth_issuer="https://auth.invalid",
        oauth_introspection_url="https://auth.invalid/introspect",
        oauth_resource="https://ops.invalid/mcp",
        oauth_client_secret_file=secret,
        oauth_client_id="test",
    )
    claims = {
        "active": True,
        "exp": int(time.time()) + 60,
        "aud": ["https://ops.invalid/mcp"],
        "iss": "https://auth.invalid",
        "scope": "staging:read",
        "client_id": "test",
        **change,
    }
    response = httpx.Response(
        200, json=claims, request=httpx.Request("POST", settings.oauth_introspection_url)
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", AsyncMock(return_value=response))
    assert (
        asyncio.run(IntrospectionVerifier(settings).verify_token("synthetic-access-token")) is None
    )


def test_mcp_authenticated_surface(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from test_closeout import configured

    from deepaha_ops.main import create_app

    settings = configured(tmp_path)
    settings.oauth_issuer = "https://auth.invalid"
    settings.oauth_introspection_url = "https://auth.invalid/introspect"
    settings.oauth_resource = "https://ops.invalid/mcp"
    with TestClient(create_app(settings)) as c:
        assert c.post("/mcp", json={}).status_code == 401
        metadata = c.get("/.well-known/oauth-protected-resource/mcp").json()
        assert "staging:deploy" in metadata["scopes_supported"]
