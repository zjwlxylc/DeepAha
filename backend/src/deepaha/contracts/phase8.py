from datetime import date
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, HttpUrl, StringConstraints, model_validator

from deepaha.contracts.common import (
    EntityId,
    Instant,
    NonEmptyString,
    OpportunityPublicId,
    VersionNumber,
)
from deepaha.contracts.phase1 import ContractModel

DeliveryErrorCode = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{0,63}$"),
]
PersonalDetailPath = Annotated[
    str,
    StringConstraints(pattern=r"^/me/opportunities/opp_[0-9a-f]{32}$"),
]


class Phase8ContractModel(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReminderKind(StrEnum):
    DEADLINE_CHANGED = "DEADLINE_CHANGED"


class DeadlineChangeDirection(StrEnum):
    ADVANCED = "ADVANCED"
    EXTENDED = "EXTENDED"


class ReminderCadence(StrEnum):
    AS_SOON_AS_GOVERNED = "AS_SOON_AS_GOVERNED"


class ReminderTarget(StrEnum):
    TEST_INBOX = "TEST_INBOX"


class NotificationOutboxStatus(StrEnum):
    WAITING_GOVERNANCE = "WAITING_GOVERNANCE"
    AVAILABLE = "AVAILABLE"
    LEASED = "LEASED"
    DELIVERED = "DELIVERED"
    SUPPRESSED = "SUPPRESSED"
    FAILED = "FAILED"


class NotificationDeliveryOutcome(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    TRANSIENT_FAILURE = "TRANSIENT_FAILURE"
    PERMANENT_FAILURE = "PERMANENT_FAILURE"


class ReminderPreferenceSnapshotSchemaV07(Phase8ContractModel):
    preference_snapshot_id: EntityId
    preference_id: EntityId
    user_id: EntityId
    version: VersionNumber
    predecessor_snapshot_id: EntityId | None
    reminder_kind: Literal[ReminderKind.DEADLINE_CHANGED]
    enabled: bool
    cadence: Literal[ReminderCadence.AS_SOON_AS_GOVERNED]
    target: Literal[ReminderTarget.TEST_INBOX]
    actor_user_id: EntityId
    preference_policy_version: Literal["phase8-deadline-reminder-v1"]
    contract_version: Literal["0.7.0"]
    created_at: Instant

    @model_validator(mode="after")
    def validate_stream(self) -> Self:
        if self.actor_user_id != self.user_id:
            raise ValueError("preference actor must be the owner")
        if self.version == 1 and self.predecessor_snapshot_id is not None:
            raise ValueError("initial preference snapshot cannot have a predecessor")
        if self.version > 1 and self.predecessor_snapshot_id is None:
            raise ValueError("later preference snapshot requires a predecessor")
        if self.predecessor_snapshot_id == self.preference_snapshot_id:
            raise ValueError("preference snapshot cannot precede itself")
        return self


class DeadlineChangeReminderIntentSchemaV07(Phase8ContractModel):
    reminder_id: EntityId
    user_id: EntityId
    opportunity_id: EntityId
    event_id: EntityId
    from_version: VersionNumber
    to_version: VersionNumber
    old_closes_on: date
    new_closes_on: date
    direction: DeadlineChangeDirection
    previous_evidence_ref_id: EntityId
    current_evidence_ref_id: EntityId
    action_snapshot_id: EntityId
    preference_snapshot_id: EntityId
    user_state_snapshot_id: EntityId
    consent_version: NonEmptyString
    detected_at: Instant
    created_at: Instant
    reminder_kind: Literal[ReminderKind.DEADLINE_CHANGED]
    cadence: Literal[ReminderCadence.AS_SOON_AS_GOVERNED]
    target: Literal[ReminderTarget.TEST_INBOX]
    contract_version: Literal["0.7.0"]

    @model_validator(mode="after")
    def validate_change(self) -> Self:
        if self.to_version != self.from_version + 1:
            raise ValueError("deadline reminder requires consecutive versions")
        if self.old_closes_on == self.new_closes_on:
            raise ValueError("deadline reminder requires a changed date")
        expected = (
            DeadlineChangeDirection.ADVANCED
            if self.new_closes_on < self.old_closes_on
            else DeadlineChangeDirection.EXTENDED
        )
        if self.direction is not expected:
            raise ValueError("deadline direction does not match the date change")
        if self.created_at < self.detected_at:
            raise ValueError("reminder cannot be created before event detection")
        return self


class NotificationDeliveryAttemptSchemaV07(Phase8ContractModel):
    delivery_attempt_id: EntityId
    reminder_id: EntityId
    attempt_number: Annotated[int, Field(ge=1, le=3)]
    lease_token: EntityId
    adapter: Literal["POSTGRES_TEST_INBOX"]
    outcome: NotificationDeliveryOutcome
    error_code: DeliveryErrorCode | None
    started_at: Instant
    completed_at: Instant
    contract_version: Literal["0.7.0"]

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("delivery attempt completion cannot precede start")
        if self.outcome is NotificationDeliveryOutcome.SUCCEEDED:
            if self.error_code is not None:
                raise ValueError("successful delivery cannot have an error code")
        elif self.error_code is None:
            raise ValueError("failed delivery requires an error code")
        return self


class TestInboxEntrySchemaV07(Phase8ContractModel):
    inbox_entry_id: EntityId
    reminder_id: EntityId
    user_id: EntityId
    opportunity_id: EntityId
    opportunity_public_id: OpportunityPublicId
    opportunity_title: NonEmptyString
    event_id: EntityId
    from_version: VersionNumber
    to_version: VersionNumber
    old_closes_on: date
    new_closes_on: date
    direction: DeadlineChangeDirection
    previous_evidence_ref_id: EntityId
    current_evidence_ref_id: EntityId
    previous_official_url: HttpUrl
    current_official_url: HttpUrl
    personal_detail_path: PersonalDetailPath
    detected_at: Instant
    delivered_at: Instant
    target: Literal[ReminderTarget.TEST_INBOX]
    contract_version: Literal["0.7.0"]

    @model_validator(mode="after")
    def validate_entry(self) -> Self:
        if self.to_version != self.from_version + 1:
            raise ValueError("inbox entry requires consecutive versions")
        expected = (
            DeadlineChangeDirection.ADVANCED
            if self.new_closes_on < self.old_closes_on
            else DeadlineChangeDirection.EXTENDED
        )
        if self.old_closes_on == self.new_closes_on or self.direction is not expected:
            raise ValueError("inbox deadline direction is inconsistent")
        expected_path = f"/me/opportunities/{self.opportunity_public_id}"
        if self.personal_detail_path != expected_path:
            raise ValueError("personal detail path must match opportunity public ID")
        if self.delivered_at < self.detected_at:
            raise ValueError("inbox delivery cannot precede event detection")
        return self


__all__ = [
    "DeadlineChangeDirection",
    "DeadlineChangeReminderIntentSchemaV07",
    "NotificationDeliveryAttemptSchemaV07",
    "NotificationDeliveryOutcome",
    "NotificationOutboxStatus",
    "ReminderCadence",
    "ReminderKind",
    "ReminderPreferenceSnapshotSchemaV07",
    "ReminderTarget",
    "TestInboxEntrySchemaV07",
]
