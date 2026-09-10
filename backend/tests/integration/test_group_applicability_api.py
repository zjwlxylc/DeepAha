"""Actual database API round trip; synthetic review is not human acceptance."""

import json
from copy import deepcopy
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from deepaha.api.investigations import get_investigation_store
from deepaha.api.local_human_test import require_local_test_principal
from deepaha.investigations.contracts import digest
from deepaha.investigations.group_applicability import read_group_rule_applicability
from deepaha.investigations.group_applicability_decision_contracts import GroupApplicabilityHistory
from tests.api.test_investigations import make_client
from tests.integration.test_group_applicability_decisions import command
from tests.integration.test_group_rule_applicability import prepared
from tests.integration.test_investigation_store import StoreHarness, harness

__all__ = ["harness"]
pytestmark = pytest.mark.integration


def test_private_decision_roundtrip_and_response_integrity(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    h = harness
    task, plan, source, candidate = prepared(h, monkeypatch)
    view = read_group_rule_applicability(h.store, task, plan, source, candidate, h.principal)
    client, _ = make_client(tmp_path)
    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_investigation_store] = lambda: h.store
    app.dependency_overrides[require_local_test_principal] = lambda: h.principal
    base = f"/api/v1/local-human-test/investigations/{task}"
    get_url = f"{base}/unit-plans/{plan}/group-applicability-decisions/{source}/{candidate}"
    post_url = f"{base}/group-applicability-decisions"
    payload = command(view).model_dump(mode="json")
    with client:
        empty = client.get(get_url)
        assert empty.status_code == 200 and empty.json()["latest"] is None
        assert client.post(post_url, json=payload).status_code == 400
        first = client.post(post_url, json=payload, headers={"Idempotency-Key": "first"})
        assert first.status_code == 200
        retry = client.post(post_url, json=payload, headers={"Idempotency-Key": "first"})
        assert retry.json() == first.json()
        assert (
            client.post(post_url, json=payload, headers={"Idempotency-Key": "stale"}).status_code
            == 409
        )
        next_payload = command(view, "DOES_NOT_APPLY", UUID(first.json()["decision_id"]))
        second = client.post(
            post_url,
            json=next_payload.model_dump(mode="json"),
            headers={"Idempotency-Key": "second"},
        )
        assert second.status_code == 200
        history = client.get(get_url)
        assert history.status_code == 200
        assert history.headers["cache-control"] == "private, no-store"
        assert first.headers["cache-control"] == "private, no-store"
        assert len(history.json()["history"]) == 2
        assert history.json()["latest"] == second.json()
    GroupApplicabilityHistory.model_validate(history.json())
    for case in ("latest", "request", "context", "quote", "prefix"):
        bad = deepcopy(history.json())
        if case == "latest":
            bad["latest"] = None
        elif case == "request":
            bad["history"][0]["request"]["outcome"] = "DOES_NOT_APPLY"
        elif case == "context":
            bad["history"][0]["context"]["target_entity_id"] = "another-position"
            bad["history"][0]["context_hash"] = digest(bad["history"][0]["context"])
        elif case == "quote":
            bad["history"][0]["evidence_snapshot"][0]["quote"] = "Altered quote"
        else:
            row = bad["history"][0]
            row["context"]["source_review_hash"] = "f" * 64
            row["context_hash"] = digest(row["context"])
            row["request"]["context_hash"] = row["context_hash"]
            row["request_hash"] = digest(row["request"])
        with pytest.raises(ValidationError):
            GroupApplicabilityHistory.model_validate(bad)
    (tmp_path / "group-decisions-fixture.json").write_text(
        json.dumps(
            {"view": view, "empty": empty.json(), "saved": history.json()}, ensure_ascii=False
        ),
        encoding="utf-8",
    )
