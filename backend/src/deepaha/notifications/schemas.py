from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deepaha.contracts.phase8 import TestInboxEntrySchemaV07


class ReminderPreferenceWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool


class ReminderInboxPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[TestInboxEntrySchemaV07, ...]
    count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_count(self) -> Self:
        if self.count != len(self.items):
            raise ValueError("inbox count must match items")
        return self


__all__ = ["ReminderInboxPage", "ReminderPreferenceWrite"]
