from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, sessionmaker
from starlette.responses import JSONResponse

from deepaha.api.personal import PRIVATE_CACHE_CONTROL
from deepaha.contracts.common import EntityId
from deepaha.core.settings import Settings, get_settings
from deepaha.db.session import get_engine, get_write_session
from deepaha.personal.profile import idempotency_key_sha256
from deepaha.review.auth import (
    ReviewerAuthenticationError,
    ReviewerPrincipal,
    ReviewerRole,
    require_reviewer_authority,
    resolve_reviewer_principal,
)
from deepaha.review.schemas import (
    ApprovedLabelResult,
    ApprovedLabelWrite,
    ConfidenceAssessmentResult,
    ConfidenceAssessmentWrite,
    FeedbackAdjudicationResult,
    FeedbackAdjudicationWrite,
    ReviewCaseDetail,
    ReviewQueuePage,
)
from deepaha.review.service import ReviewIdempotencyConflict, ReviewService, ReviewUnavailable

router = APIRouter(prefix="/api/v1/review/feedback", tags=["review"])


class ReviewProblemDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    title: str
    status: int
    detail: str
    instance: str


class ReviewApiProblem(Exception):
    def __init__(
        self,
        *,
        status: int,
        slug: str,
        title: str,
        detail: str,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.slug = slug
        self.title = title
        self.detail = detail


def review_problem_response(error: ReviewApiProblem) -> JSONResponse:
    return JSONResponse(
        status_code=error.status,
        content=ReviewProblemDetails(
            type=f"https://deepaha.example/problems/{error.slug}",
            title=error.title,
            status=error.status,
            detail=error.detail,
            instance="/api/v1/review/feedback/resource",
        ).model_dump(mode="json"),
        headers={"Cache-Control": PRIVATE_CACHE_CONTROL},
    )


def review_invalid_request_response() -> JSONResponse:
    return review_problem_response(
        ReviewApiProblem(
            status=400,
            slug="invalid-review-request",
            title="Invalid review request",
            detail="The review request is invalid.",
        )
    )


def review_unavailable_response() -> JSONResponse:
    return review_problem_response(
        ReviewApiProblem(
            status=503,
            slug="review-service-unavailable",
            title="Review service unavailable",
            detail="The review service is temporarily unavailable.",
        )
    )


def _factory(session: Session) -> sessionmaker[Session]:
    return sessionmaker(bind=session.get_bind(), expire_on_commit=False)


def get_review_service(
    session: Annotated[Session, Depends(get_write_session)],
) -> ReviewService:
    return ReviewService(
        session_factory=_factory(session),
        now_factory=lambda: datetime.now(UTC),
    )


def require_reviewer_principal(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReviewerPrincipal:
    values = request.headers.getlist("authorization")
    try:
        if len(values) != 1:
            raise ReviewerAuthenticationError("reviewer authentication failed")
        engine = get_engine(settings)
        try:
            with Session(engine) as session:
                return resolve_reviewer_principal(values[0], session, settings)
        finally:
            engine.dispose()
    except ReviewerAuthenticationError as error:
        raise ReviewApiProblem(
            status=401,
            slug="reviewer-authentication-failed",
            title="Reviewer authentication failed",
            detail="Reviewer authentication failed.",
        ) from error


def require_review_idempotency_key(request: Request) -> str:
    values = request.headers.getlist("idempotency-key")
    if len(values) != 1:
        raise _invalid()
    try:
        idempotency_key_sha256(values[0])
    except ValueError as error:
        raise _invalid() from error
    return values[0]


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = PRIVATE_CACHE_CONTROL


def _authorize(principal: ReviewerPrincipal, role: ReviewerRole) -> None:
    try:
        require_reviewer_authority(principal, role)
    except ReviewerAuthenticationError as error:
        raise ReviewApiProblem(
            status=403,
            slug="reviewer-authorization-failed",
            title="Reviewer authorization failed",
            detail="Reviewer authorization failed.",
        ) from error


def _invalid() -> ReviewApiProblem:
    return ReviewApiProblem(
        status=400,
        slug="invalid-review-request",
        title="Invalid review request",
        detail="The review request is invalid.",
    )


def _not_found() -> ReviewApiProblem:
    return ReviewApiProblem(
        status=404,
        slug="review-resource-not-found",
        title="Review resource not found",
        detail="The review resource was not found.",
    )


def _conflict() -> ReviewApiProblem:
    return ReviewApiProblem(
        status=409,
        slug="review-idempotency-conflict",
        title="Review idempotency conflict",
        detail="The idempotency key was already used for a different request.",
    )


@router.get("")
def list_review_queue(
    response: Response,
    principal: Annotated[ReviewerPrincipal, Depends(require_reviewer_principal)],
    service: Annotated[ReviewService, Depends(get_review_service)],
) -> ReviewQueuePage:
    _authorize(principal, ReviewerRole.FEEDBACK_REVIEWER)
    result = service.list_queue(principal)
    _private(response)
    return result


@router.get("/{review_case_id}")
def get_review_case(
    review_case_id: EntityId,
    response: Response,
    principal: Annotated[ReviewerPrincipal, Depends(require_reviewer_principal)],
    service: Annotated[ReviewService, Depends(get_review_service)],
) -> ReviewCaseDetail:
    _authorize(principal, ReviewerRole.FEEDBACK_REVIEWER)
    result = service.get_case(principal, review_case_id)
    if result is None:
        raise _not_found()
    _private(response)
    return result


@router.post("/{review_case_id}/assessments", status_code=status.HTTP_201_CREATED)
def append_assessment(
    review_case_id: EntityId,
    command: ConfidenceAssessmentWrite,
    response: Response,
    principal: Annotated[ReviewerPrincipal, Depends(require_reviewer_principal)],
    idempotency_key: Annotated[str, Depends(require_review_idempotency_key)],
    service: Annotated[ReviewService, Depends(get_review_service)],
) -> ConfidenceAssessmentResult:
    _authorize(principal, ReviewerRole.FEEDBACK_REVIEWER)
    try:
        result = service.append_assessment(
            principal,
            review_case_id,
            command,
            idempotency_key=idempotency_key,
        )
    except ReviewIdempotencyConflict as error:
        raise _conflict() from error
    except ReviewUnavailable as error:
        raise _not_found() from error
    if result is None:
        raise _not_found()
    _private(response)
    return result


@router.post("/{review_case_id}/adjudications", status_code=status.HTTP_201_CREATED)
def append_adjudication(
    review_case_id: EntityId,
    command: FeedbackAdjudicationWrite,
    response: Response,
    principal: Annotated[ReviewerPrincipal, Depends(require_reviewer_principal)],
    idempotency_key: Annotated[str, Depends(require_review_idempotency_key)],
    service: Annotated[ReviewService, Depends(get_review_service)],
) -> FeedbackAdjudicationResult:
    _authorize(principal, ReviewerRole.FEEDBACK_ADJUDICATOR)
    try:
        result = service.append_adjudication(
            principal,
            review_case_id,
            command,
            idempotency_key=idempotency_key,
        )
    except ReviewIdempotencyConflict as error:
        raise _conflict() from error
    except ReviewUnavailable as error:
        raise _not_found() from error
    if result is None:
        raise _not_found()
    _private(response)
    return result


@router.post("/{review_case_id}/labels", status_code=status.HTTP_201_CREATED)
def create_label(
    review_case_id: EntityId,
    command: ApprovedLabelWrite,
    response: Response,
    principal: Annotated[ReviewerPrincipal, Depends(require_reviewer_principal)],
    idempotency_key: Annotated[str, Depends(require_review_idempotency_key)],
    service: Annotated[ReviewService, Depends(get_review_service)],
) -> ApprovedLabelResult:
    _authorize(principal, ReviewerRole.LABEL_CURATOR)
    try:
        result = service.create_label(
            principal,
            review_case_id,
            command,
            idempotency_key=idempotency_key,
        )
    except ReviewIdempotencyConflict as error:
        raise _conflict() from error
    except ReviewUnavailable as error:
        raise _not_found() from error
    if result is None:
        raise _not_found()
    _private(response)
    return result


__all__ = [
    "ReviewApiProblem",
    "get_review_service",
    "require_reviewer_principal",
    "review_invalid_request_response",
    "review_problem_response",
    "review_unavailable_response",
    "router",
]
