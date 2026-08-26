from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from uuid import UUID

from sqlalchemy.orm import Session

from deepaha.core.settings import Settings
from deepaha.review.models import ReviewerAccountModel, ReviewerAuthSessionModel

REVIEWER_AUTHENTICATION_FAILURE = "reviewer authentication failed"
REVIEW_PURPOSE = "FEEDBACK_REVIEW_AND_VALIDATION"
OPPORTUNITY_FACT_VALIDATION_PURPOSE = "OPPORTUNITY_FACT_VALIDATION"
REVIEW_PURPOSES = frozenset({REVIEW_PURPOSE, OPPORTUNITY_FACT_VALIDATION_PURPOSE})


class ReviewerAuthenticationError(ValueError):
    pass


class ReviewerRole(StrEnum):
    FEEDBACK_REVIEWER = "FEEDBACK_REVIEWER"
    FEEDBACK_ADJUDICATOR = "FEEDBACK_ADJUDICATOR"
    LABEL_CURATOR = "LABEL_CURATOR"
    VALIDATION_REVIEWER = "VALIDATION_REVIEWER"
    LOCAL_TEST_OPERATOR = "LOCAL_TEST_OPERATOR"


@dataclass(frozen=True, slots=True)
class ReviewerPrincipal:
    reviewer_id: UUID
    roles: frozenset[ReviewerRole]
    purposes: frozenset[str]
    synthetic: bool


def reviewer_token_digest(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def parse_reviewer_bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise ReviewerAuthenticationError(REVIEWER_AUTHENTICATION_FAILURE)
    scheme, separator, token = authorization.partition(" ")
    if (
        not separator
        or scheme.lower() != "bearer"
        or not 16 <= len(token) <= 256
        or any(character.isspace() or not character.isprintable() for character in token)
    ):
        raise ReviewerAuthenticationError(REVIEWER_AUTHENTICATION_FAILURE)
    return token


def assert_reviewer_fixture_auth_enabled(settings: Settings) -> None:
    if settings.reviewer_auth_mode != "fixture" or settings.environment not in {
        "development",
        "test",
    }:
        raise ReviewerAuthenticationError(REVIEWER_AUTHENTICATION_FAILURE)


def resolve_reviewer_principal(
    authorization: str | None,
    session: Session,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> ReviewerPrincipal:
    assert_reviewer_fixture_auth_enabled(settings)
    token = parse_reviewer_bearer_token(authorization)
    auth_session = session.get(ReviewerAuthSessionModel, reviewer_token_digest(token))
    current_time = now or datetime.now(UTC)
    if (
        auth_session is None
        or auth_session.revoked_at is not None
        or auth_session.expires_at <= current_time
    ):
        raise ReviewerAuthenticationError(REVIEWER_AUTHENTICATION_FAILURE)
    reviewer = session.get(ReviewerAccountModel, auth_session.reviewer_id)
    if reviewer is None or not reviewer.active:
        raise ReviewerAuthenticationError(REVIEWER_AUTHENTICATION_FAILURE)
    try:
        roles = frozenset(ReviewerRole(role) for role in reviewer.roles)
    except ValueError as error:
        raise ReviewerAuthenticationError(REVIEWER_AUTHENTICATION_FAILURE) from error
    purposes = frozenset(reviewer.allowed_purposes)
    if not roles or not purposes or not purposes.issubset(REVIEW_PURPOSES):
        raise ReviewerAuthenticationError(REVIEWER_AUTHENTICATION_FAILURE)
    return ReviewerPrincipal(
        reviewer_id=reviewer.reviewer_id,
        roles=roles,
        purposes=purposes,
        synthetic=reviewer.synthetic,
    )


def require_reviewer_authority(
    principal: ReviewerPrincipal,
    role: ReviewerRole,
    purpose: str = REVIEW_PURPOSE,
) -> None:
    if role not in principal.roles or purpose not in principal.purposes:
        raise ReviewerAuthenticationError(REVIEWER_AUTHENTICATION_FAILURE)


__all__ = [
    "OPPORTUNITY_FACT_VALIDATION_PURPOSE",
    "REVIEWER_AUTHENTICATION_FAILURE",
    "REVIEW_PURPOSE",
    "REVIEW_PURPOSES",
    "ReviewerAuthenticationError",
    "ReviewerPrincipal",
    "ReviewerRole",
    "assert_reviewer_fixture_auth_enabled",
    "parse_reviewer_bearer_token",
    "require_reviewer_authority",
    "resolve_reviewer_principal",
    "reviewer_token_digest",
]
