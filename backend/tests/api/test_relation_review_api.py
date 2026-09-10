from pathlib import Path
from typing import cast
from uuid import uuid7

import pytest
from fastapi import FastAPI

from deepaha.api.local_human_test import require_local_test_principal
from deepaha.review.auth import ReviewerRole
from tests.api.test_investigations import make_client


@pytest.mark.parametrize(
    "method,suffix",
    [
        ("post", "relation-proposals"),
        ("post", "relation-decisions"),
        ("get", f"relation-proposals/{uuid7()}"),
        ("get", f"unit-plans/{uuid7()}/relation-proposals"),
        ("get", f"unit-plans/{uuid7()}/relation-proposal-context"),
        ("get", f"unit-plans/{uuid7()}/relation-queue"),
    ],
)
@pytest.mark.parametrize("enabled", [False, True])
def test_relation_routes_respect_private_gate(
    tmp_path: Path, method: str, suffix: str, enabled: bool
) -> None:
    client, store = make_client(
        tmp_path, enabled=enabled, roles=frozenset({ReviewerRole.FEEDBACK_REVIEWER})
    )
    with client:
        response = client.request(
            method, f"/api/v1/local-human-test/investigations/{uuid7()}/{suffix}", json={}
        )
    assert response.status_code == (403 if enabled else 404)
    assert not store.mock_calls


@pytest.mark.parametrize(
    "method,suffix",
    [
        ("post", "relation-proposals"),
        ("post", "relation-decisions"),
        ("get", f"relation-proposals/{uuid7()}"),
        ("get", f"unit-plans/{uuid7()}/relation-proposals"),
        ("get", f"unit-plans/{uuid7()}/relation-proposal-context"),
        ("get", f"unit-plans/{uuid7()}/relation-queue"),
    ],
)
def test_relation_routes_require_authentication(tmp_path: Path, method: str, suffix: str) -> None:
    client, store = make_client(tmp_path)
    app = cast(FastAPI, client.app)
    del app.dependency_overrides[require_local_test_principal]
    with client:
        response = client.request(
            method, f"/api/v1/local-human-test/investigations/{uuid7()}/{suffix}", json={}
        )
    assert response.status_code == 401
    assert response.headers["cache-control"] == "private, no-store"
    assert not store.mock_calls
