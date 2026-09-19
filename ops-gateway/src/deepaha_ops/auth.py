from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status


@dataclass(frozen=True, slots=True)
class Principal:
    token_fingerprint: str
    scopes: frozenset[str]


def _bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_REQUIRED"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    if len(token) < 32 or len(token) > 512:
        raise HTTPException(status_code=401, detail={"code": "AUTH_INVALID"})
    return token


def authenticate(request: Request) -> Principal:
    settings = request.app.state.settings
    token = _bearer_token(request)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    match_scopes: frozenset[str] | None = None
    for configured_digest, scopes in settings.token_scopes().items():
        if hmac.compare_digest(digest, configured_digest):
            match_scopes = scopes
            break
    if match_scopes is None:
        raise HTTPException(status_code=401, detail={"code": "AUTH_INVALID"})
    return Principal(token_fingerprint=digest, scopes=match_scopes)


def require_scope(scope: str):
    def dependency(principal: Principal = Depends(authenticate)) -> Principal:
        if scope not in principal.scopes:
            raise HTTPException(
                status_code=403,
                detail={"code": "SCOPE_REQUIRED", "scope": scope},
            )
        return principal

    return dependency
