from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from deepaha.db.session import get_read_only_session
from deepaha.public_catalog.cursor import InvalidCursor
from deepaha.public_catalog.schemas import (
    PublicOpportunityDetail,
    PublicOpportunityPage,
    PublicOpportunityQuery,
)
from deepaha.public_catalog.service import PublicCatalogService

router = APIRouter(prefix="/api/v1/public", tags=["public-opportunities"])
CACHE_CONTROL = "public, max-age=60, stale-while-revalidate=300"
QUERY_KEYS = frozenset({"q", "type", "status", "region", "sort", "cursor", "limit"})


class ProblemDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    title: str
    status: int
    detail: str
    instance: str


def get_public_catalog_service(
    session: Annotated[Session, Depends(get_read_only_session)],
) -> PublicCatalogService:
    return PublicCatalogService(session)


def _problem(
    request: Request,
    *,
    status: int,
    slug: str,
    title: str,
    detail: str,
) -> JSONResponse:
    body = ProblemDetails(
        type=f"https://deepaha.example/problems/{slug}",
        title=title,
        status=status,
        detail=detail,
        instance=request.url.path,
    )
    return JSONResponse(
        status_code=status,
        content=body.model_dump(mode="json"),
        media_type="application/problem+json",
    )


def public_catalog_unavailable_response(request: Request) -> JSONResponse:
    return _problem(
        request,
        status=503,
        slug="public-catalog-unavailable",
        title="Public opportunity catalog unavailable",
        detail="The public opportunity catalog is temporarily unavailable.",
    )


def _parse_query(request: Request) -> PublicOpportunityQuery:
    values: dict[str, str] = {}
    for key, value in request.query_params.multi_items():
        if key not in QUERY_KEYS or key in values:
            raise ValueError("unknown or repeated public query parameter")
        values[key] = value
    return PublicOpportunityQuery.model_validate(values)


@router.get(
    "/opportunities",
    response_model=PublicOpportunityPage,
    responses={400: {"model": ProblemDetails}, 503: {"model": ProblemDetails}},
)
def list_public_opportunities(
    request: Request,
    response: Response,
    service: Annotated[PublicCatalogService, Depends(get_public_catalog_service)],
) -> PublicOpportunityPage | JSONResponse:
    try:
        query = _parse_query(request)
    except ValueError, ValidationError:
        return _problem(
            request,
            status=400,
            slug="invalid-public-query",
            title="Invalid public opportunity query",
            detail="The public opportunity query is invalid.",
        )
    try:
        result = service.list_opportunities(query)
    except InvalidCursor:
        return _problem(
            request,
            status=400,
            slug="invalid-public-cursor",
            title="Invalid public opportunity cursor",
            detail="The pagination cursor is invalid or no longer reproducible.",
        )
    except SQLAlchemyError:
        return public_catalog_unavailable_response(request)
    response.headers["Cache-Control"] = CACHE_CONTROL
    return result


@router.get(
    "/opportunities/{public_id}",
    response_model=PublicOpportunityDetail,
    responses={404: {"model": ProblemDetails}, 503: {"model": ProblemDetails}},
)
def get_public_opportunity(
    public_id: str,
    request: Request,
    response: Response,
    service: Annotated[PublicCatalogService, Depends(get_public_catalog_service)],
) -> PublicOpportunityDetail | JSONResponse:
    try:
        result = service.get_opportunity(public_id)
    except SQLAlchemyError:
        return public_catalog_unavailable_response(request)
    if result is None:
        return _problem(
            request,
            status=404,
            slug="public-opportunity-not-found",
            title="Public opportunity not found",
            detail="The governed public opportunity was not found.",
        )
    response.headers["Cache-Control"] = CACHE_CONTROL
    return result
