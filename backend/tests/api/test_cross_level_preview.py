import json
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
def test_private_cross_level_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str, status: int
) -> None:
    client, _ = make_client(
        tmp_path,
        enabled=case != "disabled",
        roles=frozenset({ReviewerRole.FEEDBACK_REVIEWER}) if case == "role" else None,
    )
    service = Mock(
        side_effect=InvestigationError(
            "UNIT_PLAN_NOT_FOUND" if case == "missing" else "CROSS_LEVEL_INPUT_CHANGED"
        )
    )
    monkeypatch.setattr("deepaha.investigations.cross_level_preview.preview_cross_level", service)
    with client:
        response = client.get(
            f"/api/v1/local-human-test/investigations/{uuid7()}/unit-plans/{uuid7()}/cross-level-preview"
        )
    assert response.status_code == status
    assert not service.called if case in {"disabled", "role"} else service.called
    assert "snapshot" not in response.json()


@pytest.mark.parametrize("wrong", ["task", "plan"])
def test_returned_snapshot_must_match_requested_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wrong: str
) -> None:
    value = json.loads(
        (Path(__file__).parents[3] / "web/tests/cross-level-fixture.json").read_text(
            encoding="utf-8"
        )
    )
    group = value["dependencies"]["group"]
    task = group["dependencies"]["group_source"]["source"]["task_id"]
    plan = group["snapshot"]["base_v2"]["plan_id"]
    client, _ = make_client(tmp_path)
    monkeypatch.setattr(
        "deepaha.investigations.cross_level_preview.preview_cross_level", lambda *args: value
    )
    requested_task = uuid7() if wrong == "task" else task
    requested_plan = uuid7() if wrong == "plan" else plan
    with client:
        response = client.get(
            f"/api/v1/local-human-test/investigations/{requested_task}"
            f"/unit-plans/{requested_plan}/cross-level-preview"
        )
    assert response.status_code == 409
    assert "snapshot" not in response.json()
