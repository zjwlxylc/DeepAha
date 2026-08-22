import logging
import re
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import JSONResponse

from deepaha.api.health import router as system_router
from deepaha.api.personal import (
    PersonalApiProblem,
    personal_invalid_request_response,
    personal_problem_response,
    personal_unavailable_response,
)
from deepaha.api.personal import router as personal_router
from deepaha.api.public_opportunities import public_catalog_unavailable_response
from deepaha.api.public_opportunities import router as public_opportunities_router
from deepaha.core.logging import configure_logging
from deepaha.core.settings import get_settings

REQUEST_ID_PATTERN = re.compile(r"^[!-~]{1,128}$")
logger = logging.getLogger("deepaha.http")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    application = FastAPI(title="DeepAha API", version=settings.app_version)

    @application.exception_handler(PersonalApiProblem)
    async def personal_problem(
        _request: Request,
        error: PersonalApiProblem,
    ) -> JSONResponse:
        return personal_problem_response(error)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(
        request: Request,
        error: RequestValidationError,
    ) -> Response:
        if request.url.path.startswith("/api/v1/me"):
            return personal_invalid_request_response()
        return await request_validation_exception_handler(request, error)

    @application.exception_handler(SQLAlchemyError)
    async def database_dependency_failure(
        request: Request,
        _error: SQLAlchemyError,
    ) -> JSONResponse:
        if request.url.path.startswith("/api/v1/me"):
            return personal_unavailable_response()
        return public_catalog_unavailable_response(request)

    @application.middleware("http")
    async def request_context(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        candidate = request.headers.get("X-Request-ID", "")
        request_id = candidate if REQUEST_ID_PATTERN.fullmatch(candidate) else uuid4().hex
        started = perf_counter()
        response = await call_next(request)
        duration_ms = round((perf_counter() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "http_request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "request_id": request_id,
            },
        )
        return response

    application.include_router(system_router)
    application.include_router(public_opportunities_router)
    application.include_router(personal_router)
    return application


app = create_app()
