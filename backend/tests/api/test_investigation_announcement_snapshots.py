from pathlib import Path
from unittest.mock import Mock
from uuid import uuid7

import pytest

from deepaha.investigations.contracts import InvestigationError
from tests.api.test_investigations import make_client


@pytest.mark.parametrize("operation", ["preview", "create", "read"])
def test_announcement_snapshot_routes_use_current_private_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    client, store = make_client(tmp_path)
    task, base, snapshot = uuid7(), uuid7(), uuid7()
    root = f"/api/v1/local-human-test/investigations/{task}"
    paths = {
        "preview": f"{root}/unit-plans/{base}/announcement-snapshot-input",
        "create": f"{root}/unit-plans/{base}/announcement-snapshots",
        "read": f"{root}/announcement-snapshots/{snapshot}",
    }
    name = {
        "preview": "preview_announcement_snapshot",
        "create": "materialize_announcement_snapshot",
        "read": "load_announcement_snapshot",
    }[operation]
    service = Mock(return_value={"synthetic": True})
    monkeypatch.setattr(f"deepaha.investigations.announcement_snapshots.{name}", service)
    with client:
        response = (
            client.post(paths[operation], json={"expected_dependencies_hash": "a" * 64})
            if operation == "create"
            else client.get(paths[operation])
        )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == {"synthetic": True}
    assert service.call_args.args[:3] == (store, task, snapshot if operation == "read" else base)
    if operation == "create":
        assert service.call_args.args[3] == "a" * 64


@pytest.mark.parametrize(
    "code,status",
    [
        ("ANNOUNCEMENT_SNAPSHOT_NOT_FOUND", 404),
        ("ANNOUNCEMENT_SNAPSHOT_STALE", 409),
        ("ANNOUNCEMENT_SNAPSHOT_INTEGRITY_FAILED", 409),
        ("HUMAN_VALIDATION_AUTHORITY_REQUIRED", 403),
    ],
)
def test_announcement_snapshot_errors_do_not_return_stale_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: str, status: int
) -> None:
    client, _ = make_client(tmp_path)
    monkeypatch.setattr(
        "deepaha.investigations.announcement_snapshots.load_announcement_snapshot",
        Mock(side_effect=InvestigationError(code)),
    )
    with client:
        response = client.get(
            f"/api/v1/local-human-test/investigations/{uuid7()}/announcement-snapshots/{uuid7()}"
        )
    assert response.status_code == status
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == {"detail": {"code": code}}


def test_caller_cannot_supply_selected_source_rules(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    with client:
        response = client.post(
            f"/api/v1/local-human-test/investigations/{uuid7()}/unit-plans/{uuid7()}/announcement-snapshots",
            json={"expected_dependencies_hash": "a" * 64, "selected_rule_ids": []},
        )
    assert response.status_code == 400
