from datetime import date, datetime
from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, JsonValue, model_validator

from deepaha.contracts.phase1 import OpportunityStatus
from deepaha.contracts.phase2 import OpportunityTypeV02


class PublicSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicDataLabel(StrEnum):
    REAL_GOLD = "REAL_GOLD"
    LICENSE_SAFE_FIXTURE = "LICENSE_SAFE_FIXTURE"


class PublicOpportunitySort(StrEnum):
    PUBLISHED_DESC = "PUBLISHED_DESC"
    DEADLINE_ASC = "DEADLINE_ASC"


class PersonalizationAvailability(StrEnum):
    PHASE_6_NOT_IMPLEMENTED = "PHASE_6_NOT_IMPLEMENTED"


class PublicOpportunityQuery(PublicSchema):
    q: str | None = Field(default=None, min_length=1, max_length=100)
    type: OpportunityTypeV02 | None = None
    status: OpportunityStatus | None = None
    region: str | None = Field(default=None, min_length=1, max_length=80)
    sort: PublicOpportunitySort = PublicOpportunitySort.PUBLISHED_DESC
    cursor: str | None = Field(default=None, min_length=1, max_length=1024)
    limit: int = Field(default=20, ge=1, le=50)

    @model_validator(mode="after")
    def normalize_search_values(self) -> Self:
        for field_name in ("q", "region"):
            value = getattr(self, field_name)
            if value is None:
                continue
            normalized = value.strip()
            if not normalized:
                raise ValueError(f"{field_name} must not be blank")
            object.__setattr__(self, field_name, normalized)
        return self


class PublicOpportunityCard(PublicSchema):
    public_id: str = Field(pattern=r"^opp_[0-9a-f]{32}$")
    title: str = Field(min_length=1)
    type: OpportunityTypeV02
    jurisdiction: str = Field(min_length=1)
    locations: tuple[str, ...]
    issuer_name: str = Field(min_length=1)
    status: OpportunityStatus
    published_at: datetime
    deadline: date
    last_verified_at: datetime
    change_markers: tuple[str, ...]
    data_label: PublicDataLabel


class PublicOpportunityPage(PublicSchema):
    items: tuple[PublicOpportunityCard, ...]
    next_cursor: str | None
    count: int = Field(ge=0)
    data_labels: tuple[PublicDataLabel, ...]
    reproduced_at: datetime | None


class PublicEvidence(PublicSchema):
    field_path: str = Field(min_length=1)
    evidence_ref_id: UUID
    document_id: UUID
    locator_kind: str = Field(min_length=1)
    locator_value: str | None
    locator_payload: dict[str, JsonValue] | None
    quote_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    precedence: int = Field(ge=100, le=600)
    authority: str = Field(min_length=1)
    official_url: HttpUrl


class PublicFieldChange(PublicSchema):
    field_path: str = Field(min_length=1)
    before: JsonValue | None
    after: JsonValue | None


class PublicHistoryEvent(PublicSchema):
    event_id: UUID
    from_version: int | None = Field(default=None, ge=1)
    to_version: int = Field(ge=1)
    event_type: str = Field(min_length=1)
    changed_fields: tuple[str, ...] = Field(min_length=1)
    changes: tuple[PublicFieldChange, ...] = Field(min_length=1)
    detected_at: datetime
    evidence_ref_id: UUID
    document_id: UUID
    official_url: HttpUrl


class PublicOpportunityDetail(PublicOpportunityCard):
    current_version: int = Field(ge=1)
    application_url: HttpUrl
    attachment_urls: tuple[HttpUrl, ...]
    key_evidence: tuple[PublicEvidence, ...] = Field(min_length=1)
    history: tuple[PublicHistoryEvent, ...] = Field(min_length=1)
    personalization_availability: Literal[PersonalizationAvailability.PHASE_6_NOT_IMPLEMENTED] = (
        PersonalizationAvailability.PHASE_6_NOT_IMPLEMENTED
    )
