"""HTTP surface of the material exclusion / revocation endpoints.

The business layer lives in :mod:`deepaha.investigations.document_exclusions`; these tests
only cover what the route adds on top of it: the mandatory ``Idempotency-Key`` header,
request validation, ``Cache-Control`` and the pass-through of domain error codes. Real
behaviour (row counts, ``UNSUPPORTED`` gating) is asserted in
``tests/integration/test_investigation_document_exclusions.py``.
"""

from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid7

import pytest

from deepaha.investigations.contracts import InvestigationError
from deepaha.review.auth import ReviewerRole
from tests.api.test_investigations import make_client

EXCLUDE_MODULE = "deepaha.investigations.document_exclusions.exclude_document"
REVOKE_MODULE = "deepaha.investigations.document_exclusions.revoke_exclusion"
DELIVERY_HASH = "a" * 64
REASON = "No parser exists for this legacy attachment."


def _path(task_id: UUID, suffix: str = "") -> str:
    """Build the URL of one exclusion route for a task."""
    return f"/api/v1/local-human-test/investigations/{task_id}/document-exclusions{suffix}"


def _body(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "delivery_hash": DELIVERY_HASH,
        "material_id": "legacy.doc",
        "reason": REASON,
    }
    payload.update(overrides)
    return payload


def _preparation() -> dict[str, Any]:
    """A minimal but realistic refreshed task view with excluded material."""
    return {
        "status": "PENDING_REVIEW",
        "document_preparation": {
            "status": "PREPARED",
            "material_count": 2,
            "prepared_count": 2,
            "excluded_count": 1,
            "unsupported_count": 0,
            "materials": [
                {
                    "material_id": "legacy.doc",
                    "outcome": "SUCCEEDED",
                    "excluded": True,
                    "evidence_mode": "OPAQUE_NO_TEXT",
                    "exclusion": {
                        "reason": REASON,
                        "excluded_by": str(uuid7()),
                        "excluded_at": "2026-09-07T10:00:00+00:00",
                    },
                },
                {
                    "material_id": "notice",
                    "outcome": "SUCCEEDED",
                    "excluded": False,
                    "evidence_mode": "TEXT",
                    "exclusion": None,
                },
            ],
        },
    }


@pytest.mark.parametrize("route,suffix", [("exclude", ""), ("revoke", "/revoke")])
def test_exclusion_writes_require_an_idempotency_key(
    tmp_path: Path, route: str, suffix: str
) -> None:
    client, _ = make_client(tmp_path)
    target = EXCLUDE_MODULE if route == "exclude" else REVOKE_MODULE
    with client, patch(target) as call:
        missing = client.post(_path(uuid7(), suffix), json=_body())
    assert missing.status_code == 400
    assert missing.json() == {"detail": {"code": "IDEMPOTENCY_KEY_REQUIRED"}}
    assert not call.mock_calls


@pytest.mark.parametrize("route,suffix", [("exclude", ""), ("revoke", "/revoke")])
def test_malformed_idempotency_key_is_refused(tmp_path: Path, route: str, suffix: str) -> None:
    client, _ = make_client(tmp_path)
    target = EXCLUDE_MODULE if route == "exclude" else REVOKE_MODULE
    with client, patch(target) as call:
        response = client.post(
            _path(uuid7(), suffix), json=_body(), headers={"Idempotency-Key": " padded "}
        )
    assert response.status_code == 400
    assert response.json() == {"detail": {"code": "IDEMPOTENCY_KEY_INVALID"}}
    assert not call.mock_calls


@pytest.mark.parametrize(
    "payload",
    [{"reason": ""}, {"material_id": ""}, {"delivery_hash": "short"}, {"extra": True}],
)
def test_invalid_body_is_refused_as_local_test_problem(tmp_path: Path, payload: Any) -> None:
    client, store = make_client(tmp_path)
    with client, patch(EXCLUDE_MODULE) as call:
        response = client.post(
            _path(uuid7()),
            json=_body(**payload),
            headers={"Idempotency-Key": "exclude-synthetic-material"},
        )
    assert response.status_code == 400
    assert response.json() == {"detail": {"code": "INVALID_LOCAL_HUMAN_TEST_REQUEST"}}
    assert not call.mock_calls
    assert not store.mock_calls


def test_exclusion_returns_refreshed_document_preparation(tmp_path: Path) -> None:
    client, store = make_client(tmp_path)
    task_id = uuid7()
    with client, patch(EXCLUDE_MODULE, return_value=_preparation()) as call:
        response = client.post(
            _path(task_id), json=_body(), headers={"Idempotency-Key": "exclude-once"}
        )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    preparation = response.json()["document_preparation"]
    assert preparation["excluded_count"] == 1 and preparation["unsupported_count"] == 0
    material = preparation["materials"][0]
    assert material["material_id"] == "legacy.doc"
    assert material["excluded"] is True
    assert material["evidence_mode"] == "OPAQUE_NO_TEXT"
    assert material["exclusion"]["reason"] == REASON
    call.assert_called_once()
    assert call.call_args.args[0] is store
    assert call.call_args.args[1:5] == (task_id, DELIVERY_HASH, "legacy.doc", REASON)


def test_revocation_returns_refreshed_document_preparation(tmp_path: Path) -> None:
    client, store = make_client(tmp_path)
    task_id = uuid7()
    renewed = "Parser became available; reinstate the material."
    with client, patch(REVOKE_MODULE, return_value=_preparation()) as call:
        response = client.post(
            _path(task_id, "/revoke"),
            json=_body(reason=renewed),
            headers={"Idempotency-Key": "revoke-synthetic-material"},
        )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json()["document_preparation"]["excluded_count"] == 1
    call.assert_called_once()
    assert call.call_args.args[0] is store
    assert call.call_args.args[1:5] == (task_id, DELIVERY_HASH, "legacy.doc", renewed)


@pytest.mark.parametrize(
    "code,status",
    [
        ("DOCUMENT_EXCLUSION_ALREADY_PRESENT", 409),
        ("DOCUMENT_EXCLUSION_DELIVERY_CONFLICT", 409),
        ("DOCUMENT_EXCLUSION_MATERIAL_NOT_FOUND", 404),
        ("DOCUMENT_EXCLUSION_NOT_ALLOWED", 409),
        ("DOCUMENT_EXCLUSION_NOT_UNSUPPORTED", 409),
        ("DOCUMENT_OPERATOR_REQUIRED", 409),
        ("STORED_MATERIAL_INTEGRITY_FAILED", 409),
    ],
)
def test_exclusion_domain_codes_pass_through_unchanged(
    tmp_path: Path, code: str, status: int
) -> None:
    client, store = make_client(tmp_path)
    with client, patch(EXCLUDE_MODULE, side_effect=InvestigationError(code)):
        response = client.post(
            _path(uuid7()), json=_body(), headers={"Idempotency-Key": "exclusion-failure"}
        )
    assert response.status_code == status
    assert response.json() == {"detail": {"code": code}}
    assert not store.mock_calls


@pytest.mark.parametrize(
    "code,status",
    [
        ("DOCUMENT_EXCLUSION_NOT_FOUND", 409),
        ("DOCUMENT_EXCLUSION_DELIVERY_CONFLICT", 409),
        ("DOCUMENT_EXCLUSION_NOT_ALLOWED", 409),
    ],
)
def test_revocation_domain_codes_pass_through_unchanged(
    tmp_path: Path, code: str, status: int
) -> None:
    client, _ = make_client(tmp_path)
    with client, patch(REVOKE_MODULE, side_effect=InvestigationError(code)):
        response = client.post(
            _path(uuid7(), "/revoke"), json=_body(), headers={"Idempotency-Key": "revoke-failure"}
        )
    assert response.status_code == status
    assert response.json() == {"detail": {"code": code}}


@pytest.mark.parametrize("suffix", ["", "/revoke"])
def test_unrelated_reviewer_cannot_decide(tmp_path: Path, suffix: str) -> None:
    client, _ = make_client(tmp_path, roles=frozenset({ReviewerRole.FEEDBACK_REVIEWER}))
    with client:
        response = client.post(
            _path(uuid7(), suffix), json=_body(), headers={"Idempotency-Key": "wrong-reviewer"}
        )
    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "INVESTIGATION_ROLE_REQUIRED"}}


def test_disabled_local_human_test_hides_exclusion_routes(tmp_path: Path) -> None:
    client, store = make_client(tmp_path, enabled=False)
    with client:
        response = client.post(
            _path(uuid7()), json=_body(), headers={"Idempotency-Key": "disabled"}
        )
    assert response.status_code == 404
    assert not store.mock_calls
