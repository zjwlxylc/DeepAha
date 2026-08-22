import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid7

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.contracts.phase8 import DeadlineChangeReminderIntentSchemaV07
from deepaha.core.settings import RETRY_DELAYS_SECONDS
from deepaha.notifications.adapters import (
    PermanentDeliveryError,
    PostgresTestInboxAdapter,
    TransientDeliveryError,
)
from deepaha.notifications.models import (
    NotificationDeliveryAttemptModel,
    NotificationOutboxModel,
    ReminderPreferenceSnapshotModel,
)
from deepaha.opportunities.models import Opportunity
from deepaha.personal.models import (
    PersonalActionSnapshotModel,
    PersonalUserModel,
    UserStateSnapshotModel,
)
from deepaha.public_catalog.service import PublicCatalogService

LOGGER = logging.getLogger(__name__)


class ReminderDeliveryAdapter(Protocol):
    def deliver(
        self,
        session: Session,
        intent: DeadlineChangeReminderIntentSchemaV07,
        *,
        delivered_at: datetime,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class ReminderWorkerRunSummary:
    inspected: int
    promoted: int
    claimed: int
    delivered: int
    suppressed: int
    retried: int
    failed: int
    waiting_governance: int


@dataclass(frozen=True, slots=True)
class _Claim:
    reminder_id: UUID
    lease_token: UUID


def validate_worker_limit(limit: int | None, *, default: int = 50) -> int:
    resolved = default if limit is None else limit
    if not 1 <= resolved <= 100:
        raise ValueError("worker limit must be between 1 and 100")
    return resolved


def _now_utc() -> datetime:
    return datetime.now(UTC)


class ReminderWorker:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        adapter: ReminderDeliveryAdapter | None = None,
        clock: Callable[[], datetime] = _now_utc,
        id_factory: Callable[[], UUID] = uuid7,
        batch_size: int = 50,
        lease_seconds: int = 60,
        logger: logging.Logger = LOGGER,
    ) -> None:
        self._session_factory = session_factory
        self._adapter = adapter or PostgresTestInboxAdapter(id_factory=id_factory)
        self._clock = clock
        self._id_factory = id_factory
        self._batch_size = validate_worker_limit(batch_size)
        if not 10 <= lease_seconds <= 3600:
            raise ValueError("lease seconds must be between 10 and 3600")
        self._lease_seconds = lease_seconds
        self._logger = logger

    def run_once(self, *, limit: int | None = None) -> ReminderWorkerRunSummary:
        batch_limit = validate_worker_limit(limit, default=self._batch_size)
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("worker clock must return a timezone-aware instant")

        claims, inspected, promoted, waiting = self._promote_recover_and_claim(
            now=now,
            limit=batch_limit,
        )
        delivered = suppressed = retried = failed = 0
        for claim in claims:
            try:
                outcome = self._process_claim(claim, now=now)
            except Exception:
                self._logger.error(
                    "reminder processing rolled back reminder_id=%s "
                    "code=WORKER_PROCESSING_ROLLBACK",
                    claim.reminder_id,
                )
                continue
            if outcome == "DELIVERED":
                delivered += 1
            elif outcome == "SUPPRESSED":
                suppressed += 1
            elif outcome == "RETRIED":
                retried += 1
            elif outcome == "FAILED":
                failed += 1
            elif outcome == "WAITING_GOVERNANCE":
                waiting += 1

        return ReminderWorkerRunSummary(
            inspected=inspected,
            promoted=promoted,
            claimed=len(claims),
            delivered=delivered,
            suppressed=suppressed,
            retried=retried,
            failed=failed,
            waiting_governance=waiting,
        )

    def _promote_recover_and_claim(
        self,
        *,
        now: datetime,
        limit: int,
    ) -> tuple[tuple[_Claim, ...], int, int, int]:
        inspected_ids: set[UUID] = set()
        promoted = 0
        waiting = 0
        claims: list[_Claim] = []
        with self._session_factory.begin() as session:
            waiting_rows = session.scalars(
                select(NotificationOutboxModel)
                .where(NotificationOutboxModel.status == "WAITING_GOVERNANCE")
                .order_by(NotificationOutboxModel.created_at, NotificationOutboxModel.reminder_id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
            for row in waiting_rows:
                inspected_ids.add(row.reminder_id)
                if not self._is_governed(session, row):
                    waiting += 1
                    continue
                row.status = "AVAILABLE"
                row.available_at = now
                row.next_attempt_at = now
                row.updated_at = now
                promoted += 1

            expired_rows = session.scalars(
                select(NotificationOutboxModel)
                .where(
                    NotificationOutboxModel.status == "LEASED",
                    NotificationOutboxModel.lease_until <= now,
                )
                .order_by(NotificationOutboxModel.lease_until, NotificationOutboxModel.reminder_id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
            for row in expired_rows:
                inspected_ids.add(row.reminder_id)
                row.status = "AVAILABLE"
                row.lease_token = None
                row.lease_until = None
                row.claimed_at = None
                row.next_attempt_at = now
                row.updated_at = now

            session.flush()
            available_rows = session.scalars(
                select(NotificationOutboxModel)
                .where(
                    NotificationOutboxModel.status == "AVAILABLE",
                    or_(
                        NotificationOutboxModel.next_attempt_at.is_(None),
                        NotificationOutboxModel.next_attempt_at <= now,
                    ),
                )
                .order_by(
                    NotificationOutboxModel.next_attempt_at,
                    NotificationOutboxModel.reminder_id,
                )
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
            for row in available_rows:
                inspected_ids.add(row.reminder_id)
                lease_token = self._id_factory()
                row.status = "LEASED"
                row.lease_token = lease_token
                row.lease_until = now + timedelta(seconds=self._lease_seconds)
                row.claimed_at = now
                row.updated_at = now
                claims.append(_Claim(reminder_id=row.reminder_id, lease_token=lease_token))
        return tuple(claims), len(inspected_ids), promoted, waiting

    def _process_claim(self, claim: _Claim, *, now: datetime) -> str | None:
        with self._session_factory.begin() as session:
            row = session.scalar(
                select(NotificationOutboxModel)
                .where(
                    NotificationOutboxModel.reminder_id == claim.reminder_id,
                    NotificationOutboxModel.status == "LEASED",
                    NotificationOutboxModel.lease_token == claim.lease_token,
                )
                .with_for_update()
            )
            if row is None:
                return None
            if not self._is_governed(session, row):
                self._return_to_governance_wait(row, now=now)
                self._logger.info(
                    "reminder returned to governance wait reminder_id=%s "
                    "code=PUBLIC_GOVERNANCE_LOST",
                    claim.reminder_id,
                )
                return "WAITING_GOVERNANCE"
            if not self._user_controls_allow(session, row):
                row.status = "SUPPRESSED"
                row.terminal_at = now
                row.last_error_code = None
                row.updated_at = now
                self._clear_lease(row)
                self._logger.info(
                    "reminder suppressed reminder_id=%s code=USER_CONTROL_SUPPRESSED",
                    claim.reminder_id,
                )
                return "SUPPRESSED"

            try:
                intent = self._intent(row)
            except ValidationError:
                row.status = "FAILED"
                row.terminal_at = now
                row.last_error_code = "REMINDER_BINDING_INVALID"
                row.updated_at = now
                self._clear_lease(row)
                self._logger.warning(
                    "reminder binding failed reminder_id=%s code=REMINDER_BINDING_INVALID",
                    claim.reminder_id,
                )
                return "FAILED"

            attempt_number = row.attempt_count + 1
            started_at = now
            try:
                with session.begin_nested():
                    self._adapter.deliver(session, intent, delivered_at=now)
            except TransientDeliveryError as error:
                self._record_attempt(
                    session,
                    row=row,
                    claim=claim,
                    attempt_number=attempt_number,
                    outcome="TRANSIENT_FAILURE",
                    error_code=error.code,
                    started_at=started_at,
                    completed_at=now,
                )
                row.attempt_count = attempt_number
                row.last_error_code = error.code
                row.updated_at = now
                self._clear_lease(row)
                if attempt_number >= 3:
                    row.status = "FAILED"
                    row.terminal_at = now
                    outcome = "FAILED"
                else:
                    row.status = "AVAILABLE"
                    row.next_attempt_at = now + timedelta(
                        seconds=RETRY_DELAYS_SECONDS[attempt_number - 1]
                    )
                    outcome = "RETRIED"
                self._logger.warning(
                    "reminder delivery failed reminder_id=%s attempt=%s code=%s",
                    claim.reminder_id,
                    attempt_number,
                    error.code,
                )
                return outcome
            except PermanentDeliveryError as error:
                self._record_attempt(
                    session,
                    row=row,
                    claim=claim,
                    attempt_number=attempt_number,
                    outcome="PERMANENT_FAILURE",
                    error_code=error.code,
                    started_at=started_at,
                    completed_at=now,
                )
                row.attempt_count = attempt_number
                row.status = "FAILED"
                row.terminal_at = now
                row.last_error_code = error.code
                row.updated_at = now
                self._clear_lease(row)
                self._logger.warning(
                    "reminder delivery failed reminder_id=%s attempt=%s code=%s",
                    claim.reminder_id,
                    attempt_number,
                    error.code,
                )
                return "FAILED"

            self._record_attempt(
                session,
                row=row,
                claim=claim,
                attempt_number=attempt_number,
                outcome="SUCCEEDED",
                error_code=None,
                started_at=started_at,
                completed_at=now,
            )
            row.attempt_count = attempt_number
            row.status = "DELIVERED"
            row.terminal_at = now
            row.next_attempt_at = None
            row.last_error_code = None
            row.updated_at = now
            self._clear_lease(row)
            return "DELIVERED"

    @staticmethod
    def _is_governed(session: Session, row: NotificationOutboxModel) -> bool:
        opportunity = session.get(Opportunity, row.opportunity_id)
        if opportunity is None:
            return False
        detail = PublicCatalogService(session).get_opportunity(opportunity.public_id)
        return detail is not None and detail.current_version == row.to_version

    @staticmethod
    def _user_controls_allow(session: Session, row: NotificationOutboxModel) -> bool:
        user = session.get(PersonalUserModel, row.user_id)
        if user is None or not user.active:
            return False
        action = session.scalar(
            select(PersonalActionSnapshotModel)
            .where(
                PersonalActionSnapshotModel.user_id == row.user_id,
                PersonalActionSnapshotModel.opportunity_id == row.opportunity_id,
            )
            .order_by(
                PersonalActionSnapshotModel.created_at.desc(),
                PersonalActionSnapshotModel.version.desc(),
                PersonalActionSnapshotModel.action_snapshot_id.desc(),
            )
            .limit(1)
        )
        preference = session.scalar(
            select(ReminderPreferenceSnapshotModel)
            .where(
                ReminderPreferenceSnapshotModel.user_id == row.user_id,
                ReminderPreferenceSnapshotModel.reminder_kind == "DEADLINE_CHANGED",
            )
            .order_by(
                ReminderPreferenceSnapshotModel.created_at.desc(),
                ReminderPreferenceSnapshotModel.version.desc(),
                ReminderPreferenceSnapshotModel.preference_snapshot_id.desc(),
            )
            .limit(1)
        )
        state = session.scalar(
            select(UserStateSnapshotModel)
            .where(UserStateSnapshotModel.user_id == row.user_id)
            .order_by(
                UserStateSnapshotModel.created_at.desc(),
                UserStateSnapshotModel.version.desc(),
                UserStateSnapshotModel.user_state_snapshot_id.desc(),
            )
            .limit(1)
        )
        return bool(
            action is not None
            and action.saved
            and preference is not None
            and preference.enabled
            and state is not None
            and "ACTION_TRACKING" in state.allowed_purposes
        )

    @staticmethod
    def _intent(row: NotificationOutboxModel) -> DeadlineChangeReminderIntentSchemaV07:
        return DeadlineChangeReminderIntentSchemaV07.model_validate(
            {
                "reminder_id": row.reminder_id,
                "user_id": row.user_id,
                "opportunity_id": row.opportunity_id,
                "event_id": row.event_id,
                "from_version": row.from_version,
                "to_version": row.to_version,
                "old_closes_on": row.old_closes_on,
                "new_closes_on": row.new_closes_on,
                "direction": row.direction,
                "previous_evidence_ref_id": row.previous_evidence_ref_id,
                "current_evidence_ref_id": row.current_evidence_ref_id,
                "action_snapshot_id": row.action_snapshot_id,
                "preference_snapshot_id": row.preference_snapshot_id,
                "user_state_snapshot_id": row.user_state_snapshot_id,
                "consent_version": row.consent_version,
                "detected_at": row.detected_at,
                "created_at": row.created_at,
                "reminder_kind": row.reminder_kind,
                "cadence": row.cadence,
                "target": row.target,
                "contract_version": row.contract_version,
            }
        )

    def _record_attempt(
        self,
        session: Session,
        *,
        row: NotificationOutboxModel,
        claim: _Claim,
        attempt_number: int,
        outcome: str,
        error_code: str | None,
        started_at: datetime,
        completed_at: datetime,
    ) -> None:
        session.add(
            NotificationDeliveryAttemptModel(
                delivery_attempt_id=self._id_factory(),
                reminder_id=row.reminder_id,
                attempt_number=attempt_number,
                lease_token=claim.lease_token,
                adapter="POSTGRES_TEST_INBOX",
                outcome=outcome,
                error_code=error_code,
                started_at=started_at,
                completed_at=completed_at,
                contract_version="0.7.0",
            )
        )

    @staticmethod
    def _clear_lease(row: NotificationOutboxModel) -> None:
        row.lease_token = None
        row.lease_until = None
        row.claimed_at = None

    @classmethod
    def _return_to_governance_wait(
        cls,
        row: NotificationOutboxModel,
        *,
        now: datetime,
    ) -> None:
        row.status = "WAITING_GOVERNANCE"
        row.available_at = None
        row.next_attempt_at = None
        row.last_error_code = None
        row.updated_at = now
        cls._clear_lease(row)


__all__ = [
    "ReminderWorker",
    "ReminderWorkerRunSummary",
    "validate_worker_limit",
]
