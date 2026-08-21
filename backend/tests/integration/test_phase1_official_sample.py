import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid7

import pytest
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from deepaha.artifacts.models import RawArtifact
from deepaha.artifacts.s3 import S3ObjectStore
from deepaha.artifacts.service import ImportRawArtifactCommand, import_raw_artifact
from deepaha.core.settings import Settings
from deepaha.documents.models import Document, EvidenceRef
from deepaha.opportunities.models import Opportunity
from deepaha.sources.models import Source

FIXTURES = Path(__file__).parents[1] / "fixtures" / "official"
FIXTURE_PATH = FIXTURES / "civil-service-fast-stream-news-2025.json"
MANIFEST_PATH = FIXTURES / "civil-service-fast-stream-news-2025.manifest.json"
FIXED_SHA256 = "1589f9177e197a578c8d37bd5a3bc869a17d7b0936f156666f69a2f88fbb9d2b"
FIXED_SIZE = 11662
pytestmark = pytest.mark.integration


class _CaptureManifest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    requested_url: str
    resolved_url: str
    retrieved_at: datetime
    http_status: int
    media_type: str
    byte_size: int
    content_sha256: str
    collector_version: str
    metadata_schema_version: str


class _GovUkFixtureDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    first_published_at: datetime


@dataclass(frozen=True, slots=True)
class _FixtureDocument:
    title: str
    published_at: datetime


def load_official_fixture() -> tuple[bytes, _CaptureManifest, _FixtureDocument]:
    content = FIXTURE_PATH.read_bytes()
    if len(content) != FIXED_SIZE or sha256(content).hexdigest() != FIXED_SHA256:
        raise ValueError("official fixture identity does not match its fixed contract")

    manifest = _CaptureManifest.model_validate_json(MANIFEST_PATH.read_bytes())
    payload = _GovUkFixtureDocument.model_validate_json(content)
    published_at = payload.first_published_at.astimezone(UTC)
    if published_at != datetime(2025, 9, 16, 23, 0, tzinfo=UTC):
        raise ValueError("official fixture publication time changed")
    return content, manifest, _FixtureDocument(title=payload.title, published_at=published_at)


@pytest.fixture(scope="module")
def object_store() -> S3ObjectStore:
    store = S3ObjectStore(Settings())
    store.ensure_bucket()
    return store


def test_official_fixture_has_fixed_bytes_and_open_licence() -> None:
    content = FIXTURE_PATH.read_bytes()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert len(content) == FIXED_SIZE
    assert sha256(content).hexdigest() == FIXED_SHA256
    assert manifest["content_sha256"] == FIXED_SHA256
    assert manifest["byte_size"] == FIXED_SIZE
    assert manifest["license"]["name"] == "Open Government Licence v3.0"
    assert manifest["limitations"]["gold_business_sample"] is False
    assert manifest["limitations"]["current_application_status_proven"] is False


def test_official_sample_round_trips_raw_bytes_and_separates_domain_entities(
    session: Session,
    object_store: S3ObjectStore,
) -> None:
    content, manifest, fixture_document = load_official_fixture()
    source_id = uuid7()
    source = Source(
        source_id=source_id,
        public_id=f"src_{source_id.hex}",
        canonical_url=manifest.requested_url,
        authority_name="Government Skills and Civil Service Fast Stream",
        tier="OFFICIAL_PRIMARY",
        jurisdiction="United Kingdom",
        active=True,
        created_at=manifest.retrieved_at,
        updated_at=manifest.retrieved_at,
    )
    session.add(source)
    session.flush()
    command = ImportRawArtifactCommand(
        source_id=source.source_id,
        requested_url=manifest.requested_url,
        resolved_url=manifest.resolved_url,
        retrieved_at=manifest.retrieved_at,
        http_status=manifest.http_status,
        media_type=manifest.media_type,
        content=content,
        collector_version=manifest.collector_version,
        metadata_schema_version=manifest.metadata_schema_version,
    )

    first = import_raw_artifact(session=session, object_store=object_store, command=command)
    second = import_raw_artifact(session=session, object_store=object_store, command=command)
    document = Document(
        document_id=uuid7(),
        artifact_id=first.artifact.artifact_id,
        title=fixture_document.title,
        published_at=fixture_document.published_at,
        language="en",
        extracted_text_uri=None,
        parser_name="phase1_fixture_manifest",
        parser_version="0.1.0",
        parse_confidence=None,
        created_at=manifest.retrieved_at,
    )
    opportunity = Opportunity(
        opportunity_id=uuid7(),
        public_id=f"opp_{uuid7().hex}",
        type="CIVIL_SERVICE",
        canonical_title="Civil Service Fast Stream",
        issuer_name="Government Skills and Civil Service Fast Stream",
        jurisdiction="United Kingdom",
        current_version=None,
        status="UNKNOWN",
        publication_status="INTERNAL",
        created_at=manifest.retrieved_at,
        updated_at=manifest.retrieved_at,
    )
    session.add_all([document, opportunity])
    session.flush()
    evidence_ref = EvidenceRef(
        evidence_ref_id=uuid7(),
        document_id=document.document_id,
        artifact_id=first.artifact.artifact_id,
        locator_kind="full_document",
        locator_value="*",
        quote_sha256=FIXED_SHA256,
    )
    session.add(evidence_ref)
    session.commit()

    artifact_id = first.artifact.artifact_id
    document_id = document.document_id
    opportunity_id = opportunity.opportunity_id
    evidence_ref_id = evidence_ref.evidence_ref_id
    session.expire_all()
    reloaded_source = session.get(Source, source_id)
    reloaded_artifact = session.get(RawArtifact, artifact_id)
    reloaded_document = session.get(Document, document_id)
    reloaded_opportunity = session.get(Opportunity, opportunity_id)
    reloaded_evidence = session.get(EvidenceRef, evidence_ref_id)

    assert first.created is True
    assert second.created is False
    assert second.artifact.artifact_id == artifact_id
    assert session.scalar(select(func.count()).select_from(RawArtifact)) == 1
    assert reloaded_source is not None
    assert reloaded_artifact is not None
    assert reloaded_document is not None
    assert reloaded_opportunity is not None
    assert reloaded_evidence is not None
    assert reloaded_source.authority_name == "Government Skills and Civil Service Fast Stream"
    assert object_store.get_bytes(key=reloaded_artifact.object_key) == content
    assert sha256(content).hexdigest() == reloaded_artifact.content_sha256 == FIXED_SHA256
    assert reloaded_document.title == fixture_document.title
    assert reloaded_document.published_at == datetime(2025, 9, 16, 23, 0, tzinfo=UTC)
    assert reloaded_evidence.document_id == reloaded_document.document_id
    assert reloaded_evidence.artifact_id == reloaded_artifact.artifact_id
    assert reloaded_evidence.locator_kind == "full_document"
    assert reloaded_evidence.locator_value == "*"
    assert reloaded_evidence.quote_sha256 == FIXED_SHA256
    assert reloaded_document.document_id != reloaded_opportunity.opportunity_id
    assert reloaded_document.title != reloaded_opportunity.canonical_title
    assert reloaded_opportunity.current_version is None
    assert {column.name for column in Opportunity.__table__.columns}.isdisjoint(
        {"document_id", "artifact_id"}
    )
