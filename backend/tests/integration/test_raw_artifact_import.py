from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4, uuid7

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from deepaha.artifacts.models import RawArtifact
from deepaha.artifacts.object_store import ObjectMetadata
from deepaha.artifacts.s3 import S3ObjectStore
from deepaha.artifacts.service import (
    ImportRawArtifactCommand,
    RawArtifactProvenanceConflict,
    build_raw_object_key,
    import_raw_artifact,
)
from deepaha.core.settings import Settings
from deepaha.sources.models import Source

pytestmark = pytest.mark.integration


class FailIfCalledObjectStore:
    def ensure_bucket(self) -> None:
        raise AssertionError("object store must not be called")

    def put_bytes_if_absent(
        self,
        *,
        key: str,
        content: bytes,
        media_type: str | None,
        sha256: str,
    ) -> ObjectMetadata:
        raise AssertionError("object store must not be called")

    def get_bytes(self, *, key: str) -> bytes:
        raise AssertionError("object store must not be called")

    def stat(self, *, key: str) -> ObjectMetadata:
        raise AssertionError("object store must not be called")


@pytest.fixture(scope="module")
def object_store() -> S3ObjectStore:
    store = S3ObjectStore(Settings())
    store.ensure_bucket()
    return store


@pytest.fixture
def source(session: Session) -> Source:
    now = datetime(2026, 8, 21, 9, 0, tzinfo=UTC)
    source_id = uuid7()
    value = Source(
        source_id=source_id,
        public_id=f"src_{source_id.hex}",
        canonical_url=f"https://example.gov/source/{source_id.hex}",
        authority_name="Example official authority",
        tier="OFFICIAL_PRIMARY",
        jurisdiction="Example jurisdiction",
        active=True,
        created_at=now,
        updated_at=now,
    )
    session.add(value)
    session.flush()
    return value


def command_for(source: Source) -> ImportRawArtifactCommand:
    return ImportRawArtifactCommand(
        source_id=source.source_id,
        requested_url="https://example.gov/official.json",
        resolved_url="https://example.gov/official.json",
        retrieved_at=datetime(2026, 8, 21, 9, 59, 8, 5000, tzinfo=UTC),
        http_status=200,
        media_type="application/json; charset=utf-8",
        content=b'{"official":true}',
        collector_version="phase1_fixture/0.1.0",
        metadata_schema_version="0.1.0",
    )


def test_replaying_same_capture_returns_same_raw_artifact(
    session: Session,
    object_store: S3ObjectStore,
    source: Source,
) -> None:
    command = command_for(source)

    first = import_raw_artifact(session=session, object_store=object_store, command=command)
    second = import_raw_artifact(session=session, object_store=object_store, command=command)

    assert first.created is True
    assert second.created is False
    assert second.artifact.artifact_id == first.artifact.artifact_id
    assert session.scalar(select(func.count()).select_from(RawArtifact)) == 1


def test_changed_capture_metadata_is_an_explicit_provenance_conflict(
    session: Session,
    object_store: S3ObjectStore,
    source: Source,
) -> None:
    command = command_for(source)
    import_raw_artifact(session=session, object_store=object_store, command=command)

    with pytest.raises(RawArtifactProvenanceConflict) as captured:
        import_raw_artifact(
            session=session,
            object_store=object_store,
            command=replace(command, retrieved_at=command.retrieved_at + timedelta(seconds=1)),
        )

    assert captured.value.code == "RAW_ARTIFACT_PROVENANCE_CONFLICT"
    assert session.scalar(select(func.count()).select_from(RawArtifact)) == 1


def test_database_rollback_can_retry_without_deleting_the_object(
    session: Session,
    object_store: S3ObjectStore,
    source: Source,
) -> None:
    session.commit()
    command = command_for(source)

    first = import_raw_artifact(session=session, object_store=object_store, command=command)
    first_artifact_id = first.artifact.artifact_id
    session.rollback()

    second = import_raw_artifact(session=session, object_store=object_store, command=command)

    assert first.created is True
    assert second.created is True
    assert second.artifact.artifact_id != first_artifact_id
    assert session.scalar(select(func.count()).select_from(RawArtifact)) == 1
    assert object_store.get_bytes(key=second.artifact.object_key) == command.content


def test_build_raw_object_key_uses_sha256_content_addressing() -> None:
    digest = sha256(b"official-bytes").hexdigest()

    assert build_raw_object_key(digest) == f"raw/sha256/{digest[:2]}/{digest}"


def test_zero_byte_content_is_rejected_before_storage(session: Session, source: Source) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        import_raw_artifact(
            session=session,
            object_store=FailIfCalledObjectStore(),
            command=replace(command_for(source), content=b""),
        )


@pytest.mark.parametrize(
    "invalid_command",
    [
        lambda command: replace(command, source_id=uuid4()),
        lambda command: replace(command, requested_url="not-a-url"),
        lambda command: replace(command, retrieved_at=command.retrieved_at.replace(tzinfo=None)),
        lambda command: replace(command, http_status=99),
        lambda command: replace(command, collector_version=" "),
    ],
)
def test_invalid_capture_metadata_is_rejected_before_storage(
    session: Session,
    source: Source,
    invalid_command: Callable[[ImportRawArtifactCommand], ImportRawArtifactCommand],
) -> None:
    command = invalid_command(command_for(source))

    with pytest.raises(ValidationError):
        import_raw_artifact(
            session=session,
            object_store=FailIfCalledObjectStore(),
            command=command,
        )
