from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from deepaha.db.base import Base


class RawArtifact(Base):
    __tablename__ = "raw_artifacts"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(artifact_id) = 7", name="artifact_id_uuid7"),
        CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="content_sha256_format"),
        CheckConstraint("byte_size > 0", name="positive_byte_size"),
        CheckConstraint(
            "http_status is null or http_status between 100 and 599",
            name="http_status_range",
        ),
        CheckConstraint(
            "object_key = 'raw/sha256/' || substring(content_sha256 from 1 for 2) "
            "|| '/' || content_sha256",
            name="content_addressed_object_key",
        ),
        UniqueConstraint("source_id", "content_sha256"),
    )

    artifact_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    source_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("sources.source_id", ondelete="RESTRICT"),
    )
    requested_url: Mapped[str] = mapped_column(Text)
    resolved_url: Mapped[str] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    http_status: Mapped[int | None] = mapped_column(Integer)
    media_type: Mapped[str | None] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64))
    storage_bucket: Mapped[str] = mapped_column(String(63))
    object_key: Mapped[str] = mapped_column(Text)
    byte_size: Mapped[int] = mapped_column(Integer)
    collector_version: Mapped[str] = mapped_column(String(128))
    metadata_schema_version: Mapped[str] = mapped_column(String(64))

    @property
    def storage_uri(self) -> str:
        return f"s3://{self.storage_bucket}/{self.object_key}"
