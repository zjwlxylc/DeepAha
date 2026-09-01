from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from uuid import UUID, uuid7

from pydantic import BaseModel, ConfigDict, HttpUrl
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from deepaha.artifacts.models import RawArtifact
from deepaha.artifacts.object_store import ObjectIntegrityError, ObjectMetadata, ObjectStore
from deepaha.contracts.common import EntityId, HttpStatus, Instant, NonEmptyString
from deepaha.contracts.phase1 import RawArtifactSchema


@dataclass(frozen=True, slots=True)
class ImportRawArtifactCommand:
    source_id: UUID
    requested_url: str
    resolved_url: str
    retrieved_at: datetime
    http_status: int | None
    media_type: str | None
    content: bytes
    collector_version: str
    metadata_schema_version: str


@dataclass(frozen=True, slots=True)
class ImportRawArtifactResult:
    artifact: RawArtifact
    created: bool


@dataclass(frozen=True, slots=True)
class _PreparedRawArtifact:
    candidate: dict[str, object]
    source_id: UUID
    content_sha256: str


class RawArtifactProvenanceConflict(RuntimeError):
    def __init__(self) -> None:
        self.code = "RAW_ARTIFACT_PROVENANCE_CONFLICT"
        super().__init__(self.code)


class _ValidatedImportCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: EntityId
    requested_url: HttpUrl
    resolved_url: HttpUrl
    retrieved_at: Instant
    http_status: HttpStatus | None
    media_type: NonEmptyString | None
    collector_version: NonEmptyString
    metadata_schema_version: NonEmptyString


def build_raw_object_key(content_sha256: str) -> str:
    return f"raw/sha256/{content_sha256[:2]}/{content_sha256}"


def import_raw_artifact(
    *,
    session: Session,
    object_store: ObjectStore,
    command: ImportRawArtifactCommand,
    reuse_content_identity: bool = False,
) -> ImportRawArtifactResult:
    prepared = _prepare_raw_artifact(
        object_store=object_store,
        command=command,
        require_matching_media_type=True,
    )
    result = _insert_or_load_raw_artifact(session, prepared)
    if (
        not result.created
        and not reuse_content_identity
        and not _same_capture(result.artifact, prepared.candidate)
    ):
        raise RawArtifactProvenanceConflict
    return result


def _prepare_raw_artifact(
    *,
    object_store: ObjectStore,
    command: ImportRawArtifactCommand,
    require_matching_media_type: bool,
) -> _PreparedRawArtifact:
    if not command.content:
        raise ValueError("raw artifact content must not be empty")

    validated = _ValidatedImportCommand.model_validate(
        {
            "source_id": command.source_id,
            "requested_url": command.requested_url,
            "resolved_url": command.resolved_url,
            "retrieved_at": command.retrieved_at,
            "http_status": command.http_status,
            "media_type": command.media_type,
            "collector_version": command.collector_version,
            "metadata_schema_version": command.metadata_schema_version,
        }
    )
    digest = sha256(command.content).hexdigest()
    object_key = build_raw_object_key(digest)
    stored = object_store.put_bytes_if_absent(
        key=object_key,
        content=command.content,
        media_type=validated.media_type,
        sha256=digest,
    )
    _verify_stored_object(
        stored,
        object_key,
        command.content,
        digest,
        validated.media_type if require_matching_media_type else None,
    )

    artifact_id = uuid7()
    contract = RawArtifactSchema.model_validate(
        {
            "artifact_id": artifact_id,
            "source_id": validated.source_id,
            "requested_url": validated.requested_url,
            "resolved_url": validated.resolved_url,
            "retrieved_at": validated.retrieved_at,
            "http_status": validated.http_status,
            "media_type": validated.media_type,
            "content_sha256": digest,
            "storage_uri": f"s3://{stored.bucket}/{stored.key}",
            "byte_size": len(command.content),
            "collector_version": validated.collector_version,
            "metadata_schema_version": validated.metadata_schema_version,
        }
    )
    candidate = {
        "artifact_id": contract.artifact_id,
        "source_id": contract.source_id,
        "requested_url": str(contract.requested_url),
        "resolved_url": str(contract.resolved_url),
        "retrieved_at": contract.retrieved_at,
        "http_status": contract.http_status,
        "media_type": contract.media_type,
        "content_sha256": contract.content_sha256,
        "storage_bucket": stored.bucket,
        "object_key": stored.key,
        "byte_size": contract.byte_size,
        "collector_version": contract.collector_version,
        "metadata_schema_version": contract.metadata_schema_version,
    }
    return _PreparedRawArtifact(
        candidate=candidate,
        source_id=contract.source_id,
        content_sha256=contract.content_sha256,
    )


def _insert_or_load_raw_artifact(
    session: Session, prepared: _PreparedRawArtifact
) -> ImportRawArtifactResult:
    statement = (
        insert(RawArtifact)
        .values(prepared.candidate)
        .on_conflict_do_nothing(index_elements=[RawArtifact.source_id, RawArtifact.content_sha256])
        .returning(RawArtifact.artifact_id)
    )
    inserted_id = session.scalar(statement)
    if inserted_id is not None:
        artifact = session.get(RawArtifact, inserted_id)
        if artifact is None:
            raise RuntimeError("inserted RawArtifact could not be loaded")
        return ImportRawArtifactResult(artifact=artifact, created=True)

    existing = session.scalar(
        select(RawArtifact).where(
            RawArtifact.source_id == prepared.source_id,
            RawArtifact.content_sha256 == prepared.content_sha256,
        )
    )
    if existing is None:
        raise RuntimeError("conflicting RawArtifact could not be loaded")
    return ImportRawArtifactResult(artifact=existing, created=False)


def _verify_stored_object(
    stored: ObjectMetadata,
    expected_key: str,
    content: bytes,
    digest: str,
    media_type: str | None,
) -> None:
    mismatched = (
        stored.key != expected_key
        or stored.byte_size != len(content)
        or stored.sha256 != digest
        or (media_type is not None and stored.media_type != media_type)
    )
    if mismatched:
        raise ObjectIntegrityError("stored object metadata does not match import command")


def _same_capture(existing: RawArtifact, candidate: dict[str, object]) -> bool:
    compared_fields = (
        "requested_url",
        "resolved_url",
        "retrieved_at",
        "http_status",
        "media_type",
        "byte_size",
        "collector_version",
        "metadata_schema_version",
        "storage_bucket",
        "object_key",
    )
    return all(getattr(existing, field) == candidate[field] for field in compared_fields)
