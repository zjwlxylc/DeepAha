"""RFC 7662 verification delegated to the configured mature authorization server."""

import time

import httpx
from mcp.server.auth.provider import AccessToken

from .config import ALL_SCOPES


class IntrospectionVerifier:
    def __init__(self, settings):
        self.settings = settings
        if not settings.oauth_introspection_url.startswith(settings.oauth_issuer.rstrip("/") + "/"):
            raise ValueError("introspection must belong to the configured issuer")

    async def verify_token(self, token):
        if not token or len(token) > 4096:
            return None
        try:
            secret = self.settings.oauth_client_secret_file.read_text().strip()
            async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
                response = await client.post(
                    self.settings.oauth_introspection_url,
                    auth=(self.settings.oauth_client_id, secret),
                    data={"token": token, "token_type_hint": "access_token"},
                )
                response.raise_for_status()
                data = response.json()
            audience = data.get("aud", [])
            if isinstance(audience, str):
                audience = [audience]
            resources = data.get("resource", [])
            if isinstance(resources, str):
                resources = [resources]
            if (
                data.get("active") is not True
                or data.get("iss") != self.settings.oauth_issuer
                or float(data.get("exp", 0)) <= time.time()
            ):
                return None
            if (
                self.settings.oauth_resource not in audience
                and self.settings.oauth_resource not in resources
            ):
                return None
            if data.get("token_type", "Bearer").lower() != "bearer":
                return None
            scopes = set(data.get("scope", "").split()) & ALL_SCOPES
            if not scopes or not data.get("client_id"):
                return None
            return AccessToken(
                token=token,
                client_id=data["client_id"],
                subject=data.get("sub"),
                scopes=sorted(scopes),
                expires_at=int(data["exp"]),
                resource=self.settings.oauth_resource,
                claims={"iss": data["iss"]},
            )
        except (OSError, ValueError, TypeError, httpx.HTTPError):
            return None
