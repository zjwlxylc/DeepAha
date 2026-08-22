from enum import StrEnum
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, HttpUrl, field_validator, model_validator

from deepaha.contracts.common import (
    EntityId,
    HttpStatus,
    Instant,
    NonEmptyString,
    OpportunityPublicId,
    Sha256,
    VersionNumber,
)
from deepaha.contracts.phase1 import (
    ContractModel,
    DocumentSchema,
    OpportunityStatus,
    OpportunityType,
    PublicationStatus,
    RawArtifactSchema,
    SourceSchema,
)


class OpportunityTypeV02(StrEnum):
    PUBLIC_INSTITUTION_JOB = OpportunityType.PUBLIC_INSTITUTION_JOB
    STATE_OWNED_ENTERPRISE_JOB = OpportunityType.STATE_OWNED_ENTERPRISE_JOB
    CIVIL_SERVICE = OpportunityType.CIVIL_SERVICE
    GRASSROOTS_PROGRAM = OpportunityType.GRASSROOTS_PROGRAM
    YOUTH_POLICY_BENEFIT = OpportunityType.YOUTH_POLICY_BENEFIT
    POSTGRAD_RECOMMENDATION = OpportunityType.POSTGRAD_RECOMMENDATION
    ADMISSION_CHANGE = OpportunityType.ADMISSION_CHANGE
    COMPETITION = "COMPETITION"
    RESEARCH_PROGRAM = "RESEARCH_PROGRAM"
    SCHOLARSHIP = "SCHOLARSHIP"
    YOUTH_DEVELOPMENT_PROGRAM = "YOUTH_DEVELOPMENT_PROGRAM"


class CaptureOutcome(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    NOT_MODIFIED = "NOT_MODIFIED"
    FAILED = "FAILED"


class BrowserPolicy(StrEnum):
    NEVER = "NEVER"
    FALLBACK = "FALLBACK"


class ContentUseBasis(StrEnum):
    OPEN_LICENSE = "OPEN_LICENSE"
    OFFICIAL_PUBLIC_ACCESS = "OFFICIAL_PUBLIC_ACCESS"
    LINK_ONLY = "LINK_ONLY"
    UNKNOWN = "UNKNOWN"


class RobotsDecision(StrEnum):
    ALLOWED = "ALLOWED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    DISALLOWED = "DISALLOWED"
    UNKNOWN = "UNKNOWN"


class ParseOutcome(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


class SourceEndpointSchema(ContractModel):
    endpoint_id: EntityId
    source_id: EntityId
    url: HttpUrl = Field(
        json_schema_extra={
            "not": {"pattern": r"^[A-Za-z][A-Za-z0-9+.-]*://[^/?#]*@"},
        }
    )
    allowed_hosts: tuple[NonEmptyString, ...] = Field(min_length=1)
    expected_media_types: tuple[NonEmptyString, ...] = Field(min_length=1)
    browser_policy: BrowserPolicy
    minimum_interval_seconds: int = Field(ge=1)
    timeout_seconds: int = Field(ge=1, le=120)
    max_attempts: int = Field(ge=1, le=3)
    robots_url: HttpUrl | None
    robots_decision: RobotsDecision
    robots_checked_at: Instant
    content_use_basis: ContentUseBasis
    license_name: NonEmptyString | None
    license_url: HttpUrl | None
    attribution: NonEmptyString | None
    fixture_storage_allowed: bool
    usage_note: NonEmptyString
    policy_version: NonEmptyString
    active: bool
    verified_at: Instant
    created_at: Instant
    updated_at: Instant

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def normalize_allowed_hosts(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            return value
        normalized: list[object] = []
        for host in value:
            normalized.append(host.strip().lower().rstrip(".") if isinstance(host, str) else host)
        if len(normalized) != len(set(normalized)):
            raise ValueError("allowed_hosts must not contain duplicates")
        return tuple(normalized)

    @field_validator("expected_media_types", mode="before")
    @classmethod
    def normalize_media_types(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            return value
        normalized: list[object] = []
        for media_type in value:
            if isinstance(media_type, str):
                normalized.append(media_type.strip().lower())
            else:
                normalized.append(media_type)
        if len(normalized) != len(set(normalized)):
            raise ValueError("expected_media_types must not contain duplicates")
        return tuple(normalized)

    @model_validator(mode="after")
    def require_policy_consistency(self) -> Self:
        parsed_url = urlsplit(str(self.url))
        if parsed_url.username is not None or parsed_url.password is not None:
            raise ValueError("endpoint url must not contain credentials")
        host = (parsed_url.hostname or "").lower().rstrip(".")
        if host not in self.allowed_hosts:
            raise ValueError("url host must be present in allowed_hosts")
        if self.active and self.robots_decision not in {
            RobotsDecision.ALLOWED,
            RobotsDecision.NOT_APPLICABLE,
        }:
            raise ValueError("active endpoint requires approved robots_decision")
        if self.active and self.content_use_basis is ContentUseBasis.UNKNOWN:
            raise ValueError("active endpoint requires known content_use_basis")
        if self.content_use_basis is ContentUseBasis.OPEN_LICENSE and (
            self.license_name is None or self.license_url is None
        ):
            raise ValueError("OPEN_LICENSE requires license_name and license_url")
        if (
            self.fixture_storage_allowed
            and self.content_use_basis is not ContentUseBasis.OPEN_LICENSE
        ):
            raise ValueError("fixture storage requires OPEN_LICENSE")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be before created_at")
        return self


class CaptureObservationSchema(ContractModel):
    observation_id: EntityId
    collection_run_id: EntityId
    attempt_number: int = Field(ge=1)
    endpoint_id: EntityId
    source_id: EntityId
    requested_url: HttpUrl
    resolved_url: HttpUrl | None
    started_at: Instant
    completed_at: Instant
    outcome: CaptureOutcome
    http_status: HttpStatus | None
    response_etag: NonEmptyString | None
    response_last_modified: NonEmptyString | None
    artifact_id: EntityId | None
    error_code: NonEmptyString | None
    collector_name: NonEmptyString
    collector_version: NonEmptyString
    policy_version: NonEmptyString

    @model_validator(mode="after")
    def require_outcome_consistency(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not be before started_at")
        if self.outcome is CaptureOutcome.SUCCEEDED and (
            self.artifact_id is None or self.error_code is not None
        ):
            raise ValueError("SUCCEEDED requires artifact_id and forbids error_code")
        if self.outcome is CaptureOutcome.NOT_MODIFIED and (
            self.http_status != 304 or self.artifact_id is None or self.error_code is not None
        ):
            raise ValueError("NOT_MODIFIED requires HTTP 304 and artifact_id")
        if self.outcome is CaptureOutcome.FAILED and (
            self.artifact_id is not None or self.error_code is None
        ):
            raise ValueError("FAILED requires error_code and forbids artifact_id")
        return self


class ParseAttemptSchema(ContractModel):
    parse_attempt_id: EntityId
    artifact_id: EntityId
    parser_name: NonEmptyString
    parser_version: NonEmptyString
    started_at: Instant
    completed_at: Instant
    outcome: ParseOutcome
    document_id: EntityId | None
    error_code: NonEmptyString | None
    input_media_type: NonEmptyString

    @model_validator(mode="after")
    def require_outcome_consistency(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not be before started_at")
        if self.outcome is ParseOutcome.SUCCEEDED and (
            self.document_id is None or self.error_code is not None
        ):
            raise ValueError("SUCCEEDED requires document_id and forbids error_code")
        if self.outcome is ParseOutcome.NEEDS_REVIEW and self.document_id is None:
            raise ValueError("NEEDS_REVIEW requires document_id")
        if self.outcome is ParseOutcome.FAILED and (
            self.document_id is not None or self.error_code is None
        ):
            raise ValueError("FAILED requires error_code and forbids document_id")
        return self


LegacyLocatorKind = Literal["page", "paragraph", "css_selector", "text_span", "full_document"]


class LegacyEvidenceLocator(ContractModel):
    kind: LegacyLocatorKind
    value: NonEmptyString

    @model_validator(mode="after")
    def require_full_document_value(self) -> Self:
        if self.kind == "full_document" and self.value != "*":
            raise ValueError("full_document locator value must be '*'")
        return self


class HtmlSelectorLocator(ContractModel):
    schema_version: Literal["0.2.0"]
    kind: Literal["html_selector"]
    selector: NonEmptyString
    text_sha256: Sha256


class PdfPageTextLocator(ContractModel):
    schema_version: Literal["0.2.0"]
    kind: Literal["pdf_page_text"]
    page_number: int = Field(ge=1)
    text_start: int = Field(ge=0)
    text_end: int = Field(gt=0)
    text_sha256: Sha256

    @model_validator(mode="after")
    def require_nonempty_range(self) -> Self:
        if self.text_end <= self.text_start:
            raise ValueError("text_end must be greater than text_start")
        return self


class SpreadsheetRangeLocator(ContractModel):
    schema_version: Literal["0.2.0"]
    kind: Literal["spreadsheet_range"]
    sheet_name: NonEmptyString
    start_row: int = Field(ge=1)
    end_row: int = Field(ge=1)
    start_column: int = Field(ge=1)
    end_column: int = Field(ge=1)
    cells_sha256: Sha256

    @model_validator(mode="after")
    def require_ordered_range(self) -> Self:
        if self.end_row < self.start_row:
            raise ValueError("end_row must not be before start_row")
        if self.end_column < self.start_column:
            raise ValueError("end_column must not be before start_column")
        return self


EvidenceLocatorV02 = Annotated[
    LegacyEvidenceLocator | HtmlSelectorLocator | PdfPageTextLocator | SpreadsheetRangeLocator,
    Field(discriminator="kind"),
]


class EvidenceRefSchemaV02(ContractModel):
    document_id: EntityId
    artifact_id: EntityId
    locator: EvidenceLocatorV02
    quote_sha256: Sha256 | None


class OpportunitySchemaV02(ContractModel):
    opportunity_id: EntityId
    public_id: OpportunityPublicId
    type: OpportunityTypeV02
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


__all__ = [
    "BrowserPolicy",
    "CaptureObservationSchema",
    "CaptureOutcome",
    "ContentUseBasis",
    "DocumentSchema",
    "EvidenceLocatorV02",
    "EvidenceRefSchemaV02",
    "HtmlSelectorLocator",
    "LegacyEvidenceLocator",
    "OpportunitySchemaV02",
    "OpportunityTypeV02",
    "ParseAttemptSchema",
    "ParseOutcome",
    "PdfPageTextLocator",
    "RawArtifactSchema",
    "RobotsDecision",
    "SourceEndpointSchema",
    "SourceSchema",
    "SpreadsheetRangeLocator",
]
