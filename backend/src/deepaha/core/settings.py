from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    database_url: str | None = None
    object_store_endpoint: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:55000")
    object_store_region: str = "us-east-1"
    object_store_bucket: str = "deepaha-raw"
    object_store_access_key: str | None = None
    object_store_secret_key: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
