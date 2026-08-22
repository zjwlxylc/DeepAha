from datetime import date, timedelta
from enum import StrEnum
from typing import Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from deepaha.contracts.common import (
    EntityId,
    Instant,
    NonEmptyString,
    Sha256,
    VersionNumber,
)
from deepaha.contracts.phase1 import ContractModel
from deepaha.contracts.phase2 import OpportunityTypeV02
from deepaha.contracts.phase4 import EducationLevel, EligibilityStatus, StudentStatus


class Phase6ContractModel(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LifeStage(StrEnum):
    STUDENT = "STUDENT"
    GRADUATING = "GRADUATING"
    EARLY_CAREER = "EARLY_CAREER"
    UNEMPLOYED = "UNEMPLOYED"
    OTHER = "OTHER"


class GoalType(StrEnum):
    PUBLIC_SERVICE_EMPLOYMENT = "PUBLIC_SERVICE_EMPLOYMENT"
    STATE_OWNED_ENTERPRISE_EMPLOYMENT = "STATE_OWNED_ENTERPRISE_EMPLOYMENT"
    CIVIL_SERVICE = "CIVIL_SERVICE"
    GRASSROOTS_SERVICE = "GRASSROOTS_SERVICE"
    POLICY_BENEFIT = "POLICY_BENEFIT"
    GROWTH_PROGRAM = "GROWTH_PROGRAM"


class ProfileFieldV05(StrEnum):
    LIFE_STAGE = "life_stage"
    GOAL_TYPES = "goal_types"
    EDUCATION_LEVEL = "education_level"
    MAJOR_NAME = "major_name"
    MAJOR_CODE = "major_code"
    GRADUATION_YEAR = "graduation_year"
    STUDENT_STATUS = "student_status"
    BIRTH_DATE = "birth_date"
    HUKOU_REGION = "hukou_region"
    RESIDENCE_REGION = "residence_region"
    TARGET_REGIONS = "target_regions"
    CERTIFICATES = "certificates"


class UserDataPurpose(StrEnum):
    ELIGIBILITY = "ELIGIBILITY"
    PERSONAL_RANKING = "PERSONAL_RANKING"
    ACTION_TRACKING = "ACTION_TRACKING"


class RankingReasonCode(StrEnum):
    ELIGIBILITY_ELIGIBLE = "ELIGIBILITY_ELIGIBLE"
    ELIGIBILITY_LIKELY = "ELIGIBILITY_LIKELY"
    ELIGIBILITY_UNCERTAIN = "ELIGIBILITY_UNCERTAIN"
    ELIGIBILITY_INELIGIBLE = "ELIGIBILITY_INELIGIBLE"
    PREFERRED_REGION = "PREFERRED_REGION"
    PREFERRED_TYPE = "PREFERRED_TYPE"
    EARLIER_DEADLINE = "EARLIER_DEADLINE"
    STABLE_ID_TIE_BREAK = "STABLE_ID_TIE_BREAK"


class ActionState(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    PREPARING = "PREPARING"
    APPLIED = "APPLIED"
    COMPLETED = "COMPLETED"
    DISMISSED = "DISMISSED"


class ActionEventType(StrEnum):
    SAVED_CHANGED = "SAVED_CHANGED"
    OFFICIAL_LINK_OPENED = "OFFICIAL_LINK_OPENED"
    MATERIAL_PLAN_CHANGED = "MATERIAL_PLAN_CHANGED"
    ACTION_STATE_CHANGED = "ACTION_STATE_CHANGED"


class UserProfileAttributesSchemaV05(Phase6ContractModel):
    education_level: EducationLevel | None
    major_name: NonEmptyString | None
    major_code: NonEmptyString | None
    graduation_year: int | None
    student_status: StudentStatus | None
    birth_date: date | None
    hukou_region: NonEmptyString | None
    residence_region: NonEmptyString | None
    target_regions: tuple[NonEmptyString, ...] | None
    certificates: tuple[NonEmptyString, ...] | None

    @field_validator("target_regions", "certificates", mode="before")
    @classmethod
    def normalize_optional_string_sets(cls, value: object) -> object:
        if value is None or not isinstance(value, (list, tuple)):
            return value
        normalized = tuple(sorted(str(item).strip() for item in value))
        if len(normalized) != len(set(normalized)):
            raise ValueError("set-like profile fields must not contain duplicates")
        return normalized


class UserStateSnapshotSchemaV05(Phase6ContractModel):
    user_state_snapshot_id: EntityId
    user_state_id: EntityId
    version: VersionNumber
    qualification_profile_snapshot_id: EntityId
    qualification_profile_version: VersionNumber
    life_stage: LifeStage | None
    goal_types: tuple[GoalType, ...]
    attributes: UserProfileAttributesSchemaV05
    preference_regions: tuple[NonEmptyString, ...]
    preference_types: tuple[OpportunityTypeV02, ...]
    skipped_fields: tuple[ProfileFieldV05, ...]
    personalization_enabled: bool
    consent_version: NonEmptyString
    allowed_purposes: tuple[UserDataPurpose, ...]
    scenario_clock: date
    input_sha256: Sha256
    created_at: Instant

    @field_validator(
        "goal_types",
        "preference_regions",
        "preference_types",
        "skipped_fields",
        "allowed_purposes",
        mode="before",
    )
    @classmethod
    def normalize_unique_sets(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            return value
        normalized = tuple(sorted(value, key=str))
        if len(normalized) != len(set(normalized)):
            raise ValueError("set-like user state fields must not contain duplicates")
        return normalized

    @model_validator(mode="after")
    def reject_skipped_provided_conflicts(self) -> Self:
        provided: dict[ProfileFieldV05, object | None] = {
            ProfileFieldV05.LIFE_STAGE: self.life_stage,
            ProfileFieldV05.GOAL_TYPES: self.goal_types or None,
            ProfileFieldV05.EDUCATION_LEVEL: self.attributes.education_level,
            ProfileFieldV05.MAJOR_NAME: self.attributes.major_name,
            ProfileFieldV05.MAJOR_CODE: self.attributes.major_code,
            ProfileFieldV05.GRADUATION_YEAR: self.attributes.graduation_year,
            ProfileFieldV05.STUDENT_STATUS: self.attributes.student_status,
            ProfileFieldV05.BIRTH_DATE: self.attributes.birth_date,
            ProfileFieldV05.HUKOU_REGION: self.attributes.hukou_region,
            ProfileFieldV05.RESIDENCE_REGION: self.attributes.residence_region,
            ProfileFieldV05.TARGET_REGIONS: self.attributes.target_regions,
            ProfileFieldV05.CERTIFICATES: self.attributes.certificates,
        }
        conflicts = [field for field in self.skipped_fields if provided[field] is not None]
        if conflicts:
            raise ValueError("skipped fields must be absent")
        if not self.allowed_purposes:
            raise ValueError("allowed_purposes must not be empty")
        return self


class PersonalRankingItemSchemaV05(Phase6ContractModel):
    ordinal: int = Field(ge=1, le=3)
    opportunity_id: EntityId
    opportunity_version: VersionNumber
    match_snapshot_id: EntityId
    eligibility_status: EligibilityStatus
    reason_codes: tuple[RankingReasonCode, ...]
    deadline: date

    @field_validator("reason_codes", mode="before")
    @classmethod
    def require_unique_reasons(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            return value
        normalized = tuple(value)
        if not normalized:
            raise ValueError("reason_codes must not be empty")
        if len(normalized) != len(set(normalized)):
            raise ValueError("reason_codes must not contain duplicates")
        return normalized


class PersonalRankingSnapshotSchemaV05(Phase6ContractModel):
    ranking_snapshot_id: EntityId
    user_state_snapshot_id: EntityId
    qualification_profile_snapshot_id: EntityId
    qualification_profile_version: VersionNumber
    scenario_clock: date
    window_end: date
    ranker_version: NonEmptyString
    input_sha256: Sha256
    items: tuple[PersonalRankingItemSchemaV05, ...] = Field(max_length=3)
    omitted_rule_set_count: int = Field(ge=0)
    created_at: Instant

    @model_validator(mode="after")
    def require_reproducible_window_and_items(self) -> Self:
        if self.window_end != self.scenario_clock + timedelta(days=90):
            raise ValueError("window_end must be exactly 90 days after scenario_clock")
        ordinals = tuple(item.ordinal for item in self.items)
        if ordinals != tuple(range(1, len(self.items) + 1)):
            raise ValueError("ranking ordinals must be consecutive from one")
        opportunity_ids = tuple(item.opportunity_id for item in self.items)
        if len(opportunity_ids) != len(set(opportunity_ids)):
            raise ValueError("ranking opportunity IDs must be unique")
        match_ids = tuple(item.match_snapshot_id for item in self.items)
        if len(match_ids) != len(set(match_ids)):
            raise ValueError("ranking match snapshot IDs must be unique")
        if any(item.eligibility_status is EligibilityStatus.INELIGIBLE for item in self.items):
            raise ValueError("INELIGIBLE items cannot enter personal priorities")
        if any(
            item.deadline < self.scenario_clock or item.deadline > self.window_end
            for item in self.items
        ):
            raise ValueError("ranking item deadline must be inside the 90-day window")
        return self


class MaterialPlanItemSchemaV05(Phase6ContractModel):
    material_item_id: EntityId
    label: str = Field(min_length=1, max_length=80)
    completed: bool
    due_on: date | None

    @field_validator("label", mode="before")
    @classmethod
    def normalize_label(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class PersonalActionSnapshotSchemaV05(Phase6ContractModel):
    action_snapshot_id: EntityId
    action_id: EntityId
    version: VersionNumber
    opportunity_id: EntityId
    opportunity_version: VersionNumber
    saved: bool
    state: ActionState
    material_items: tuple[MaterialPlanItemSchemaV05, ...] = Field(max_length=20)
    last_event_id: EntityId
    input_sha256: Sha256
    created_at: Instant

    @model_validator(mode="after")
    def require_unique_material_ids(self) -> Self:
        material_ids = tuple(item.material_item_id for item in self.material_items)
        if len(material_ids) != len(set(material_ids)):
            raise ValueError("material item IDs must be unique")
        return self


class PersonalActionEventSchemaV05(Phase6ContractModel):
    event_id: EntityId
    action_id: EntityId
    action_snapshot_id: EntityId
    event_type: ActionEventType
    payload_sha256: Sha256
    occurred_at: Instant


__all__ = [
    "ActionEventType",
    "ActionState",
    "GoalType",
    "LifeStage",
    "MaterialPlanItemSchemaV05",
    "PersonalActionEventSchemaV05",
    "PersonalActionSnapshotSchemaV05",
    "PersonalRankingItemSchemaV05",
    "PersonalRankingSnapshotSchemaV05",
    "Phase6ContractModel",
    "ProfileFieldV05",
    "RankingReasonCode",
    "UserDataPurpose",
    "UserProfileAttributesSchemaV05",
    "UserStateSnapshotSchemaV05",
]
