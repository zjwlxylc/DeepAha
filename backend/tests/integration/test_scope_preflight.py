"""Read-only authenticated preflight against real synthetic DB records."""

from dataclasses import replace
from pathlib import Path
from typing import cast
from uuid import uuid7

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from deepaha.api.investigations import get_investigation_store
from deepaha.api.local_human_test import require_local_test_principal
from deepaha.investigations.group_applicability_decisions import (
    DecideGroupApplicability,
    save_group_applicability,
)
from deepaha.investigations.models import InvestigationEvent
from deepaha.investigations.relation_decisions import save_relation_decision
from deepaha.investigations.relation_proposals import save_relation_proposal
from deepaha.review.models import ReviewerAccountModel
from tests.api.test_investigations import make_client
from tests.integration.test_investigation_store import StoreHarness, harness
from tests.integration.test_relation_decisions import request, reviewer
from tests.integration.test_relation_proposals import setup

__all__ = ["harness"]
pytestmark = pytest.mark.integration


def test_scope_preflight_reads_all_relations_and_rechecks_sources(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    h = harness
    task, command = setup(h, monkeypatch)
    client, _ = make_client(tmp_path)
    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_investigation_store] = lambda: h.store
    app.dependency_overrides[require_local_test_principal] = lambda: h.principal
    url = (
        f"/api/v1/local-human-test/investigations/{task}/unit-plans/"
        f"{command.target_plan_id}/scope-preflight"
    )
    with client:
        empty = client.get(url)
        assert empty.status_code == 200, empty.text
        assert empty.json()["relations"] == []
        first = save_relation_proposal(h.store, task, command, h.principal, "first")
        second = save_relation_proposal(h.store, task, command, h.principal, "second")
        independent = reviewer(h)
        save_relation_decision(h.store, task, request(first), independent, "approve")
        with h.factory() as session:
            events_before = session.scalar(select(func.count()).select_from(InvestigationEvent))
        value = client.get(url)
        assert value.status_code == 200, value.text
        assert value.headers["cache-control"] == "private, no-store"
        data = value.json()
        assert [r["status"] for r in data["relations"]] == ["APPROVED", "UNREVIEWED"]
        assert data["source_row_count"] == len(data["conditions"]) + len(
            data["excluded_source_rows"]
        )
        assert data["executable"] is False and data["overall_qualification"] == "UNCERTAIN"
        assert "HUMAN_SCOPE_REVIEW_UNVERIFIED" in data["blockers"]
        with h.factory() as session:
            assert (
                session.scalar(select(func.count()).select_from(InvestigationEvent))
                == events_before
            )
        assert client.get(url.replace(str(task), str(uuid7()))).status_code == 404
        assert client.get(url.replace(str(command.target_plan_id), str(uuid7()))).status_code == 404
        group = second["package"]["proposal"]["source_review"]["dependencies"]["group"][
            "dependencies"
        ]["group_source"]
        latest = next(iter(group["applicability_histories"].values()))[-1]
        revised = DecideGroupApplicability.model_validate(
            latest["request"]
            | {"previous_decision_id": latest["decision_id"], "outcome": "DOES_NOT_APPLY"}
        )
        save_group_applicability(h.store, task, revised, h.principal, "exclude")
        stale = client.get(url).json()
        assert [r["status"] for r in stale["relations"]] == ["STALE", "STALE"]
        assert stale["source_review_hash"] != data["source_review_hash"]
        app.dependency_overrides[require_local_test_principal] = lambda: replace(
            h.principal, synthetic=True
        )
        assert client.get(url).status_code == 403
        app.dependency_overrides[require_local_test_principal] = lambda: h.principal
        with h.factory.begin() as session:
            account = session.get(ReviewerAccountModel, h.principal.reviewer_id)
            assert account is not None
            account.active = False
        revoked = client.get(url)
        assert revoked.status_code == 403
        assert revoked.headers["cache-control"] == "private, no-store"


def test_scope_preflight_refuses_partial_relation_sets(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    h = harness
    task, command = setup(h, monkeypatch)
    save_relation_proposal(h.store, task, command, h.principal, "first")
    monkeypatch.setattr("deepaha.investigations.scope_preflight.MAX_RELATIONS", 0)
    client, _ = make_client(tmp_path)
    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_investigation_store] = lambda: h.store
    app.dependency_overrides[require_local_test_principal] = lambda: h.principal
    url = (
        f"/api/v1/local-human-test/investigations/{task}/unit-plans/"
        f"{command.target_plan_id}/scope-preflight"
    )
    with client:
        response = client.get(url)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "SCOPE_PREFLIGHT_RELATION_LIMIT"
