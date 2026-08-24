from collections.abc import Iterable, Sequence
from datetime import datetime
from uuid import uuid7

from sqlalchemy import select
from sqlalchemy.orm import Session

from deepaha.contracts.phase9b import (
    AnswerAccessClass,
    DatasetManifestEntrySchemaV08,
    DatasetManifestSchemaV08,
    DatasetPartition,
)
from deepaha.p9b.hashing import split_manifest_hash
from deepaha.p9b.models import DatasetManifest, DatasetManifestEntry

SPLIT_MANIFEST_VERSION = "p9b-split-manifest-v0.8.0"

_COUNTS = {
    DatasetPartition.CALIBRATION: 30,
    DatasetPartition.DEVELOPMENT: 70,
    DatasetPartition.VALIDATION: 30,
    DatasetPartition.LOCKED_ACCEPTANCE: 200,
}
_ACCESS = {
    DatasetPartition.CALIBRATION: AnswerAccessClass.ASSISTED_CALIBRATION,
    DatasetPartition.DEVELOPMENT: AnswerAccessClass.DEVELOPMENT_VISIBLE,
    DatasetPartition.VALIDATION: AnswerAccessClass.VALIDATION_BLIND,
    DatasetPartition.LOCKED_ACCEPTANCE: AnswerAccessClass.LOCKED_BLIND,
}


class DatasetLeakageError(ValueError):
    pass


def _validate_manifest_entries(
    entries: Sequence[DatasetManifestEntrySchemaV08],
) -> None:
    entry_ids: set[str] = set()
    identities: set[tuple[object, ...]] = set()
    atomic_by_leakage_key: dict[tuple[str, object], str] = {}
    for entry in entries:
        if entry.entry_id in entry_ids:
            raise DatasetLeakageError("entry_id appears more than once")
        entry_ids.add(entry.entry_id)
        identity = (
            entry.opportunity_id,
            entry.opportunity_version,
            entry.opportunity_unit_id,
            entry.opportunity_unit_version_id,
        )
        if identity in identities:
            raise DatasetLeakageError("identity appears more than once")
        identities.add(identity)
        leakage_keys = [
            ("source_bundle_id", entry.source_bundle_id),
            ("source_bundle_revision_id", entry.source_bundle_revision_id),
            *(
                ("near_duplicate_cluster_ids", cluster_id)
                for cluster_id in entry.near_duplicate_cluster_ids
            ),
            *(("unit_lineage_ids", lineage_id) for lineage_id in entry.unit_lineage_ids),
        ]
        for leakage_key in leakage_keys:
            prior_group = atomic_by_leakage_key.setdefault(
                leakage_key,
                entry.atomic_group_id,
            )
            if prior_group != entry.atomic_group_id:
                raise DatasetLeakageError(f"{leakage_key[0]} must share one atomic_group_id")


def _manifest_payload(values: dict[str, object]) -> dict[str, object]:
    excluded = {
        "manifest_hash",
        "invalidated_at",
        "invalidation_reason",
        "successor_manifest_hash",
    }
    return {key: value for key, value in values.items() if key not in excluded}


def _manifest_hash(manifest: DatasetManifestSchemaV08) -> str:
    values = manifest.model_dump(mode="json")
    return split_manifest_hash(_manifest_payload(values))


def build_frozen_manifest(
    *,
    partition: DatasetPartition,
    entries: Sequence[DatasetManifestEntrySchemaV08],
    evaluation_cutoff: datetime,
    frozen_by: str,
    frozen_at: datetime,
) -> DatasetManifestSchemaV08:
    exact = _COUNTS[partition]
    if len(entries) != exact:
        raise ValueError(f"partition requires exact entry count {exact}")
    _validate_manifest_entries(entries)
    values: dict[str, object] = {
        "split_manifest_version": SPLIT_MANIFEST_VERSION,
        "partition": partition,
        "expected_entry_count": exact,
        "actual_entry_count": len(entries),
        "atomic_group_count": len({entry.atomic_group_id for entry in entries}),
        "entries": list(entries),
        "evaluation_cutoff": evaluation_cutoff,
        "answer_access_class": _ACCESS[partition],
        "frozen_by": frozen_by,
        "frozen_at": frozen_at,
        "invalidated_at": None,
        "invalidation_reason": None,
        "successor_manifest_hash": None,
    }
    serialized: dict[str, object] = {}
    for key, value in values.items():
        if key == "entries":
            serialized[key] = [entry.model_dump(mode="json") for entry in entries]
        elif isinstance(value, (DatasetPartition, AnswerAccessClass)):
            serialized[key] = value.value
        elif isinstance(value, datetime):
            serialized[key] = value.isoformat().replace("+00:00", "Z")
        else:
            serialized[key] = value
    values["manifest_hash"] = split_manifest_hash(_manifest_payload(serialized))
    return DatasetManifestSchemaV08.model_validate(values)


def _claim(
    seen: dict[object, DatasetPartition],
    *,
    value: object,
    partition: DatasetPartition,
    field: str,
) -> None:
    previous = seen.setdefault(value, partition)
    if previous != partition:
        raise DatasetLeakageError(
            f"{field} crosses partitions: {previous.value} -> {partition.value}"
        )


def validate_partition_set(manifests: Iterable[DatasetManifestSchemaV08]) -> None:
    by_partition: dict[DatasetPartition, DatasetManifestSchemaV08] = {}
    for manifest in manifests:
        if manifest.partition in by_partition:
            raise DatasetLeakageError(f"duplicate manifest for {manifest.partition.value}")
        if _manifest_hash(manifest) != manifest.manifest_hash:
            raise DatasetLeakageError(f"manifest_hash mismatch for {manifest.partition.value}")
        by_partition[manifest.partition] = manifest
    if set(by_partition) != set(DatasetPartition):
        raise DatasetLeakageError("partition set must contain all four partitions exactly once")

    identity_seen: dict[object, DatasetPartition] = {}
    bundle_seen: dict[object, DatasetPartition] = {}
    revision_seen: dict[object, DatasetPartition] = {}
    atomic_seen: dict[object, DatasetPartition] = {}
    near_seen: dict[object, DatasetPartition] = {}
    lineage_seen: dict[object, DatasetPartition] = {}
    for partition in DatasetPartition:
        for entry in by_partition[partition].entries:
            identity = (
                entry.opportunity_id,
                entry.opportunity_version,
                entry.opportunity_unit_id,
                entry.opportunity_unit_version_id,
            )
            _claim(
                identity_seen,
                value=identity,
                partition=partition,
                field="identity",
            )
            _claim(
                bundle_seen,
                value=entry.source_bundle_id,
                partition=partition,
                field="source_bundle_id",
            )
            _claim(
                revision_seen,
                value=entry.source_bundle_revision_id,
                partition=partition,
                field="source_bundle_revision_id",
            )
            _claim(
                atomic_seen,
                value=entry.atomic_group_id,
                partition=partition,
                field="atomic_group_id",
            )
            for cluster_id in entry.near_duplicate_cluster_ids:
                _claim(
                    near_seen,
                    value=cluster_id,
                    partition=partition,
                    field="near_duplicate_cluster_ids",
                )
            for lineage_id in entry.unit_lineage_ids:
                _claim(
                    lineage_seen,
                    value=lineage_id,
                    partition=partition,
                    field="unit_lineage_ids",
                )


class DatasetManifestRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def persist_frozen(
        self,
        manifest: DatasetManifestSchemaV08,
    ) -> DatasetManifest:
        _validate_manifest_entries(manifest.entries)
        if _manifest_hash(manifest) != manifest.manifest_hash:
            raise DatasetLeakageError("manifest_hash mismatch")
        existing = self._session.scalar(
            select(DatasetManifest).where(DatasetManifest.manifest_hash == manifest.manifest_hash)
        )
        if existing is not None:
            if existing.status != "FROZEN":
                raise DatasetLeakageError("an invalidated manifest cannot be frozen again")
            return existing
        manifest_id = uuid7()
        row = DatasetManifest(
            dataset_manifest_id=manifest_id,
            split_manifest_version=manifest.split_manifest_version,
            partition=manifest.partition.value,
            expected_entry_count=manifest.expected_entry_count,
            actual_entry_count=0,
            atomic_group_count=0,
            evaluation_cutoff=manifest.evaluation_cutoff,
            answer_access_class=manifest.answer_access_class.value,
            status="DRAFT",
            frozen_by=manifest.frozen_by,
            created_at=manifest.frozen_at,
            frozen_at=None,
            invalidated_at=None,
            invalidation_reason=None,
            successor_manifest_hash=None,
            manifest_hash=manifest.manifest_hash,
        )
        self._session.add(row)
        self._session.flush()
        self._session.add_all(
            [
                DatasetManifestEntry(
                    dataset_manifest_id=manifest_id,
                    entry_id=entry.entry_id,
                    partition=entry.partition.value,
                    opportunity_id=entry.opportunity_id,
                    opportunity_version=entry.opportunity_version,
                    opportunity_unit_id=entry.opportunity_unit_id,
                    opportunity_unit_version_id=entry.opportunity_unit_version_id,
                    source_bundle_id=entry.source_bundle_id,
                    source_bundle_revision_id=entry.source_bundle_revision_id,
                    canonical_bundle_hash=entry.canonical_bundle_hash,
                    atomic_group_id=entry.atomic_group_id,
                    near_duplicate_cluster_ids=entry.near_duplicate_cluster_ids,
                    unit_lineage_ids=entry.unit_lineage_ids,
                    evaluation_as_of=entry.evaluation_as_of,
                    answer_access_class=entry.answer_access_class.value,
                    created_at=manifest.frozen_at,
                )
                for entry in manifest.entries
            ]
        )
        self._session.flush()
        row.actual_entry_count = manifest.actual_entry_count
        row.atomic_group_count = manifest.atomic_group_count
        row.status = "FROZEN"
        row.frozen_at = manifest.frozen_at
        self._session.flush()
        return row

    def invalidate(
        self,
        manifest_hash: str,
        *,
        invalidated_at: datetime,
        reason: str,
        successor_manifest_hash: str | None,
    ) -> DatasetManifest:
        row = self._session.scalar(
            select(DatasetManifest).where(DatasetManifest.manifest_hash == manifest_hash)
        )
        if row is None or row.status != "FROZEN":
            raise DatasetLeakageError("only a FROZEN manifest can be invalidated")
        if not reason.strip():
            raise DatasetLeakageError("manifest invalidation requires a reason")
        row.status = "INVALIDATED"
        row.invalidated_at = invalidated_at
        row.invalidation_reason = reason
        row.successor_manifest_hash = successor_manifest_hash
        self._session.flush()
        return row


__all__ = [
    "DatasetLeakageError",
    "DatasetManifestRepository",
    "SPLIT_MANIFEST_VERSION",
    "build_frozen_manifest",
    "validate_partition_set",
]
