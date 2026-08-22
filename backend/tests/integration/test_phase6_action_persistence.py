from datetime import UTC, datetime
from uuid import UUID, uuid7

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from deepaha.contracts.phase6 import ActionState
from deepaha.personal.actions import ActionService, ActionUnavailable
from deepaha.personal.auth import Principal
from deepaha.personal.models import (
    PersonalActionEventModel,
    PersonalActionSnapshotModel,
    PersonalIdempotencyRecordModel,
)
from deepaha.personal.profile import IdempotencyConflict, ProfileService
from deepaha.personal.schemas import MaterialPlanItemWrite
from tests.integration.test_phase6_profile_persistence import (
    USER_A_ID,
    USER_B_ID,
    profile_command,
    seed_users,
)
from tests.public_catalog.support import persist_phase5_fixture

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)
UNKNOWN_PUBLIC_ID = "opp_00000000000000000000000000000000"


def test_action_writes_are_idempotent_owner_scoped_and_audited(
    migrated_engine: Engine,
) -> None:
    seed_users(migrated_engine)
    with Session(migrated_engine) as session:
        public_ids = persist_phase5_fixture(session)
        session.commit()
    public_id = public_ids[0]
    factory = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    profile_service = ProfileService(
        session_factory=factory,
        id_factory=uuid7,
        now_factory=lambda: NOW,
    )
    principal_a = Principal(user_id=USER_A_ID)
    principal_b = Principal(user_id=USER_B_ID)
    for index, principal in enumerate((principal_a, principal_b), start=1):
        profile_service.save(
            principal,
            profile_command(),
            idempotency_key=f"action-profile-request-000{index}",
        )
    service = ActionService(
        session_factory=factory,
        profile_service=profile_service,
        id_factory=uuid7,
        now_factory=lambda: NOW,
    )

    saved = service.set_saved(
        principal_a,
        public_id,
        True,
        idempotency_key="saved-request-0001",
    )
    replay = service.set_saved(
        principal_a,
        public_id,
        True,
        idempotency_key="saved-request-0001",
    )
    same_state = service.set_saved(
        principal_a,
        public_id,
        True,
        idempotency_key="saved-request-0002",
    )

    assert replay == saved
    assert same_state == saved
    with pytest.raises(IdempotencyConflict, match="idempotency key conflict"):
        service.set_saved(
            principal_a,
            public_id,
            False,
            idempotency_key="saved-request-0001",
        )

    failing_ids = iter((uuid7(), saved.last_event_id))
    failing_service = ActionService(
        session_factory=factory,
        profile_service=profile_service,
        id_factory=lambda: next(failing_ids),
        now_factory=lambda: NOW,
    )
    with pytest.raises(IntegrityError):
        failing_service.set_status(
            principal_a,
            public_id,
            ActionState.PREPARING,
            idempotency_key="status-rollback-request-0001",
        )
    assert service.get_current(principal_a, public_id) == saved

    preparing = service.set_status(
        principal_a,
        public_id,
        ActionState.PREPARING,
        idempotency_key="status-request-0001",
    )
    materials = service.set_material_plan(
        principal_a,
        public_id,
        (
            MaterialPlanItemWrite(
                material_item_id=UUID("019b0000-0000-7000-8000-000000000701"),
                label="合成报名表",
                completed=False,
                due_on=None,
            ),
        ),
        idempotency_key="materials-request-0001",
    )
    official = service.record_official_link(
        principal_a,
        public_id,
        idempotency_key="official-link-request-0001",
    )
    official_replay = service.record_official_link(
        principal_a,
        public_id,
        idempotency_key="official-link-request-0001",
    )

    assert preparing.version == 2
    assert materials.version == 3
    assert official.action.version == 4
    assert official_replay == official
    assert str(official.official_url).startswith("https://phase5-fixture.example.test/")
    assert service.get_current(principal_a, public_id) == official.action
    assert service.get_current(principal_b, public_id) is None
    assert service.get_current(principal_a, UNKNOWN_PUBLIC_ID) is None

    owned_by_b = service.set_saved(
        principal_b,
        public_id,
        True,
        idempotency_key="saved-request-user-b-0001",
    )
    assert owned_by_b.action_id != saved.action_id
    assert service.get_current(principal_a, public_id) == official.action

    with pytest.raises(ActionUnavailable, match="personal action unavailable"):
        service.set_saved(
            principal_a,
            UNKNOWN_PUBLIC_ID,
            True,
            idempotency_key="unknown-opportunity-0001",
        )

    with Session(migrated_engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(PersonalActionSnapshotModel)
                .where(PersonalActionSnapshotModel.user_id == USER_A_ID)
            )
            == 4
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(PersonalActionEventModel)
                .where(PersonalActionEventModel.user_id == USER_A_ID)
            )
            == 4
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(PersonalIdempotencyRecordModel)
                .where(PersonalIdempotencyRecordModel.user_id == USER_A_ID)
            )
            == 6
        )

    profile_service.save(
        principal_a,
        profile_command(allowed_purposes=["ELIGIBILITY", "PERSONAL_RANKING"]),
        idempotency_key="action-purpose-revoked-0001",
    )
    assert service.get_current(principal_a, public_id) is None
    with pytest.raises(ActionUnavailable, match="personal action unavailable"):
        service.set_status(
            principal_a,
            public_id,
            ActionState.APPLIED,
            idempotency_key="action-purpose-revoked-write-0001",
        )
