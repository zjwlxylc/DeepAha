from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from deepaha.db.base import Base


class PublicCatalogEntry(Base):
    __tablename__ = "public_catalog_entries"
    __table_args__ = (
        CheckConstraint(
            "opportunity_version >= 1",
            name="positive_opportunity_version",
        ),
        CheckConstraint(
            "collection_kind in ('REAL_GOLD', 'LICENSE_SAFE_FIXTURE')",
            name="collection_kind_values",
        ),
        CheckConstraint(
            "content_use_basis in ('OPEN_LICENSE', 'OFFICIAL_PUBLIC_ACCESS', 'LINK_ONLY')",
            name="content_use_basis_values",
        ),
        CheckConstraint("length(btrim(dataset_id)) >= 1", name="dataset_id_nonempty"),
        CheckConstraint(
            "length(btrim(dataset_version)) >= 1",
            name="dataset_version_nonempty",
        ),
        CheckConstraint("length(btrim(reviewed_by)) >= 1", name="reviewed_by_nonempty"),
        CheckConstraint(
            "last_verified_at >= approved_at",
            name="verification_timestamp_order",
        ),
        ForeignKeyConstraint(
            ["opportunity_id", "opportunity_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
            ondelete="RESTRICT",
        ),
    )

    opportunity_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    opportunity_version: Mapped[int] = mapped_column(Integer)
    collection_kind: Mapped[str] = mapped_column(String(24))
    dataset_id: Mapped[str] = mapped_column(String(128))
    dataset_version: Mapped[str] = mapped_column(String(64))
    content_use_basis: Mapped[str] = mapped_column(String(32))
    reviewed_by: Mapped[str] = mapped_column(Text)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
