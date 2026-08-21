from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DEEPAHA_", extra="ignore")

    app_name: str = "deepaha-api"
    app_version: str = "0.1.0"
    api_version: str = "v1"
    contract_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
