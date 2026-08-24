from datetime import UTC, datetime
from uuid import UUID, uuid4, uuid7

import pytest
from sqlalchemy import Engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from deepaha.artifacts.models import RawArtifact
from deepaha.contracts.phase1 import (
    DocumentSchema,
    EvidenceRefSchema,
    OpportunitySchema,
    RawArtifactSchema,
    SourceSchema,
)
from deepaha.core.settings import Settings
from deepaha.db.session import get_engine
from deepaha.documents.models import Document, EvidenceRef
from deepaha.documents.parser import LEGACY_PARSE_CONTRACT_VERSION
from deepaha.opportunities.models import Opportunity
from deepaha.p9b.hashing import document_parse_key
from deepaha.sources.models import Source

pytestmark = pytest.mark.integration
FIXED_SHA256 = "1589f9177e197a578c8d37bd5a3bc869a17d7b0936f156666f69a2f88fbb9d2b"


def test_get_engine_requires_database_url() -> None:
    with pytest.raises(ValueError, match="DEEPAHA_DATABASE_URL"):
        get_engine(Settings(database_url=None))


def source(*, source_id: UUID | None = None, suffix: str = "1") -> Source:
    return Source(
        source_id=source_id or uuid7(),
        public_id=f"src_{suffix.zfill(32)}",
        canonical_url=f"https://example.gov/source/{suffix}",
        authority_name="Example official authority",
        tier="OFFICIAL_PRIMARY",
        jurisdiction="Example jurisdiction",
        active=True,
        created_at=datetime(2026, 8, 21, 9, 0, tzinfo=UTC),
        updated_at=datetime(2026, 8, 21, 9, 0, tzinfo=UTC),
    )


def raw_artifact(
    source_id: UUID,
    *,
    artifact_id: UUID | None = None,
    content_sha256: str = FIXED_SHA256,
) -> RawArtifact:
    return RawArtifact(
        artifact_id=artifact_id or uuid7(),
        source_id=source_id,
        requested_url="https://example.gov/official.json",
        resolved_url="https://example.gov/official.json",
        retrieved_at=datetime(2026, 8, 21, 9, 59, 8, 5000, tzinfo=UTC),
        http_status=200,
        media_type="application/json; charset=utf-8",
        content_sha256=content_sha256,
        storage_bucket="deepaha-raw",
        object_key=f"raw/sha256/{content_sha256[:2]}/{content_sha256}",
        byte_size=11662,
        collector_version="phase1_fixture/0.1.0",
        metadata_schema_version="0.1.0",
    )


def opportunity(*, current_version: int | None = None) -> Opportunity:
    return Opportunity(
        opportunity_id=uuid7(),
        public_id=f"opp_{uuid7().hex}",
        type="CIVIL_SERVICE",
        canonical_title="Civil Service Fast Stream",
        issuer_name="Civil Service Fast Stream",
        jurisdiction="United Kingdom",
        current_version=current_version,
        status="UNKNOWN",
        publication_status="INTERNAL",
        created_at=datetime(2026, 8, 21, 10, 0, tzinfo=UTC),
        updated_at=datetime(2026, 8, 21, 10, 0, tzinfo=UTC),
    )


def test_document_and_opportunity_are_distinct_tables(migrated_engine: Engine) -> None:
    inspector = inspect(migrated_engine)
    document_columns = {item["name"] for item in inspector.get_columns("documents")}
    opportunity_columns = {item["name"] for item in inspector.get_columns("opportunities")}

    assert "opportunity_id" not in document_columns
    assert "document_id" not in opportunity_columns
    assert "artifact_id" not in opportunity_columns


def test_schema_fields_map_explicitly_to_persistence_columns(migrated_engine: Engine) -> None:
    inspector = inspect(migrated_engine)
    columns = {
        table: {item["name"] for item in inspector.get_columns(table)}
        for table in ("sources", "raw_artifacts", "documents", "opportunities", "evidence_refs")
    }

    assert columns["sources"] == set(SourceSchema.model_fields)
    assert columns["documents"] == set(DocumentSchema.model_fields) | {
        "parse_contract_version",
        "document_parse_key",
    }
    assert columns["opportunities"] == set(OpportunitySchema.model_fields)
    assert columns["raw_artifacts"] == (set(RawArtifactSchema.model_fields) - {"storage_uri"}) | {
        "storage_bucket",
        "object_key",
    }
    legacy_evidence_columns = (set(EvidenceRefSchema.model_fields) - {"locator"}) | {
        "evidence_ref_id",
        "locator_kind",
        "locator_value",
    }
    assert legacy_evidence_columns <= columns["evidence_refs"]
    assert columns["evidence_refs"] == legacy_evidence_columns | {
        "locator_schema_version",
        "locator_payload",
    }


def test_uuid4_primary_key_is_rejected(session: Session) -> None:
    session.add(source(source_id=uuid4()))

    with pytest.raises(IntegrityError):
        session.flush()


def test_duplicate_source_url_is_rejected(session: Session) -> None:
    first = source(suffix="1")
    second = source(suffix="2")
    second.canonical_url = first.canonical_url
    session.add_all([first, second])

    with pytest.raises(IntegrityError):
        session.flush()


def test_duplicate_source_content_is_rejected(session: Session) -> None:
    owner = source()
    session.add(owner)
    session.flush()
    session.add_all([raw_artifact(owner.source_id), raw_artifact(owner.source_id)])

    with pytest.raises(IntegrityError):
        session.flush()


def test_malformed_hash_is_rejected(session: Session) -> None:
    owner = source()
    session.add(owner)
    session.flush()
    session.add(raw_artifact(owner.source_id, content_sha256="A" * 64))

    with pytest.raises(IntegrityError):
        session.flush()


def test_zero_byte_artifact_is_rejected(session: Session) -> None:
    owner = source()
    artifact = raw_artifact(owner.source_id)
    artifact.byte_size = 0
    session.add_all([owner, artifact])

    with pytest.raises(IntegrityError):
        session.flush()


def test_opportunity_version_zero_is_rejected(session: Session) -> None:
    session.add(opportunity(current_version=0))

    with pytest.raises(IntegrityError):
        session.flush()


def test_evidence_ref_rejects_document_artifact_mismatch(session: Session) -> None:
    owner = source()
    session.add(owner)
    session.flush()
    first_artifact = raw_artifact(owner.source_id)
    second_artifact = raw_artifact(
        owner.source_id,
        content_sha256="2" * 64,
    )
    session.add_all([first_artifact, second_artifact])
    session.flush()
    document = Document(
        document_id=uuid7(),
        artifact_id=first_artifact.artifact_id,
        title="Official document",
        published_at=None,
        language="en",
        extracted_text_uri=None,
        parser_name="phase1_fixture_manifest",
        parser_version="0.1.0",
        parse_contract_version=LEGACY_PARSE_CONTRACT_VERSION,
        document_parse_key=document_parse_key(
            artifact_id=first_artifact.artifact_id,
            artifact_sha256=first_artifact.content_sha256,
            parser_name="phase1_fixture_manifest",
            parser_version="0.1.0",
            parse_contract_version=LEGACY_PARSE_CONTRACT_VERSION,
        ),
        parse_confidence=None,
        created_at=datetime(2026, 8, 21, 10, 0, tzinfo=UTC),
    )
    session.add(document)
    session.flush()
    session.add(
        EvidenceRef(
            evidence_ref_id=uuid7(),
            document_id=document.document_id,
            artifact_id=second_artifact.artifact_id,
            locator_kind="full_document",
            locator_value="*",
            quote_sha256=FIXED_SHA256,
        )
    )

    with pytest.raises(IntegrityError):
        session.flush()


def test_raw_artifact_derives_public_storage_uri(session: Session) -> None:
    owner = source()
    session.add(owner)
    session.flush()
    artifact = raw_artifact(owner.source_id)
    session.add(artifact)
    session.flush()

    assert artifact.storage_uri == f"s3://deepaha-raw/{artifact.object_key}"
