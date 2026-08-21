from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, HttpUrl, model_validator

from deepaha.contracts.common import (
    Confidence,
    EntityId,
    HttpStatus,
    Instant,
    LanguageTag,
    NonEmptyString,
    OpportunityPublicId,
    PositiveByteSize,
    S3Uri,
    Sha256,
    SourcePublicId,
    VersionNumber,
)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceTier(StrEnum):
    OFFICIAL_PRIMARY = "OFFICIAL_PRIMARY"
    OFFICIAL_AGGREGATOR = "OFFICIAL_AGGREGATOR"
    TRUSTED_SECONDARY = "TRUSTED_SECONDARY"
    COMMUNITY_SIGNAL = "COMMUNITY_SIGNAL"


class OpportunityType(StrEnum):
    PUBLIC_INSTITUTION_JOB = "PUBLIC_INSTITUTION_JOB"
    STATE_OWNED_ENTERPRISE_JOB = "STATE_OWNED_ENTERPRISE_JOB"
    CIVIL_SERVICE = "CIVIL_SERVICE"
    GRASSROOTS_PROGRAM = "GRASSROOTS_PROGRAM"
    YOUTH_POLICY_BENEFIT = "YOUTH_POLICY_BENEFIT"
    POSTGRAD_RECOMMENDATION = "POSTGRAD_RECOMMENDATION"
    ADMISSION_CHANGE = "ADMISSION_CHANGE"


class OpportunityStatus(StrEnum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    CLOSING_SOON = "CLOSING_SOON"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"
    UNKNOWN = "UNKNOWN"


class PublicationStatus(StrEnum):
    INTERNAL = "INTERNAL"
    READY = "READY"
    PUBLISHED = "PUBLISHED"
    WITHDRAWN = "WITHDRAWN"


class EvidenceLocatorKind(StrEnum):
    PAGE = "page"
    PARAGRAPH = "paragraph"
    CSS_SELECTOR = "css_selector"
    TEXT_SPAN = "text_span"
    FULL_DOCUMENT = "full_document"


class SourceSchema(ContractModel):
    source_id: EntityId
    public_id: SourcePublicId
    canonical_url: HttpUrl
    authority_name: NonEmptyString
    tier: SourceTier
    jurisdiction: NonEmptyString | None
    active: bool
    created_at: Instant
    updated_at: Instant

    @model_validator(mode="after")
    def require_monotonic_timestamps(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be before created_at")
        return self


class RawArtifactSchema(ContractModel):
    artifact_id: EntityId
    source_id: EntityId
    requested_url: HttpUrl
    resolved_url: HttpUrl
    retrieved_at: Instant
    http_status: HttpStatus | None
    media_type: NonEmptyString | None
    content_sha256: Sha256
    storage_uri: S3Uri
    byte_size: PositiveByteSize
    collector_version: NonEmptyString
    metadata_schema_version: NonEmptyString


class DocumentSchema(ContractModel):
    document_id: EntityId
    artifact_id: EntityId
    title: NonEmptyString | None
    published_at: Instant | None
    language: LanguageTag
    extracted_text_uri: S3Uri | None
    parser_name: NonEmptyString
    parser_version: NonEmptyString
    parse_confidence: Confidence | None
    created_at: Instant


class OpportunitySchema(ContractModel):
    opportunity_id: EntityId
    public_id: OpportunityPublicId
    type: OpportunityType
    canonical_title: NonEmptyString
    issuer_name: NonEmptyString
    jurisdiction: NonEmptyString | None
    current_version: VersionNumber | None
    status: OpportunityStatus
    publication_status: PublicationStatus
    created_at: Instant
    updated_at: Instant

    @model_validator(mode="after")
    def require_monotonic_timestamps(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be before created_at")
        return self


class EvidenceLocator(ContractModel):
    kind: EvidenceLocatorKind
    value: NonEmptyString

    @model_validator(mode="after")
    def require_full_document_value(self) -> Self:
        if self.kind is EvidenceLocatorKind.FULL_DOCUMENT and self.value != "*":
            raise ValueError("full_document locator value must be '*'")
        return self


class EvidenceRefSchema(ContractModel):
    document_id: EntityId
    artifact_id: EntityId
    locator: EvidenceLocator
    quote_sha256: Sha256 | None
