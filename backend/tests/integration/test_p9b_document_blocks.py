from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid7

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from deepaha.artifacts.s3 import S3ObjectStore
from deepaha.artifacts.service import ImportRawArtifactCommand, import_raw_artifact
from deepaha.core.settings import Settings
from deepaha.documents.html import P9BHtmlDocumentParser
from deepaha.documents.models import Document, DocumentBlock, EvidenceRef
from deepaha.documents.service import DocumentService, ParseDocumentCommand
from deepaha.documents.spreadsheet import XLSX_MEDIA_TYPE, P9BSpreadsheetDocumentParser
from deepaha.sources.models import Source

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 24, 14, 0, tzinfo=UTC)
CONTENT = b"<html lang='zh-CN'><body><main><p>Official field value</p></main></body></html>"
XLSX = Path(__file__).parents[1] / "fixtures" / "documents" / "minimal-table.xlsx"


class FixedClock:
    def now(self) -> datetime:
        return NOW


@pytest.fixture(scope="module")
def object_store() -> S3ObjectStore:
    store = S3ObjectStore(Settings())
    store.ensure_bucket()
    return store


@pytest.fixture
def owned_session_factory(migrated_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=migrated_engine, expire_on_commit=False)


def _create_artifact(
    factory: sessionmaker[Session],
    object_store: S3ObjectStore,
    *,
    content: bytes = CONTENT,
    media_type: str = "text/html",
) -> UUID:
    source_id = uuid7()
    with factory.begin() as session:
        session.add(
            Source(
                source_id=source_id,
                public_id=f"src_{source_id.hex}",
                canonical_url=f"https://p9b-block-{source_id.hex}.example.gov/",
                authority_name="Synthetic DocumentBlock Authority",
                tier="OFFICIAL_PRIMARY",
                jurisdiction=None,
                active=True,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.flush()
        imported = import_raw_artifact(
            session=session,
            object_store=object_store,
            command=ImportRawArtifactCommand(
                source_id=source_id,
                requested_url="https://p9b-block.example.gov/notice",
                resolved_url="https://p9b-block.example.gov/notice",
                retrieved_at=NOW,
                http_status=200,
                media_type=media_type,
                content=content,
                collector_version="test/0.8.0",
                metadata_schema_version="0.2.0",
            ),
        )
        return imported.artifact.artifact_id


def test_document_service_persists_immutable_blocks_and_field_locator_evidence(
    owned_session_factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    artifact_id = _create_artifact(owned_session_factory, object_store)
    service = DocumentService(
        session_factory=owned_session_factory,
        object_store=object_store,
        parsers=[P9BHtmlDocumentParser()],
        clock=FixedClock(),
    )

    first = service.parse(ParseDocumentCommand(artifact_id=artifact_id))
    second = service.parse(ParseDocumentCommand(artifact_id=artifact_id))

    assert first.created is True
    assert second.created is False
    assert first.document_id == second.document_id
    assert first.evidence_ref_ids == second.evidence_ref_ids
    assert first.document_block_ids == second.document_block_ids
    assert len(first.document_block_ids) == 1
    with owned_session_factory() as session:
        document = session.get(Document, first.document_id)
        assert document is not None
        assert document.parse_contract_version == "p9b-document-block-contract-v0.8.0"
        block = session.scalar(select(DocumentBlock))
        assert block is not None
        assert block.document_id == document.document_id
        assert block.document_parse_key == document.document_parse_key
        assert block.block_type == "HTML_ELEMENT"
        assert block.canonical_text_or_value == "Official field value"
        assert block.structural_locator == {
            "kind": "html_element_span",
            "selector": (
                "html:nth-of-type(1) > body:nth-of-type(1) > main:nth-of-type(1) > p:nth-of-type(1)"
            ),
            "text_start": 0,
            "text_end": len("Official field value"),
        }
        evidence = session.get(EvidenceRef, block.evidence_ref_id)
        assert evidence is not None
        assert evidence.locator_schema_version == "0.8.0"
        assert evidence.locator_kind == "html_element_span"
        assert evidence.locator_payload is not None
        assert evidence.locator_payload["block_id"] == str(block.block_id)
        assert evidence.locator_payload["document_parse_key"] == document.document_parse_key
        assert evidence.quote_sha256 == sha256(b"Official field value").hexdigest()
        assert session.scalar(select(func.count()).select_from(DocumentBlock)) == 1
        assert session.scalar(select(func.count()).select_from(EvidenceRef)) == 2

    with owned_session_factory() as session:
        block = session.get(DocumentBlock, first.document_block_ids[0])
        assert block is not None
        block.canonical_text_or_value = "mutated"
        with pytest.raises(DBAPIError, match="document_blocks are immutable"):
            session.flush()
        session.rollback()


def test_spreadsheet_cell_parent_is_bound_to_earlier_range_in_same_document(
    owned_session_factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    artifact_id = _create_artifact(
        owned_session_factory,
        object_store,
        content=XLSX.read_bytes(),
        media_type=XLSX_MEDIA_TYPE,
    )
    result = DocumentService(
        session_factory=owned_session_factory,
        object_store=object_store,
        parsers=[P9BSpreadsheetDocumentParser()],
        clock=FixedClock(),
    ).parse(ParseDocumentCommand(artifact_id=artifact_id))

    with owned_session_factory() as session:
        blocks = tuple(
            session.scalars(
                select(DocumentBlock)
                .where(DocumentBlock.document_id == result.document_id)
                .order_by(DocumentBlock.ordinal)
            )
        )
        assert len(blocks) == 14
        by_id = {block.block_id: block for block in blocks}
        cells = [block for block in blocks if block.block_type == "SPREADSHEET_CELL"]
        assert cells
        for cell in cells:
            assert cell.parent_block_id is not None
            parent = by_id[cell.parent_block_id]
            assert parent.block_type == "SPREADSHEET_RANGE"
            assert parent.ordinal < cell.ordinal
            assert parent.document_id == cell.document_id
