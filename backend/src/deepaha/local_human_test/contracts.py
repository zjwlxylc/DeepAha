from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator


class RunMode(StrEnum):
    LIVE_OFFICIAL = "LIVE_OFFICIAL"
    OFFICIAL_REPLAY = "OFFICIAL_REPLAY"


class RunStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ItemStatus(StrEnum):
    CREATED = "CREATED"
    ACQUIRING = "ACQUIRING"
    BOOTSTRAP_REVIEW = "BOOTSTRAP_REVIEW"
    EXTRACTING = "EXTRACTING"
    FACT_REVIEW = "FACT_REVIEW"
    RULE_REVIEW = "RULE_REVIEW"
    READY_TO_PUBLISH = "READY_TO_PUBLISH"
    COMPLETED = "COMPLETED"
    ACQUISITION_REJECTED = "ACQUISITION_REJECTED"
    FAILED_CONFIG = "FAILED_CONFIG"
    PARTIAL_BUDGET_EXHAUSTED = "PARTIAL_BUDGET_EXHAUSTED"
    UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"
    MODEL_OUTPUT_INVALID = "MODEL_OUTPUT_INVALID"
    EVIDENCE_BINDING_INVALID = "EVIDENCE_BINDING_INVALID"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ReviewDecisionKind(StrEnum):
    BOOTSTRAP = "BOOTSTRAP"
    FACT = "FACT"
    RULE = "RULE"
    PUBLISH = "PUBLISH"


class ExternalCallBudget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    official_request_limit: int = Field(default=9, ge=1, le=9)
    llm_call_limit: int = Field(default=8, ge=1, le=8)
    max_input_tokens: int = Field(default=12_000, ge=1, le=12_000)
    max_output_tokens: int = Field(default=3_000, ge=1, le=3_000)
    timeout_seconds: int = Field(default=90, ge=1, le=90)
    temperature: Literal[0] = 0


class ProviderConfigSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    base_url: AnyHttpUrl
    protocol: Literal["openai_chat_completions"]
    model_id: str = Field(min_length=1, max_length=128)
    model_snapshot: str = Field(min_length=1, max_length=128)

    @field_validator("base_url")
    @classmethod
    def require_https_origin(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.scheme != "https" or value.username or value.password:
            raise ValueError("Provider base URL must be an HTTPS origin without userinfo")
        if value.query is not None or value.fragment is not None:
            raise ValueError("Provider base URL must not contain query or fragment")
        return value


class CreateRunCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: RunMode
    recipe_ids: tuple[str, ...]
    provider: ProviderConfigSnapshot
    budget: ExternalCallBudget = Field(default_factory=ExternalCallBudget)
    reviewer_id: UUID

    @model_validator(mode="after")
    def validate_recipe_ids(self) -> Self:
        if not self.recipe_ids:
            raise ValueError("At least one Recipe is required")
        if any(not recipe_id.strip() for recipe_id in self.recipe_ids):
            raise ValueError("Recipe IDs must not be blank")
        if len(self.recipe_ids) != len(set(self.recipe_ids)):
            raise ValueError("Recipe IDs must be unique")
        return self


__all__ = [
    "CreateRunCommand",
    "ExternalCallBudget",
    "ItemStatus",
    "ProviderConfigSnapshot",
    "ReviewDecisionKind",
    "RunMode",
    "RunStatus",
]
