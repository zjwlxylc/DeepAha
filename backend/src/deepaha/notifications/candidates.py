import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID, uuid7

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from deepaha.contracts.phase8 import (
    DeadlineChangeDirection,
    DeadlineChangeReminderIntentSchemaV07,
)
from deepaha.notifications.models import (
    NotificationOutboxModel,
    ReminderPreferenceSnapshotModel,
)
from deepaha.opportunities.models import OpportunityEvent, OpportunityVersion
from deepaha.personal.models import (
    PersonalActionSnapshotModel,
    PersonalUserModel,
    UserStateSnapshotModel,
)

DEADLINE_FIELD = "application_window.closes_on"
ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class DeadlineReminderBindingError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RecognizedDeadlineChange:
    old_closes_on: date
    new_closes_on: date
    direction: DeadlineChangeDirection


@dataclass(frozen=True, slots=True)
class DeadlineChangeBinding:
    recognized: RecognizedDeadlineChange
    previous_evidence_ref_id: UUID
    current_evidence_ref_id: UUID


@dataclass(frozen=True, slots=True)
class DeadlineReminderAudienceBinding:
    action_snapshot_id: UUID
    preference_snapshot_id: UUID
    user_state_snapshot_id: UUID
    consent_version: str


def _strict_iso_date(value: object) -> date | None:
    if not isinstance(value, str) or ISO_DATE_PATTERN.fullmatch(value) is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def recognize_deadline_change(event: object) -> RecognizedDeadlineChange | None:
    if not isinstance(event, OpportunityEvent):
        return None
    if event.event_type != "DEADLINE_CHANGED":
        return None
    if event.from_version is None or event.to_version != event.from_version + 1:
        return None
    if tuple(event.changed_fields) != (DEADLINE_FIELD,) or len(event.changes) != 1:
        return None
    change = event.changes[0]
    if not isinstance(change, Mapping) or change.get("field_path") != DEADLINE_FIELD:
        return None
    old_closes_on = _strict_iso_date(change.get("before"))
    new_closes_on = _strict_iso_date(change.get("after"))
    if old_closes_on is None or new_closes_on is None or old_closes_on == new_closes_on:
        return None
    direction = (
        DeadlineChangeDirection.ADVANCED
        if new_closes_on < old_closes_on
        else DeadlineChangeDirection.EXTENDED
    )
    return RecognizedDeadlineChange(
        old_closes_on=old_closes_on,
        new_closes_on=new_closes_on,
        direction=direction,
    )


def _version_deadline(version: OpportunityVersion) -> date | None:
    application_window = version.snapshot.get("application_window")
    if not isinstance(application_window, Mapping):
        return None
    return _strict_iso_date(application_window.get("closes_on"))


def _deadline_evidence_id(version: OpportunityVersion) -> UUID | None:
    matches = [
        item
        for item in version.field_evidence
        if isinstance(item, Mapping) and item.get("field_path") == DEADLINE_FIELD
    ]
    if len(matches) != 1:
        return None
    try:
        return UUID(str(matches[0].get("evidence_ref_id")))
    except TypeError, ValueError:
        return None


def load_deadline_change_binding(
    session: Session,
    event: OpportunityEvent,
) -> DeadlineChangeBinding | None:
    recognized = recognize_deadline_change(event)
    if recognized is None:
        return None
    assert event.from_version is not None
    previous_version = session.get(
        OpportunityVersion,
        (event.opportunity_id, event.from_version),
    )
    current_version = session.get(
        OpportunityVersion,
        (event.opportunity_id, event.to_version),
    )
    if previous_version is None or current_version is None:
        raise DeadlineReminderBindingError("deadline versions are unavailable")
    previous_evidence_ref_id = _deadline_evidence_id(previous_version)
    current_evidence_ref_id = _deadline_evidence_id(current_version)
    try:
        changed_evidence_ref_id = UUID(str(event.changes[0].get("evidence_ref_id")))
    except (TypeError, ValueError) as error:
        raise DeadlineReminderBindingError("deadline change evidence is invalid") from error
    if (
        _version_deadline(previous_version) != recognized.old_closes_on
        or _version_deadline(current_version) != recognized.new_closes_on
        or previous_evidence_ref_id is None
        or current_evidence_ref_id is None
        or current_evidence_ref_id != changed_evidence_ref_id
        or current_evidence_ref_id != event.source_evidence_ref_id
    ):
        raise DeadlineReminderBindingError("deadline event/version evidence mismatch")
    return DeadlineChangeBinding(
        recognized=recognized,
        previous_evidence_ref_id=previous_evidence_ref_id,
        current_evidence_ref_id=current_evidence_ref_id,
    )


def _audience_statement(
    event: OpportunityEvent,
    *,
    user_id: UUID | None = None,
) -> Select[tuple[UUID, UUID, UUID, UUID, str]]:
    latest_actions = (
        select(
            PersonalActionSnapshotModel.user_id.label("user_id"),
            PersonalActionSnapshotModel.opportunity_id.label("opportunity_id"),
            PersonalActionSnapshotModel.action_snapshot_id.label("action_snapshot_id"),
            PersonalActionSnapshotModel.saved.label("saved"),
        )
        .where(
            PersonalActionSnapshotModel.opportunity_id == event.opportunity_id,
            PersonalActionSnapshotModel.created_at <= event.detected_at,
        )
        .distinct(
            PersonalActionSnapshotModel.user_id,
            PersonalActionSnapshotModel.opportunity_id,
        )
        .order_by(
            PersonalActionSnapshotModel.user_id,
            PersonalActionSnapshotModel.opportunity_id,
            PersonalActionSnapshotModel.version.desc(),
            PersonalActionSnapshotModel.created_at.desc(),
            PersonalActionSnapshotModel.action_snapshot_id.desc(),
        )
        .subquery("latest_phase8_actions")
    )
    latest_preferences = (
        select(
            ReminderPreferenceSnapshotModel.user_id.label("user_id"),
            ReminderPreferenceSnapshotModel.preference_snapshot_id.label("preference_snapshot_id"),
            ReminderPreferenceSnapshotModel.enabled.label("enabled"),
        )
        .where(
            ReminderPreferenceSnapshotModel.reminder_kind == "DEADLINE_CHANGED",
            ReminderPreferenceSnapshotModel.created_at <= event.detected_at,
        )
        .distinct(
            ReminderPreferenceSnapshotModel.user_id,
            ReminderPreferenceSnapshotModel.reminder_kind,
        )
        .order_by(
            ReminderPreferenceSnapshotModel.user_id,
            ReminderPreferenceSnapshotModel.reminder_kind,
            ReminderPreferenceSnapshotModel.version.desc(),
            ReminderPreferenceSnapshotModel.created_at.desc(),
            ReminderPreferenceSnapshotModel.preference_snapshot_id.desc(),
        )
        .subquery("latest_phase8_preferences")
    )
    latest_states = (
        select(
            UserStateSnapshotModel.user_id.label("user_id"),
            UserStateSnapshotModel.user_state_snapshot_id.label("user_state_snapshot_id"),
            UserStateSnapshotModel.consent_version.label("consent_version"),
            UserStateSnapshotModel.allowed_purposes.label("allowed_purposes"),
        )
        .where(UserStateSnapshotModel.created_at <= event.detected_at)
        .distinct(UserStateSnapshotModel.user_id)
        .order_by(
            UserStateSnapshotModel.user_id,
            UserStateSnapshotModel.version.desc(),
            UserStateSnapshotModel.created_at.desc(),
            UserStateSnapshotModel.user_state_snapshot_id.desc(),
        )
        .subquery("latest_phase8_user_states")
    )
    statement = (
        select(
            latest_actions.c.user_id,
            latest_actions.c.action_snapshot_id,
            latest_preferences.c.preference_snapshot_id,
            latest_states.c.user_state_snapshot_id,
            latest_states.c.consent_version,
        )
        .join(
            latest_preferences,
            latest_preferences.c.user_id == latest_actions.c.user_id,
        )
        .join(latest_states, latest_states.c.user_id == latest_actions.c.user_id)
        .join(PersonalUserModel, PersonalUserModel.user_id == latest_actions.c.user_id)
        .where(
            latest_actions.c.saved.is_(True),
            latest_preferences.c.enabled.is_(True),
            latest_states.c.allowed_purposes.contains(["ACTION_TRACKING"]),
            PersonalUserModel.active.is_(True),
        )
    )
    if user_id is not None:
        statement = statement.where(latest_actions.c.user_id == user_id)
    return statement.order_by(latest_actions.c.user_id)


def load_deadline_reminder_audience_binding(
    session: Session,
    event: OpportunityEvent,
    user_id: UUID,
) -> DeadlineReminderAudienceBinding | None:
    audience = session.execute(_audience_statement(event, user_id=user_id)).one_or_none()
    if audience is None:
        return None
    return DeadlineReminderAudienceBinding(
        action_snapshot_id=audience.action_snapshot_id,
        preference_snapshot_id=audience.preference_snapshot_id,
        user_state_snapshot_id=audience.user_state_snapshot_id,
        consent_version=audience.consent_version,
    )


class DeadlineReminderCandidateService:
    def __init__(self, *, id_factory: Callable[[], UUID] = uuid7) -> None:
        self._id_factory = id_factory

    def capture_for_event(
        self,
        session: Session,
        event: OpportunityEvent,
        *,
        created_at: datetime,
    ) -> tuple[UUID, ...]:
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("candidate creation time must be timezone-aware")
        binding = load_deadline_change_binding(session, event)
        if binding is None:
            return ()
        recognized = binding.recognized

        reminder_ids: list[UUID] = []
        for audience in session.execute(_audience_statement(event)):
            existing = session.scalar(
                select(NotificationOutboxModel).where(
                    NotificationOutboxModel.user_id == audience.user_id,
                    NotificationOutboxModel.event_id == event.event_id,
                    NotificationOutboxModel.to_version == event.to_version,
                    NotificationOutboxModel.reminder_kind == "DEADLINE_CHANGED",
                    NotificationOutboxModel.target == "TEST_INBOX",
                )
            )
            if existing is not None:
                reminder_ids.append(existing.reminder_id)
                continue
            reminder_id = self._id_factory()
            intent = DeadlineChangeReminderIntentSchemaV07.model_validate(
                {
                    "reminder_id": reminder_id,
                    "user_id": audience.user_id,
                    "opportunity_id": event.opportunity_id,
                    "event_id": event.event_id,
                    "from_version": event.from_version,
                    "to_version": event.to_version,
                    "old_closes_on": recognized.old_closes_on,
                    "new_closes_on": recognized.new_closes_on,
                    "direction": recognized.direction,
                    "previous_evidence_ref_id": binding.previous_evidence_ref_id,
                    "current_evidence_ref_id": binding.current_evidence_ref_id,
                    "action_snapshot_id": audience.action_snapshot_id,
                    "preference_snapshot_id": audience.preference_snapshot_id,
                    "user_state_snapshot_id": audience.user_state_snapshot_id,
                    "consent_version": audience.consent_version,
                    "detected_at": event.detected_at,
                    "created_at": created_at,
                    "reminder_kind": "DEADLINE_CHANGED",
                    "cadence": "AS_SOON_AS_GOVERNED",
                    "target": "TEST_INBOX",
                    "contract_version": "0.7.0",
                }
            )
            session.add(
                NotificationOutboxModel(
                    **intent.model_dump(),
                    status="WAITING_GOVERNANCE",
                    available_at=None,
                    lease_token=None,
                    lease_until=None,
                    claimed_at=None,
                    attempt_count=0,
                    next_attempt_at=None,
                    last_error_code=None,
                    terminal_at=None,
                    updated_at=created_at,
                )
            )
            reminder_ids.append(reminder_id)
        return tuple(reminder_ids)


__all__ = [
    "DeadlineReminderBindingError",
    "DeadlineReminderAudienceBinding",
    "DeadlineChangeBinding",
    "DeadlineReminderCandidateService",
    "RecognizedDeadlineChange",
    "load_deadline_change_binding",
    "load_deadline_reminder_audience_binding",
    "recognize_deadline_change",
]
