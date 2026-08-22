from datetime import UTC, date, datetime, timedelta
from secrets import token_urlsafe
from uuid import UUID, uuid7

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.core.settings import Settings
from deepaha.personal.auth import Principal, resolve_principal, token_digest
from deepaha.personal.models import (
    PersonalAuthSessionModel,
    PersonalUserModel,
    UserStateSnapshotModel,
)
from deepaha.personal.profile import IdempotencyConflict, ProfileService
from deepaha.personal.schemas import ProfileWrite
from deepaha.profiles.models import ProfileSnapshotModel

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)
USER_A_ID = UUID("019b0000-0000-7000-8000-000000000501")
USER_A_STATE_ID = UUID("019b0000-0000-7000-8000-000000000511")
USER_B_ID = UUID("019b0000-0000-7000-8000-000000000502")
USER_B_STATE_ID = UUID("019b0000-0000-7000-8000-000000000512")
TOKEN_A = token_urlsafe(32)


def profile_command(**changes: object) -> ProfileWrite:
    values: dict[str, object] = {
        "life_stage": "GRADUATING",
        "goal_types": ["PUBLIC_SERVICE_EMPLOYMENT"],
        "attributes": {
            "education_level": "BACHELOR",
            "major_name": "合成软件工程",
            "major_code": "080902",
            "graduation_year": 2026,
            "student_status": "GRADUATING",
            "birth_date": None,
            "hukou_region": None,
            "residence_region": "合成杭州市",
            "target_regions": None,
            "certificates": None,
        },
        "preference_regions": ["合成杭州市"],
        "preference_types": ["PUBLIC_INSTITUTION_JOB"],
        "skipped_fields": ["birth_date", "hukou_region", "target_regions", "certificates"],
        "personalization_enabled": True,
        "consent_version": "phase6-consent-v1",
        "allowed_purposes": ["ACTION_TRACKING", "ELIGIBILITY", "PERSONAL_RANKING"],
        "scenario_clock": date(2026, 8, 22),
    }
    values.update(changes)
    return ProfileWrite.model_validate(values)


def seed_users(engine: Engine) -> None:
    with Session(engine) as session:
        session.add_all(
            [
                PersonalUserModel(
                    user_id=USER_A_ID,
                    user_state_id=USER_A_STATE_ID,
                    active=True,
                    created_at=NOW,
                ),
                PersonalUserModel(
                    user_id=USER_B_ID,
                    user_state_id=USER_B_STATE_ID,
                    active=True,
                    created_at=NOW,
                ),
            ]
        )
        session.flush()
        session.add(
            PersonalAuthSessionModel(
                token_sha256=token_digest(TOKEN_A),
                user_id=USER_A_ID,
                expires_at=NOW + timedelta(days=1),
                revoked_at=None,
                created_at=NOW,
            )
        )
        session.commit()


def test_fixture_session_resolves_server_side_and_fails_closed(migrated_engine: Engine) -> None:
    seed_users(migrated_engine)
    settings = Settings(environment="test", personal_auth_mode="fixture")

    with Session(migrated_engine) as session:
        principal = resolve_principal(
            f"Bearer {TOKEN_A}",
            session,
            settings,
            now=NOW,
        )

    assert principal == Principal(user_id=USER_A_ID)


def test_profile_snapshots_are_versioned_idempotent_and_owner_scoped(
    migrated_engine: Engine,
) -> None:
    seed_users(migrated_engine)
    factory = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    service = ProfileService(session_factory=factory, id_factory=uuid7, now_factory=lambda: NOW)
    principal_a = Principal(user_id=USER_A_ID)
    principal_b = Principal(user_id=USER_B_ID)

    first = service.save(principal_a, profile_command(), idempotency_key="profile-request-0001")
    replay = service.save(principal_a, profile_command(), idempotency_key="profile-request-0001")
    same_content = service.save(
        principal_a,
        profile_command(),
        idempotency_key="profile-request-0002",
    )
    changed = service.save(
        principal_a,
        profile_command(preference_regions=["合成宁波市"]),
        idempotency_key="profile-request-0003",
    )

    assert replay.user_state_snapshot_id == first.user_state_snapshot_id
    assert same_content.user_state_snapshot_id == first.user_state_snapshot_id
    assert changed.version == 2
    assert service.get_current(principal_a) == changed
    assert service.get_current(principal_b) is None
    assert service.get_snapshot(principal_b, first.user_state_snapshot_id) is None
    assert service.get_snapshot(principal_a, uuid7()) is None

    with pytest.raises(IdempotencyConflict, match="idempotency key conflict"):
        service.save(
            principal_a,
            profile_command(preference_regions=["合成温州市"]),
            idempotency_key="profile-request-0001",
        )

    with Session(migrated_engine) as session:
        state_rows = session.scalars(
            select(UserStateSnapshotModel).where(UserStateSnapshotModel.user_id == USER_A_ID)
        ).all()
        profile = session.get(ProfileSnapshotModel, first.qualification_profile_snapshot_id)

    assert len(state_rows) == 2
    assert profile is not None
    assert profile.synthetic is False
    assert profile.profile_schema_version == "0.5.0"
    assert profile.attributes["target_regions"] is None
    assert profile.attributes["certificates"] is None
