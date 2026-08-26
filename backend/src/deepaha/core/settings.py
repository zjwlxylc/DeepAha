from functools import lru_cache
from pathlib import Path
from typing import Final, Literal

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

RETRY_DELAYS_SECONDS: Final = (60, 300)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DEEPAHA_",
        extra="ignore",
        validate_default=True,
    )

    app_name: str = "deepaha-api"
    app_version: str = "0.1.0"
    api_version: str = "v1"
    contract_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"
    allow_live_source_check: bool = False
    personal_auth_mode: Literal["disabled", "fixture"] = "disabled"
    reviewer_auth_mode: Literal["disabled", "fixture"] = "disabled"
    local_human_test_enabled: bool = False
    local_human_test_root: Path | None = None
    local_human_test_bind_host: Literal["127.0.0.1", "localhost", "::1"] = "127.0.0.1"
    local_human_test_worker_id: str = "local-human-test-worker"
    local_human_test_lease_seconds: int = Field(default=60, ge=30, le=300)
    notification_worker_batch_size: int = Field(default=50, ge=1, le=100)
    notification_lease_seconds: int = Field(default=60, ge=10, le=3600)
    database_url: str | None = None
    object_store_endpoint: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:55000")
    object_store_region: str = "us-east-1"
    object_store_bucket: str = "deepaha-raw"
    object_store_access_key: str | None = None
    object_store_secret_key: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
