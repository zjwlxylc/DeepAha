import json
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid7

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.artifacts.models import RawArtifact
from deepaha.contracts.phase1 import OpportunityStatus, SourceTier
from deepaha.contracts.phase2 import OpportunityTypeV02
from deepaha.contracts.phase3 import OpportunityDocumentRole
from deepaha.documents.models import Document, EvidenceRef
from deepaha.opportunities.models import (
    DocumentOpportunityLink,
    Opportunity,
    OpportunityEvent,
    OpportunityVersion,
)
from deepaha.opportunities.service import OpportunityResolutionService
from deepaha.opportunities.types import OpportunityPatch, ResolutionDocument
from deepaha.sources.models import Source

pytestmark = pytest.mark.integration
ROOT = Path(__file__).parents[3]
MANIFEST = ROOT / "config" / "acquisition" / "real-opportunity-replay.v1.json"


def test_real_s02_manifest_replays_stable_opportunity_identity(
    migrated_engine: Engine,
) -> None:
    payload: dict[str, object] = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert set(payload) == {
        "schema_version",
        "source_acquisition_entry_id",
        "document",
        "resolution_input",
        "expected",
    }
    assert payload["schema_version"] == "1.0.0"
    document = payload["document"]
    resolution = payload["resolution_input"]
    expected = payload["expected"]
    assert isinstance(document, dict)
    assert isinstance(resolution, dict)
    assert isinstance(expected, dict)
    assert document["content_sha256"] == (
        "1b12bb32943fff5869d411ef74ca205d60a118cb66f0925017a1c9f3c3659641"
    )
    assert document["normalized_text_sha256"] == (
        "a518c753b038da2ba4d256f0ebf3e36aa90d02eebc67a22e3b787afa99025b42"
    )

    factory = sessionmaker(migrated_engine, expire_on_commit=False)
    _seed_real_document(factory, document, resolution)
    command = _resolution_command(document, resolution)
    service = OpportunityResolutionService(
        session_factory=factory,
        clock=lambda: datetime.fromisoformat(str(expected["resolved_at"])),
        id_factory=uuid7,
    )

    first = service.resolve(command)
    second = service.resolve(command)

    assert second == first
    assert first.disposition == "CREATED"
    assert first.public_id == expected["public_id"]
    assert first.resolution_key == expected["resolution_key"]
    assert first.version == expected["version"] == 1
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Opportunity)) == 1
        assert session.scalar(select(func.count()).select_from(OpportunityVersion)) == 1
        assert session.scalar(select(func.count()).select_from(OpportunityEvent)) == 1
        assert session.scalar(select(func.count()).select_from(DocumentOpportunityLink)) == 1
        opportunity = session.scalar(select(Opportunity))
        assert opportunity is not None
        assert opportunity.status == "UNKNOWN"
        assert opportunity.publication_status == "INTERNAL"


def _seed_real_document(
    factory: sessionmaker[Session],
    document: dict[str, object],
    resolution: dict[str, object],
) -> None:
    source_id = UUID(str(resolution["source_id"]))
    artifact_id = UUID(str(document["artifact_id"]))
    document_id = UUID(str(document["document_id"]))
    byte_size = document["byte_size"]
    assert isinstance(byte_size, int)
    with factory.begin() as session:
        session.add(
            Source(
                source_id=source_id,
                public_id="src_00000000000000000000000000000212",
                canonical_url="https://www.mohrss.gov.cn/",
                authority_name="中华人民共和国人力资源和社会保障部",
                tier="OFFICIAL_PRIMARY",
                jurisdiction="全国",
                active=True,
                created_at=datetime.fromisoformat(str(document["retrieved_at"])),
                updated_at=datetime.fromisoformat(str(document["retrieved_at"])),
            )
        )
        session.flush()
        session.add(
            RawArtifact(
                artifact_id=artifact_id,
                source_id=source_id,
                requested_url=str(document["requested_url"]),
                resolved_url=str(document["requested_url"]),
                retrieved_at=datetime.fromisoformat(str(document["retrieved_at"])),
                http_status=200,
                media_type="text/html;charset=UTF-8",
                content_sha256=str(document["content_sha256"]),
                storage_bucket="deepaha-raw",
                object_key=str(document["object_key"]),
                byte_size=byte_size,
                collector_version="0.2.0",
                metadata_schema_version="0.2.0",
            )
        )
        session.flush()
        session.add(
            Document(
                document_id=document_id,
                artifact_id=artifact_id,
                title=str(document["title"]),
                published_at=None,
                language="en",
                extracted_text_uri=str(document["extracted_text_uri"]),
                parser_name="html_lxml",
                parser_version="0.2.0",
                parse_confidence=None,
                created_at=datetime.fromisoformat(str(document["document_created_at"])),
            )
        )
        session.flush()
        locator = document["evidence_locator"]
        assert isinstance(locator, dict)
        session.add(
            EvidenceRef(
                evidence_ref_id=UUID(str(resolution["evidence_ref_id"])),
                document_id=document_id,
                artifact_id=artifact_id,
                locator_kind="html_selector",
                locator_value=None,
                locator_schema_version="0.2.0",
                locator_payload=locator,
                quote_sha256=str(locator["text_sha256"]),
            )
        )


def _resolution_command(
    document: dict[str, object],
    resolution: dict[str, object],
) -> ResolutionDocument:
    facts = resolution["facts"]
    assert isinstance(facts, dict)
    return ResolutionDocument(
        document_id=UUID(str(document["document_id"])),
        source_id=UUID(str(resolution["source_id"])),
        source_tier=SourceTier(str(resolution["source_tier"])),
        evidence_ref_id=UUID(str(resolution["evidence_ref_id"])),
        role=OpportunityDocumentRole(str(resolution["role"])),
        canonical_url=str(resolution["canonical_url"]),
        external_id=str(resolution["external_id"]),
        references_document_ids=(),
        effective_at=datetime.fromisoformat(str(resolution["effective_at"])),
        facts=OpportunityPatch(
            canonical_title=str(facts["canonical_title"]),
            type=OpportunityTypeV02(str(facts["type"])),
            issuer_name=str(facts["issuer_name"]),
            jurisdiction=str(facts["jurisdiction"]),
            status=OpportunityStatus(str(facts["status"])),
            published_at=datetime.fromisoformat(str(facts["published_at"])),
            application_url=str(facts["application_url"]),
        ),
    )
