import pytest

from deepaha.core.settings import Settings


def test_settings_have_versioned_defaults() -> None:
    settings = Settings()

    assert settings.app_name == "deepaha-api"
    assert settings.app_version == "0.1.0"
    assert settings.api_version == "v1"
    assert settings.contract_version == "0.1.0"


def test_settings_read_prefixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPAHA_ENVIRONMENT", "test")

    assert Settings().environment == "test"


def test_settings_read_phase1_storage_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DEEPAHA_DATABASE_URL",
        "postgresql+psycopg://deepaha:local@127.0.0.1:55432/deepaha",
    )
    monkeypatch.setenv("DEEPAHA_OBJECT_STORE_ENDPOINT", "http://127.0.0.1:55000")
    monkeypatch.setenv("DEEPAHA_OBJECT_STORE_BUCKET", "deepaha-raw")
    monkeypatch.setenv("DEEPAHA_OBJECT_STORE_ACCESS_KEY", "local-access")
    monkeypatch.setenv("DEEPAHA_OBJECT_STORE_SECRET_KEY", "local-secret")

    settings = Settings()

    assert settings.database_url is not None
    assert settings.object_store_secret_key is not None
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert str(settings.object_store_endpoint) == "http://127.0.0.1:55000/"
    assert settings.object_store_bucket == "deepaha-raw"
    assert settings.object_store_access_key == "local-access"
    assert settings.object_store_secret_key.get_secret_value() == "local-secret"
    assert "local-secret" not in repr(settings)
