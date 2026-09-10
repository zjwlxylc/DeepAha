from pathlib import Path
from typing import Any
from unittest.mock import Mock
from uuid import UUID, uuid7

import pytest

from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.group_rule_contracts import GROUP_RULE_PREVIEW_VERSION, GroupRulePreview
from deepaha.local_human_test.review import RULE_DERIVATION_VERSION
from deepaha.review.auth import ReviewerRole
from tests.api.test_group_facts import receipt
from tests.api.test_investigations import make_client


def preview_receipt() -> dict[str, Any]:
    review = receipt()
    result = {
        "contract_version": GROUP_RULE_PREVIEW_VERSION,
        "derivation_version": RULE_DERIVATION_VERSION,
        "scope": "READ_ONLY_GROUP_RULE_PREVIEW",
        "target": review["result"]["group_source"]["group_identity"],
        "fact_review": review,
        "rows": [],
    }
    return GroupRulePreview.model_validate(
        {"result": result, "result_hash": digest(result)}
    ).model_dump(mode="json")


def test_private_read_only_preview_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, store = make_client(tmp_path)
    payload = preview_receipt()
    review = payload["result"]["fact_review"]
    task = review["result"]["group_source"]["source"]["task_id"]
    prep = review["preparation_id"]
    service = Mock(return_value=payload)
    monkeypatch.setattr("deepaha.investigations.group_rules.preview_group_rules", service)
    with client:
        response = client.get(
            f"/api/v1/local-human-test/investigations/{task}/group-facts/{prep}/rules/preview"
        )
    assert response.status_code == 200 and response.json() == payload
    assert response.headers["cache-control"] == "private, no-store"
    assert service.call_count == 1
    assert service.call_args.args[:3] == (store, UUID(task), UUID(prep))


@pytest.mark.parametrize(
    "code,status",
    [
        ("GROUP_FACT_PREPARATION_NOT_FOUND", 404),
        ("GROUP_RULE_FACT_SET_NOT_ACTIVE", 409),
        ("GROUP_FACT_MATERIALIZATION_INTEGRITY_FAILED", 409),
        ("GROUP_IDENTITY_INTEGRITY_FAILED", 409),
        ("HUMAN_VALIDATION_AUTHORITY_REQUIRED", 403),
    ],
)
def test_preview_errors_never_return_stale_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: str, status: int
) -> None:
    client, _ = make_client(tmp_path)
    service = Mock(side_effect=InvestigationError(code))
    monkeypatch.setattr("deepaha.investigations.group_rules.preview_group_rules", service)
    with client:
        response = client.get(
            f"/api/v1/local-human-test/investigations/{uuid7()}/group-facts/{uuid7()}/rules/preview"
        )
    assert response.status_code == status
    assert response.json() == {"detail": {"code": code}}
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize("case,status", [("disabled", 404), ("unrelated-role", 403), ("post", 405)])
def test_preview_keeps_private_boundary_and_has_no_write_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str, status: int
) -> None:
    client, _ = make_client(
        tmp_path,
        enabled=case != "disabled",
        roles=frozenset({ReviewerRole.FEEDBACK_REVIEWER}) if case == "unrelated-role" else None,
    )
    service = Mock()
    monkeypatch.setattr("deepaha.investigations.group_rules.preview_group_rules", service)
    with client:
        response = client.request(
            "POST" if case == "post" else "GET",
            f"/api/v1/local-human-test/investigations/{uuid7()}/group-facts/{uuid7()}/rules/preview",
        )
    assert response.status_code == status and not service.mock_calls
