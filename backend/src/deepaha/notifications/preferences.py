import json
from collections.abc import Callable
from datetime import datetime
from hashlib import sha256
from uuid import UUID, uuid7

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.contracts.phase8 import ReminderPreferenceSnapshotSchemaV07
from deepaha.notifications.models import (
    ReminderPreferenceIdempotencyRecordModel,
    ReminderPreferenceSnapshotModel,
)
from deepaha.personal.auth import Principal
from deepaha.personal.models import PersonalUserModel
from deepaha.personal.profile import idempotency_key_sha256

DEADLINE_REMINDER_PREFERENCE_OPERATION = "DEADLINE_REMINDER_PREFERENCE"


class ReminderPreferenceIdempotencyConflict(ValueError):
    pass


class ReminderPreferenceAccessError(ValueError):
    pass


def reminder_preference_input_sha256(user_id: UUID, enabled: bool) -> str:
    payload = {
        "enabled": enabled,
        "operation": DEADLINE_REMINDER_PREFERENCE_OPERATION,
        "user_id": str(user_id),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


class ReminderPreferenceService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        id_factory: Callable[[], UUID] = uuid7,
        now_factory: Callable[[], datetime],
    ) -> None:
        self._session_factory = session_factory
        self._id_factory = id_factory
        self._now_factory = now_factory

    def get_current(
        self,
        principal: Principal,
    ) -> ReminderPreferenceSnapshotSchemaV07 | None:
        with self._session_factory() as session:
            row = self._current_row(session, principal.user_id)
            return None if row is None else self._contract_from_row(row)

    def set_enabled(
        self,
        principal: Principal,
        enabled: bool,
        *,
        idempotency_key: str,
    ) -> ReminderPreferenceSnapshotSchemaV07:
        request_sha256 = reminder_preference_input_sha256(principal.user_id, enabled)
        key_sha256 = idempotency_key_sha256(idempotency_key)
        created_at = self._now_factory()
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("reminder preference clock must be timezone-aware")

        with self._session_factory() as session:
            try:
                user = session.scalar(
                    select(PersonalUserModel)
                    .where(PersonalUserModel.user_id == principal.user_id)
                    .with_for_update()
                )
                if user is None or not user.active:
                    raise ReminderPreferenceAccessError("reminder preference unavailable")

                recorded = session.get(
                    ReminderPreferenceIdempotencyRecordModel,
                    (
                        principal.user_id,
                        DEADLINE_REMINDER_PREFERENCE_OPERATION,
                        key_sha256,
                    ),
                )
                if recorded is not None:
                    if recorded.request_sha256 != request_sha256:
                        raise ReminderPreferenceIdempotencyConflict("idempotency key conflict")
                    replay = self._owned_row(session, principal.user_id, recorded.resource_id)
                    if replay is None or replay.version != recorded.response_version:
                        raise ReminderPreferenceAccessError("reminder preference unavailable")
                    session.rollback()
                    return self._contract_from_row(replay)

                current = self._current_row(session, principal.user_id)
                if current is not None and current.enabled is enabled:
                    self._record_idempotency(
                        session,
                        principal.user_id,
                        key_sha256,
                        request_sha256,
                        current,
                        created_at,
                    )
                    session.commit()
                    return self._contract_from_row(current)

                snapshot = ReminderPreferenceSnapshotModel(
                    preference_snapshot_id=self._id_factory(),
                    preference_id=(
                        self._id_factory() if current is None else current.preference_id
                    ),
                    user_id=principal.user_id,
                    version=1 if current is None else current.version + 1,
                    predecessor_snapshot_id=(
                        None if current is None else current.preference_snapshot_id
                    ),
                    reminder_kind="DEADLINE_CHANGED",
                    enabled=enabled,
                    cadence="AS_SOON_AS_GOVERNED",
                    target="TEST_INBOX",
                    actor_user_id=principal.user_id,
                    preference_policy_version="phase8-deadline-reminder-v1",
                    contract_version="0.7.0",
                    created_at=created_at,
                )
                session.add(snapshot)
                session.flush()
                self._record_idempotency(
                    session,
                    principal.user_id,
                    key_sha256,
                    request_sha256,
                    snapshot,
                    created_at,
                )
                session.commit()
                return self._contract_from_row(snapshot)
            except Exception:
                session.rollback()
                raise

    @staticmethod
    def _current_row(
        session: Session,
        user_id: UUID,
    ) -> ReminderPreferenceSnapshotModel | None:
        return session.scalar(
            select(ReminderPreferenceSnapshotModel)
            .where(
                ReminderPreferenceSnapshotModel.user_id == user_id,
                ReminderPreferenceSnapshotModel.reminder_kind == "DEADLINE_CHANGED",
            )
            .order_by(ReminderPreferenceSnapshotModel.version.desc())
            .limit(1)
        )

    @staticmethod
    def _owned_row(
        session: Session,
        user_id: UUID,
        snapshot_id: UUID,
    ) -> ReminderPreferenceSnapshotModel | None:
        return session.scalar(
            select(ReminderPreferenceSnapshotModel).where(
                ReminderPreferenceSnapshotModel.preference_snapshot_id == snapshot_id,
                ReminderPreferenceSnapshotModel.user_id == user_id,
            )
        )

    @staticmethod
    def _record_idempotency(
        session: Session,
        user_id: UUID,
        key_sha256: str,
        request_sha256: str,
        snapshot: ReminderPreferenceSnapshotModel,
        created_at: datetime,
    ) -> None:
        session.add(
            ReminderPreferenceIdempotencyRecordModel(
                user_id=user_id,
                operation=DEADLINE_REMINDER_PREFERENCE_OPERATION,
                key_sha256=key_sha256,
                request_sha256=request_sha256,
                resource_kind="PREFERENCE",
                resource_id=snapshot.preference_snapshot_id,
                response_version=snapshot.version,
                created_at=created_at,
            )
        )
        session.flush()

    @staticmethod
    def _contract_from_row(
        row: ReminderPreferenceSnapshotModel,
    ) -> ReminderPreferenceSnapshotSchemaV07:
        return ReminderPreferenceSnapshotSchemaV07.model_validate(
            {
                "preference_snapshot_id": row.preference_snapshot_id,
                "preference_id": row.preference_id,
                "user_id": row.user_id,
                "version": row.version,
                "predecessor_snapshot_id": row.predecessor_snapshot_id,
                "reminder_kind": row.reminder_kind,
                "enabled": row.enabled,
                "cadence": row.cadence,
                "target": row.target,
                "actor_user_id": row.actor_user_id,
                "preference_policy_version": row.preference_policy_version,
                "contract_version": row.contract_version,
                "created_at": row.created_at,
            }
        )


__all__ = [
    "DEADLINE_REMINDER_PREFERENCE_OPERATION",
    "ReminderPreferenceAccessError",
    "ReminderPreferenceIdempotencyConflict",
    "ReminderPreferenceService",
    "reminder_preference_input_sha256",
]
