from pydantic import BaseModel, ConfigDict


class ReminderPreferenceWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool


__all__ = ["ReminderPreferenceWrite"]
