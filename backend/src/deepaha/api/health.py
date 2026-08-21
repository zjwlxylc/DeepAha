from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from deepaha.core.settings import Settings, get_settings

router = APIRouter(prefix="/api/v1", tags=["system"])


class HealthResponse(BaseModel):
    status: Literal["ok"]


class VersionResponse(BaseModel):
    app: str
    version: str
    api_version: str
    contract_version: str


@router.get("/health/live", response_model=HealthResponse)
def live() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=HealthResponse)
def ready() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/version", response_model=VersionResponse)
def version(settings: Settings = Depends(get_settings)) -> VersionResponse:
    return VersionResponse(
        app=settings.app_name,
        version=settings.app_version,
        api_version=settings.api_version,
        contract_version=settings.contract_version,
    )
