from pathlib import Path
from unittest.mock import Mock
from uuid import uuid7

import pytest

from deepaha.investigations.contracts import InvestigationError
from deepaha.review.auth import ReviewerRole
from tests.api.test_investigations import make_client


@pytest.mark.parametrize(
    "case,status", [("disabled", 404), ("role", 403), ("stale", 409), ("missing", 404)]
)
def test_private_inheritance_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str, status: int
) -> None:
    client, _ = make_client(
        tmp_path,
        enabled=case != "disabled",
        roles=frozenset({ReviewerRole.FEEDBACK_REVIEWER}) if case == "role" else None,
    )
    service = Mock(
        side_effect=InvestigationError(
            "UNIT_PLAN_NOT_FOUND" if case == "missing" else "GROUP_INHERITANCE_INPUT_CHANGED"
        )
    )
    monkeypatch.setattr(
        "deepaha.investigations.group_inheritance.preview_group_inheritance", service
    )
    with client:
        response = client.get(
            f"/api/v1/local-human-test/investigations/{uuid7()}/unit-plans/{uuid7()}/group-inheritance-preview"
        )
    assert response.status_code == status
    assert not service.called if case in {"disabled", "role"} else service.called
    assert "snapshot" not in response.json()
