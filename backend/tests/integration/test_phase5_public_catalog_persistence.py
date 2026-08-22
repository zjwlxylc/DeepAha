from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid7

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, delete, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from deepaha.artifacts.models import RawArtifact
from deepaha.documents.models import Document, EvidenceRef
from deepaha.opportunities.models import Opportunity, OpportunityVersion
from deepaha.sources.models import Source

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).parents[2]
NOW = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)
SHA_ONE = "1" * 64
SHA_TWO = "2" * 64


def persist_public_opportunity(session: Session) -> Opportunity:
    source_id = uuid7()
    source = Source(
        source_id=source_id,
        public_id=f"src_{source_id.hex}",
        canonical_url="https://phase5-persistence.example.gov/",
        authority_name="Synthetic Phase 5 Authority",
        tier="OFFICIAL_PRIMARY",
        jurisdiction="Synthetic-Zhejiang",
        active=True,
        created_at=NOW,
        updated_at=NOW,
    )
    artifact = RawArtifact(
        artifact_id=uuid7(),
        source_id=source.source_id,
        requested_url="https://phase5-persistence.example.gov/notices/1",
        resolved_url="https://phase5-persistence.example.gov/notices/1",
        retrieved_at=NOW,
        http_status=200,
        media_type="text/html",
        content_sha256=SHA_ONE,
        storage_bucket="deepaha-raw",
        object_key=f"raw/sha256/{SHA_ONE[:2]}/{SHA_ONE}",
        byte_size=128,
        collector_version="phase5-test/0.5.0",
        metadata_schema_version="0.2.0",
    )
    document = Document(
        document_id=uuid7(),
        artifact_id=artifact.artifact_id,
        title="Synthetic Phase 5 notice",
        published_at=NOW,
        language="und",
        extracted_text_uri=None,
        parser_name="phase5_synthetic",
        parser_version="0.5.0",
        parse_confidence=None,
        created_at=NOW,
    )
    evidence = EvidenceRef(
        evidence_ref_id=uuid7(),
        document_id=document.document_id,
        artifact_id=artifact.artifact_id,
        locator_kind="full_document",
        locator_value="*",
        locator_schema_version="0.1.0",
        locator_payload=None,
        quote_sha256=SHA_ONE,
    )
    opportunity_id = uuid7()
    opportunity = Opportunity(
        opportunity_id=opportunity_id,
        public_id=f"opp_{opportunity_id.hex}",
        type="YOUTH_DEVELOPMENT_PROGRAM",
        canonical_title="Synthetic Phase 5 opportunity",
        issuer_name="Synthetic Phase 5 Authority",
        jurisdiction="Synthetic-Zhejiang",
        current_version=None,
        status="OPEN",
        publication_status="PUBLISHED",
        created_at=NOW,
        updated_at=NOW,
    )
    version = OpportunityVersion(
        opportunity_id=opportunity.opportunity_id,
        version=1,
        effective_from=NOW,
        source_document_id=document.document_id,
        source_evidence_ref_id=evidence.evidence_ref_id,
        snapshot={
            "canonical_title": opportunity.canonical_title,
            "type": opportunity.type,
            "issuer_name": opportunity.issuer_name,
            "jurisdiction": opportunity.jurisdiction,
            "status": opportunity.status,
            "published_at": NOW.isoformat(),
            "application_window": {
                "opens_on": "2026-08-22",
                "closes_on": "2026-09-22",
                "timezone": "Asia/Shanghai",
            },
            "application_url": "https://phase5-persistence.example.gov/apply/1",
            "attachment_urls": ["https://phase5-persistence.example.gov/files/1.pdf"],
            "locations": ["Synthetic-Hangzhou"],
        },
        field_evidence=[
            {
                "field_path": "canonical_title",
                "precedence": 400,
                "evidence_ref_id": str(evidence.evidence_ref_id),
                "effective_at": NOW.isoformat(),
            }
        ],
        changes=[
            {
                "field_path": "canonical_title",
                "before": None,
                "after": opportunity.canonical_title,
                "evidence_ref_id": str(evidence.evidence_ref_id),
            }
        ],
        content_sha256=SHA_TWO,
        review_status="APPROVED",
        created_at=NOW,
    )
    session.add(source)
    session.flush()
    session.add(artifact)
    session.flush()
    session.add_all([document, opportunity])
    session.flush()
    session.add(evidence)
    session.flush()
    session.add(version)
    session.flush()
    opportunity.current_version = version.version
    session.flush()
    return opportunity


def insert_catalog_entry(
    session: Session,
    opportunity_id: UUID,
    **overrides: object,
) -> None:
    values: dict[str, object] = {
        "opportunity_id": opportunity_id,
        "opportunity_version": 1,
        "collection_kind": "LICENSE_SAFE_FIXTURE",
        "dataset_id": "phase5-public-catalog-synthetic",
        "dataset_version": "v1",
        "content_use_basis": "OPEN_LICENSE",
        "reviewed_by": "phase5-fixture-governance",
        "approved_at": NOW,
        "last_verified_at": NOW,
    }
    values.update(overrides)
    session.execute(
        text(
            """
            INSERT INTO public_catalog_entries (
                opportunity_id, opportunity_version, collection_kind,
                dataset_id, dataset_version, content_use_basis,
                reviewed_by, approved_at, last_verified_at
            ) VALUES (
                :opportunity_id, :opportunity_version, :collection_kind,
                :dataset_id, :dataset_version, :content_use_basis,
                :reviewed_by, :approved_at, :last_verified_at
            )
            """
        ),
        values,
    )
    session.flush()


def test_phase5_public_catalog_table_exists(migrated_engine: Engine) -> None:
    assert "public_catalog_entries" in inspect(migrated_engine).get_table_names()


def test_governed_catalog_entry_persists_and_restricts_opportunity_delete(
    session: Session,
) -> None:
    opportunity = persist_public_opportunity(session)
    insert_catalog_entry(session, opportunity.opportunity_id)

    row = session.execute(
        text(
            "SELECT collection_kind, dataset_id, opportunity_version "
            "FROM public_catalog_entries WHERE opportunity_id = :opportunity_id"
        ),
        {"opportunity_id": opportunity.opportunity_id},
    ).one()
    assert row == ("LICENSE_SAFE_FIXTURE", "phase5-public-catalog-synthetic", 1)

    opportunity.current_version = None
    session.flush()
    with pytest.raises(IntegrityError):
        session.execute(
            delete(OpportunityVersion).where(
                OpportunityVersion.opportunity_id == opportunity.opportunity_id,
                OpportunityVersion.version == 1,
            )
        )
        session.flush()


@pytest.mark.parametrize(
    ("overrides", "constraint_name"),
    [
        ({"opportunity_version": 0}, "positive_opportunity_version"),
        ({"collection_kind": "UNREVIEWED"}, "collection_kind_values"),
        ({"content_use_basis": "UNKNOWN"}, "content_use_basis_values"),
        ({"dataset_id": "   "}, "dataset_id_nonempty"),
        ({"dataset_version": ""}, "dataset_version_nonempty"),
        ({"reviewed_by": " "}, "reviewed_by_nonempty"),
        (
            {"approved_at": NOW, "last_verified_at": datetime(2026, 8, 22, 9, 0, tzinfo=UTC)},
            "verification_timestamp_order",
        ),
    ],
)
def test_catalog_governance_constraints_reject_invalid_rows(
    session: Session,
    overrides: dict[str, object],
    constraint_name: str,
) -> None:
    opportunity = persist_public_opportunity(session)

    with pytest.raises(IntegrityError, match=constraint_name), session.begin_nested():
        insert_catalog_entry(session, opportunity.opportunity_id, **overrides)


def test_empty_phase5_migration_round_trips(migrated_engine: Engine) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))

    command.downgrade(config, "20260822_0004")
    assert "public_catalog_entries" not in inspect(migrated_engine).get_table_names()

    command.upgrade(config, "head")
    assert "public_catalog_entries" in inspect(migrated_engine).get_table_names()


def test_phase5_downgrade_refuses_governed_rows_without_deleting_them(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        opportunity = persist_public_opportunity(session)
        insert_catalog_entry(session, opportunity.opportunity_id)
        opportunity_id = opportunity.opportunity_id
        session.commit()

    with pytest.raises(RuntimeError, match="cannot downgrade Phase 5.*publication governance"):
        command.downgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "20260822_0004")

    with migrated_engine.connect() as connection:
        count = connection.execute(
            text(
                "SELECT count(*) FROM public_catalog_entries WHERE opportunity_id = :opportunity_id"
            ),
            {"opportunity_id": opportunity_id},
        ).scalar_one()
    assert count == 1
