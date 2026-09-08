from typing import cast

import pytest
from fastapi import FastAPI
from sqlalchemy import select

from deepaha.api.investigations import get_investigation_store
from deepaha.api.local_human_test import require_local_test_principal
from deepaha.investigations.models import InvestigationUnitPlan
from tests.api.test_investigations import make_client
from tests.integration.test_investigation_store import StoreHarness, harness
from tests.integration.test_investigation_unit_snapshots import approved

__all__ = ["harness"]
pytestmark = pytest.mark.integration


def test_private_http_snapshot_is_repeatable_and_rechecks_current_verifier(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    task, command = approved(h)
    client, _ = make_client(h.object_root)
    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_investigation_store] = lambda: h.store
    app.dependency_overrides[require_local_test_principal] = lambda: h.principal
    url = f"/api/v1/local-human-test/investigations/{task}/unit-plans"
    with client:
        first = client.post(url, json=command.model_dump(mode="json"))
        assert first.status_code == 200
        assert first.headers["cache-control"] == "private, no-store"
        assert client.post(url, json=command.model_dump(mode="json")).json() == first.json()
        detail = url + "/" + first.json()["plan_id"]
        assert client.get(detail).json() == first.json()
        monkeypatch.setattr(
            "deepaha.investigations.evidence_checks.VERIFIER_VERSION", "synthetic-next"
        )
        stale = client.get(detail)
        assert stale.status_code == 409
        assert stale.headers["cache-control"] == "private, no-store"
        assert "plan" not in stale.json()
    with h.factory() as session:
        assert len(list(session.scalars(select(InvestigationUnitPlan)))) == 1
