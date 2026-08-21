from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from deepaha.db.base import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(document_id) = 7", name="document_id_uuid7"),
        CheckConstraint(
            "parse_confidence is null or parse_confidence between 0 and 1",
            name="parse_confidence_range",
        ),
        UniqueConstraint("artifact_id", "parser_name", "parser_version"),
        UniqueConstraint("document_id", "artifact_id"),
    )

    document_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    artifact_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("raw_artifacts.artifact_id", ondelete="RESTRICT"),
    )
    title: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    language: Mapped[str] = mapped_column(String(35))
    extracted_text_uri: Mapped[str | None] = mapped_column(Text)
    parser_name: Mapped[str] = mapped_column(String(128))
    parser_version: Mapped[str] = mapped_column(String(64))
    parse_confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 5))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EvidenceRef(Base):
    __tablename__ = "evidence_refs"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(evidence_ref_id) = 7",
            name="evidence_ref_id_uuid7",
        ),
        CheckConstraint(
            "locator_kind in ('page', 'paragraph', 'css_selector', 'text_span', 'full_document')",
            name="locator_kind_values",
        ),
        CheckConstraint(
            "locator_kind <> 'full_document' or locator_value = '*'",
            name="full_document_locator_value",
        ),
        CheckConstraint(
            "quote_sha256 is null or quote_sha256 ~ '^[0-9a-f]{64}$'",
            name="quote_sha256_format",
        ),
        ForeignKeyConstraint(
            ["document_id", "artifact_id"],
            ["documents.document_id", "documents.artifact_id"],
            ondelete="RESTRICT",
        ),
    )

    evidence_ref_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    document_id: Mapped[UUID] = mapped_column(Uuid)
    artifact_id: Mapped[UUID] = mapped_column(Uuid)
    locator_kind: Mapped[str] = mapped_column(String(32))
    locator_value: Mapped[str] = mapped_column(Text)
    quote_sha256: Mapped[str | None] = mapped_column(String(64))
