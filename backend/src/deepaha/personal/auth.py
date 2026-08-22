from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from sqlalchemy.orm import Session

from deepaha.core.settings import Settings
from deepaha.personal.models import PersonalAuthSessionModel, PersonalUserModel

AUTHENTICATION_FAILURE = "personal authentication failed"


class AuthenticationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UUID


def token_digest(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def parse_bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise AuthenticationError(AUTHENTICATION_FAILURE)
    scheme, separator, token = authorization.partition(" ")
    if (
        not separator
        or scheme.lower() != "bearer"
        or not 16 <= len(token) <= 256
        or any(character.isspace() or not character.isprintable() for character in token)
    ):
        raise AuthenticationError(AUTHENTICATION_FAILURE)
    return token


def assert_fixture_auth_enabled(settings: Settings) -> None:
    if settings.personal_auth_mode != "fixture" or settings.environment not in {
        "development",
        "test",
    }:
        raise AuthenticationError(AUTHENTICATION_FAILURE)


def resolve_principal(
    authorization: str | None,
    session: Session,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> Principal:
    assert_fixture_auth_enabled(settings)
    token = parse_bearer_token(authorization)
    auth_session = session.get(PersonalAuthSessionModel, token_digest(token))
    current_time = now or datetime.now(UTC)
    if (
        auth_session is None
        or auth_session.revoked_at is not None
        or auth_session.expires_at <= current_time
    ):
        raise AuthenticationError(AUTHENTICATION_FAILURE)
    user = session.get(PersonalUserModel, auth_session.user_id)
    if user is None or not user.active:
        raise AuthenticationError(AUTHENTICATION_FAILURE)
    return Principal(user_id=user.user_id)


__all__ = [
    "AuthenticationError",
    "Principal",
    "assert_fixture_auth_enabled",
    "parse_bearer_token",
    "resolve_principal",
    "token_digest",
]
