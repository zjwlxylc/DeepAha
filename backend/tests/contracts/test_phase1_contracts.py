import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ValidationError

from deepaha.contracts.export import (
    PHASE1_SCHEMAS,
    render_phase1_schemas,
    write_phase1_schemas,
)
from deepaha.contracts.phase1 import (
    DocumentSchema,
    EvidenceLocator,
    EvidenceLocatorKind,
    EvidenceRefSchema,
    OpportunitySchema,
    OpportunityStatus,
    PublicationStatus,
    RawArtifactSchema,
    SourceSchema,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
SCHEMA_DIRECTORY = REPOSITORY_ROOT / "contracts" / "schemas" / "v0.1.0"
EXAMPLE_PATH = (
    REPOSITORY_ROOT / "contracts" / "examples" / "v0.1.0" / "phase-1-official-sample.json"
)
FIXED_SHA256 = "1589f9177e197a578c8d37bd5a3bc869a17d7b0936f156666f69a2f88fbb9d2b"


def source_values() -> dict[str, object]:
    return {
        "source_id": UUID("0198d239-4b00-7000-8000-000000000001"),
        "public_id": "src_0198d2394b0070008000000000000001",
        "canonical_url": "https://www.gov.uk/government/organisations/government-skills",
        "authority_name": "Government Skills",
        "tier": "OFFICIAL_PRIMARY",
        "jurisdiction": "United Kingdom",
        "active": True,
        "created_at": datetime(2026, 8, 21, 9, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 8, 21, 9, 0, tzinfo=UTC),
    }


def raw_artifact_values() -> dict[str, object]:
    source = source_values()
    return {
        "artifact_id": UUID("0198d239-4b00-7000-8000-000000000002"),
        "source_id": source["source_id"],
        "requested_url": "https://www.gov.uk/api/content/government/news/example",
        "resolved_url": "https://www.gov.uk/api/content/government/news/example",
        "retrieved_at": datetime(2026, 8, 21, 9, 59, 8, 5000, tzinfo=UTC),
        "http_status": 200,
        "media_type": "application/json; charset=utf-8",
        "content_sha256": FIXED_SHA256,
        "storage_uri": f"s3://deepaha-raw/raw/sha256/15/{FIXED_SHA256}",
        "byte_size": 11662,
        "collector_version": "phase1_design_capture/0.1.0",
        "metadata_schema_version": "0.1.0",
    }


def document_values() -> dict[str, object]:
    raw_artifact = raw_artifact_values()
    return {
        "document_id": UUID("0198d239-4b00-7000-8000-000000000003"),
        "artifact_id": raw_artifact["artifact_id"],
        "title": "Civil Service Fast Stream named UK's top graduate employer",
        "published_at": datetime(2025, 9, 17, 7, 0, tzinfo=UTC),
        "language": "en",
        "extracted_text_uri": None,
        "parser_name": "phase1_fixture_manifest",
        "parser_version": "0.1.0",
        "parse_confidence": None,
        "created_at": datetime(2026, 8, 21, 10, 0, tzinfo=UTC),
    }


def opportunity_values() -> dict[str, object]:
    return {
        "opportunity_id": UUID("0198d239-4b00-7000-8000-000000000004"),
        "public_id": "opp_0198d2394b0070008000000000000004",
        "type": "CIVIL_SERVICE",
        "canonical_title": "Civil Service Fast Stream",
        "issuer_name": "Civil Service Fast Stream",
        "jurisdiction": "United Kingdom",
        "current_version": None,
        "status": OpportunityStatus.UNKNOWN,
        "publication_status": PublicationStatus.INTERNAL,
        "created_at": datetime(2026, 8, 21, 10, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 8, 21, 10, 0, tzinfo=UTC),
    }


def evidence_ref_values() -> dict[str, object]:
    document = document_values()
    return {
        "document_id": document["document_id"],
        "artifact_id": document["artifact_id"],
        "locator": {"kind": "full_document", "value": "*"},
        "quote_sha256": FIXED_SHA256,
    }


def test_opportunity_accepts_unversioned_internal_identity() -> None:
    opportunity = OpportunitySchema.model_validate(opportunity_values())

    assert opportunity.current_version is None
    assert opportunity.status is OpportunityStatus.UNKNOWN
    assert opportunity.publication_status is PublicationStatus.INTERNAL


def test_entity_id_rejects_uuid4() -> None:
    values = opportunity_values()
    values["opportunity_id"] = uuid4()

    with pytest.raises(ValidationError, match="UUIDv7"):
        OpportunitySchema.model_validate(values)


def test_aware_instants_are_normalized_to_utc() -> None:
    values = source_values()
    values["created_at"] = datetime(
        2026,
        8,
        21,
        17,
        0,
        tzinfo=timezone(timedelta(hours=8)),
    )
    values["updated_at"] = values["created_at"]

    source = SourceSchema.model_validate(values)

    assert source.created_at == datetime(2026, 8, 21, 9, 0, tzinfo=UTC)
    assert source.created_at.tzinfo is UTC


def test_naive_instant_is_rejected() -> None:
    values = source_values()
    values["created_at"] = datetime(2026, 8, 21, 9, 0)

    with pytest.raises(ValidationError, match="timezone"):
        SourceSchema.model_validate(values)


def test_source_rejects_updated_at_before_created_at() -> None:
    values = source_values()
    values["updated_at"] = datetime(2026, 8, 21, 8, 59, tzinfo=UTC)

    with pytest.raises(ValidationError, match="updated_at"):
        SourceSchema.model_validate(values)


@pytest.mark.parametrize("invalid_hash", ["a" * 63, "A" * 64])
def test_raw_artifact_rejects_noncanonical_sha256(invalid_hash: str) -> None:
    values = raw_artifact_values()
    values["content_sha256"] = invalid_hash

    with pytest.raises(ValidationError):
        RawArtifactSchema.model_validate(values)


def test_raw_artifact_rejects_nonpositive_byte_size() -> None:
    values = raw_artifact_values()
    values["byte_size"] = 0

    with pytest.raises(ValidationError):
        RawArtifactSchema.model_validate(values)


def test_storage_uri_rejects_endpoint_credentials() -> None:
    values = raw_artifact_values()
    values["storage_uri"] = f"s3://access:secret@deepaha-raw/raw/sha256/15/{FIXED_SHA256}"

    with pytest.raises(ValidationError):
        RawArtifactSchema.model_validate(values)


def test_opportunity_rejects_version_zero() -> None:
    values = opportunity_values()
    values["current_version"] = 0

    with pytest.raises(ValidationError):
        OpportunitySchema.model_validate(values)


def test_opportunity_rejects_unknown_type() -> None:
    values = opportunity_values()
    values["type"] = "GENERIC_JOB"

    with pytest.raises(ValidationError):
        OpportunitySchema.model_validate(values)


def test_opportunity_rejects_updated_at_before_created_at() -> None:
    values = opportunity_values()
    values["updated_at"] = datetime(2026, 8, 21, 9, 59, tzinfo=UTC)

    with pytest.raises(ValidationError, match="updated_at"):
        OpportunitySchema.model_validate(values)


def test_full_document_locator_has_fixed_value() -> None:
    assert EvidenceLocator(kind=EvidenceLocatorKind.FULL_DOCUMENT, value="*").value == "*"

    with pytest.raises(ValidationError, match="full_document"):
        EvidenceLocator(kind=EvidenceLocatorKind.FULL_DOCUMENT, value="whole page")


def test_public_contracts_reject_extra_fields() -> None:
    values = document_values()
    values["opportunity_id"] = UUID("0198d239-4b00-7000-8000-000000000004")

    with pytest.raises(ValidationError, match="Extra inputs"):
        DocumentSchema.model_validate(values)


def test_document_and_opportunity_have_distinct_contract_fields() -> None:
    assert "artifact_id" in DocumentSchema.model_fields
    assert "artifact_id" not in OpportunitySchema.model_fields
    assert "document_id" not in OpportunitySchema.model_fields
    assert "opportunity_id" not in DocumentSchema.model_fields


def test_versioned_examples_validate_with_pydantic_and_json_schema() -> None:
    from jsonschema import Draft202012Validator

    examples = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    model_by_key: dict[str, type[BaseModel]] = {
        "source": SourceSchema,
        "raw_artifact": RawArtifactSchema,
        "document": DocumentSchema,
        "opportunity": OpportunitySchema,
        "evidence_ref": EvidenceRefSchema,
    }
    schema_name_by_key = {
        "source": "source.schema.json",
        "raw_artifact": "raw-artifact.schema.json",
        "document": "document.schema.json",
        "opportunity": "opportunity.schema.json",
        "evidence_ref": "evidence-ref.schema.json",
    }

    assert set(examples) == set(model_by_key)
    for key, model in model_by_key.items():
        model.model_validate(examples[key])
        schema = json.loads((SCHEMA_DIRECTORY / schema_name_by_key[key]).read_text("utf-8"))
        Draft202012Validator(schema).validate(examples[key])


def test_checked_in_schemas_match_deterministic_renderer() -> None:
    rendered = render_phase1_schemas()

    assert set(rendered) == set(PHASE1_SCHEMAS)
    assert set(rendered) == {path.name for path in SCHEMA_DIRECTORY.glob("*.schema.json")}
    for name, content in rendered.items():
        assert (SCHEMA_DIRECTORY / name).read_bytes() == content


def test_schema_export_writes_only_to_the_versioned_contract_directory(
    tmp_path: Path,
) -> None:
    written = write_phase1_schemas(tmp_path)
    expected_directory = tmp_path / "contracts" / "schemas" / "v0.1.0"

    assert set(written) == set(PHASE1_SCHEMAS)
    assert {path.parent for path in written.values()} == {expected_directory}
    assert {path.name for path in written.values()} == set(PHASE1_SCHEMAS)
    assert not (tmp_path / "source.schema.json").exists()
