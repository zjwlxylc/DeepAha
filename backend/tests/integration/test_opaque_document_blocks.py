"""Integration tests that prove an excluded binary really persists as an opaque block."""

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid7

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.artifacts.local_file import LocalFileObjectStore
from deepaha.artifacts.object_store import ObjectIntegrityError
from deepaha.artifacts.service import ImportRawArtifactCommand, import_raw_artifact
from deepaha.documents.blocks import ParsedBlock, validate_parsed_blocks
from deepaha.documents.models import Document, DocumentBlock, EvidenceRef, ParseAttempt
from deepaha.documents.opaque import (
    OPAQUE_BLOCK_TYPE,
    OPAQUE_LOCATOR_KIND,
    OpaqueBinaryParser,
)
from deepaha.documents.service import DocumentService, ParseDocumentCommand
from deepaha.sources.models import Source

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 11, 9, 0, tzinfo=UTC)
# A legacy OLE2 compound-file header followed by a recognizable payload.
DOC_CONTENT = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00legacy-msword-body"
DOC_SHA256 = sha256(DOC_CONTENT).hexdigest()
EMPTY_SHA256 = sha256(b"").hexdigest()
MEDIA_TYPE = "application/msword"


def _object_store(tmp_path: Path) -> LocalFileObjectStore:
    store = LocalFileObjectStore(root=tmp_path / "objects", bucket="deepaha-raw")
    store.ensure_bucket()
    return store


def _create_artifact(
    factory: sessionmaker[Session], object_store: LocalFileObjectStore
) -> tuple[UUID, str, str]:
    source_id = uuid7()
    with factory.begin() as session:
        session.add(
            Source(
                source_id=source_id,
                public_id=f"src_{source_id.hex}",
                canonical_url=f"https://official.example/{source_id.hex}",
                authority_name="Synthetic official authority",
                tier="OFFICIAL_PRIMARY",
                jurisdiction="Synthetic jurisdiction",
                active=True,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.flush()
        result = import_raw_artifact(
            session=session,
            object_store=object_store,
            command=ImportRawArtifactCommand(
                source_id=source_id,
                requested_url="https://official.example/legacy.doc",
                resolved_url="https://official.example/legacy.doc",
                retrieved_at=NOW,
                http_status=200,
                media_type=MEDIA_TYPE,
                content=DOC_CONTENT,
                collector_version="test/0.2.0",
                metadata_schema_version="0.2.0",
            ),
        )
        return (
            result.artifact.artifact_id,
            result.artifact.object_key,
            result.artifact.content_sha256,
        )


def _service(factory: sessionmaker[Session], object_store: LocalFileObjectStore) -> DocumentService:
    return DocumentService(
        session_factory=factory,
        object_store=object_store,
        parsers=(OpaqueBinaryParser(frozenset({MEDIA_TYPE})),),
    )


def test_opaque_block_persists_with_no_quotable_text(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    factory = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    object_store = _object_store(tmp_path)
    artifact_id = _create_artifact(factory, object_store)[0]

    result = _service(factory, object_store).parse(ParseDocumentCommand(artifact_id=artifact_id))

    assert result.created is True
    assert result.outcome == "SUCCEEDED"
    assert result.document_id is not None
    assert result.error_code is None

    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Document)) == 1
        assert session.scalar(select(func.count()).select_from(DocumentBlock)) == 1
        assert session.scalar(select(func.count()).select_from(EvidenceRef)) == 1
        assert session.scalar(select(func.count()).select_from(ParseAttempt)) == 1

        attempt = session.scalar(select(ParseAttempt))
        assert attempt is not None
        assert attempt.outcome == "SUCCEEDED"
        assert attempt.document_id == result.document_id
        assert attempt.error_code is None

        document = session.get(Document, result.document_id)
        assert document is not None
        assert document.parser_name == "opaque_no_text"
        assert document.parser_version == "0.1.0"

        block = session.scalar(select(DocumentBlock))
        assert block is not None
        assert block.block_type == OPAQUE_BLOCK_TYPE == "OPAQUE_BINARY"
        assert block.canonical_text_or_value == ""
        assert block.ordinal == 1
        assert block.parser_name == "opaque_no_text"
        assert block.structural_locator == {
            "kind": OPAQUE_LOCATOR_KIND,
            "value_sha256": DOC_SHA256,
            "byte_size": len(DOC_CONTENT),
        }

        # The block-level citation hashes the block value, i.e. the empty string; the whole
        # file digest lives inside the structural locator instead.
        evidence = session.scalar(select(EvidenceRef))
        assert evidence is not None
        assert evidence.locator_kind == "opaque_whole_file"
        assert evidence.locator_schema_version == "0.8.0"
        assert evidence.locator_value is None
        assert evidence.quote_sha256 == EMPTY_SHA256
        assert evidence.locator_payload is not None
        assert evidence.locator_payload["value_sha256"] == EMPTY_SHA256
        assert evidence.locator_payload["block_type"] == "OPAQUE_BINARY"
        assert evidence.locator_payload["structural_locator"] == {
            "kind": OPAQUE_LOCATOR_KIND,
            "value_sha256": DOC_SHA256,
            "byte_size": len(DOC_CONTENT),
        }


def test_service_rejects_tampered_bytes_before_parsing(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    factory = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    object_store = _object_store(tmp_path)
    artifact_id, raw_key, raw_sha = _create_artifact(factory, object_store)

    # Swap the stored bytes behind the artifact so the declared digest no longer matches.
    assert object_store.delete_if_matches(key=raw_key, sha256=raw_sha)
    tampered = b"tampered-bytes"
    object_store.put_bytes_if_absent(
        key=raw_key,
        content=tampered,
        media_type=MEDIA_TYPE,
        sha256=sha256(tampered).hexdigest(),
    )

    with pytest.raises(ObjectIntegrityError):
        _service(factory, object_store).parse(ParseDocumentCommand(artifact_id=artifact_id))

    with factory() as session:
        assert session.scalar(select(func.count()).select_from(ParseAttempt)) == 0
        assert session.scalar(select(func.count()).select_from(DocumentBlock)) == 0


def test_opaque_parser_rejects_a_digest_mismatch_without_touching_the_database(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    del migrated_engine, tmp_path

    with pytest.raises(ObjectIntegrityError, match="artifact SHA-256"):
        OpaqueBinaryParser(frozenset({MEDIA_TYPE})).parse(DOC_CONTENT, artifact_sha256="0" * 64)


def test_opaque_block_carrying_text_is_rejected_before_the_database(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    del migrated_engine, tmp_path
    block = ParsedBlock(
        block_type=OPAQUE_BLOCK_TYPE,
        canonical_text_or_value="看起来像证据的文本",
        structural_locator={
            "kind": OPAQUE_LOCATOR_KIND,
            "value_sha256": DOC_SHA256,
            "byte_size": len(DOC_CONTENT),
        },
        parent_ordinal=None,
    )

    with pytest.raises(ValueError, match="opaque DocumentBlock must not carry text"):
        validate_parsed_blocks((block,))
