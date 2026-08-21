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
