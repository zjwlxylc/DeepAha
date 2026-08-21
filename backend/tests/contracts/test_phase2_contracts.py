import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import BaseModel, ValidationError

from deepaha.contracts.export import (
    PHASE2_SCHEMAS,
    render_phase1_schemas,
    render_phase2_schemas,
    write_phase2_schemas,
)
from deepaha.contracts.phase1 import OpportunityType
from deepaha.contracts.phase2 import (
    CaptureObservationSchema,
    EvidenceRefSchemaV02,
    OpportunityTypeV02,
    ParseAttemptSchema,
    SourceEndpointSchema,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
V01_SCHEMA_DIRECTORY = REPOSITORY_ROOT / "contracts" / "schemas" / "v0.1.0"
V02_SCHEMA_DIRECTORY = REPOSITORY_ROOT / "contracts" / "schemas" / "v0.2.0"
V02_EXAMPLE_PATH = REPOSITORY_ROOT / "contracts" / "examples" / "v0.2.0" / "phase-2-example.json"
NOW = datetime(2026, 8, 21, 9, 0, tzinfo=UTC)
SOURCE_ID = UUID("0198d239-4b00-7000-8000-000000000001")
ENDPOINT_ID = UUID("0198d239-4b00-7000-8000-000000000002")
ARTIFACT_ID = UUID("0198d239-4b00-7000-8000-000000000003")
DOCUMENT_ID = UUID("0198d239-4b00-7000-8000-000000000004")


def endpoint_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "endpoint_id": ENDPOINT_ID,
        "source_id": SOURCE_ID,
        "url": "https://official.example/notices",
        "allowed_hosts": ["official.example"],
        "expected_media_types": ["text/html"],
        "browser_policy": "NEVER",
        "minimum_interval_seconds": 21600,
        "timeout_seconds": 30,
        "max_attempts": 3,
        "robots_url": "https://official.example/robots.txt",
        "robots_decision": "ALLOWED",
        "robots_checked_at": NOW,
        "content_use_basis": "OFFICIAL_PUBLIC_ACCESS",
        "license_name": None,
        "license_url": None,
        "attribution": None,
        "fixture_storage_allowed": False,
        "usage_note": "Link and evidence metadata only.",
        "policy_version": "2026-08-21.1",
        "active": True,
        "verified_at": NOW,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(changes)
    return values


def observation_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "observation_id": UUID("0198d239-4b00-7000-8000-000000000005"),
        "collection_run_id": UUID("0198d239-4b00-7000-8000-000000000006"),
        "attempt_number": 1,
        "endpoint_id": ENDPOINT_ID,
        "source_id": SOURCE_ID,
        "requested_url": "https://official.example/notices",
        "resolved_url": "https://official.example/notices",
        "started_at": NOW,
        "completed_at": NOW,
        "outcome": "SUCCEEDED",
        "http_status": 200,
        "response_etag": '"etag"',
        "response_last_modified": "Thu, 21 Aug 2026 09:00:00 GMT",
        "artifact_id": ARTIFACT_ID,
        "error_code": None,
        "collector_name": "deepaha_http",
        "collector_version": "0.2.0",
        "policy_version": "2026-08-21.1",
    }
    values.update(changes)
    return values


def parse_attempt_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "parse_attempt_id": UUID("0198d239-4b00-7000-8000-000000000007"),
        "artifact_id": ARTIFACT_ID,
        "parser_name": "html_lxml",
        "parser_version": "0.2.0",
        "started_at": NOW,
        "completed_at": NOW,
        "outcome": "SUCCEEDED",
        "document_id": DOCUMENT_ID,
        "error_code": None,
        "input_media_type": "text/html",
    }
    values.update(changes)
    return values


def evidence_values(locator: dict[str, object]) -> dict[str, object]:
    return {
        "document_id": DOCUMENT_ID,
        "artifact_id": ARTIFACT_ID,
        "locator": locator,
        "quote_sha256": "1" * 64,
    }


def test_v02_has_only_approved_opportunity_additions() -> None:
    legacy = {item.value for item in OpportunityType}

    assert {item.value for item in OpportunityTypeV02} - legacy == {
        "COMPETITION",
        "RESEARCH_PROGRAM",
        "SCHOLARSHIP",
        "YOUTH_DEVELOPMENT_PROGRAM",
    }
    assert legacy <= {item.value for item in OpportunityTypeV02}


def test_active_endpoint_requires_approved_policy_and_matching_host() -> None:
    assert SourceEndpointSchema.model_validate(endpoint_values()).active is True

    for changes in (
        {"robots_decision": "UNKNOWN"},
        {"robots_decision": "DISALLOWED"},
        {"content_use_basis": "UNKNOWN"},
        {"allowed_hosts": ["other.example"]},
    ):
        with pytest.raises(ValidationError):
            SourceEndpointSchema.model_validate(endpoint_values(**changes))


def test_endpoint_open_license_and_fixture_storage_require_permission() -> None:
    with pytest.raises(ValidationError, match="OPEN_LICENSE"):
        SourceEndpointSchema.model_validate(endpoint_values(content_use_basis="OPEN_LICENSE"))

    licensed = endpoint_values(
        content_use_basis="OPEN_LICENSE",
        license_name="Example Open Licence",
        license_url="https://official.example/licence",
        fixture_storage_allowed=True,
    )
    assert SourceEndpointSchema.model_validate(licensed).fixture_storage_allowed is True

    with pytest.raises(ValidationError, match="fixture"):
        SourceEndpointSchema.model_validate(
            endpoint_values(content_use_basis="LINK_ONLY", fixture_storage_allowed=True)
        )


def test_endpoint_normalizes_hosts_and_rejects_nonmonotonic_time() -> None:
    endpoint = SourceEndpointSchema.model_validate(
        endpoint_values(allowed_hosts=["OFFICIAL.EXAMPLE"])
    )
    assert endpoint.allowed_hosts == ("official.example",)

    with pytest.raises(ValidationError, match="updated_at"):
        SourceEndpointSchema.model_validate(endpoint_values(updated_at=NOW - timedelta(seconds=1)))


def test_capture_success_requires_artifact_and_no_error() -> None:
    with pytest.raises(ValidationError, match="SUCCEEDED"):
        CaptureObservationSchema.model_validate(observation_values(artifact_id=None))
    with pytest.raises(ValidationError, match="SUCCEEDED"):
        CaptureObservationSchema.model_validate(observation_values(error_code="NETWORK_ERROR"))


def test_capture_not_modified_requires_304_and_artifact() -> None:
    valid = observation_values(outcome="NOT_MODIFIED", http_status=304)
    assert CaptureObservationSchema.model_validate(valid).artifact_id == ARTIFACT_ID

    for changes in ({"http_status": 200}, {"artifact_id": None}):
        with pytest.raises(ValidationError, match="NOT_MODIFIED"):
            CaptureObservationSchema.model_validate(
                observation_values(outcome="NOT_MODIFIED", http_status=304) | changes
            )


def test_capture_failure_requires_error_and_forbids_artifact() -> None:
    valid = observation_values(
        outcome="FAILED",
        artifact_id=None,
        error_code="NETWORK_TIMEOUT",
        http_status=None,
        resolved_url=None,
    )
    assert CaptureObservationSchema.model_validate(valid).error_code == "NETWORK_TIMEOUT"

    for changes in ({"artifact_id": ARTIFACT_ID}, {"error_code": None}):
        with pytest.raises(ValidationError, match="FAILED"):
            CaptureObservationSchema.model_validate(valid | changes)


def test_capture_rejects_backwards_time_and_extra_fields() -> None:
    with pytest.raises(ValidationError, match="completed_at"):
        CaptureObservationSchema.model_validate(
            observation_values(completed_at=NOW - timedelta(seconds=1))
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        CaptureObservationSchema.model_validate(observation_values(cookie="secret"))


def test_parse_attempt_enforces_outcome_state() -> None:
    ParseAttemptSchema.model_validate(parse_attempt_values())
    ParseAttemptSchema.model_validate(
        parse_attempt_values(outcome="NEEDS_REVIEW", error_code="PDF_PAGE_TEXT_MISSING")
    )
    ParseAttemptSchema.model_validate(
        parse_attempt_values(outcome="FAILED", document_id=None, error_code="PDF_TEXT_EMPTY")
    )

    for values in (
        parse_attempt_values(outcome="SUCCEEDED", document_id=None),
        parse_attempt_values(outcome="FAILED", document_id=DOCUMENT_ID),
        parse_attempt_values(outcome="FAILED", document_id=None, error_code=None),
    ):
        with pytest.raises(ValidationError):
            ParseAttemptSchema.model_validate(values)


def test_v02_evidence_accepts_legacy_and_structured_locators() -> None:
    EvidenceRefSchemaV02.model_validate(evidence_values({"kind": "full_document", "value": "*"}))
    EvidenceRefSchemaV02.model_validate(
        evidence_values(
            {
                "schema_version": "0.2.0",
                "kind": "html_selector",
                "selector": "main > p:nth-of-type(1)",
                "text_sha256": "1" * 64,
            }
        )
    )


def test_v02_evidence_validates_pdf_offsets_and_spreadsheet_ranges() -> None:
    with pytest.raises(ValidationError):
        EvidenceRefSchemaV02.model_validate(
            evidence_values(
                {
                    "schema_version": "0.2.0",
                    "kind": "pdf_page_text",
                    "page_number": 1,
                    "text_start": 10,
                    "text_end": 10,
                    "text_sha256": "1" * 64,
                }
            )
        )
    with pytest.raises(ValidationError):
        EvidenceRefSchemaV02.model_validate(
            evidence_values(
                {
                    "schema_version": "0.2.0",
                    "kind": "spreadsheet_range",
                    "sheet_name": "Sheet1",
                    "start_row": 2,
                    "end_row": 1,
                    "start_column": 1,
                    "end_column": 1,
                    "cells_sha256": "1" * 64,
                }
            )
        )


def test_v02_instants_normalize_to_utc_and_reject_naive_values() -> None:
    endpoint = SourceEndpointSchema.model_validate(
        endpoint_values(
            verified_at=datetime(
                2026,
                8,
                21,
                17,
                0,
                tzinfo=timezone(timedelta(hours=8)),
            )
        )
    )
    assert endpoint.verified_at == NOW

    with pytest.raises(ValidationError, match="timezone"):
        SourceEndpointSchema.model_validate(
            endpoint_values(verified_at=datetime(2026, 8, 21, 9, 0))
        )


def test_v01_renderer_bytes_remain_unchanged() -> None:
    for name, content in render_phase1_schemas().items():
        assert (V01_SCHEMA_DIRECTORY / name).read_bytes() == content


def test_v02_examples_validate_with_pydantic_and_json_schema() -> None:
    from jsonschema import Draft202012Validator

    examples = json.loads(V02_EXAMPLE_PATH.read_text("utf-8"))
    assert set(examples) == {name.removesuffix(".schema.json") for name in PHASE2_SCHEMAS}
    for name, model in PHASE2_SCHEMAS.items():
        key = name.removesuffix(".schema.json")
        model.model_validate(examples[key])
        Draft202012Validator(json.loads((V02_SCHEMA_DIRECTORY / name).read_text("utf-8"))).validate(
            examples[key]
        )


def test_checked_in_v02_schemas_match_deterministic_renderer() -> None:
    rendered = render_phase2_schemas()

    assert set(rendered) == set(PHASE2_SCHEMAS)
    assert set(rendered) == {path.name for path in V02_SCHEMA_DIRECTORY.glob("*.schema.json")}
    for name, content in rendered.items():
        assert (V02_SCHEMA_DIRECTORY / name).read_bytes() == content


def test_phase2_export_writes_only_to_v02_directory(tmp_path: Path) -> None:
    written = write_phase2_schemas(tmp_path)
    expected = tmp_path / "contracts" / "schemas" / "v0.2.0"

    assert set(written) == set(PHASE2_SCHEMAS)
    assert {path.parent for path in written.values()} == {expected}
    assert not (tmp_path / "contracts" / "schemas" / "v0.1.0").exists()


def test_phase2_schema_values_are_models() -> None:
    assert all(issubclass(model, BaseModel) for model in PHASE2_SCHEMAS.values())
