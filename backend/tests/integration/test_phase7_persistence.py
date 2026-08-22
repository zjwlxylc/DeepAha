from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import pytest
from sqlalchemy import Connection, Engine, inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from deepaha.core.settings import Settings
from deepaha.feedback.models import FeedbackEventModel
from deepaha.personal.models import (
    PersonalRankingItemModel,
    PersonalRankingSnapshotModel,
    PersonalUserModel,
    UserStateSnapshotModel,
)
from deepaha.review.auth import (
    ReviewerAuthenticationError,
    ReviewerRole,
    resolve_reviewer_principal,
    reviewer_token_digest,
)
from deepaha.review.models import (
    FeedbackReviewCaseSnapshotModel,
    ReviewerAccountModel,
    ReviewerAuthSessionModel,
)
from tests.integration.test_phase4_persistence_contract import persist_complete_phase4_graph

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 22, 11, 0, tzinfo=UTC)
REVIEWER_ID = UUID("019b0000-0000-7000-8000-000000000701")
REVIEWER_TOKEN = "phase7-reviewer-token-0001"

PHASE7_TABLES = {
    "reviewer_accounts",
    "reviewer_auth_sessions",
    "feedback_idempotency_records",
    "reviewer_idempotency_records",
    "feedback_events",
    "feedback_evidence_links",
    "feedback_review_case_snapshots",
    "feedback_confidence_assessments",
    "feedback_adjudications",
    "approved_feedback_labels",
    "feedback_improvement_candidates",
    "offline_evaluation_candidates",
    "shadow_test_candidates",
    "validation_runs",
    "release_gate_decisions",
}

IMMUTABLE_PHASE7_TABLES = PHASE7_TABLES - {
    "reviewer_accounts",
    "reviewer_auth_sessions",
    "feedback_idempotency_records",
    "reviewer_idempotency_records",
}


def seed_reviewer(session: Session) -> None:
    session.add(
        ReviewerAccountModel(
            reviewer_id=REVIEWER_ID,
            active=True,
            synthetic=True,
            principal_label="SYNTHETIC_PHASE7_REVIEWER",
            roles=[role.value for role in ReviewerRole],
            allowed_purposes=["FEEDBACK_REVIEW_AND_VALIDATION"],
            created_at=NOW,
        )
    )
    session.flush()
    session.add(
        ReviewerAuthSessionModel(
            token_sha256=reviewer_token_digest(REVIEWER_TOKEN),
            reviewer_id=REVIEWER_ID,
            expires_at=NOW + timedelta(hours=1),
            revoked_at=None,
            created_at=NOW,
        )
    )
    session.flush()


def seed_phase6_ranking(
    engine: Engine,
) -> tuple[UUID, PersonalRankingSnapshotModel, PersonalRankingItemModel, UserStateSnapshotModel]:
    owner_id = UUID("019b0000-0000-7000-8000-000000000702")
    user_state_id = UUID("019b0000-0000-7000-8000-000000000703")
    with Session(engine, expire_on_commit=False) as session:
        _, profile, match, _ = persist_complete_phase4_graph(session)
        session.add(
            PersonalUserModel(
                user_id=owner_id,
                user_state_id=user_state_id,
                active=True,
                created_at=NOW,
            )
        )
        session.flush()
        state = UserStateSnapshotModel(
            user_state_snapshot_id=uuid7(),
            user_state_id=user_state_id,
            user_id=owner_id,
            version=1,
            qualification_profile_snapshot_id=profile.profile_snapshot_id,
            qualification_profile_version=profile.version,
            life_stage="GRADUATING",
            goal_types=["PUBLIC_SERVICE_EMPLOYMENT"],
            preference_regions=["合成杭州市"],
            preference_types=["YOUTH_DEVELOPMENT_PROGRAM"],
            skipped_fields=["birth_date"],
            personalization_enabled=True,
            consent_version="phase6-consent-v1",
            allowed_purposes=["ELIGIBILITY", "PERSONAL_RANKING"],
            scenario_clock=match.scenario_clock,
            input_sha256="4" * 64,
            created_at=NOW,
        )
        session.add(state)
        session.flush()
        ranking = PersonalRankingSnapshotModel(
            ranking_snapshot_id=uuid7(),
            user_id=owner_id,
            user_state_snapshot_id=state.user_state_snapshot_id,
            qualification_profile_snapshot_id=profile.profile_snapshot_id,
            qualification_profile_version=profile.version,
            scenario_clock=match.scenario_clock,
            window_end=match.scenario_clock + timedelta(days=90),
            ranker_version="phase7-persistence-fixture-v1",
            input_sha256="5" * 64,
            omitted_rule_set_count=0,
            created_at=NOW,
        )
        session.add(ranking)
        session.flush()
        item = PersonalRankingItemModel(
            ranking_snapshot_id=ranking.ranking_snapshot_id,
            ordinal=1,
            user_id=owner_id,
            opportunity_id=match.opportunity_id,
            opportunity_version=match.opportunity_version,
            match_snapshot_id=match.snapshot_id,
            eligibility_status="ELIGIBLE",
            reason_codes=["ELIGIBILITY_ELIGIBLE"],
            deadline=match.scenario_clock + timedelta(days=30),
        )
        session.add(item)
        session.commit()
        session.expunge(ranking)
        session.expunge(item)
        session.expunge(state)
    return owner_id, ranking, item, state


def test_phase7_tables_foreign_keys_and_immutable_triggers_exist(
    connection: Connection,
) -> None:
    inspector = inspect(connection)

    assert set(inspector.get_table_names()) >= PHASE7_TABLES
    feedback_targets = {
        foreign_key["referred_table"]
        for foreign_key in inspector.get_foreign_keys("feedback_events")
    }
    assert {
        "personal_users",
        "personal_ranking_snapshots",
        "personal_ranking_items",
        "user_state_snapshots",
    } <= feedback_targets
    trigger_tables = {
        row[0]
        for row in connection.execute(
            text(
                "select event_object_table from information_schema.triggers "
                "where trigger_name = 'phase7_reject_mutation'"
            )
        )
    }
    assert trigger_tables == IMMUTABLE_PHASE7_TABLES


def test_reviewer_session_derives_roles_and_rejects_expiry_and_revocation(
    migrated_engine: Engine,
) -> None:
    settings = Settings(environment="test", reviewer_auth_mode="fixture")
    with Session(migrated_engine) as session:
        seed_reviewer(session)
        session.commit()
        principal = resolve_reviewer_principal(
            f"Bearer {REVIEWER_TOKEN}", session, settings, now=NOW
        )
        auth_session = session.get(
            ReviewerAuthSessionModel,
            reviewer_token_digest(REVIEWER_TOKEN),
        )
        assert auth_session is not None
        assert "token" not in ReviewerAuthSessionModel.__table__.columns
        assert auth_session.token_sha256 != REVIEWER_TOKEN

        assert principal.reviewer_id == REVIEWER_ID
        assert principal.synthetic is True
        assert principal.roles == frozenset(ReviewerRole)
        assert principal.purposes == frozenset({"FEEDBACK_REVIEW_AND_VALIDATION"})

        with pytest.raises(ReviewerAuthenticationError):
            resolve_reviewer_principal(
                f"Bearer {REVIEWER_TOKEN}",
                session,
                settings,
                now=NOW + timedelta(hours=1),
            )
        auth_session.revoked_at = NOW
        session.commit()
        with pytest.raises(ReviewerAuthenticationError):
            resolve_reviewer_principal(f"Bearer {REVIEWER_TOKEN}", session, settings, now=NOW)


def test_feedback_fact_is_insert_only_and_review_stream_versions_are_exact(
    migrated_engine: Engine,
) -> None:
    owner_id, ranking, item, state = seed_phase6_ranking(migrated_engine)
    feedback_event_id = uuid7()
    review_case_id = uuid7()
    with Session(migrated_engine) as session:
        session.add(
            FeedbackEventModel(
                feedback_event_id=feedback_event_id,
                owner_user_id=owner_id,
                ranking_snapshot_id=ranking.ranking_snapshot_id,
                match_snapshot_id=item.match_snapshot_id,
                opportunity_id=item.opportunity_id,
                opportunity_version=item.opportunity_version,
                user_state_snapshot_id=state.user_state_snapshot_id,
                user_state_version=state.version,
                event_type="STRUCTURED_CORRECTION",
                claim_kind="EXPLANATION_UNCLEAR",
                user_statement="合成反馈：解释缺少证据定位。",
                structured_reason_code="MISSING_EVIDENCE_EXPLANATION",
                consent_version="phase7-feedback-consent-v1",
                consent_scope="FEEDBACK_REVIEW_AND_VALIDATION",
                contract_version="0.6.0",
                input_sha256="6" * 64,
                created_at=NOW,
            )
        )
        session.add(
            FeedbackReviewCaseSnapshotModel(
                review_case_snapshot_id=uuid7(),
                review_case_id=review_case_id,
                feedback_event_id=feedback_event_id,
                version=1,
                status="RECEIVED",
                priority=2,
                due_at=NOW + timedelta(days=2),
                assigned_reviewer_id=None,
                transition_reason="INITIAL_SUBMISSION",
                input_sha256="7" * 64,
                created_at=NOW,
            )
        )
        session.commit()

    for statement in (
        "update feedback_events set user_statement = 'rewritten' where feedback_event_id = :id",
        "delete from feedback_events where feedback_event_id = :id",
    ):
        with (
            pytest.raises(DBAPIError, match="immutable"),
            migrated_engine.begin() as connection,
        ):
            connection.execute(text(statement), {"id": feedback_event_id})

    with Session(migrated_engine) as session:
        persisted = session.get(FeedbackEventModel, feedback_event_id)
        assert persisted is not None
        assert persisted.user_statement == "合成反馈：解释缺少证据定位。"
        session.add(
            FeedbackReviewCaseSnapshotModel(
                review_case_snapshot_id=uuid7(),
                review_case_id=review_case_id,
                feedback_event_id=feedback_event_id,
                version=1,
                status="NEEDS_EVIDENCE",
                priority=2,
                due_at=NOW + timedelta(days=2),
                assigned_reviewer_id=None,
                transition_reason="MISSING_EVIDENCE",
                input_sha256="8" * 64,
                created_at=NOW,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
