from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

import pytest
from pydantic import ValidationError

from deepaha.acquisition.contracts import (
    AcquisitionEvaluationSchema,
    ChallengeType,
    ContentExpectations,
    FetchRequest,
    FetchResult,
    FetchStrategy,
    SourceUsageRole,
    ValidationResult,
    ValidationStatus,
)

REQUEST_ID = UUID("019c0000-0000-7000-8000-000000000001")
SOURCE_ID = UUID("019c0000-0000-7000-8000-000000000002")
ENDPOINT_ID = UUID("019c0000-0000-7000-8000-000000000003")
BODY = b"<html><main>official notice</main></html>"
BODY_SHA256 = sha256(BODY).hexdigest()
FETCHED_AT = datetime(2026, 8, 23, 10, 0, tzinfo=UTC)


def request_values() -> dict[str, object]:
    return {
        "request_id": REQUEST_ID,
        "source_id": SOURCE_ID,
        "endpoint_id": ENDPOINT_ID,
        "requested_url": "https://notices.example.gov/list/",
        "strategy": "STATIC_HTTP",
        "allowed_hosts": ["notices.example.gov"],
        "expected_media_types": ["text/html"],
        "timeout_seconds": 30,
        "max_attempts": 2,
        "max_bytes": 1_000_000,
        "policy_version": "2026-08-23.1",
        "contract_version": "1.0.0",
    }


def result_values() -> dict[str, object]:
    return {
        "request_id": REQUEST_ID,
        "source_id": SOURCE_ID,
        "endpoint_id": ENDPOINT_ID,
        "requested_url": "https://notices.example.gov/list/",
        "final_url": "https://notices.example.gov/list/index.html",
        "redirect_chain": [
            "https://notices.example.gov/list/",
            "https://notices.example.gov/list/index.html",
        ],
        "strategy": "STATIC_HTTP",
        "fetched_at": FETCHED_AT,
        "outcome": "SUCCEEDED",
        "http_status": 200,
        "media_type": "text/html; charset=utf-8",
        "safe_headers": {"etag": '"v1"'},
        "body": BODY,
        "body_object_key": None,
        "content_sha256": BODY_SHA256,
        "byte_size": len(BODY),
        "fetcher_name": "deepaha-static-http",
        "fetcher_version": "1.0.0",
        "error_code": None,
        "contract_version": "1.0.0",
    }


def test_closed_acquisition_enums_have_only_approved_values() -> None:
    assert {value.value for value in FetchStrategy} == {
        "STRUCTURED",
        "STATIC_HTTP",
        "BROWSER",
        "OFFICIAL_ALTERNATIVE",
        "MANUAL",
    }
    assert {value.value for value in ValidationStatus} == {
        "VALID",
        "CONTENT_CHALLENGE",
        "CAPTCHA_REQUIRED",
        "AUTH_REQUIRED",
        "ACCESS_DENIED",
        "UNEXPECTED_CONTENT",
        "ZERO_DISCOVERY_SUSPECT",
        "SELECTOR_DRIFT",
    }
    assert {value.value for value in SourceUsageRole} == {
        "PRIMARY_EVIDENCE",
        "OFFICIAL_DISCOVERY",
        "TRUSTED_LEAD",
        "GENERAL_LEAD",
    }


def test_fetch_request_normalizes_policy_lists_and_is_immutable() -> None:
    value = request_values()
    value["allowed_hosts"] = ["NOTICES.EXAMPLE.GOV."]
    value["expected_media_types"] = ["TEXT/HTML"]

    request = FetchRequest.model_validate(value)

    assert request.allowed_hosts == ("notices.example.gov",)
    assert request.expected_media_types == ("text/html",)
    with pytest.raises(ValidationError):
        request.max_attempts = 3


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("request_id", "00000000-0000-4000-8000-000000000001"),
        ("source_id", "00000000-0000-4000-8000-000000000002"),
        ("endpoint_id", "00000000-0000-4000-8000-000000000003"),
        ("requested_url", "https://user:password@notices.example.gov/list/"),
        ("requested_url", "https://other.example.gov/list/"),
        ("max_attempts", 4),
        ("timeout_seconds", 121),
        ("contract_version", "1.1.0"),
    ],
)
def test_fetch_request_rejects_invalid_identity_policy_or_version(
    field: str, invalid: object
) -> None:
    values = request_values()
    values[field] = invalid

    with pytest.raises(ValidationError):
        FetchRequest.model_validate(values)


def test_fetch_request_rejects_duplicate_hosts_and_media_types() -> None:
    for field, duplicates in (
        ("allowed_hosts", ["notices.example.gov", "NOTICES.EXAMPLE.GOV."]),
        ("expected_media_types", ["text/html", "TEXT/HTML"]),
    ):
        values = request_values()
        values[field] = duplicates
        with pytest.raises(ValidationError, match="duplicates"):
            FetchRequest.model_validate(values)


def test_successful_fetch_result_requires_exact_body_hash_and_size() -> None:
    result = FetchResult.model_validate(result_values())

    assert result.content_sha256 == BODY_SHA256
    assert result.redirect_chain[-1] == result.final_url

    for field, invalid in (("content_sha256", "a" * 64), ("byte_size", len(BODY) + 1)):
        values = result_values()
        values[field] = invalid
        with pytest.raises(ValidationError):
            FetchResult.model_validate(values)


def test_fetch_result_requires_exactly_one_body_location_on_success() -> None:
    both = result_values()
    both["body_object_key"] = "raw/sha256/00/example"
    with pytest.raises(ValidationError, match="exactly one"):
        FetchResult.model_validate(both)

    neither = result_values()
    neither["body"] = None
    with pytest.raises(ValidationError, match="exactly one"):
        FetchResult.model_validate(neither)


def test_failed_fetch_result_forbids_body_and_requires_error_code() -> None:
    values = result_values()
    values.update(
        outcome="FAILED",
        http_status=None,
        media_type=None,
        body=None,
        content_sha256=None,
        byte_size=None,
        error_code="NETWORK_TIMEOUT",
    )

    result = FetchResult.model_validate(values)
    assert result.error_code == "NETWORK_TIMEOUT"

    values["body"] = BODY
    with pytest.raises(ValidationError):
        FetchResult.model_validate(values)


def test_fetch_result_rejects_redirect_chain_mismatch_and_unsafe_headers() -> None:
    wrong_chain = result_values()
    wrong_chain["redirect_chain"] = ["https://notices.example.gov/other"]
    with pytest.raises(ValidationError, match="redirect_chain"):
        FetchResult.model_validate(wrong_chain)

    for header in ("set-cookie", "authorization", "x-api-key"):
        unsafe = result_values()
        unsafe["safe_headers"] = {header: "secret"}
        with pytest.raises(ValidationError, match="safe_headers"):
            FetchResult.model_validate(unsafe)


def test_content_expectations_are_bounded_and_declarative() -> None:
    expectations = ContentExpectations.model_validate(
        {
            "minimum_bytes": 20,
            "maximum_bytes": 1_000_000,
            "required_markers": ["official notice"],
            "forbidden_markers": ["cookie challenge"],
            "required_selectors": ["main"],
            "minimum_discovered_count": 1,
            "structured_kind": None,
            "contract_version": "1.0.0",
        }
    )
    assert expectations.required_markers == ("official notice",)

    with pytest.raises(ValidationError):
        ContentExpectations.model_validate(
            {**expectations.model_dump(), "maximum_bytes": 25_000_001}
        )


def test_validation_result_enforces_fail_closed_challenge_shape() -> None:
    valid = ValidationResult.model_validate(
        {
            "status": "VALID",
            "challenge_type": None,
            "discovered_count": 3,
            "diagnostic_codes": [],
            "metrics": {"byte_size": 42, "selector_match": True},
            "validator_name": "deepaha-content-validator",
            "validator_version": "1.0.0",
            "metrics_schema_version": "1.0.0",
            "contract_version": "1.0.0",
        }
    )
    assert valid.status is ValidationStatus.VALID

    with pytest.raises(ValidationError, match="challenge_type"):
        ValidationResult.model_validate(
            {**valid.model_dump(), "status": "CONTENT_CHALLENGE", "challenge_type": None}
        )

    with pytest.raises(ValidationError, match="challenge_type"):
        ValidationResult.model_validate(
            {**valid.model_dump(), "challenge_type": ChallengeType.JAVASCRIPT_COOKIE}
        )


def test_validation_result_rejects_raw_or_nested_diagnostics() -> None:
    values: dict[str, object] = {
        "status": "UNEXPECTED_CONTENT",
        "challenge_type": None,
        "discovered_count": None,
        "diagnostic_codes": ["BODY_TOO_SHORT"],
        "metrics": {"raw_body": "<html>secret</html>"},
        "validator_name": "deepaha-content-validator",
        "validator_version": "1.0.0",
        "metrics_schema_version": "1.0.0",
        "contract_version": "1.0.0",
    }
    with pytest.raises(ValidationError, match="metrics"):
        ValidationResult.model_validate(values)


def evaluation_values() -> dict[str, object]:
    return {
        "acquisition_evaluation_id": UUID("019c0000-0000-7000-8000-000000000004"),
        "observation_id": UUID("019c0000-0000-7000-8000-000000000005"),
        "source_id": SOURCE_ID,
        "endpoint_id": ENDPOINT_ID,
        "artifact_id": UUID("019c0000-0000-7000-8000-000000000006"),
        "strategy_used": "STATIC_HTTP",
        "validation_status": "VALID",
        "challenge_type": None,
        "redirect_chain": [
            "https://notices.example.gov/list/",
            "https://notices.example.gov/list/index.html",
        ],
        "discovered_count": 3,
        "manual_intervention": False,
        "diagnostic_codes": [],
        "validator_name": "deepaha-content-validator",
        "validator_version": "1.0.0",
        "metrics_schema_version": "1.0.0",
        "validation_metrics": {"byte_size": 42, "selector_match": True},
        "evaluated_at": FETCHED_AT,
        "contract_version": "1.0.0",
    }


def test_acquisition_evaluation_is_strict_immutable_semantic_truth() -> None:
    value = AcquisitionEvaluationSchema.model_validate(evaluation_values())

    assert str(value.redirect_chain[0]) == "https://notices.example.gov/list/"
    with pytest.raises(ValidationError):
        value.validation_status = ValidationStatus.UNEXPECTED_CONTENT


def test_acquisition_evaluation_requires_manual_strategy_coherence() -> None:
    manual = evaluation_values()
    manual.update(strategy_used="MANUAL", manual_intervention=False)
    with pytest.raises(ValidationError, match="manual_intervention"):
        AcquisitionEvaluationSchema.model_validate(manual)

    automated = evaluation_values()
    automated["manual_intervention"] = True
    with pytest.raises(ValidationError, match="manual_intervention"):
        AcquisitionEvaluationSchema.model_validate(automated)


def test_acquisition_evaluation_challenge_shape_is_fail_closed() -> None:
    values = evaluation_values()
    values.update(validation_status="CAPTCHA_REQUIRED", challenge_type=None)
    with pytest.raises(ValidationError, match="challenge_type"):
        AcquisitionEvaluationSchema.model_validate(values)


def test_acquisition_evaluation_diagnostics_are_bounded_and_sanitized() -> None:
    values = evaluation_values()
    values["validation_metrics"] = {"raw_body": "secret response"}
    with pytest.raises(ValidationError, match="validation_metrics"):
        AcquisitionEvaluationSchema.model_validate(values)

    values = evaluation_values()
    values["redirect_chain"] = []
    with pytest.raises(ValidationError):
        AcquisitionEvaluationSchema.model_validate(values)

    values["metrics"] = {"nested": {"value": 1}}
    with pytest.raises(ValidationError, match="metrics"):
        ValidationResult.model_validate(values)
