import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from deepaha.contracts.export import PHASE9B_SCHEMAS, render_phase9b_schemas
from deepaha.contracts.phase9b import (
    AnswerAccessClass,
    DatasetManifestEntrySchemaV08,
    DatasetManifestSchemaV08,
    DatasetPartition,
    DocumentParseIdentitySchemaV08,
    OpportunityUnitKind,
    OpportunityUnitSchemaV08,
    SourceBundleMemberProvenanceSchemaV08,
    SourceBundleRevisionSchemaV08,
    SourceBundleRevisionStatus,
)
from deepaha.p9b.hashing import document_parse_key

REPOSITORY_ROOT = Path(__file__).parents[3]
SCHEMA_ROOT = REPOSITORY_ROOT / "contracts" / "schemas" / "v0.8.0"
EXAMPLE_PATH = REPOSITORY_ROOT / "contracts" / "examples" / "v0.8.0" / "p9-b0-example.json"


def uuid7(index: int) -> UUID:
    return UUID(f"019c0000-0000-7000-8000-{index:012x}")


def parse_identity_values(**changes: object) -> dict[str, object]:
    parse_key_override = changes.pop("document_parse_key", None)
    values: dict[str, object] = {
        "artifact_id": uuid7(1),
        "artifact_sha256": "a" * 64,
        "parser_name": "deepaha-html",
        "parser_version": "1.0.0",
        "parse_contract_version": "phase2-locator-contract-v0.2.0",
    }
    values.update(changes)
    values["document_parse_key"] = document_parse_key(**values)  # type: ignore[arg-type]
    if parse_key_override is not None:
        values["document_parse_key"] = parse_key_override
    return values


def bundle_member_values(*, revision_id: UUID) -> dict[str, object]:
    return {
        "source_bundle_member_id": uuid7(40),
        "source_bundle_revision_id": revision_id,
        "source_id": uuid7(41),
        "endpoint_id": uuid7(42),
        "capture_observation_id": uuid7(43),
        "acquisition_evaluation_id": uuid7(44),
        "acquisition_validation_status": "VALID",
        "acquisition_run_id": uuid7(45),
        "recipe_id": uuid7(46),
        "recipe_version": "2026-08-24.1",
        "policy_version": "2026-08-24.1",
        "fetch_strategy": "STATIC_HTTP",
        "fetcher_name": "static-http",
        "fetcher_version": "1.0.0",
        "validator_name": "deepaha-content-validator",
        "validator_version": "1.0.0",
        "raw_artifact_id": uuid7(47),
        "raw_artifact_sha256": "b" * 64,
        "raw_artifact_size": 12,
        "storage_bucket": "deepaha-raw",
        "object_key": f"raw/sha256/bb/{'b' * 64}",
        "document_id": uuid7(48),
        "document_parse_identity": parse_identity_values(
            artifact_id=uuid7(47), artifact_sha256="b" * 64
        ),
        "member_role": "PRIMARY_NOTICE",
        "relation_type": "PRIMARY",
        "precedence": 1000,
        "related_member_id": None,
        "effective_from": datetime(2026, 8, 24, tzinfo=UTC),
        "effective_to": None,
        "member_provenance_hash": "c" * 64,
    }


def test_document_parse_identity_binds_contract_and_rejects_wrong_key() -> None:
    identity = DocumentParseIdentitySchemaV08.model_validate(parse_identity_values())
    assert identity.parse_contract_version == "phase2-locator-contract-v0.2.0"

    with pytest.raises(ValidationError, match="document_parse_key"):
        DocumentParseIdentitySchemaV08.model_validate(
            parse_identity_values(document_parse_key="b" * 64)
        )


def test_opportunity_unit_uses_real_composite_parent_version_identity() -> None:
    values = {
        "opportunity_unit_id": uuid7(2),
        "public_id": "unit_00000000000000000000000000000002",
        "opportunity_id": uuid7(3),
        "opportunity_version": 4,
        "current_unit_key": "A001",
        "normalized_current_unit_key": "a001",
        "unit_kind": OpportunityUnitKind.POSITION,
        "lifecycle_status": "ACTIVE",
        "current_version_id": uuid7(4),
        "created_at": datetime(2026, 8, 24, tzinfo=UTC),
        "retired_at": None,
    }

    unit = OpportunityUnitSchemaV08.model_validate(values)
    assert unit.opportunity_version == 4

    values["opportunity_version_id"] = uuid7(5)
    with pytest.raises(ValidationError, match="opportunity_version_id"):
        OpportunityUnitSchemaV08.model_validate(values)


def test_member_provenance_requires_independent_acquisition_and_parse_binding() -> None:
    member = SourceBundleMemberProvenanceSchemaV08.model_validate(
        {
            "source_bundle_member_id": uuid7(10),
            "source_bundle_revision_id": uuid7(11),
            "source_id": uuid7(12),
            "endpoint_id": uuid7(13),
            "capture_observation_id": uuid7(14),
            "acquisition_evaluation_id": uuid7(15),
            "acquisition_validation_status": "VALID",
            "acquisition_run_id": uuid7(16),
            "recipe_id": uuid7(17),
            "recipe_version": "2026-08-24.1",
            "policy_version": "2026-08-24.1",
            "fetch_strategy": "STATIC_HTTP",
            "fetcher_name": "static-http",
            "fetcher_version": "1.0.0",
            "validator_name": "deepaha-content-validator",
            "validator_version": "1.0.0",
            "raw_artifact_id": uuid7(18),
            "raw_artifact_sha256": "b" * 64,
            "raw_artifact_size": 12,
            "storage_bucket": "deepaha-raw",
            "object_key": f"raw/sha256/bb/{'b' * 64}",
            "document_id": uuid7(19),
            "document_parse_identity": parse_identity_values(
                artifact_id=uuid7(18), artifact_sha256="b" * 64
            ),
            "member_role": "ATTACHMENT",
            "relation_type": "ATTACHES_TO",
            "precedence": 500,
            "related_member_id": uuid7(20),
            "effective_from": datetime(2026, 8, 24, tzinfo=UTC),
            "effective_to": None,
            "member_provenance_hash": "c" * 64,
        }
    )
    assert member.acquisition_validation_status == "VALID"

    invalid = member.model_dump(mode="python")
    invalid["acquisition_validation_status"] = "CONTENT_CHALLENGE"
    with pytest.raises(ValidationError, match="VALID"):
        SourceBundleMemberProvenanceSchemaV08.model_validate(invalid)


def test_invalidated_bundle_revision_keeps_original_frozen_timestamp() -> None:
    revision_id = uuid7(30)
    member = SourceBundleMemberProvenanceSchemaV08.model_validate(
        bundle_member_values(revision_id=revision_id)
    )

    revision = SourceBundleRevisionSchemaV08(
        source_bundle_revision_id=revision_id,
        source_bundle_id=uuid7(31),
        opportunity_id=uuid7(32),
        opportunity_version=1,
        revision_number=1,
        canonical_bundle_hash="d" * 64,
        relation_graph_version="p9b-member-relation-v0.8.0",
        precedence_graph_version="p9b-precedence-v0.8.0",
        effective_as_of=datetime(2026, 8, 24, tzinfo=UTC),
        status=SourceBundleRevisionStatus.INVALIDATED,
        members=[member],
        created_at=datetime(2026, 8, 24, tzinfo=UTC),
        frozen_at=datetime(2026, 8, 24, tzinfo=UTC),
    )

    assert revision.status == "INVALIDATED"


def manifest_entry(index: int, *, partition: DatasetPartition) -> DatasetManifestEntrySchemaV08:
    access = {
        DatasetPartition.CALIBRATION: AnswerAccessClass.ASSISTED_CALIBRATION,
        DatasetPartition.DEVELOPMENT: AnswerAccessClass.DEVELOPMENT_VISIBLE,
        DatasetPartition.VALIDATION: AnswerAccessClass.VALIDATION_BLIND,
        DatasetPartition.LOCKED_ACCEPTANCE: AnswerAccessClass.LOCKED_BLIND,
    }[partition]
    return DatasetManifestEntrySchemaV08(
        entry_id=f"entry-{index:03d}",
        partition=partition,
        opportunity_id=uuid7(1000 + index),
        opportunity_version=1,
        opportunity_unit_id=uuid7(2000 + index),
        opportunity_unit_version_id=uuid7(3000 + index),
        source_bundle_id=uuid7(4000 + index),
        source_bundle_revision_id=uuid7(5000 + index),
        canonical_bundle_hash="d" * 64,
        atomic_group_id=f"atomic-{index:03d}",
        near_duplicate_cluster_ids=[f"near-{index:03d}"],
        unit_lineage_ids=[f"lineage-{index:03d}"],
        evaluation_as_of=datetime(2026, 8, 24, tzinfo=UTC),
        answer_access_class=access,
    )


@pytest.mark.parametrize(
    ("partition", "expected_count"),
    [
        (DatasetPartition.CALIBRATION, 30),
        (DatasetPartition.DEVELOPMENT, 70),
        (DatasetPartition.VALIDATION, 30),
        (DatasetPartition.LOCKED_ACCEPTANCE, 200),
    ],
)
def test_dataset_manifest_requires_exact_entry_and_atomic_group_counts(
    partition: DatasetPartition, expected_count: int
) -> None:
    entries = [manifest_entry(index, partition=partition) for index in range(expected_count)]
    manifest = DatasetManifestSchemaV08(
        split_manifest_version="1.0.0",
        partition=partition,
        expected_entry_count=expected_count,
        actual_entry_count=expected_count,
        atomic_group_count=expected_count,
        entries=entries,
        evaluation_cutoff=datetime(2026, 8, 24, tzinfo=UTC),
        answer_access_class=entries[0].answer_access_class,
        frozen_by="human-curator-01",
        frozen_at=datetime(2026, 8, 24, tzinfo=UTC),
        invalidated_at=None,
        invalidation_reason=None,
        successor_manifest_hash=None,
        manifest_hash="e" * 64,
    )
    assert manifest.actual_entry_count == expected_count

    with pytest.raises(ValidationError, match="exact"):
        DatasetManifestSchemaV08.model_validate(
            {**manifest.model_dump(mode="python"), "actual_entry_count": expected_count + 1}
        )
    with pytest.raises(ValidationError, match="atomic_group_count"):
        DatasetManifestSchemaV08.model_validate(
            {**manifest.model_dump(mode="python"), "atomic_group_count": expected_count - 1}
        )


def test_v08_renderer_matches_checked_in_json_schemas() -> None:
    rendered = render_phase9b_schemas()
    assert set(rendered) == set(PHASE9B_SCHEMAS)
    for name, content in rendered.items():
        assert (SCHEMA_ROOT / name).read_bytes() == content
        Draft202012Validator.check_schema(json.loads(content))


def test_v08_example_uses_composite_opportunity_version_and_valid_parse_identity() -> None:
    example = json.loads(EXAMPLE_PATH.read_text("utf-8"))

    unit = OpportunityUnitSchemaV08.model_validate(example["opportunity_unit"])
    parse_identity = DocumentParseIdentitySchemaV08.model_validate(
        example["document_parse_identity"]
    )

    assert unit.opportunity_version == 4
    assert "opportunity_version_id" not in example["opportunity_unit"]
    assert parse_identity.document_parse_key == (
        "76a7a2cd02753d93e0d459a02ff26e73f0d775ad97c28c781ead845b7dd0125d"
    )
