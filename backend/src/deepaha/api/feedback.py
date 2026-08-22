from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session, sessionmaker

from deepaha.api.personal import (
    PRIVATE_CACHE_CONTROL,
    PersonalApiProblem,
    require_idempotency_key,
    require_principal,
)
from deepaha.contracts.common import EntityId, OpportunityPublicId
from deepaha.db.session import get_write_session
from deepaha.feedback.schemas import (
    FeedbackEvidenceWrite,
    FeedbackStatusDetail,
    FeedbackStatusPage,
    FeedbackSubmissionWrite,
)
from deepaha.feedback.service import (
    FeedbackIdempotencyConflict,
    FeedbackService,
    FeedbackUnavailable,
)
from deepaha.personal.auth import Principal

router = APIRouter(prefix="/api/v1/me", tags=["feedback"])


def _factory(session: Session) -> sessionmaker[Session]:
    return sessionmaker(bind=session.get_bind(), expire_on_commit=False)


def get_feedback_service(
    session: Annotated[Session, Depends(get_write_session)],
) -> FeedbackService:
    return FeedbackService(
        session_factory=_factory(session),
        now_factory=lambda: datetime.now(UTC),
    )


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = PRIVATE_CACHE_CONTROL


def _not_found() -> PersonalApiProblem:
    return PersonalApiProblem(
        status=404,
        slug="personal-resource-not-found",
        title="Personal resource not found",
        detail="The personal resource was not found.",
    )


def _conflict() -> PersonalApiProblem:
    return PersonalApiProblem(
        status=409,
        slug="idempotency-conflict",
        title="Idempotency conflict",
        detail="The idempotency key was already used for a different request.",
    )


@router.post(
    "/opportunities/{public_id}/feedback",
    status_code=status.HTTP_201_CREATED,
)
def submit_feedback(
    public_id: OpportunityPublicId,
    command: FeedbackSubmissionWrite,
    response: Response,
    principal: Annotated[Principal, Depends(require_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    service: Annotated[FeedbackService, Depends(get_feedback_service)],
) -> FeedbackStatusDetail:
    try:
        result = service.submit(
            principal,
            public_id,
            command,
            idempotency_key=idempotency_key,
        )
    except FeedbackIdempotencyConflict as error:
        raise _conflict() from error
    except FeedbackUnavailable as error:
        raise _not_found() from error
    _private(response)
    return result


@router.get("/feedback")
def list_feedback(
    response: Response,
    principal: Annotated[Principal, Depends(require_principal)],
    service: Annotated[FeedbackService, Depends(get_feedback_service)],
) -> FeedbackStatusPage:
    result = service.list_owned(principal)
    _private(response)
    return result


@router.get("/feedback/{feedback_event_id}")
def get_feedback(
    feedback_event_id: EntityId,
    response: Response,
    principal: Annotated[Principal, Depends(require_principal)],
    service: Annotated[FeedbackService, Depends(get_feedback_service)],
) -> FeedbackStatusDetail:
    result = service.get_owned(principal, feedback_event_id)
    if result is None:
        raise _not_found()
    _private(response)
    return result


@router.post("/feedback/{feedback_event_id}/evidence")
def append_feedback_evidence(
    feedback_event_id: EntityId,
    command: FeedbackEvidenceWrite,
    response: Response,
    principal: Annotated[Principal, Depends(require_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    service: Annotated[FeedbackService, Depends(get_feedback_service)],
) -> FeedbackStatusDetail:
    try:
        result = service.append_evidence(
            principal,
            feedback_event_id,
            command,
            idempotency_key=idempotency_key,
        )
    except FeedbackIdempotencyConflict as error:
        raise _conflict() from error
    except FeedbackUnavailable as error:
        raise _not_found() from error
    if result is None:
        raise _not_found()
    _private(response)
    return result


__all__ = ["get_feedback_service", "router"]
