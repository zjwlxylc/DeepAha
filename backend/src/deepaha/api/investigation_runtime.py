from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from deepaha.api.investigations import PrincipalDep, StoreDep, list_sources, problem
from deepaha.api.local_human_test import require_local_human_test, require_local_idempotency_key
from deepaha.core.settings import Settings, get_settings
from deepaha.investigations.contracts import InvestigationError
from deepaha.investigations.local_config import (
    LocalWmaConfigStore,
    SaveWmaConfig,
    inspect_configuration,
)
from deepaha.investigations.runtime import worker_status
from deepaha.local_human_test.provider_config import WindowsDirectoryHardener, WindowsDpapiProtector
from deepaha.review.auth import (
    OPPORTUNITY_FACT_VALIDATION_PURPOSE,
    ReviewerAuthenticationError,
    ReviewerRole,
)

router = APIRouter(
    prefix="/api/v1/local-human-test/investigation-runtime",
    dependencies=[Depends(require_local_human_test)],
)
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_wma_config(settings: SettingsDep) -> LocalWmaConfigStore:
    if settings.local_human_test_root is None:
        raise HTTPException(404)
    return LocalWmaConfigStore(
        settings.local_human_test_root, WindowsDpapiProtector(), WindowsDirectoryHardener()
    )


ConfigDep = Annotated[LocalWmaConfigStore, Depends(get_wma_config)]


@router.get("")
def readiness(
    store: StoreDep,
    principal: PrincipalDep,
    config: ConfigDep,
    settings: SettingsDep,
    response: Response,
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "private, no-store"
    sources = list_sources(store, principal, response)["sources"]
    try:
        status = config.status()
    except InvestigationError as error:
        status = {"state": "UNREADABLE", "error_code": error.code}
    assert settings.local_human_test_root is not None
    worker = worker_status(
        settings.local_human_test_root, settings.database_url or "", datetime.now(UTC)
    )
    return {
        "login": "AUTHENTICATED",
        "database": "CONNECTED",
        "source_count": len(sources),
        "worker": worker,
        "wma": status,
        "dispatch_enabled": (
            worker["state"] == "RUNNING"
            and (status.get("state") if isinstance(status, dict) else None) == "CONNECTION_VERIFIED"
            and len(sources) > 0
        ),
    }


def require_operator(principal: PrincipalDep) -> None:
    if (
        principal.synthetic
        or ReviewerRole.LOCAL_TEST_OPERATOR not in principal.roles
        or OPPORTUNITY_FACT_VALIDATION_PURPOSE not in principal.purposes
    ):
        raise HTTPException(403, detail={"code": "REAL_OPERATOR_REQUIRED"})


@router.post("/configuration")
def save_config(
    command: SaveWmaConfig, principal: PrincipalDep, config: ConfigDep, response: Response
) -> dict[str, Any]:
    require_operator(principal)
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return config.save(command, principal.reviewer_id)
    except InvestigationError as error:
        raise problem(error) from None


@router.post("/check")
async def check_config(
    principal: PrincipalDep, config: ConfigDep, response: Response
) -> dict[str, Any]:
    require_operator(principal)
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return await inspect_configuration(config)
    except InvestigationError as error:
        raise problem(error) from None


@router.post("/tasks/{task_id}/dispatch")
def request_task_dispatch(
    task_id: UUID,
    store: StoreDep,
    principal: PrincipalDep,
    config: ConfigDep,
    response: Response,
    request_key: Annotated[str, Depends(require_local_idempotency_key)],
) -> dict[str, Any]:
    require_operator(principal)
    response.headers["Cache-Control"] = "private, no-store"
    try:
        status = config.status()
        if status.get("state") != "CONNECTION_VERIFIED":
            raise HTTPException(409, detail={"code": "WMA_CONNECTION_NOT_VERIFIED"})
        return store.request_dispatch(
            task_id,
            principal,
            configuration_revision=status["revision"],
            request_key=request_key,
            configuration_agent_id=status.get("agent_id"),
            configuration_source_app=status.get("source_app"),
        )
    except (InvestigationError, ReviewerAuthenticationError) as error:
        raise problem(error) from None
