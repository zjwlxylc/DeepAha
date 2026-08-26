from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from deepaha.api.local_human_test import (
    get_local_provider_config_store,
    require_local_test_principal,
)
from deepaha.core.settings import Settings, get_settings
from deepaha.local_human_test.provider_config import (
    ProviderConfigIdempotencyConflict,
    ProviderConfigStatus,
    SaveProviderConfig,
)
from deepaha.main import create_app
from deepaha.review.auth import ReviewerPrincipal, ReviewerRole

NOW = datetime(2026, 8, 26, 10, 0, tzinfo=UTC)
REVIEWER_ID = UUID("019d0000-0000-7000-8000-000000000701")


class FakeProviderStore:
    def __init__(self) -> None:
        self.saved: SaveProviderConfig | None = None
        self.read_count = 0
        self.saved_key: str | None = None
        self.saved_model_id: str | None = None

    def status(self) -> ProviderConfigStatus:
        self.read_count += 1
        return ProviderConfigStatus(
            configured=self.saved is not None,
            provider=None if self.saved is None else self.saved.provider,
            base_url=None if self.saved is None else str(self.saved.base_url).rstrip("/"),
            protocol=None if self.saved is None else self.saved.protocol,
            model_id=None if self.saved is None else self.saved.model_id,
            model_snapshot=None if self.saved is None else self.saved.model_snapshot,
            provider_region=None if self.saved is None else self.saved.provider_region,
            zero_retention=None if self.saved is None else self.saved.zero_retention,
            training_use=None if self.saved is None else self.saved.training_use,
            supports_idempotency=(None if self.saved is None else self.saved.supports_idempotency),
            egress_ready=(self.saved is not None and self.saved.provider_region != "unknown"),
            updated_at=None if self.saved is None else NOW,
        )

    def save(
        self,
        command: SaveProviderConfig,
        *,
        idempotency_key: str,
    ) -> ProviderConfigStatus:
        if (
            self.saved_key == idempotency_key
            and self.saved_model_id is not None
            and self.saved_model_id != command.model_id
        ):
            raise ProviderConfigIdempotencyConflict("must not expose either request")
        self.saved = command
        self.saved_key = idempotency_key
        self.saved_model_id = command.model_id
        return self.status()

    def delete_secret(self) -> ProviderConfigStatus:
        self.saved = None
        return self.status()


def _settings(*, enabled: bool = True) -> Settings:
    return Settings(
        environment="development",
        reviewer_auth_mode="fixture",
        local_human_test_enabled=enabled,
        local_human_test_root=Path("C:/local/deepaha-human-test"),
    )


def _principal(*roles: ReviewerRole) -> ReviewerPrincipal:
    return ReviewerPrincipal(
        reviewer_id=REVIEWER_ID,
        roles=frozenset(roles),
        purposes=frozenset({"OPPORTUNITY_FACT_VALIDATION"}),
        synthetic=False,
    )


@pytest.fixture
def client() -> Iterator[tuple[TestClient, FakeProviderStore]]:
    application = create_app()
    store = FakeProviderStore()
    application.dependency_overrides[get_settings] = _settings
    application.dependency_overrides[require_local_test_principal] = lambda: _principal(
        ReviewerRole.LOCAL_TEST_OPERATOR,
        ReviewerRole.VALIDATION_REVIEWER,
    )
    application.dependency_overrides[get_local_provider_config_store] = lambda: store
    with TestClient(application, base_url="http://127.0.0.1") as value:
        yield value, store
    application.dependency_overrides.clear()


def test_provider_status_never_returns_secret(
    client: tuple[TestClient, FakeProviderStore],
) -> None:
    api, _store = client

    response = api.get("/api/v1/local-human-test/config/provider")

    assert response.status_code == 200
    assert "api_key" not in response.text
    assert "protected_api_key" not in response.text
    assert response.json()["configured"] is False


def test_provider_save_requires_idempotency_and_returns_only_redacted_status(
    client: tuple[TestClient, FakeProviderStore],
) -> None:
    api, store = client
    body = {
        "provider": "agnes",
        "base_url": "https://provider.invalid",
        "protocol": "openai_chat_completions",
        "model_id": "agnes-chat",
        "model_snapshot": "agnes-chat-2026-08-26",
        "provider_region": "cn",
        "zero_retention": True,
        "training_use": False,
        "supports_idempotency": True,
        "api_key": "local-test-secret-value",
    }

    missing_key = api.put("/api/v1/local-human-test/config/provider", json=body)
    saved = api.put(
        "/api/v1/local-human-test/config/provider",
        json=body,
        headers={"Idempotency-Key": "provider-save-1"},
    )

    assert missing_key.status_code == 400
    assert saved.status_code == 200
    assert saved.json()["egress_ready"] is True
    assert "local-test-secret-value" not in saved.text
    assert store.saved is not None


def test_provider_save_same_key_different_body_is_redacted_conflict(
    client: tuple[TestClient, FakeProviderStore],
) -> None:
    api, _store = client
    body = {
        "provider": "agnes",
        "base_url": "https://provider.invalid",
        "protocol": "openai_chat_completions",
        "model_id": "agnes-chat",
        "model_snapshot": "agnes-chat-2026-08-26",
        "provider_region": "cn",
        "zero_retention": True,
        "training_use": False,
        "supports_idempotency": True,
        "api_key": "local-test-secret-value",
    }
    headers = {"Idempotency-Key": "provider-save-conflict"}

    first = api.put(
        "/api/v1/local-human-test/config/provider",
        json=body,
        headers=headers,
    )
    second = api.put(
        "/api/v1/local-human-test/config/provider",
        json=body | {"model_id": "different-model"},
        headers=headers,
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert "must not expose" not in second.text
    assert "local-test-secret-value" not in second.text


@pytest.mark.parametrize("host", ["example.com", "192.0.2.10", "10.0.0.8"])
def test_control_api_rejects_non_loopback_host(
    client: tuple[TestClient, FakeProviderStore],
    host: str,
) -> None:
    api, store = client

    response = api.get(
        "/api/v1/local-human-test/config/provider",
        headers={"Host": host},
    )

    assert response.status_code == 404
    assert store.read_count == 0


def test_disabled_feature_is_indistinguishable_from_missing_route(
    client: tuple[TestClient, FakeProviderStore],
) -> None:
    api, store = client
    cast(FastAPI, api.app).dependency_overrides[get_settings] = lambda: _settings(enabled=False)

    response = api.get("/api/v1/local-human-test/config/provider")

    assert response.status_code == 404
    assert store.read_count == 0


def test_operator_role_is_required(
    client: tuple[TestClient, FakeProviderStore],
) -> None:
    api, store = client
    cast(FastAPI, api.app).dependency_overrides[require_local_test_principal] = lambda: _principal(
        ReviewerRole.VALIDATION_REVIEWER
    )

    response = api.get("/api/v1/local-human-test/config/provider")

    assert response.status_code == 403
    assert store.read_count == 0


def test_invalid_local_provider_request_is_redacted_and_uses_stable_code(
    client: tuple[TestClient, FakeProviderStore],
) -> None:
    api, _store = client

    response = api.put(
        "/api/v1/local-human-test/config/provider",
        json={
            "provider": "agnes",
            "base_url": "https://provider.invalid",
            "protocol": "unsupported-protocol",
            "model_id": "agnes-chat",
            "model_snapshot": "agnes-chat-2026-08-26",
            "provider_region": "cn",
            "zero_retention": True,
            "training_use": False,
            "supports_idempotency": True,
            "api_key": "must-not-echo-this-secret",
        },
        headers={"Idempotency-Key": "invalid-provider"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": {"code": "INVALID_LOCAL_HUMAN_TEST_REQUEST"}}
    assert "must-not-echo-this-secret" not in response.text
