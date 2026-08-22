from datetime import date
from enum import StrEnum
from typing import Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, HttpUrl, JsonValue, field_validator, model_validator

from deepaha.contracts.common import (
    EntityId,
    Instant,
    NonEmptyString,
    Sha256,
    VersionNumber,
)
from deepaha.contracts.phase1 import ContractModel, OpportunityStatus
from deepaha.contracts.phase2 import OpportunityTypeV02


class OpportunityReviewStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class OpportunityDocumentRole(StrEnum):
    PRIMARY_NOTICE = "PRIMARY_NOTICE"
    ATTACHMENT = "ATTACHMENT"
    POSITION_TABLE = "POSITION_TABLE"
    CORRECTION = "CORRECTION"
    DEADLINE_EXTENSION = "DEADLINE_EXTENSION"
    CANCELLATION = "CANCELLATION"
    RESULT = "RESULT"
    OFFICIAL_GUIDANCE = "OFFICIAL_GUIDANCE"


class ResolutionDisposition(StrEnum):
    CREATED = "CREATED"
    LINKED = "LINKED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class OpportunityEventType(StrEnum):
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    CORRECTED = "CORRECTED"
    DEADLINE_CHANGED = "DEADLINE_CHANGED"
    ATTACHMENT_REPLACED = "ATTACHMENT_REPLACED"
    CANCELLED = "CANCELLED"
    REOPENED = "REOPENED"


class OpportunityAliasType(StrEnum):
    TITLE = "TITLE"
    URL = "URL"
    EXTERNAL_ID = "EXTERNAL_ID"


class OpportunityIdentityActionType(StrEnum):
    MERGE = "MERGE"
    SPLIT = "SPLIT"
    MERGE_REVERSAL = "MERGE_REVERSAL"
    SPLIT_REVERSAL = "SPLIT_REVERSAL"


class OpportunityIdentityMemberRole(StrEnum):
    SOURCE = "SOURCE"
    TARGET = "TARGET"
    PARENT = "PARENT"
    CHILD = "CHILD"


class SnapshotField(StrEnum):
    CANONICAL_TITLE = "canonical_title"
    TYPE = "type"
    ISSUER_NAME = "issuer_name"
    JURISDICTION = "jurisdiction"
    STATUS = "status"
    PUBLISHED_AT = "published_at"
    APPLICATION_WINDOW_OPENS_ON = "application_window.opens_on"
    APPLICATION_WINDOW_CLOSES_ON = "application_window.closes_on"
    APPLICATION_WINDOW_TIMEZONE = "application_window.timezone"
    APPLICATION_URL = "application_url"
    ATTACHMENT_URLS = "attachment_urls"
    LOCATIONS = "locations"


class ApplicationWindowSchema(ContractModel):
    opens_on: date | None
    closes_on: date | None
    timezone: NonEmptyString | None

    @field_validator("timezone")
    @classmethod
    def require_iana_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("timezone must be a known IANA timezone") from error
        return value

    @model_validator(mode="after")
    def require_ordered_dates(self) -> Self:
        if (
            self.opens_on is not None
            and self.closes_on is not None
            and self.closes_on < self.opens_on
        ):
            raise ValueError("closes_on must not be before opens_on")
        return self


class OpportunitySnapshotSchema(ContractModel):
    canonical_title: NonEmptyString
    type: OpportunityTypeV02
    issuer_name: NonEmptyString
    jurisdiction: NonEmptyString | None
    status: OpportunityStatus
    published_at: Instant | None
    application_window: ApplicationWindowSchema
    application_url: HttpUrl | None
    attachment_urls: tuple[HttpUrl, ...]
    locations: tuple[NonEmptyString, ...]

    @field_validator("attachment_urls", mode="before")
    @classmethod
    def normalize_attachment_urls(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            return value
        normalized = tuple(sorted(str(item).strip() for item in value))
        if len(normalized) != len(set(normalized)):
            raise ValueError("attachment_urls must not contain duplicates")
        return normalized

    @field_validator("locations", mode="before")
    @classmethod
    def normalize_locations(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            return value
        normalized = tuple(sorted(str(item).strip() for item in value))
        if len(normalized) != len(set(normalized)):
            raise ValueError("locations must not contain duplicates")
        return normalized


class OpportunityFieldEvidenceSchema(ContractModel):
    field_path: SnapshotField
    precedence: int = Field(ge=100, le=600)
    evidence_ref_id: EntityId
    effective_at: Instant


class OpportunityFieldChangeSchema(ContractModel):
    field_path: SnapshotField
    before: JsonValue | None
    after: JsonValue | None
    evidence_ref_id: EntityId

    @model_validator(mode="after")
    def require_changed_value(self) -> Self:
        if self.before == self.after:
            raise ValueError("before and after must differ")
        return self


class OpportunityVersionSchemaV03(ContractModel):
    opportunity_id: EntityId
    version: VersionNumber
    effective_from: Instant
    source_document_id: EntityId
    source_evidence_ref_id: EntityId
    snapshot: OpportunitySnapshotSchema
    field_evidence: tuple[OpportunityFieldEvidenceSchema, ...]
    changes: tuple[OpportunityFieldChangeSchema, ...] = Field(min_length=1)
    content_sha256: Sha256
    review_status: OpportunityReviewStatus
    created_at: Instant

    @model_validator(mode="after")
    def require_matching_field_evidence(self) -> Self:
        evidence_by_field = {item.field_path: item for item in self.field_evidence}
        if len(evidence_by_field) != len(self.field_evidence):
            raise ValueError("field_evidence must contain unique field paths")
        changed_fields = tuple(change.field_path for change in self.changes)
        if len(changed_fields) != len(set(changed_fields)):
            raise ValueError("changes must contain unique field paths")
        for change in self.changes:
            evidence = evidence_by_field.get(change.field_path)
            if evidence is None or evidence.evidence_ref_id != change.evidence_ref_id:
                raise ValueError("each change requires matching field evidence")
        if self.created_at < self.effective_from:
            raise ValueError("created_at must not be before effective_from")
        return self


class OpportunityEventSchemaV03(ContractModel):
    event_id: EntityId
    opportunity_id: EntityId
    from_version: VersionNumber | None
    to_version: VersionNumber
    event_type: OpportunityEventType
    changed_fields: tuple[SnapshotField, ...] = Field(min_length=1)
    changes: tuple[OpportunityFieldChangeSchema, ...] = Field(min_length=1)
    source_document_id: EntityId
    source_evidence_ref_id: EntityId
    detected_at: Instant

    @model_validator(mode="after")
    def require_version_transition(self) -> Self:
        if self.event_type is OpportunityEventType.CREATED:
            if self.from_version is not None or self.to_version != 1:
                raise ValueError("CREATED requires from_version=null and to_version=1")
        elif self.from_version is None or self.to_version != self.from_version + 1:
            raise ValueError("non-CREATED event requires a continuous version transition")
        if tuple(dict.fromkeys(self.changed_fields)) != self.changed_fields:
            raise ValueError("changed_fields must be unique and ordered")
        if tuple(change.field_path for change in self.changes) != self.changed_fields:
            raise ValueError("changed_fields must match changes order")
        return self


class DocumentOpportunityLinkSchema(ContractModel):
    link_id: EntityId
    document_id: EntityId
    opportunity_id: EntityId
    role: OpportunityDocumentRole
    resolution_key: NonEmptyString
    resolver_version: NonEmptyString
    source_evidence_ref_id: EntityId
    linked_at: Instant
    ended_at: Instant | None
    ended_by_identity_action_id: EntityId | None

    @model_validator(mode="after")
    def require_paired_end_fields(self) -> Self:
        if (self.ended_at is None) != (self.ended_by_identity_action_id is None):
            raise ValueError("ended_at and ended_by_identity_action_id must both be set or absent")
        if self.ended_at is not None and self.ended_at < self.linked_at:
            raise ValueError("ended_at must not be before linked_at")
        return self


class OpportunityResolutionCandidateSchema(ContractModel):
    candidate_id: EntityId
    document_id: EntityId
    candidate_opportunity_ids: tuple[EntityId, ...]
    proposed_role: OpportunityDocumentRole
    proposed_snapshot: OpportunitySnapshotSchema | None
    reason_codes: tuple[NonEmptyString, ...] = Field(min_length=1)
    resolver_version: NonEmptyString
    source_evidence_ref_id: EntityId
    review_status: Literal[OpportunityReviewStatus.PENDING]
    created_at: Instant

    @model_validator(mode="after")
    def require_unique_candidate_values(self) -> Self:
        if len(self.candidate_opportunity_ids) != len(set(self.candidate_opportunity_ids)):
            raise ValueError("candidate_opportunity_ids must be unique")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("reason_codes must be unique")
        return self


class OpportunityAliasSchemaV03(ContractModel):
    alias_id: EntityId
    opportunity_id: EntityId
    alias_type: OpportunityAliasType
    alias_value: NonEmptyString
    normalized_value: NonEmptyString
    source_id: EntityId | None
    source_document_id: EntityId
    source_evidence_ref_id: EntityId
    created_at: Instant

    @model_validator(mode="after")
    def require_external_id_source(self) -> Self:
        if self.alias_type is OpportunityAliasType.EXTERNAL_ID and self.source_id is None:
            raise ValueError("EXTERNAL_ID alias requires source_id")
        return self


class OpportunityIdentityMemberSchema(ContractModel):
    opportunity_id: EntityId
    role: OpportunityIdentityMemberRole


class OpportunityIdentityActionSchema(ContractModel):
    action_id: EntityId
    action_type: OpportunityIdentityActionType
    members: tuple[OpportunityIdentityMemberSchema, ...]
    reversal_of_action_id: EntityId | None
    actor: NonEmptyString
    reason: NonEmptyString
    source_document_id: EntityId | None
    source_evidence_ref_id: EntityId | None
    occurred_at: Instant

    @model_validator(mode="after")
    def require_action_shape(self) -> Self:
        if len({member.opportunity_id for member in self.members}) != len(self.members):
            raise ValueError("identity action member opportunity IDs must be unique")
        counts = {
            role: sum(member.role is role for member in self.members)
            for role in OpportunityIdentityMemberRole
        }
        merge_shape = (
            counts[OpportunityIdentityMemberRole.TARGET] == 1
            and counts[OpportunityIdentityMemberRole.SOURCE] >= 1
            and counts[OpportunityIdentityMemberRole.PARENT] == 0
            and counts[OpportunityIdentityMemberRole.CHILD] == 0
        )
        split_shape = (
            counts[OpportunityIdentityMemberRole.PARENT] == 1
            and counts[OpportunityIdentityMemberRole.CHILD] >= 2
            and counts[OpportunityIdentityMemberRole.SOURCE] == 0
            and counts[OpportunityIdentityMemberRole.TARGET] == 0
        )
        if (
            self.action_type
            in {
                OpportunityIdentityActionType.MERGE,
                OpportunityIdentityActionType.MERGE_REVERSAL,
            }
            and not merge_shape
        ):
            raise ValueError("MERGE action requires one TARGET and at least one SOURCE")
        if (
            self.action_type
            in {
                OpportunityIdentityActionType.SPLIT,
                OpportunityIdentityActionType.SPLIT_REVERSAL,
            }
            and not split_shape
        ):
            raise ValueError("SPLIT action requires one PARENT and at least two CHILD members")
        is_reversal = self.action_type in {
            OpportunityIdentityActionType.MERGE_REVERSAL,
            OpportunityIdentityActionType.SPLIT_REVERSAL,
        }
        if is_reversal and self.reversal_of_action_id is None:
            raise ValueError("reversal action requires reversal_of_action_id")
        if not is_reversal and self.reversal_of_action_id is not None:
            raise ValueError("non-reversal action forbids reversal_of_action_id")
        if (self.source_document_id is None) != (self.source_evidence_ref_id is None):
            raise ValueError("source document and evidence fields must both be set or absent")
        return self


__all__ = [
    "ApplicationWindowSchema",
    "DocumentOpportunityLinkSchema",
    "OpportunityAliasSchemaV03",
    "OpportunityAliasType",
    "OpportunityDocumentRole",
    "OpportunityEventSchemaV03",
    "OpportunityEventType",
    "OpportunityFieldChangeSchema",
    "OpportunityFieldEvidenceSchema",
    "OpportunityIdentityActionSchema",
    "OpportunityIdentityActionType",
    "OpportunityIdentityMemberRole",
    "OpportunityIdentityMemberSchema",
    "OpportunityResolutionCandidateSchema",
    "OpportunityReviewStatus",
    "OpportunitySnapshotSchema",
    "OpportunityVersionSchemaV03",
    "ResolutionDisposition",
    "SnapshotField",
]
