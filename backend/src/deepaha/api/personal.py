from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from starlette.responses import JSONResponse

from deepaha.contracts.phase6 import (
    PersonalActionSnapshotSchemaV05,
    PersonalRankingSnapshotSchemaV05,
    UserStateSnapshotSchemaV05,
)
from deepaha.core.settings import Settings, get_settings
from deepaha.db.session import get_engine, get_write_session
from deepaha.eligibility.service import EligibilityService
from deepaha.opportunities.models import Opportunity
from deepaha.personal.actions import ActionService, ActionUnavailable
from deepaha.personal.auth import (
    AuthenticationError,
    Principal,
    assert_fixture_auth_enabled,
    parse_bearer_token,
    resolve_principal,
)
from deepaha.personal.matching import PersonalMatchError, PersonalMatchService
from deepaha.personal.profile import (
    IdempotencyConflict,
    ProfileAccessError,
    ProfileService,
    idempotency_key_sha256,
)
from deepaha.personal.schemas import (
    ActionStatusWrite,
    MaterialPlanWrite,
    OfficialLinkResult,
    PersonalOpportunityDetail,
    PersonalPriorityItem,
    PersonalPriorityPage,
    ProfileWrite,
    SavedWrite,
)
from deepaha.public_catalog.service import PublicCatalogService
from deepaha.rules.major import load_approved_major_mapping, load_major_catalog

router = APIRouter(prefix="/api/v1/me", tags=["personal"])
PRIVATE_CACHE_CONTROL = "private, no-store"
FIXTURE_DIRECTORY = Path(__file__).parents[3] / "tests" / "fixtures" / "evaluation"


class PersonalProblemDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    title: str
    status: int
    detail: str
    instance: str


class PersonalApiProblem(Exception):
    def __init__(
        self,
        *,
        status: int,
        slug: str,
        title: str,
        detail: str,
        instance: str = "/api/v1/me/resource",
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.slug = slug
        self.title = title
        self.detail = detail
        self.instance = instance


def personal_problem_response(error: PersonalApiProblem) -> JSONResponse:
    body = PersonalProblemDetails(
        type=f"https://deepaha.example/problems/{error.slug}",
        title=error.title,
        status=error.status,
        detail=error.detail,
        instance=error.instance,
    )
    return JSONResponse(
        status_code=error.status,
        content=body.model_dump(mode="json"),
        headers={"Cache-Control": PRIVATE_CACHE_CONTROL},
        media_type="application/problem+json",
    )


def personal_invalid_request_response() -> JSONResponse:
    return personal_problem_response(
        PersonalApiProblem(
            status=400,
            slug="invalid-personal-request",
            title="Invalid personal request",
            detail="The personal request is invalid.",
        )
    )


def personal_unavailable_response() -> JSONResponse:
    return personal_problem_response(
        PersonalApiProblem(
            status=503,
            slug="personal-service-unavailable",
            title="Personal service unavailable",
            detail="The personal service is temporarily unavailable.",
        )
    )


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


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = PRIVATE_CACHE_CONTROL


def _factory(session: Session) -> sessionmaker[Session]:
    return sessionmaker(bind=session.get_bind(), expire_on_commit=False)


def _allow_synthetic_fixture_profile(settings: Settings) -> bool:
    return settings.personal_auth_mode == "fixture" and settings.environment in {
        "development",
        "test",
    }


def get_profile_service(
    session: Annotated[Session, Depends(get_write_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProfileService:
    return ProfileService(
        session_factory=_factory(session),
        now_factory=lambda: datetime.now(UTC),
        allow_synthetic_fixture_profile=_allow_synthetic_fixture_profile(settings),
    )


def get_personal_match_service(
    session: Annotated[Session, Depends(get_write_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PersonalMatchService:
    factory = _factory(session)
    profile_service = ProfileService(
        session_factory=factory,
        now_factory=lambda: datetime.now(UTC),
        allow_synthetic_fixture_profile=_allow_synthetic_fixture_profile(settings),
    )
    catalog = load_major_catalog(FIXTURE_DIRECTORY / "phase4-major-catalog.json")
    mapping = load_approved_major_mapping(
        FIXTURE_DIRECTORY / "phase4-major-mapping.json",
        catalog,
    )
    return PersonalMatchService(
        session_factory=factory,
        profile_service=profile_service,
        eligibility_service=EligibilityService(session_factory=factory),
        major_catalog=catalog,
        major_mapping=mapping,
        now_factory=lambda: datetime.now(UTC),
    )


def get_action_service(
    session: Annotated[Session, Depends(get_write_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ActionService:
    factory = _factory(session)
    return ActionService(
        session_factory=factory,
        profile_service=ProfileService(
            session_factory=factory,
            now_factory=lambda: datetime.now(UTC),
            allow_synthetic_fixture_profile=_allow_synthetic_fixture_profile(settings),
        ),
        now_factory=lambda: datetime.now(UTC),
    )


def require_principal(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    values = request.headers.getlist("authorization")
    try:
        assert_fixture_auth_enabled(settings)
        if len(values) != 1:
            raise AuthenticationError("personal authentication failed")
        parse_bearer_token(values[0])
        engine = get_engine(settings)
        try:
            with Session(engine) as session:
                return resolve_principal(values[0], session, settings)
        finally:
            engine.dispose()
    except AuthenticationError as error:
        raise PersonalApiProblem(
            status=401,
            slug="personal-authentication-failed",
            title="Personal authentication failed",
            detail="Personal authentication failed.",
        ) from error


def require_idempotency_key(request: Request) -> str:
    values = request.headers.getlist("idempotency-key")
    if len(values) != 1:
        raise personal_invalid_request()
    try:
        idempotency_key_sha256(values[0])
    except ValueError as error:
        raise personal_invalid_request() from error
    return values[0]


def personal_invalid_request() -> PersonalApiProblem:
    return PersonalApiProblem(
        status=400,
        slug="invalid-personal-request",
        title="Invalid personal request",
        detail="The personal request is invalid.",
    )


def _action_write[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except IdempotencyConflict as error:
        raise _conflict() from error
    except (ActionUnavailable, ProfileAccessError) as error:
        raise _not_found() from error


@router.get("/profile")
def get_profile(
    response: Response,
    principal: Annotated[Principal, Depends(require_principal)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
) -> UserStateSnapshotSchemaV05:
    result = service.get_current(principal)
    if result is None:
        raise _not_found()
    _private(response)
    return result


@router.put("/profile")
def put_profile(
    command: ProfileWrite,
    response: Response,
    principal: Annotated[Principal, Depends(require_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
) -> UserStateSnapshotSchemaV05:
    try:
        result = service.save(
            principal,
            command,
            idempotency_key=idempotency_key,
        )
    except IdempotencyConflict as error:
        raise _conflict() from error
    except ProfileAccessError as error:
        raise _not_found() from error
    _private(response)
    return result


@router.post("/matches")
def run_matches(
    response: Response,
    principal: Annotated[Principal, Depends(require_principal)],
    service: Annotated[PersonalMatchService, Depends(get_personal_match_service)],
) -> PersonalRankingSnapshotSchemaV05:
    try:
        result = service.run(principal)
    except PersonalMatchError as error:
        raise _not_found() from error
    _private(response)
    return result


@router.get("/matches/latest")
def get_latest_matches(
    response: Response,
    principal: Annotated[Principal, Depends(require_principal)],
    service: Annotated[PersonalMatchService, Depends(get_personal_match_service)],
) -> PersonalRankingSnapshotSchemaV05:
    result = service.get_latest(principal)
    if result is None:
        raise _not_found()
    _private(response)
    return result


@router.get("/opportunities", response_model=PersonalPriorityPage)
def get_personal_opportunities(
    response: Response,
    principal: Annotated[Principal, Depends(require_principal)],
    service: Annotated[PersonalMatchService, Depends(get_personal_match_service)],
    session: Annotated[Session, Depends(get_write_session)],
) -> PersonalPriorityPage:
    ranking = service.get_latest(principal)
    if ranking is None:
        raise _not_found()
    catalog = PublicCatalogService(session)
    items: list[PersonalPriorityItem] = []
    for ranking_item in ranking.items:
        public_id = session.scalar(
            select(Opportunity.public_id).where(
                Opportunity.opportunity_id == ranking_item.opportunity_id
            )
        )
        opportunity = None if public_id is None else catalog.get_opportunity(public_id)
        if opportunity is None:
            raise PersonalApiProblem(
                status=503,
                slug="personal-service-unavailable",
                title="Personal service unavailable",
                detail="The personal service is temporarily unavailable.",
            )
        items.append(
            PersonalPriorityItem(
                ranking=ranking_item,
                opportunity=opportunity,
            )
        )
    _private(response)
    return PersonalPriorityPage(
        ranking_snapshot_id=ranking.ranking_snapshot_id,
        items=tuple(items),
        omitted_rule_set_count=ranking.omitted_rule_set_count,
    )


@router.get(
    "/opportunities/{public_id}",
    response_model=PersonalOpportunityDetail,
)
def get_personal_opportunity(
    public_id: str,
    response: Response,
    principal: Annotated[Principal, Depends(require_principal)],
    match_service: Annotated[
        PersonalMatchService,
        Depends(get_personal_match_service),
    ],
    action_service: Annotated[ActionService, Depends(get_action_service)],
    session: Annotated[Session, Depends(get_write_session)],
) -> PersonalOpportunityDetail:
    opportunity = PublicCatalogService(session).get_opportunity(public_id)
    eligibility = match_service.get_eligibility(principal, public_id)
    if opportunity is None or eligibility is None:
        raise _not_found()
    result = PersonalOpportunityDetail(
        opportunity=opportunity,
        eligibility=eligibility,
        action=action_service.get_current(principal, public_id),
    )
    _private(response)
    return result


@router.get("/rankings/{snapshot_id}")
def get_ranking_snapshot(
    snapshot_id: UUID,
    response: Response,
    principal: Annotated[Principal, Depends(require_principal)],
    service: Annotated[PersonalMatchService, Depends(get_personal_match_service)],
) -> PersonalRankingSnapshotSchemaV05:
    result = service.get_snapshot(principal, snapshot_id)
    if result is None:
        raise _not_found()
    _private(response)
    return result


@router.get("/opportunities/{public_id}/action")
def get_action(
    public_id: str,
    response: Response,
    principal: Annotated[Principal, Depends(require_principal)],
    service: Annotated[ActionService, Depends(get_action_service)],
) -> PersonalActionSnapshotSchemaV05:
    result = service.get_current(principal, public_id)
    if result is None:
        raise _not_found()
    _private(response)
    return result


@router.put("/opportunities/{public_id}/saved")
def put_saved(
    public_id: str,
    command: SavedWrite,
    response: Response,
    principal: Annotated[Principal, Depends(require_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    service: Annotated[ActionService, Depends(get_action_service)],
) -> PersonalActionSnapshotSchemaV05:
    result = _action_write(
        lambda: service.set_saved(
            principal,
            public_id,
            command.saved,
            idempotency_key=idempotency_key,
        )
    )
    _private(response)
    return result


@router.put("/opportunities/{public_id}/status")
def put_status(
    public_id: str,
    command: ActionStatusWrite,
    response: Response,
    principal: Annotated[Principal, Depends(require_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    service: Annotated[ActionService, Depends(get_action_service)],
) -> PersonalActionSnapshotSchemaV05:
    result = _action_write(
        lambda: service.set_status(
            principal,
            public_id,
            command.state,
            idempotency_key=idempotency_key,
        )
    )
    _private(response)
    return result


@router.put("/opportunities/{public_id}/materials")
def put_materials(
    public_id: str,
    command: MaterialPlanWrite,
    response: Response,
    principal: Annotated[Principal, Depends(require_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    service: Annotated[ActionService, Depends(get_action_service)],
) -> PersonalActionSnapshotSchemaV05:
    result = _action_write(
        lambda: service.set_material_plan(
            principal,
            public_id,
            command.items,
            idempotency_key=idempotency_key,
        )
    )
    _private(response)
    return result


@router.post("/opportunities/{public_id}/official-link")
def post_official_link(
    public_id: str,
    response: Response,
    principal: Annotated[Principal, Depends(require_principal)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    service: Annotated[ActionService, Depends(get_action_service)],
) -> OfficialLinkResult:
    result = _action_write(
        lambda: service.record_official_link(
            principal,
            public_id,
            idempotency_key=idempotency_key,
        )
    )
    assert isinstance(result, OfficialLinkResult)
    _private(response)
    return result


__all__ = [
    "PersonalApiProblem",
    "get_action_service",
    "get_personal_match_service",
    "get_profile_service",
    "personal_invalid_request_response",
    "personal_problem_response",
    "personal_unavailable_response",
    "require_principal",
    "router",
]
