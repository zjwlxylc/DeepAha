from pathlib import Path
from typing import Any
from unittest.mock import Mock
from uuid import UUID, uuid7

import pytest

from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.group_rule_review_contracts import GROUP_RULE_REVIEW_VERSION
from deepaha.review.auth import ReviewerRole
from tests.api.test_group_rule_preview import preview_receipt
from tests.api.test_investigations import make_client


def receipt() -> dict[str, Any]:
    preview = preview_receipt()
    facts = preview["result"]["fact_review"]
    result = {
        "contract_version": GROUP_RULE_REVIEW_VERSION,
        "scope": "GROUP_RULE_REVIEW_ONLY",
        "preview": preview,
        "rows": [],
    }
    return {
        "preparation_id": str(uuid7()),
        "fact_preparation_id": facts["preparation_id"],
        "fact_set_id": str(uuid7()),
        "result": result,
        "result_hash": digest(result),
        "reviewer_id": facts["reviewer_id"],
        "created_at": facts["created_at"],
        "decisions": {},
        "history": [],
    }


@pytest.mark.parametrize("operation", ["prepare", "read", "decide"])
def test_private_group_rule_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    client, store = make_client(tmp_path)
    data = receipt()
    task = uuid7()
    base = f"/api/v1/local-human-test/investigations/{task}"
    service = Mock(return_value=data)
    target = {
        "prepare": "prepare_group_rule_review",
        "read": "load_group_rule_review",
        "decide": "decide_group_rule",
    }[operation]
    monkeypatch.setattr(f"deepaha.investigations.group_rule_review.{target}", service)
    body = {
        "expected_preparation_hash": data["result_hash"],
        "rule_candidate_id": str(uuid7()),
        "decision": "REJECT",
        "evidence": [],
        "reason": "Synthetic test",
    }
    with client:
        if operation == "prepare":
            response = client.post(
                f"{base}/group-facts/{data['fact_preparation_id']}/rules",
                json={"expected_preview_hash": data["result"]["preview"]["result_hash"]},
            )
        elif operation == "read":
            response = client.get(f"{base}/group-rules/{data['preparation_id']}")
        else:
            response = client.post(
                f"{base}/group-rules/{data['preparation_id']}/decisions",
                json=body,
                headers={"Idempotency-Key": "test-group-rule"},
            )
    assert response.status_code == 200 and response.json() == data
    assert response.headers["cache-control"] == "private, no-store"
    assert service.call_count == 1 and service.call_args.args[:2] == (store, task)
    assert service.call_args.args[2] == UUID(
        data["fact_preparation_id" if operation == "prepare" else "preparation_id"]
    )
    if operation == "decide":
        assert service.call_args.args[-1] == "test-group-rule"


@pytest.mark.parametrize(
    "code,status",
    [
        ("GROUP_RULE_PREPARATION_NOT_FOUND", 404),
        ("GROUP_RULE_MATERIALIZATION_INTEGRITY_FAILED", 409),
        ("HUMAN_VALIDATION_AUTHORITY_REQUIRED", 403),
    ],
)
def test_review_read_errors_are_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: str, status: int
) -> None:
    client, _ = make_client(tmp_path)
    monkeypatch.setattr(
        "deepaha.investigations.group_rule_review.load_group_rule_review",
        Mock(side_effect=InvestigationError(code)),
    )
    with client:
        response = client.get(
            f"/api/v1/local-human-test/investigations/{uuid7()}/group-rules/{uuid7()}"
        )
    assert response.status_code == status
    assert response.json() == {"detail": {"code": code}}
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize("case,status", [("disabled", 404), ("role", 403), ("key", 400)])
def test_review_write_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str, status: int
) -> None:
    client, _ = make_client(
        tmp_path,
        enabled=case != "disabled",
        roles=frozenset({ReviewerRole.FEEDBACK_REVIEWER}) if case == "role" else None,
    )
    service = Mock()
    monkeypatch.setattr("deepaha.investigations.group_rule_review.decide_group_rule", service)
    with client:
        response = client.post(
            f"/api/v1/local-human-test/investigations/{uuid7()}/group-rules/{uuid7()}/decisions",
            json={
                "expected_preparation_hash": "a" * 64,
                "rule_candidate_id": str(uuid7()),
                "decision": "REJECT",
                "evidence": [],
                "reason": "Synthetic",
            },
        )
    assert response.status_code == status and not service.mock_calls
