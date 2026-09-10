from pathlib import Path
from unittest.mock import Mock
from uuid import UUID, uuid7

import pytest

from deepaha.investigations.contracts import InvestigationError
from tests.api.test_investigations import make_client
from tests.investigations.test_group_contracts import record_fixture


@pytest.mark.parametrize("operation", ["preview", "register", "read"])
def test_private_group_source_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    client, store = make_client(tmp_path)
    record = record_fixture()
    task = UUID(record["source"]["task_id"])
    root = f"/api/v1/local-human-test/investigations/{task}"
    payload = (
        {
            "source": record["source"],
            "source_hash": record["source_hash"],
            "existing_group_id": None,
            "registration": None,
        }
        if operation == "preview"
        else record
    )
    service = Mock(return_value=payload)
    name = {
        "preview": "preview_group_source",
        "register": "register_group_source",
        "read": "load_group_source",
    }[operation]
    monkeypatch.setattr(
        f"deepaha.investigations.group_bindings.{name}",
        service,
    )
    with client:
        if operation == "preview":
            response = client.get(root + "/group-source-input", params={"entity_id": "unit"})
        elif operation == "register":
            response = client.post(
                root + "/group-bindings",
                json={"entity_id": "unit", "expected_source_hash": record["source_hash"]},
            )
        else:
            response = client.get(root + "/group-bindings/" + record["group_binding_id"])
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == payload
    assert service.call_args.args[:2] == (store, task)
    assert service.call_args.args[2] == (
        UUID(record["group_binding_id"]) if operation == "read" else "unit"
    )


@pytest.mark.parametrize(
    "code,status",
    [
        ("GROUP_SOURCE_NOT_FOUND", 404),
        ("GROUP_SOURCE_STALE", 409),
        ("HUMAN_VALIDATION_AUTHORITY_REQUIRED", 403),
    ],
)
def test_group_errors_do_not_expose_stale_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: str, status: int
) -> None:
    client, _ = make_client(tmp_path)
    monkeypatch.setattr(
        "deepaha.investigations.group_bindings.load_group_source",
        Mock(side_effect=InvestigationError(code)),
    )
    with client:
        response = client.get(
            f"/api/v1/local-human-test/investigations/{uuid7()}/group-bindings/{uuid7()}"
        )
    assert response.status_code == status
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == {"detail": {"code": code}}


def test_api_rejects_caller_selected_members(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    with client:
        response = client.post(
            f"/api/v1/local-human-test/investigations/{uuid7()}/group-bindings",
            json={"entity_id": "unit", "expected_source_hash": "a" * 64, "members": []},
        )
    assert response.status_code == 400
