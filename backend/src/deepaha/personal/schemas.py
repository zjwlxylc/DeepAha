from datetime import date
from typing import Literal, Self

from pydantic import ConfigDict, Field, HttpUrl, field_validator, model_validator

from deepaha.contracts.common import EntityId
from deepaha.contracts.phase2 import OpportunityTypeV02
from deepaha.contracts.phase4 import MatchSnapshotSchemaV04
from deepaha.contracts.phase6 import (
    ActionState,
    GoalType,
    LifeStage,
    PersonalActionEventSchemaV05,
    PersonalActionSnapshotSchemaV05,
    PersonalRankingItemSchemaV05,
    Phase6ContractModel,
    ProfileFieldV05,
    UserDataPurpose,
    UserProfileAttributesSchemaV05,
)
from deepaha.public_catalog.schemas import (
    PublicOpportunityCard,
    PublicOpportunityDetail,
)


class PersonalInputModel(Phase6ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProfileWrite(PersonalInputModel):
    life_stage: LifeStage | None
    goal_types: tuple[GoalType, ...]
    attributes: UserProfileAttributesSchemaV05
    preference_regions: tuple[str, ...]
    preference_types: tuple[OpportunityTypeV02, ...]
    skipped_fields: tuple[ProfileFieldV05, ...]
    personalization_enabled: bool
    consent_version: Literal["phase6-consent-v1"]
    allowed_purposes: tuple[UserDataPurpose, ...]
    scenario_clock: date

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
            raise ValueError("set-like profile input fields must not contain duplicates")
        return normalized

    @model_validator(mode="after")
    def require_minimized_consistent_input(self) -> Self:
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
        if any(provided[field] is not None for field in self.skipped_fields):
            raise ValueError("skipped fields must be absent")
        if not self.allowed_purposes:
            raise ValueError("allowed_purposes must not be empty")
        return self


class SavedWrite(PersonalInputModel):
    saved: bool


class ActionStatusWrite(PersonalInputModel):
    state: ActionState


class MaterialPlanItemWrite(PersonalInputModel):
    material_item_id: EntityId
    label: str = Field(min_length=1, max_length=80)
    completed: bool
    due_on: date | None

    @field_validator("label", mode="before")
    @classmethod
    def normalize_label(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class MaterialPlanWrite(PersonalInputModel):
    items: tuple[MaterialPlanItemWrite, ...] = Field(max_length=20)

    @model_validator(mode="after")
    def require_unique_item_ids(self) -> Self:
        item_ids = tuple(item.material_item_id for item in self.items)
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("material item IDs must be unique")
        return self


class OfficialLinkResult(PersonalInputModel):
    official_url: HttpUrl
    action: PersonalActionSnapshotSchemaV05
    event: PersonalActionEventSchemaV05


class PersonalPriorityItem(PersonalInputModel):
    ranking: PersonalRankingItemSchemaV05
    opportunity: PublicOpportunityCard


class PersonalPriorityPage(PersonalInputModel):
    ranking_snapshot_id: EntityId
    items: tuple[PersonalPriorityItem, ...] = Field(max_length=3)
    omitted_rule_set_count: int = Field(ge=0)


class PersonalOpportunityDetail(PersonalInputModel):
    opportunity: PublicOpportunityDetail
    eligibility: MatchSnapshotSchemaV04
    action: PersonalActionSnapshotSchemaV05 | None


__all__ = [
    "ActionStatusWrite",
    "MaterialPlanItemWrite",
    "MaterialPlanWrite",
    "OfficialLinkResult",
    "PersonalOpportunityDetail",
    "PersonalPriorityItem",
    "PersonalPriorityPage",
    "ProfileWrite",
    "SavedWrite",
]
