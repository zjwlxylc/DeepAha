from pathlib import Path
from unittest.mock import Mock
from uuid import uuid7

import pytest

from deepaha.investigations.contracts import InvestigationError
from deepaha.review.auth import ReviewerRole
from tests.api.test_investigations import make_client


@pytest.mark.parametrize("index", [False, True])
@pytest.mark.parametrize(
    "case,status", [("disabled", 404), ("role", 403), ("stale", 409), ("missing", 404)]
)
def test_group_context_read_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, index: bool, case: str, status: int
) -> None:
    client, _ = make_client(
        tmp_path,
        enabled=case != "disabled",
        roles=frozenset({ReviewerRole.FEEDBACK_REVIEWER}) if case == "role" else None,
    )
    service = Mock(
        side_effect=InvestigationError(
            "UNIT_PLAN_NOT_FOUND" if case == "missing" else "GROUP_APPLICABILITY_SOURCE_CONFLICT"
        )
    )
    operation = "list_group_rule_contexts" if index else "read_group_rule_applicability"
    monkeypatch.setattr(
        f"deepaha.investigations.group_applicability.{operation}",
        service,
    )
    suffix = "group-rule-contexts" if index else f"group-rule-applicability/{uuid7()}/{uuid7()}"
    with client:
        response = client.get(
            f"/api/v1/local-human-test/investigations/{uuid7()}/unit-plans/{uuid7()}/{suffix}"
        )
    assert response.status_code == status
    assert not service.called if case in {"disabled", "role"} else service.called
    if case in {"stale", "missing"}:
        assert response.headers["cache-control"] == "private, no-store"
        assert "context" not in response.json()


@pytest.mark.parametrize("write", [False, True])
@pytest.mark.parametrize(
    "case,status", [("disabled", 404), ("role", 403), ("stale", 409), ("missing", 404)]
)
def test_group_decision_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, write: bool, case: str, status: int
) -> None:
    client, _ = make_client(
        tmp_path,
        enabled=case != "disabled",
        roles=frozenset({ReviewerRole.FEEDBACK_REVIEWER}) if case == "role" else None,
    )
    service = Mock(
        side_effect=InvestigationError(
            "UNIT_PLAN_NOT_FOUND" if case == "missing" else "GROUP_APPLICABILITY_CONTEXT_CHANGED"
        )
    )
    operation = "save_group_applicability" if write else "load_group_applicability_decisions"
    monkeypatch.setattr(
        f"deepaha.investigations.group_applicability_decisions.{operation}", service
    )
    task, plan, source, candidate = [str(uuid7()) for _ in range(4)]
    base = f"/api/v1/local-human-test/investigations/{task}"
    with client:
        if write:
            response = client.post(
                f"{base}/group-applicability-decisions",
                json={
                    "target_plan_id": plan,
                    "source_rule_preparation_id": source,
                    "source_rule_candidate_id": candidate,
                    "context_hash": "a" * 64,
                    "previous_decision_id": None,
                    "outcome": "NEEDS_ADJUDICATION",
                    "reason": "Synthetic pending review",
                    "evidence": [],
                },
                headers={"Idempotency-Key": "synthetic"},
            )
        else:
            response = client.get(
                f"{base}/unit-plans/{plan}/group-applicability-decisions/{source}/{candidate}"
            )
    assert response.status_code == status
    assert not service.called if case in {"disabled", "role"} else service.called
    assert "context" not in response.json()
