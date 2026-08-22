import logging
import re
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import JSONResponse

from deepaha.api.health import router as system_router
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

    @application.exception_handler(SQLAlchemyError)
    async def database_dependency_failure(
        request: Request,
        _error: SQLAlchemyError,
    ) -> JSONResponse:
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
    return application


app = create_app()
