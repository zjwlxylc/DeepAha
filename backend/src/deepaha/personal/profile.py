import json
from collections.abc import Callable
from datetime import datetime
from hashlib import sha256
from uuid import UUID, uuid7

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.contracts.phase6 import (
    UserProfileAttributesSchemaV05,
    UserStateSnapshotSchemaV05,
)
from deepaha.personal.auth import Principal
from deepaha.personal.models import (
    PersonalIdempotencyRecordModel,
    PersonalUserModel,
    UserStateSnapshotModel,
)
from deepaha.personal.schemas import ProfileWrite
from deepaha.profiles.models import ProfileSnapshotModel

PROFILE_OPERATION = "PROFILE_WRITE"


class IdempotencyConflict(ValueError):
    pass


class ProfileAccessError(ValueError):
    pass


def profile_input_sha256(user_id: UUID, command: ProfileWrite) -> str:
    payload = {
        "user_id": str(user_id),
        "profile": command.model_dump(mode="json"),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def idempotency_key_sha256(value: str) -> str:
    if not 16 <= len(value) <= 128 or any(
        character.isspace() or not character.isprintable() for character in value
    ):
        raise ValueError("invalid idempotency key")
    return sha256(value.encode("utf-8")).hexdigest()


class ProfileService:
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

    def get_current(self, principal: Principal) -> UserStateSnapshotSchemaV05 | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(UserStateSnapshotModel)
                .where(UserStateSnapshotModel.user_id == principal.user_id)
                .order_by(UserStateSnapshotModel.version.desc())
                .limit(1)
            )
            return None if row is None else self._contract_from_row(session, row)

    def get_snapshot(
        self,
        principal: Principal,
        snapshot_id: UUID,
    ) -> UserStateSnapshotSchemaV05 | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(UserStateSnapshotModel).where(
                    UserStateSnapshotModel.user_state_snapshot_id == snapshot_id,
                    UserStateSnapshotModel.user_id == principal.user_id,
                )
            )
            return None if row is None else self._contract_from_row(session, row)

    def save(
        self,
        principal: Principal,
        command: ProfileWrite,
        *,
        idempotency_key: str,
    ) -> UserStateSnapshotSchemaV05:
        request_sha256 = profile_input_sha256(principal.user_id, command)
        key_sha256 = idempotency_key_sha256(idempotency_key)
        created_at = self._now_factory()
        with self._session_factory() as session:
            try:
                user = session.get(PersonalUserModel, principal.user_id)
                if user is None or not user.active:
                    raise ProfileAccessError("personal profile unavailable")

                recorded = session.get(
                    PersonalIdempotencyRecordModel,
                    (principal.user_id, PROFILE_OPERATION, key_sha256),
                )
                if recorded is not None:
                    if recorded.request_sha256 != request_sha256:
                        raise IdempotencyConflict("idempotency key conflict")
                    row = self._owned_row(session, principal.user_id, recorded.resource_id)
                    if row is None:
                        raise ProfileAccessError("personal profile unavailable")
                    session.rollback()
                    return self._contract_from_row(session, row)

                existing = session.scalar(
                    select(UserStateSnapshotModel).where(
                        UserStateSnapshotModel.user_id == principal.user_id,
                        UserStateSnapshotModel.input_sha256 == request_sha256,
                    )
                )
                if existing is not None:
                    self._record_idempotency(
                        session,
                        principal.user_id,
                        key_sha256,
                        request_sha256,
                        existing,
                        created_at,
                    )
                    session.commit()
                    return self._contract_from_row(session, existing)

                current_state = session.scalar(
                    select(UserStateSnapshotModel)
                    .where(UserStateSnapshotModel.user_id == principal.user_id)
                    .order_by(UserStateSnapshotModel.version.desc())
                    .limit(1)
                )
                version = 1 if current_state is None else current_state.version + 1
                attributes_payload = command.attributes.model_dump(mode="json")
                profile: ProfileSnapshotModel | None = None
                current_profile = (
                    None
                    if current_state is None
                    else session.get(
                        ProfileSnapshotModel,
                        current_state.qualification_profile_snapshot_id,
                    )
                )
                if (
                    current_profile is not None
                    and not current_profile.synthetic
                    and current_profile.profile_schema_version == "0.5.0"
                    and current_profile.attributes == attributes_payload
                    and current_profile.scenario_clock == command.scenario_clock
                ):
                    profile_snapshot_id = current_profile.profile_snapshot_id
                    profile_version = current_profile.version
                else:
                    latest_profile_version = session.scalar(
                        select(func.max(ProfileSnapshotModel.version)).where(
                            ProfileSnapshotModel.profile_id == user.user_state_id
                        )
                    )
                    profile_version = (latest_profile_version or 0) + 1
                    profile_snapshot_id = self._id_factory()
                    profile = ProfileSnapshotModel(
                        profile_snapshot_id=profile_snapshot_id,
                        profile_id=user.user_state_id,
                        version=profile_version,
                        synthetic=False,
                        persona_family_id=None,
                        attributes=attributes_payload,
                        scenario_clock=command.scenario_clock,
                        profile_schema_version="0.5.0",
                        created_at=created_at,
                        created_by="USER_SELF_SERVICE",
                        reviewed_by="NOT_REVIEWED_PHASE6",
                        change_note="Phase 6 immutable self-service qualification projection.",
                    )
                state_snapshot_id = self._id_factory()
                state = UserStateSnapshotModel(
                    user_state_snapshot_id=state_snapshot_id,
                    user_state_id=user.user_state_id,
                    user_id=user.user_id,
                    version=version,
                    qualification_profile_snapshot_id=profile_snapshot_id,
                    qualification_profile_version=profile_version,
                    life_stage=None if command.life_stage is None else command.life_stage.value,
                    goal_types=[item.value for item in command.goal_types],
                    preference_regions=list(command.preference_regions),
                    preference_types=[item.value for item in command.preference_types],
                    skipped_fields=[item.value for item in command.skipped_fields],
                    personalization_enabled=command.personalization_enabled,
                    consent_version=command.consent_version,
                    allowed_purposes=[item.value for item in command.allowed_purposes],
                    scenario_clock=command.scenario_clock,
                    input_sha256=request_sha256,
                    created_at=created_at,
                )
                if profile is not None:
                    session.add(profile)
                    session.flush()
                session.add(state)
                session.flush()
                self._record_idempotency(
                    session,
                    principal.user_id,
                    key_sha256,
                    request_sha256,
                    state,
                    created_at,
                )
                session.commit()
                return self._contract_from_row(session, state)
            except Exception:
                session.rollback()
                raise

    @staticmethod
    def _owned_row(
        session: Session,
        user_id: UUID,
        snapshot_id: UUID,
    ) -> UserStateSnapshotModel | None:
        return session.scalar(
            select(UserStateSnapshotModel).where(
                UserStateSnapshotModel.user_state_snapshot_id == snapshot_id,
                UserStateSnapshotModel.user_id == user_id,
            )
        )

    @staticmethod
    def _record_idempotency(
        session: Session,
        user_id: UUID,
        key_sha256: str,
        request_sha256: str,
        state: UserStateSnapshotModel,
        created_at: datetime,
    ) -> None:
        session.add(
            PersonalIdempotencyRecordModel(
                user_id=user_id,
                operation=PROFILE_OPERATION,
                key_sha256=key_sha256,
                request_sha256=request_sha256,
                resource_kind="PROFILE",
                resource_id=state.user_state_snapshot_id,
                response_version=state.version,
                created_at=created_at,
            )
        )
        session.flush()

    @staticmethod
    def _contract_from_row(
        session: Session,
        row: UserStateSnapshotModel,
    ) -> UserStateSnapshotSchemaV05:
        profile = session.get(ProfileSnapshotModel, row.qualification_profile_snapshot_id)
        if (
            profile is None
            or profile.synthetic
            or profile.profile_schema_version != "0.5.0"
            or profile.version != row.qualification_profile_version
            or profile.scenario_clock != row.scenario_clock
        ):
            raise ProfileAccessError("personal profile unavailable")
        attributes = UserProfileAttributesSchemaV05.model_validate(profile.attributes)
        return UserStateSnapshotSchemaV05.model_validate(
            {
                "user_state_snapshot_id": row.user_state_snapshot_id,
                "user_state_id": row.user_state_id,
                "version": row.version,
                "qualification_profile_snapshot_id": row.qualification_profile_snapshot_id,
                "qualification_profile_version": row.qualification_profile_version,
                "life_stage": row.life_stage,
                "goal_types": row.goal_types,
                "attributes": attributes,
                "preference_regions": row.preference_regions,
                "preference_types": row.preference_types,
                "skipped_fields": row.skipped_fields,
                "personalization_enabled": row.personalization_enabled,
                "consent_version": row.consent_version,
                "allowed_purposes": row.allowed_purposes,
                "scenario_clock": row.scenario_clock,
                "input_sha256": row.input_sha256,
                "created_at": row.created_at,
            }
        )


__all__ = [
    "IdempotencyConflict",
    "ProfileAccessError",
    "ProfileService",
    "idempotency_key_sha256",
    "profile_input_sha256",
]
