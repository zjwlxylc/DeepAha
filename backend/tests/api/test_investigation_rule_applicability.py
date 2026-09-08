from pathlib import Path
from unittest.mock import Mock
from uuid import uuid7

import pytest

from deepaha.investigations.contracts import InvestigationError
from tests.api.test_investigations import make_client


@pytest.mark.parametrize("operation", ["read", "save"])
def test_private_applicability_routes_delegate_exact_context_and_cursor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    client, store = make_client(tmp_path)
    task, plan, source, candidate = (uuid7() for _ in range(4))
    body: dict[str, object] = {
        "target_plan_id": str(plan),
        "source_rule_preparation_id": str(source),
        "source_rule_candidate_id": str(candidate),
        "context_hash": "a" * 64,
        "previous_decision_id": None,
        "outcome": "NEEDS_ADJUDICATION",
        "reason": "Synthetic review awaiting scope evidence",
        "evidence": [],
    }
    service = Mock(return_value={"scope": "synthetic-only"})
    monkeypatch.setattr(
        f"deepaha.investigations.applicability.{operation}_rule_applicability", service
    )
    cursor = f"{uuid7()}:{uuid7()}"
    with client:
        response = (
            client.get(
                f"/api/v1/local-human-test/investigations/{task}/unit-plans/{plan}/rule-applicability/{source}/{candidate}",
                params={"after": cursor},
            )
            if operation == "read"
            else client.post(
                f"/api/v1/local-human-test/investigations/{task}/rule-applicability",
                json=body,
                headers={"Idempotency-Key": "scope-test"},
            )
        )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == service.return_value
    assert service.call_args.args[:2] == (store, task)
    if operation == "read":
        assert service.call_args.args[2:5] == (plan, source, candidate)
        assert service.call_args.kwargs == {"after": cursor}
    else:
        assert service.call_args.args[2].model_dump(mode="json") == body
        assert service.call_args.args[-1] == "scope-test"
    assert not store.mock_calls


@pytest.mark.parametrize(
    "code,status",
    [
        ("RULE_APPLICABILITY_CONTEXT_CHANGED", 409),
        ("RULE_APPLICABILITY_PREDECESSOR_CHANGED", 409),
        ("RULE_APPLICABILITY_SOURCE_NOT_FOUND", 404),
        ("HUMAN_VALIDATION_AUTHORITY_REQUIRED", 403),
    ],
)
def test_applicability_failures_are_private_not_old_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: str, status: int
) -> None:
    client, _ = make_client(tmp_path)
    monkeypatch.setattr(
        "deepaha.investigations.applicability.read_rule_applicability",
        Mock(side_effect=InvestigationError(code)),
    )
    with client:
        response = client.get(
            f"/api/v1/local-human-test/investigations/{uuid7()}/unit-plans/{uuid7()}/rule-applicability/{uuid7()}/{uuid7()}"
        )
    assert response.status_code == status
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == {"detail": {"code": code}}


def test_resolved_review_requires_evidence_before_calling_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = make_client(tmp_path)
    service = Mock()
    monkeypatch.setattr("deepaha.investigations.applicability.save_rule_applicability", service)
    body: dict[str, object] = {
        "target_plan_id": str(uuid7()),
        "source_rule_preparation_id": str(uuid7()),
        "source_rule_candidate_id": str(uuid7()),
        "context_hash": "a" * 64,
        "previous_decision_id": None,
        "outcome": "DOES_NOT_APPLY",
        "reason": "No evidence",
        "evidence": [],
    }
    with client:
        response = client.post(
            f"/api/v1/local-human-test/investigations/{uuid7()}/rule-applicability",
            json=body,
            headers={"Idempotency-Key": "scope-test"},
        )
    assert response.status_code == 400  # Project-wide request validation response.
    service.assert_not_called()


def test_applicability_hidden_when_review_environment_disabled(tmp_path: Path) -> None:
    client, store = make_client(tmp_path, enabled=False)
    with client:
        response = client.get(
            f"/api/v1/local-human-test/investigations/{uuid7()}/unit-plans/{uuid7()}/rule-applicability/{uuid7()}/{uuid7()}"
        )
    assert response.status_code == 404
    assert not store.mock_calls
