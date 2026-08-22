from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from deepaha.review.auth import ReviewerRole, reviewer_token_digest
from deepaha.review.models import ReviewerAccountModel, ReviewerAuthSessionModel

CREATED_AT = datetime(2026, 8, 22, 11, 0, tzinfo=UTC)
EXPIRES_AT = datetime(2099, 1, 1, tzinfo=UTC)


def reviewer_id(index: int) -> UUID:
    return UUID(f"019b0000-0000-7000-8000-{700 + index:012d}")


def persist_reviewer(
    session: Session,
    *,
    index: int,
    token: str,
    roles: tuple[ReviewerRole, ...],
) -> UUID:
    identity = reviewer_id(index)
    session.add(
        ReviewerAccountModel(
            reviewer_id=identity,
            active=True,
            synthetic=True,
            principal_label=f"SYNTHETIC_PHASE7_REVIEWER_{index}",
            roles=[role.value for role in roles],
            allowed_purposes=["FEEDBACK_REVIEW_AND_VALIDATION"],
            created_at=CREATED_AT,
        )
    )
    session.flush()
    session.add(
        ReviewerAuthSessionModel(
            token_sha256=reviewer_token_digest(token),
            reviewer_id=identity,
            expires_at=EXPIRES_AT,
            revoked_at=None,
            created_at=CREATED_AT,
        )
    )
    session.flush()
    return identity


__all__ = ["persist_reviewer", "reviewer_id"]
