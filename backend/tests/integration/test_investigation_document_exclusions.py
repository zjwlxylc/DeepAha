"""Exclusion / revocation over HTTP, verified against real persistence.

The unit-level suite (``tests/api/test_investigation_document_exclusions.py``) only proves the
route contract; these checks prove the route actually writes one append-only row and lets a
task whose material no parser can read reach ``PREPARED``.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from deepaha.api.investigations import get_investigation_store
from deepaha.api.local_human_test import require_local_test_principal
from deepaha.core.settings import Settings, get_settings
from deepaha.investigations.models import InvestigationDocumentExclusion
from deepaha.main import create_app
from tests.integration.test_investigation_documents import _with_extras
from tests.integration.test_investigation_store import StoreHarness
from tests.integration.test_investigation_store import harness as original_harness

harness = original_harness
pytestmark = pytest.mark.integration

REASON = "Legacy application/msword attachment; no parser exists, kept whole-file only."
LEGACY = {"legacy.doc": ("application/msword", b"synthetic unsupported legacy format")}


@pytest.fixture
def api(harness: StoreHarness) -> Iterator[TestClient]:
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: Settings(
        local_human_test_enabled=True, local_human_test_root=harness.object_root
    )
    application.dependency_overrides[get_investigation_store] = lambda: harness.store
    application.dependency_overrides[require_local_test_principal] = lambda: harness.principal
    with TestClient(application, base_url="http://127.0.0.1") as value:
        yield value


def _url(task_id: Any, suffix: str = "") -> str:
    return f"/api/v1/local-human-test/investigations/{task_id}/document-exclusions{suffix}"


def _exclusion_rows(h: StoreHarness) -> int:
    with h.factory() as session:
        value = session.scalar(select(func.count()).select_from(InvestigationDocumentExclusion))
        return int(value or 0)


def _material(view: dict[str, Any], material_id: str) -> dict[str, Any]:
    rows: dict[str, dict[str, Any]] = {
        row["material_id"]: row for row in view["document_preparation"]["materials"]
    }
    return rows[material_id]


def test_excluded_legacy_material_lets_preparation_reach_prepared(
    api: TestClient, harness: StoreHarness
) -> None:
    h = harness
    task_id, delivery_hash = _with_extras(h, LEGACY)
    payload: dict[str, Any] = {
        "delivery_hash": delivery_hash,
        "material_id": "legacy.doc",
        "reason": REASON,
    }
    assert _material(h.store.get(task_id), "legacy.doc")["outcome"] == "UNSUPPORTED"
    excluded = api.post(_url(task_id), json=payload, headers={"Idempotency-Key": "exclude-once"})
    assert excluded.status_code == 200
    assert excluded.headers["cache-control"] == "private, no-store"
    material = _material(excluded.json(), "legacy.doc")
    assert material["excluded"] is True
    assert material["outcome"] == "NOT_PREPARED"
    # No opaque block exists yet, so there is still no evidence of any kind.
    assert material["evidence_mode"] is None
    assert material["exclusion"]["reason"] == REASON
    assert excluded.json()["delivery_hash"] == delivery_hash

    replayed = api.post(_url(task_id), json=payload, headers={"Idempotency-Key": "exclude-once"})
    assert replayed.status_code == 409
    assert replayed.json() == {"detail": {"code": "DOCUMENT_EXCLUSION_ALREADY_PRESENT"}}
    assert _exclusion_rows(h) == 1

    preparation = h.store.prepare_documents(task_id, delivery_hash, h.principal)[
        "document_preparation"
    ]
    assert preparation["status"] == "PREPARED"
    assert preparation["excluded_count"] == 1 and preparation["unsupported_count"] == 0
    legacy = {row["material_id"]: row for row in preparation["materials"]}
    assert legacy["legacy.doc"]["outcome"] == "SUCCEEDED"
    assert legacy["legacy.doc"]["evidence_mode"] == "OPAQUE_NO_TEXT"
    assert legacy["legacy.doc"]["block_count"] == 1
    assert _exclusion_rows(h) == 1


def test_materials_a_parser_understands_are_never_excludable(
    api: TestClient, harness: StoreHarness
) -> None:
    h = harness
    fixtures = Path(__file__).parents[1] / "fixtures/documents"
    task_id, delivery_hash = _with_extras(
        h,
        {
            **LEGACY,
            "empty.pdf": ("application/pdf", (fixtures / "empty-text.pdf").read_bytes()),
        },
    )
    h.store.prepare_documents(task_id, delivery_hash, h.principal)
    for material_id in ("notice", "empty.pdf"):
        response = api.post(
            _url(task_id),
            json={
                "delivery_hash": delivery_hash,
                "material_id": material_id,
                "reason": REASON,
            },
            headers={"Idempotency-Key": f"refuse-{material_id}"},
        )
        assert response.status_code == 409
        assert response.json() == {"detail": {"code": "DOCUMENT_EXCLUSION_NOT_UNSUPPORTED"}}
    assert _exclusion_rows(h) == 0


def test_exclusion_needs_the_current_delivery_and_a_real_reason(
    api: TestClient, harness: StoreHarness
) -> None:
    h = harness
    task_id, delivery_hash = _with_extras(h, LEGACY)
    stale = api.post(
        _url(task_id),
        json={"delivery_hash": "0" * 64, "material_id": "legacy.doc", "reason": REASON},
        headers={"Idempotency-Key": "stale-delivery"},
    )
    assert stale.status_code == 409
    assert stale.json() == {"detail": {"code": "DOCUMENT_EXCLUSION_DELIVERY_CONFLICT"}}

    blank = api.post(
        _url(task_id),
        json={"delivery_hash": delivery_hash, "material_id": "legacy.doc", "reason": "   "},
        headers={"Idempotency-Key": "blank-reason"},
    )
    assert blank.status_code == 409
    assert blank.json() == {"detail": {"code": "DOCUMENT_EXCLUSION_REASON_REQUIRED"}}

    unknown = api.post(
        _url(task_id),
        json={"delivery_hash": delivery_hash, "material_id": "ghost.doc", "reason": REASON},
        headers={"Idempotency-Key": "unknown-material"},
    )
    assert unknown.status_code == 404
    assert unknown.json() == {"detail": {"code": "DOCUMENT_EXCLUSION_MATERIAL_NOT_FOUND"}}
    assert _exclusion_rows(h) == 0


def test_missing_idempotency_key_writes_nothing(api: TestClient, harness: StoreHarness) -> None:
    h = harness
    task_id, delivery_hash = _with_extras(h, LEGACY)
    response = api.post(
        _url(task_id),
        json={"delivery_hash": delivery_hash, "material_id": "legacy.doc", "reason": REASON},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": {"code": "IDEMPOTENCY_KEY_REQUIRED"}}
    assert _exclusion_rows(h) == 0


def test_revocation_restores_the_text_requirement_and_cannot_repeat(
    api: TestClient, harness: StoreHarness
) -> None:
    h = harness
    task_id, delivery_hash = _with_extras(h, LEGACY)
    payload: dict[str, Any] = {
        "delivery_hash": delivery_hash,
        "material_id": "legacy.doc",
        "reason": REASON,
    }
    assert (
        api.post(
            _url(task_id), json=payload, headers={"Idempotency-Key": "exclude-before-revoke"}
        ).status_code
        == 200
    )
    revoked = api.post(
        _url(task_id, "/revoke"),
        json={**payload, "reason": "Parser available again; material must yield text."},
        headers={"Idempotency-Key": "revoke-once"},
    )
    assert revoked.status_code == 200
    assert revoked.headers["cache-control"] == "private, no-store"
    assert revoked.json()["document_preparation"]["excluded_count"] == 0
    assert _material(revoked.json(), "legacy.doc")["excluded"] is False
    assert _material(revoked.json(), "legacy.doc")["outcome"] == "UNSUPPORTED"
    # The original decision survives as history instead of being overwritten.
    assert _exclusion_rows(h) == 1

    again = api.post(
        _url(task_id, "/revoke"),
        json={**payload, "reason": "Parser available again; material must yield text."},
        headers={"Idempotency-Key": "revoke-once"},
    )
    assert again.status_code == 409
    assert again.json() == {"detail": {"code": "DOCUMENT_EXCLUSION_NOT_FOUND"}}
    assert _exclusion_rows(h) == 1
    with h.factory() as session:
        row = session.scalar(select(InvestigationDocumentExclusion))
        assert row is not None and row.revoked_at is not None
        assert row.revoked_reason == "Parser available again; material must yield text."
        assert row.excluded_by == h.principal.reviewer_id
        assert row.revoked_by == h.principal.reviewer_id
