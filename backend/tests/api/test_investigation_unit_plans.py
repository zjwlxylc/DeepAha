from pathlib import Path
from typing import Any
from unittest.mock import Mock
from uuid import uuid7

import pytest

from deepaha.investigations.contracts import InvestigationError
from tests.api.test_investigations import make_client


@pytest.mark.parametrize("operation", ["create", "read"])
def test_private_unit_routes_call_only_trusted_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    client, store = make_client(tmp_path)
    task_id, plan_id = uuid7(), uuid7()
    command = {
        key: str(uuid7())
        for key in (
            "binding_id",
            "check_id",
            "fact_preparation_id",
            "fact_set_id",
            "rule_preparation_id",
        )
    }
    command.update(delivery_hash="a" * 64, entity_id="position")
    service = Mock(return_value={"plan_id": str(plan_id), "scope": "synthetic-only"})
    name = "materialize_unit_plan" if operation == "create" else "load_unit_plan"
    monkeypatch.setattr(f"deepaha.investigations.unit_snapshots.{name}", service)
    with client:
        response = (
            client.post(
                f"/api/v1/local-human-test/investigations/{task_id}/unit-plans", json=command
            )
            if operation == "create"
            else client.get(
                f"/api/v1/local-human-test/investigations/{task_id}/unit-plans/{plan_id}"
            )
        )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == service.return_value
    assert service.call_args.args[:2] == (store, task_id)
    if operation == "create":
        assert service.call_args.args[2].model_dump(mode="json") == command
    else:
        assert service.call_args.args[2] == plan_id
    assert not store.mock_calls


@pytest.mark.parametrize(
    "code,status",
    [
        ("UNIT_PLAN_NOT_FOUND", 404),
        ("UNIT_PLAN_INTEGRITY_FAILED", 409),
        ("RULE_FACT_SET_CONFLICT", 409),
    ],
)
def test_unit_read_failure_is_not_cacheable_or_a_cached_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: str, status: int
) -> None:
    client, _ = make_client(tmp_path)

    def fail(*_: Any) -> None:
        raise InvestigationError(code)

    monkeypatch.setattr("deepaha.investigations.unit_snapshots.load_unit_plan", fail)
    with client:
        response = client.get(
            f"/api/v1/local-human-test/investigations/{uuid7()}/unit-plans/{uuid7()}"
        )
    assert response.status_code == status
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == {"detail": {"code": code}}


def test_unit_read_is_hidden_when_local_review_disabled(tmp_path: Path) -> None:
    client, store = make_client(tmp_path, enabled=False)
    with client:
        assert (
            client.get(
                f"/api/v1/local-human-test/investigations/{uuid7()}/unit-plans/{uuid7()}"
            ).status_code
            == 404
        )
    assert not store.mock_calls
