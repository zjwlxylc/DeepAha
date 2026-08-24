from datetime import UTC, datetime
from uuid import UUID

import pytest

from deepaha.contracts.phase9b import (
    AnswerAccessClass,
    DatasetManifestEntrySchemaV08,
    DatasetManifestSchemaV08,
    DatasetPartition,
)
from deepaha.p9b.datasets import (
    DatasetLeakageError,
    build_frozen_manifest,
    validate_partition_set,
)

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
COUNTS = {
    DatasetPartition.CALIBRATION: 30,
    DatasetPartition.DEVELOPMENT: 70,
    DatasetPartition.VALIDATION: 30,
    DatasetPartition.LOCKED_ACCEPTANCE: 200,
}
ACCESS = {
    DatasetPartition.CALIBRATION: AnswerAccessClass.ASSISTED_CALIBRATION,
    DatasetPartition.DEVELOPMENT: AnswerAccessClass.DEVELOPMENT_VISIBLE,
    DatasetPartition.VALIDATION: AnswerAccessClass.VALIDATION_BLIND,
    DatasetPartition.LOCKED_ACCEPTANCE: AnswerAccessClass.LOCKED_BLIND,
}


def uuid7(index: int) -> UUID:
    return UUID(f"019c0000-{index // 65536:04x}-7{index % 4096:03x}-8000-{index:012x}")


def entries(partition: DatasetPartition, *, offset: int) -> list[DatasetManifestEntrySchemaV08]:
    return [
        DatasetManifestEntrySchemaV08(
            entry_id=f"{partition.value.lower()}-{index}",
            partition=partition,
            opportunity_id=uuid7(offset + index * 7 + 1),
            opportunity_version=1,
            opportunity_unit_id=uuid7(offset + index * 7 + 2),
            opportunity_unit_version_id=uuid7(offset + index * 7 + 3),
            source_bundle_id=uuid7(offset + index * 7 + 4),
            source_bundle_revision_id=uuid7(offset + index * 7 + 5),
            canonical_bundle_hash=f"{offset + index:064x}",
            atomic_group_id=f"atomic-{offset + index}",
            near_duplicate_cluster_ids=[f"near-{offset + index}"],
            unit_lineage_ids=[f"lineage-{offset + index}"],
            evaluation_as_of=NOW,
            answer_access_class=ACCESS[partition],
        )
        for index in range(COUNTS[partition])
    ]


def valid_manifests() -> tuple[DatasetManifestSchemaV08, ...]:
    offsets = {
        DatasetPartition.CALIBRATION: 1_000,
        DatasetPartition.DEVELOPMENT: 10_000,
        DatasetPartition.VALIDATION: 20_000,
        DatasetPartition.LOCKED_ACCEPTANCE: 30_000,
    }
    return tuple(
        build_frozen_manifest(
            partition=partition,
            entries=entries(partition, offset=offsets[partition]),
            evaluation_cutoff=NOW,
            frozen_by="synthetic-human-curator",
            frozen_at=NOW,
        )
        for partition in DatasetPartition
    )


def test_builds_exact_partition_counts_and_reproducible_hashes() -> None:
    manifests = valid_manifests()

    validate_partition_set(manifests)

    assert [manifest.actual_entry_count for manifest in manifests] == [30, 70, 30, 200]
    assert all(manifest.atomic_group_count == manifest.actual_entry_count for manifest in manifests)
    assert all(len(manifest.manifest_hash) == 64 for manifest in manifests)
    assert manifests == valid_manifests()


def test_rejects_any_entry_count_over_or_under_exact_target() -> None:
    rows = entries(DatasetPartition.CALIBRATION, offset=1_000)[:-1]

    with pytest.raises(ValueError, match="exact entry count 30"):
        build_frozen_manifest(
            partition=DatasetPartition.CALIBRATION,
            entries=rows,
            evaluation_cutoff=NOW,
            frozen_by="synthetic-human-curator",
            frozen_at=NOW,
        )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("source_bundle_id", "source_bundle_id"),
        ("atomic_group_id", "atomic_group_id"),
        ("near_duplicate_cluster_ids", "near_duplicate_cluster_ids"),
        ("unit_lineage_ids", "unit_lineage_ids"),
    ],
)
def test_atomic_leakage_group_cannot_cross_partition(field: str, replacement: str) -> None:
    manifests = list(valid_manifests())
    development = manifests[1]
    locked = manifests[3]
    copied = getattr(development.entries[0], replacement)
    locked_entries = list(locked.entries)
    locked_entries[0] = locked_entries[0].model_copy(update={field: copied})
    manifests[3] = build_frozen_manifest(
        partition=DatasetPartition.LOCKED_ACCEPTANCE,
        entries=locked_entries,
        evaluation_cutoff=NOW,
        frozen_by="synthetic-human-curator",
        frozen_at=NOW,
    )

    with pytest.raises(DatasetLeakageError, match=field):
        validate_partition_set(manifests)


def test_locked_rejects_identity_seen_in_any_earlier_partition() -> None:
    manifests = list(valid_manifests())
    calibration = manifests[0]
    locked = manifests[3]
    locked_entries = list(locked.entries)
    locked_entries[0] = locked_entries[0].model_copy(
        update={
            "opportunity_id": calibration.entries[0].opportunity_id,
            "opportunity_version": calibration.entries[0].opportunity_version,
            "opportunity_unit_id": calibration.entries[0].opportunity_unit_id,
            "opportunity_unit_version_id": calibration.entries[0].opportunity_unit_version_id,
        }
    )
    manifests[3] = build_frozen_manifest(
        partition=DatasetPartition.LOCKED_ACCEPTANCE,
        entries=locked_entries,
        evaluation_cutoff=NOW,
        frozen_by="synthetic-human-curator",
        frozen_at=NOW,
    )

    with pytest.raises(DatasetLeakageError, match="identity"):
        validate_partition_set(manifests)


def test_same_bundle_must_share_one_atomic_group_inside_partition() -> None:
    rows = entries(DatasetPartition.CALIBRATION, offset=1_000)
    rows[1] = rows[1].model_copy(update={"source_bundle_id": rows[0].source_bundle_id})

    with pytest.raises(DatasetLeakageError, match="atomic_group_id"):
        build_frozen_manifest(
            partition=DatasetPartition.CALIBRATION,
            entries=rows,
            evaluation_cutoff=NOW,
            frozen_by="synthetic-human-curator",
            frozen_at=NOW,
        )


def test_duplicate_entry_or_identity_is_not_counted_twice() -> None:
    rows = entries(DatasetPartition.CALIBRATION, offset=1_000)
    rows[1] = rows[0].model_copy(update={"entry_id": "duplicate-identity"})

    with pytest.raises(DatasetLeakageError, match="identity"):
        build_frozen_manifest(
            partition=DatasetPartition.CALIBRATION,
            entries=rows,
            evaluation_cutoff=NOW,
            frozen_by="synthetic-human-curator",
            frozen_at=NOW,
        )


def test_invalidation_audit_does_not_rewrite_frozen_manifest_hash() -> None:
    manifests = list(valid_manifests())
    original_hash = manifests[0].manifest_hash
    manifests[0] = manifests[0].model_copy(
        update={
            "invalidated_at": NOW,
            "invalidation_reason": "Superseded after source correction",
            "successor_manifest_hash": "f" * 64,
        }
    )

    validate_partition_set(manifests)

    assert manifests[0].manifest_hash == original_hash
