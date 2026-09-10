from pathlib import Path
from typing import Any
from unittest.mock import Mock
from uuid import UUID, uuid7

import pytest

from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.group_fact_contracts import GROUP_FACT_VERSION, GroupFactRecord
from tests.api.test_investigations import make_client
from tests.investigations.test_group_contracts import record_fixture


def receipt() -> dict[str, Any]:
    result = {
        "contract_version": GROUP_FACT_VERSION,
        "scope": "GROUP_FACT_REVIEW_ONLY",
        "group_source": record_fixture(),
        "check_id": str(uuid7()),
        "check_hash": "a" * 64,
        "source_row_count": 0,
        "rows": [],
        "excluded_rows": [],
        "extraction_run_id": None,
    }
    return GroupFactRecord.model_validate(
        {
            "preparation_id": str(uuid7()),
            "result": result,
            "result_hash": digest(result),
            "reviewer_id": str(uuid7()),
            "created_at": "2026-09-10T00:00:00Z",
            "decisions": {},
            "history": [],
            "fact_set": None,
        }
    ).model_dump(mode="json")


@pytest.mark.parametrize("operation", ["prepare", "read", "decisions", "promotions"])
def test_private_group_fact_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    client, store = make_client(tmp_path)
    payload = receipt()
    source = payload["result"]["group_source"]
    task = source["source"]["task_id"]
    root = f"/api/v1/local-human-test/investigations/{task}"
    name = {"prepare": "prepare_group_facts", "read": "load_group_facts"}.get(
        operation, "act_on_group_facts"
    )
    service = Mock(return_value=payload)
    monkeypatch.setattr(f"deepaha.investigations.group_facts.{name}", service)
    with client:
        if operation == "prepare":
            response = client.post(
                root + f"/group-bindings/{source['group_binding_id']}/facts",
                json={
                    "check_id": payload["result"]["check_id"],
                    "expected_source_hash": source["source_hash"],
                },
            )
        elif operation == "read":
            response = client.get(root + f"/group-facts/{payload['preparation_id']}")
        else:
            command = {"expected_preparation_hash": payload["result_hash"], "reason": "Synthetic"}
            if operation == "decisions":
                command.update(
                    candidate_id=str(uuid7()),
                    decision="UNKNOWN",
                    evidence_support="UNKNOWN",
                    precedence_check="UNKNOWN",
                )
            response = client.post(
                root + f"/group-facts/{payload['preparation_id']}/{operation}",
                json=command,
                headers={"Idempotency-Key": "synthetic"},
            )
    assert response.status_code == 200 and response.json() == payload
    assert response.headers["cache-control"] == "private, no-store"
    assert service.call_args.args[:2] == (store, UUID(task))
    assert service.call_args.args[2] == UUID(
        source["group_binding_id"] if operation == "prepare" else payload["preparation_id"]
    )
    if operation in {"decisions", "promotions"}:
        assert service.call_args.args[-1] == "synthetic"


@pytest.mark.parametrize(
    "code,status",
    [
        ("GROUP_FACT_PREPARATION_NOT_FOUND", 404),
        ("GROUP_FACT_SOURCE_NOT_FOUND", 404),
        ("GROUP_FACT_MATERIALIZATION_INTEGRITY_FAILED", 409),
        ("HUMAN_VALIDATION_AUTHORITY_REQUIRED", 403),
    ],
)
def test_group_fact_errors_are_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: str, status: int
) -> None:
    client, _ = make_client(tmp_path)
    monkeypatch.setattr(
        "deepaha.investigations.group_facts.load_group_facts",
        Mock(side_effect=InvestigationError(code)),
    )
    with client:
        response = client.get(
            f"/api/v1/local-human-test/investigations/{uuid7()}/group-facts/{uuid7()}"
        )
    assert response.status_code == status
    assert response.json() == {"detail": {"code": code}}
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize("invalid", ["extra", "missing-key", "bad-enum"])
def test_group_decision_rejects_forged_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalid: str
) -> None:
    client, _ = make_client(tmp_path)
    service = Mock()
    monkeypatch.setattr("deepaha.investigations.group_facts.act_on_group_facts", service)
    body: dict[str, Any] = {
        "expected_preparation_hash": "a" * 64,
        "candidate_id": str(uuid7()),
        "decision": "APPROVE",
        "evidence_support": "SUPPORTED",
        "precedence_check": "PASSED",
        "reason": "Synthetic",
    }
    if invalid == "extra":
        body["normalized_value"] = {"minimum_level": "BACHELOR"}
    if invalid == "bad-enum":
        body["decision"] = "AUTO_APPROVED"
    with client:
        response = client.post(
            f"/api/v1/local-human-test/investigations/{uuid7()}/group-facts/{uuid7()}/decisions",
            json=body,
            headers={} if invalid == "missing-key" else {"Idempotency-Key": "synthetic"},
        )
    assert response.status_code == 400
    assert not service.mock_calls
