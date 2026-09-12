from pathlib import Path
from typing import Any
from unittest.mock import Mock
from uuid import uuid7

import pytest
from fastapi.testclient import TestClient

from deepaha.api.investigations import get_investigation_store
from deepaha.api.local_human_test import require_local_test_principal
from deepaha.core.settings import Settings, get_settings
from deepaha.investigations.contracts import InvestigationError
from deepaha.main import create_app
from deepaha.review.auth import ReviewerPrincipal, ReviewerRole


def make_client(
    tmp_path: Path,
    *,
    enabled: bool = True,
    roles: frozenset[ReviewerRole] | None = None,
    purposes: frozenset[str] | None = None,
    synthetic: bool = True,
) -> tuple[TestClient, Mock]:
    app = create_app()
    store = Mock()
    app.dependency_overrides[get_settings] = lambda: Settings(
        local_human_test_enabled=enabled, local_human_test_root=tmp_path
    )
    app.dependency_overrides[get_investigation_store] = lambda: store
    app.dependency_overrides[require_local_test_principal] = lambda: ReviewerPrincipal(
        uuid7(),
        roles if roles is not None else frozenset({ReviewerRole.LOCAL_TEST_OPERATOR}),
        purposes if purposes is not None else frozenset({"OPPORTUNITY_FACT_VALIDATION"}),
        synthetic,
    )
    return TestClient(app, base_url="http://127.0.0.1"), store


@pytest.mark.parametrize("suffix", ["", "/sources", "/binding-targets", "/" + str(uuid7())])
def test_disabled_intake_stays_hidden(tmp_path: Path, suffix: str) -> None:
    client, store = make_client(tmp_path, enabled=False)
    with client:
        response = client.get("/api/v1/local-human-test/investigations" + suffix)
    assert response.status_code == 404
    assert not store.mock_calls


def test_unrelated_reviewer_cannot_read_intake(tmp_path: Path) -> None:
    client, store = make_client(tmp_path, roles=frozenset({ReviewerRole.FEEDBACK_REVIEWER}))
    with client:
        response = client.get("/api/v1/local-human-test/investigations")
    assert response.status_code == 403
    assert not store.mock_calls


def test_registration_requires_idempotency_and_never_dispatches(tmp_path: Path) -> None:
    client, store = make_client(tmp_path)
    payload: dict[str, Any] = {
        "source_id": str(uuid7()),
        "endpoint_id": str(uuid7()),
        "notice_url": "https://official.example/a",
        "brief": "公开调查",
    }
    store.create.return_value = uuid7()
    store.get.return_value = {"status": "QUEUED"}
    with client:
        missing = client.post("/api/v1/local-human-test/investigations", json=payload)
        created = client.post(
            "/api/v1/local-human-test/investigations",
            json=payload,
            headers={"Idempotency-Key": "synthetic-request"},
        )
    assert missing.status_code == 400
    assert created.status_code == 201
    assert created.json()["status"] == "QUEUED"
    assert created.headers["cache-control"] == "private, no-store"
    assert [call[0] for call in store.mock_calls] == ["create", "get"]


def test_domain_failure_only_exposes_stable_code(tmp_path: Path) -> None:
    client, store = make_client(tmp_path)
    store.get.side_effect = InvestigationError("INVESTIGATION_NOT_FOUND")
    with client:
        response = client.get(f"/api/v1/local-human-test/investigations/{uuid7()}")
    assert response.status_code == 404
    assert response.json() == {"detail": {"code": "INVESTIGATION_NOT_FOUND"}}


def test_review_must_supply_current_delivery_hash(tmp_path: Path) -> None:
    client, store = make_client(tmp_path)
    with client:
        response = client.post(
            f"/api/v1/local-human-test/investigations/{uuid7()}/review",
            json={"decision": "APPROVE", "reason": "Synthetic"},
            headers={"Idempotency-Key": "synthetic-review"},
        )
    assert response.status_code == 400
    assert not store.mock_calls


def test_document_preparation_requires_frozen_delivery_and_returns_private_receipt(
    tmp_path: Path,
) -> None:
    client, store = make_client(tmp_path)
    task_id = uuid7()
    store.prepare_documents.return_value = {
        "status": "PENDING_REVIEW",
        "document_preparation": {"status": "PREPARED"},
    }
    with client:
        missing = client.post(
            f"/api/v1/local-human-test/investigations/{task_id}/documents", json={}
        )
        result = client.post(
            f"/api/v1/local-human-test/investigations/{task_id}/documents",
            json={"delivery_hash": "a" * 64},
        )
    assert missing.status_code == 400
    assert result.status_code == 200
    assert result.json()["document_preparation"]["status"] == "PREPARED"
    assert result.headers["cache-control"] == "private, no-store"
    store.prepare_documents.assert_called_once()
    assert store.prepare_documents.call_args.args[:2] == (task_id, "a" * 64)


def test_disabled_document_preparation_cannot_parse(tmp_path: Path) -> None:
    client, store = make_client(tmp_path, enabled=False)
    with client:
        result = client.post(
            f"/api/v1/local-human-test/investigations/{uuid7()}/documents",
            json={"delivery_hash": "a" * 64},
        )
    assert result.status_code == 404
    assert not store.mock_calls


def test_binding_requires_exact_contract_and_idempotency(tmp_path: Path) -> None:
    client, store = make_client(tmp_path)
    task_id = uuid7()
    payload = {
        "delivery_hash": "a" * 64,
        "opportunity_id": str(uuid7()),
        "opportunity_version": 1,
        "reason": "Synthetic association",
        "positions": [],
    }
    store.bind.return_value = {"entity_binding": {"scope": "ENTITY_ASSOCIATION_ONLY"}}
    with client:
        missing_key = client.post(
            f"/api/v1/local-human-test/investigations/{task_id}/bindings", json=payload
        )
        invalid = client.post(
            f"/api/v1/local-human-test/investigations/{task_id}/bindings",
            json=payload | {"opportunity_version": 0},
            headers={"Idempotency-Key": "one"},
        )
        result = client.post(
            f"/api/v1/local-human-test/investigations/{task_id}/bindings",
            json=payload,
            headers={"Idempotency-Key": "one"},
        )
    assert missing_key.status_code == invalid.status_code == 400
    assert result.status_code == 200
    assert result.headers["cache-control"] == "private, no-store"
    store.bind.assert_called_once()


def test_disabled_binding_cannot_mutate(tmp_path: Path) -> None:
    client, store = make_client(tmp_path, enabled=False)
    with client:
        result = client.post(
            f"/api/v1/local-human-test/investigations/{uuid7()}/bindings",
            json={
                "delivery_hash": "a" * 64,
                "opportunity_id": str(uuid7()),
                "opportunity_version": 1,
                "reason": "Synthetic association",
            },
            headers={"Idempotency-Key": "one"},
        )
    assert result.status_code == 404
    assert not store.mock_calls


@pytest.mark.parametrize("kind", ["identity", "positions"])
def test_identity_endpoints_require_key_and_return_private_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    client, store = make_client(tmp_path)
    method = Mock(return_value={"status": "APPROVED", "entity_binding": {"sequence": 1}})
    monkeypatch.setattr(f"deepaha.investigations.registration.register_{kind}", method)
    payload: dict[str, Any] = {
        "delivery_hash": "a" * 64,
        "reason": "Synthetic registration",
        "positions": [],
    }
    if kind == "identity":
        payload.update(canonical_title="Test", type="PUBLIC_INSTITUTION_JOB", issuer_name="Test")
    else:
        payload.update(
            previous_binding_id=str(uuid7()),
            positions=[
                {
                    "entity_id": "post",
                    "unit_key": "P01",
                    "label": "Synthetic post",
                }
            ],
        )
    with client:
        path = f"/api/v1/local-human-test/investigations/{uuid7()}/{kind}"
        missing = client.post(path, json=payload)
        result = client.post(path, json=payload, headers={"Idempotency-Key": "synthetic-identity"})
    assert missing.status_code == 400
    assert result.status_code == 200
    assert result.headers["cache-control"] == "private, no-store"
    assert method.call_count == 1


@pytest.mark.parametrize("kind", ["identity", "positions"])
@pytest.mark.parametrize("enabled", [True, False])
def test_identity_routes_preserve_intake_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, enabled: bool
) -> None:
    client, store = make_client(
        tmp_path, enabled=enabled, roles=frozenset({ReviewerRole.FEEDBACK_REVIEWER})
    )
    method = Mock()
    monkeypatch.setattr(f"deepaha.investigations.registration.register_{kind}", method)
    with client:
        response = client.post(
            f"/api/v1/local-human-test/investigations/{uuid7()}/{kind}",
            json={},
            headers={"Idempotency-Key": "synthetic"},
        )
    assert response.status_code == (403 if enabled else 404)
    method.assert_not_called()
    assert not store.mock_calls


@pytest.mark.parametrize("suffix", ["facts", "facts/decisions", "facts/promotions"])
def test_fact_routes_validate_inputs_key_and_return_private_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str
) -> None:
    client, store = make_client(tmp_path)
    method = Mock()
    monkeypatch.setattr(
        "deepaha.investigations.facts."
        + ("prepare_facts" if suffix == "facts" else "act_on_facts"),
        method,
    )
    store.get.return_value = {"fact_review": {"scope": "INDEPENDENT_FACT_REVIEW"}}
    payload: dict[str, Any] = {
        "delivery_hash": "a" * 64,
        "binding_id": str(uuid7()),
        "check_id": str(uuid7()),
    }
    if suffix != "facts":
        payload.update(preparation_id=str(uuid7()), reason="Synthetic review")
        if suffix.endswith("decisions"):
            payload.update(
                candidate_id=str(uuid7()),
                decision="APPROVE",
                evidence_support="SUPPORTED",
                precedence_check="PASSED",
            )
        else:
            payload.update(entity_id="position-1")
    with client:
        path = f"/api/v1/local-human-test/investigations/{uuid7()}/{suffix}"
        invalid = client.post(path, json={}, headers={"Idempotency-Key": "test"})
        assert invalid.status_code == 400
        if suffix != "facts":
            assert client.post(path, json=payload).status_code == 400
        result = client.post(path, json=payload, headers={"Idempotency-Key": "test"})
    assert result.status_code == 200
    assert result.headers["cache-control"] == "private, no-store"
    assert result.json() == store.get.return_value
    method.assert_called_once()


@pytest.mark.parametrize("suffix", ["facts", "facts/decisions", "facts/promotions"])
@pytest.mark.parametrize(
    "enabled,roles,expected",
    [
        (False, None, 404),
        (True, frozenset({ReviewerRole.FEEDBACK_REVIEWER}), 403),
    ],
)
def test_fact_routes_cannot_bypass_intake_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    enabled: bool,
    roles: frozenset[ReviewerRole] | None,
    expected: int,
) -> None:
    client, store = make_client(tmp_path, enabled=enabled, roles=roles)
    method = Mock()
    monkeypatch.setattr("deepaha.investigations.facts.prepare_facts", method)
    monkeypatch.setattr("deepaha.investigations.facts.act_on_facts", method)
    with client:
        result = client.post(
            f"/api/v1/local-human-test/investigations/{uuid7()}/{suffix}",
            json={},
            headers={"Idempotency-Key": "test"},
        )
    assert result.status_code == expected
    method.assert_not_called()
    assert not store.mock_calls


@pytest.mark.parametrize("suffix", ["rules", "rules/decisions"])
def test_rule_routes_validate_and_return_private_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str
) -> None:
    client, store = make_client(tmp_path)
    method = Mock()
    monkeypatch.setattr(
        "deepaha.investigations.rules." + ("prepare_rules" if suffix == "rules" else "decide_rule"),
        method,
    )
    store.get.return_value = {"rule_review": {"current": [], "history": []}}
    payload: dict[str, Any] = {
        "delivery_hash": "a" * 64,
        "binding_id": str(uuid7()),
        "check_id": str(uuid7()),
        "fact_preparation_id": str(uuid7()),
        "entity_id": "post",
        "fact_set_id": str(uuid7()),
    }
    if suffix != "rules":
        payload.update(
            rule_preparation_id=str(uuid7()),
            rule_candidate_id=str(uuid7()),
            decision="NEEDS_ADJUDICATION",
            evidence=[],
            reason="Synthetic review",
        )
    with client:
        path = f"/api/v1/local-human-test/investigations/{uuid7()}/{suffix}"
        assert client.post(path, json={}, headers={"Idempotency-Key": "test"}).status_code == 400
        if suffix != "rules":
            assert client.post(path, json=payload).status_code == 400
        result = client.post(path, json=payload, headers={"Idempotency-Key": "test"})
    assert result.status_code == 200
    assert result.headers["cache-control"] == "private, no-store"
    assert result.json() == store.get.return_value
    method.assert_called_once()


@pytest.mark.parametrize("suffix", ["rules", "rules/decisions"])
@pytest.mark.parametrize("enabled", [True, False])
def test_rule_routes_preserve_access_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str, enabled: bool
) -> None:
    client, store = make_client(
        tmp_path, enabled=enabled, roles=frozenset({ReviewerRole.FEEDBACK_REVIEWER})
    )
    method = Mock()
    monkeypatch.setattr("deepaha.investigations.rules.prepare_rules", method)
    monkeypatch.setattr("deepaha.investigations.rules.decide_rule", method)
    with client:
        result = client.post(
            f"/api/v1/local-human-test/investigations/{uuid7()}/{suffix}",
            json={},
            headers={"Idempotency-Key": "test"},
        )
    assert result.status_code == (403 if enabled else 404)
    method.assert_not_called()
    assert not store.mock_calls
