from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from threading import Barrier
from uuid import UUID, uuid7

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.contracts.phase3 import ApplicationWindowSchema, OpportunityDocumentRole
from deepaha.documents.models import EvidenceRef
from deepaha.eligibility.models import EligibilityResultModel
from deepaha.matching.models import MatchSnapshotModel
from deepaha.notifications.candidates import (
    DeadlineReminderCandidateService,
    recognize_deadline_change,
)
from deepaha.notifications.models import (
    NotificationOutboxModel,
    ReminderPreferenceSnapshotModel,
)
from deepaha.opportunities.models import Opportunity, OpportunityEvent, OpportunityVersion
from deepaha.opportunities.service import OpportunityResolutionService
from deepaha.opportunities.types import OpportunityPatch, ResolutionDocument
from deepaha.personal.models import (
    PersonalActionSnapshotModel,
    PersonalRankingItemModel,
    PersonalRankingSnapshotModel,
    PersonalUserModel,
    UserStateSnapshotModel,
)
from deepaha.profiles.models import ProfileSnapshotModel
from deepaha.rules.models import RuleEvidenceModel, RuleModel, RuleSetModel
from tests.integration.test_opportunity_resolution_service import (
    CLOCK_TIME,
    PUBLIC_ID,
    commands_by_id,
    seed_fixture_documents,
)

pytestmark = pytest.mark.integration
SCENARIO_DAY = date(2026, 8, 22)
PRE_EVENT_TIME = CLOCK_TIME - timedelta(minutes=10)
USER_IDS = {
    "eligible": UUID("019b0000-0000-7000-8000-000000000831"),
    "disabled": UUID("019b0000-0000-7000-8000-000000000832"),
    "unsaved": UUID("019b0000-0000-7000-8000-000000000833"),
    "ranked_only": UUID("019b0000-0000-7000-8000-000000000834"),
    "revoked": UUID("019b0000-0000-7000-8000-000000000835"),
}


@dataclass(frozen=True, slots=True)
class AudienceBindings:
    eligible_action_snapshot_id: UUID
    eligible_preference_snapshot_id: UUID
    eligible_preference_id: UUID
    eligible_user_state_snapshot_id: UUID


def _initial_deadline_command() -> ResolutionDocument:
    evidence_command = commands_by_id()["cancellation"]
    return replace(
        evidence_command,
        role=OpportunityDocumentRole.DEADLINE_EXTENSION,
        effective_at=datetime(2026, 8, 22, 9, 4, 30, tzinfo=UTC),
        facts=OpportunityPatch(
            application_window=ApplicationWindowSchema(
                opens_on=date(2026, 8, 22),
                closes_on=date(2026, 9, 20),
                timezone="Asia/Shanghai",
            )
        ),
    )


def _prepare_pre_deadline_service(
    factory: sessionmaker[Session],
    *,
    candidate_service: DeadlineReminderCandidateService | None = None,
) -> tuple[OpportunityResolutionService, Opportunity]:
    seed_fixture_documents(factory)
    service = OpportunityResolutionService(
        session_factory=factory,
        clock=lambda: CLOCK_TIME,
        id_factory=uuid7,
        candidate_service=candidate_service,
    )
    commands = commands_by_id()
    for name in ("primary", "attachment", "position_table", "correction"):
        service.resolve(commands[name])
    service.resolve(_initial_deadline_command())
    with factory() as session:
        opportunity = session.scalar(select(Opportunity).where(Opportunity.public_id == PUBLIC_ID))
        assert opportunity is not None
        session.expunge(opportunity)
    return service, opportunity


def _state(
    *,
    user_id: UUID,
    user_state_id: UUID,
    profile: ProfileSnapshotModel,
    version: int,
    allowed_purposes: list[str],
    created_at: datetime,
    digest_character: str,
) -> UserStateSnapshotModel:
    return UserStateSnapshotModel(
        user_state_snapshot_id=uuid7(),
        user_state_id=user_state_id,
        user_id=user_id,
        version=version,
        qualification_profile_snapshot_id=profile.profile_snapshot_id,
        qualification_profile_version=profile.version,
        life_stage="EARLY_CAREER",
        goal_types=["PUBLIC_SERVICE_EMPLOYMENT"],
        preference_regions=[],
        preference_types=[],
        skipped_fields=[],
        personalization_enabled=True,
        consent_version="phase6-consent-v1",
        allowed_purposes=allowed_purposes,
        scenario_clock=SCENARIO_DAY,
        input_sha256=digest_character * 64,
        created_at=created_at,
    )


def _action(
    *,
    user_id: UUID,
    opportunity: Opportunity,
    action_id: UUID,
    version: int,
    saved: bool,
    created_at: datetime,
    digest_character: str,
) -> PersonalActionSnapshotModel:
    assert opportunity.current_version is not None
    return PersonalActionSnapshotModel(
        action_snapshot_id=uuid7(),
        action_id=action_id,
        user_id=user_id,
        version=version,
        opportunity_id=opportunity.opportunity_id,
        opportunity_version=opportunity.current_version,
        saved=saved,
        state="NOT_STARTED",
        material_items=[],
        last_event_id=uuid7(),
        input_sha256=digest_character * 64,
        created_at=created_at,
    )


def _preference(
    *,
    user_id: UUID,
    preference_id: UUID,
    version: int,
    enabled: bool,
    predecessor_snapshot_id: UUID | None,
    created_at: datetime,
) -> ReminderPreferenceSnapshotModel:
    return ReminderPreferenceSnapshotModel(
        preference_snapshot_id=uuid7(),
        preference_id=preference_id,
        user_id=user_id,
        version=version,
        predecessor_snapshot_id=predecessor_snapshot_id,
        reminder_kind="DEADLINE_CHANGED",
        enabled=enabled,
        cadence="AS_SOON_AS_GOVERNED",
        target="TEST_INBOX",
        actor_user_id=user_id,
        preference_policy_version="phase8-deadline-reminder-v1",
        contract_version="0.7.0",
        created_at=created_at,
    )


def _seed_ranked_only_evidence(
    session: Session,
    *,
    opportunity: Opportunity,
    profile: ProfileSnapshotModel,
    state: UserStateSnapshotModel,
) -> None:
    assert opportunity.current_version is not None
    version = session.get(
        OpportunityVersion,
        (opportunity.opportunity_id, opportunity.current_version),
    )
    assert version is not None
    evidence = session.get(EvidenceRef, version.source_evidence_ref_id)
    assert evidence is not None
    rule_set_id = uuid7()
    rule_id = uuid7()
    rule_set = RuleSetModel(
        rule_set_id=rule_set_id,
        version=1,
        opportunity_id=opportunity.opportunity_id,
        opportunity_version=version.version,
        root_rule_ids=[str(rule_id)],
        review_status="APPROVED",
        rule_schema_version="0.4.0",
        created_at=PRE_EVENT_TIME,
    )
    rule = RuleModel(
        rule_set_id=rule_set_id,
        rule_set_version=1,
        rule_id=rule_id,
        code="phase8-ranked-only-evidence",
        operator="EXISTS",
        field="education_level",
        value_type=None,
        value=None,
        operand_rule_ids=[],
        required=True,
        reason_template="Synthetic ranked-only counterexample.",
    )
    session.add(rule_set)
    session.flush()
    session.add(rule)
    session.flush()
    session.add(
        RuleEvidenceModel(
            rule_set_id=rule_set_id,
            rule_set_version=1,
            rule_id=rule_id,
            evidence_ref_id=evidence.evidence_ref_id,
            document_id=evidence.document_id,
            authority="ORIGINAL_OFFICIAL_NOTICE",
            precedence=400,
            relation="SUPPORTS",
            effective_at=PRE_EVENT_TIME,
            assertion_sha256=version.content_sha256,
        )
    )
    session.flush()
    result = EligibilityResultModel(
        result_id=uuid7(),
        opportunity_id=opportunity.opportunity_id,
        opportunity_version=version.version,
        rule_set_id=rule_set_id,
        rule_set_version=1,
        profile_snapshot_id=profile.profile_snapshot_id,
        status="ELIGIBLE",
        rule_results=[
            {
                "rule_id": str(rule_id),
                "outcome": "SATISFIED",
                "deterministic": True,
                "official_evidence": True,
                "reason_code": "RULE_SATISFIED",
                "evidence_ref_ids": [str(evidence.evidence_ref_id)],
                "missing_fields": [],
            }
        ],
        satisfied_rule_ids=[str(rule_id)],
        conflict_rule_ids=[],
        unknown_rule_ids=[],
        missing_fields=[],
        review_reasons=[],
        evaluated_at=PRE_EVENT_TIME,
        engine_version="phase8-ranked-only-engine-v1",
    )
    session.add(result)
    session.flush()
    match = MatchSnapshotModel(
        snapshot_id=uuid7(),
        eligibility_result_id=result.result_id,
        opportunity_id=opportunity.opportunity_id,
        opportunity_version=version.version,
        rule_set_id=rule_set_id,
        rule_set_version=1,
        profile_snapshot_id=profile.profile_snapshot_id,
        profile_version=profile.version,
        compiler_version="phase8-ranked-only-compiler-v1",
        engine_version="phase8-ranked-only-engine-v1",
        major_catalog_version="phase8-ranked-only-catalog-v1",
        major_mapping_version="phase8-ranked-only-mapping-v1",
        scenario_clock=SCENARIO_DAY,
        input_sha256="d" * 64,
        created_at=PRE_EVENT_TIME,
    )
    session.add(match)
    session.flush()
    ranking = PersonalRankingSnapshotModel(
        ranking_snapshot_id=uuid7(),
        user_id=USER_IDS["ranked_only"],
        user_state_snapshot_id=state.user_state_snapshot_id,
        qualification_profile_snapshot_id=profile.profile_snapshot_id,
        qualification_profile_version=profile.version,
        scenario_clock=SCENARIO_DAY,
        window_end=SCENARIO_DAY + timedelta(days=90),
        ranker_version="phase8-ranked-only-ranker-v1",
        input_sha256="e" * 64,
        omitted_rule_set_count=0,
        created_at=PRE_EVENT_TIME,
    )
    session.add(ranking)
    session.flush()
    application_window = version.snapshot["application_window"]
    assert isinstance(application_window, dict)
    raw_closes_on = application_window["closes_on"]
    assert isinstance(raw_closes_on, str)
    closes_on = date.fromisoformat(raw_closes_on)
    session.add(
        PersonalRankingItemModel(
            ranking_snapshot_id=ranking.ranking_snapshot_id,
            ordinal=1,
            user_id=USER_IDS["ranked_only"],
            opportunity_id=opportunity.opportunity_id,
            opportunity_version=version.version,
            match_snapshot_id=match.snapshot_id,
            eligibility_status="ELIGIBLE",
            reason_codes=["SYNTHETIC_RANKED_ONLY"],
            deadline=closes_on,
        )
    )
    session.flush()


def _seed_audience(
    factory: sessionmaker[Session],
    opportunity: Opportunity,
    *,
    eligible_enabled: bool = True,
) -> AudienceBindings:
    with factory() as session:
        profile = ProfileSnapshotModel(
            profile_snapshot_id=uuid7(),
            profile_id=uuid7(),
            version=1,
            synthetic=True,
            persona_family_id=None,
            attributes={"education_level": "BACHELOR"},
            scenario_clock=SCENARIO_DAY,
            profile_schema_version="0.4.0",
            created_at=PRE_EVENT_TIME,
            created_by="phase8-candidate-test",
            reviewed_by="phase8-candidate-test",
            change_note="Synthetic Phase 8 audience counterexamples.",
        )
        session.add(profile)
        session.flush()
        states: dict[str, UserStateSnapshotModel] = {}
        for index, (role, user_id) in enumerate(USER_IDS.items(), start=1):
            user_state_id = uuid7()
            session.add(
                PersonalUserModel(
                    user_id=user_id,
                    user_state_id=user_state_id,
                    active=True,
                    created_at=PRE_EVENT_TIME,
                )
            )
            session.flush()
            state = _state(
                user_id=user_id,
                user_state_id=user_state_id,
                profile=profile,
                version=1,
                allowed_purposes=["ACTION_TRACKING"],
                created_at=PRE_EVENT_TIME,
                digest_character=f"{index:x}",
            )
            session.add(state)
            session.flush()
            if role == "revoked":
                state = _state(
                    user_id=user_id,
                    user_state_id=user_state_id,
                    profile=profile,
                    version=2,
                    allowed_purposes=["ELIGIBILITY"],
                    created_at=PRE_EVENT_TIME + timedelta(minutes=1),
                    digest_character="a",
                )
                session.add(state)
                session.flush()
            states[role] = state

        actions: dict[str, PersonalActionSnapshotModel] = {}
        for index, role in enumerate(("eligible", "disabled", "unsaved", "revoked"), start=1):
            action_id = uuid7()
            action = _action(
                user_id=USER_IDS[role],
                opportunity=opportunity,
                action_id=action_id,
                version=1,
                saved=True,
                created_at=PRE_EVENT_TIME,
                digest_character=f"{index + 4:x}",
            )
            session.add(action)
            session.flush()
            if role == "unsaved":
                action = _action(
                    user_id=USER_IDS[role],
                    opportunity=opportunity,
                    action_id=action_id,
                    version=2,
                    saved=False,
                    created_at=PRE_EVENT_TIME + timedelta(minutes=1),
                    digest_character="b",
                )
                session.add(action)
                session.flush()
            actions[role] = action

        preferences: dict[str, ReminderPreferenceSnapshotModel] = {}
        for role in USER_IDS:
            preference_id = uuid7()
            enabled = eligible_enabled if role == "eligible" else True
            preference = _preference(
                user_id=USER_IDS[role],
                preference_id=preference_id,
                version=1,
                enabled=enabled,
                predecessor_snapshot_id=None,
                created_at=PRE_EVENT_TIME,
            )
            session.add(preference)
            session.flush()
            if role == "disabled":
                preference = _preference(
                    user_id=USER_IDS[role],
                    preference_id=preference_id,
                    version=2,
                    enabled=False,
                    predecessor_snapshot_id=preference.preference_snapshot_id,
                    created_at=PRE_EVENT_TIME + timedelta(minutes=1),
                )
                session.add(preference)
                session.flush()
            preferences[role] = preference

        _seed_ranked_only_evidence(
            session,
            opportunity=opportunity,
            profile=profile,
            state=states["ranked_only"],
        )
        session.commit()
        return AudienceBindings(
            eligible_action_snapshot_id=actions["eligible"].action_snapshot_id,
            eligible_preference_snapshot_id=preferences["eligible"].preference_snapshot_id,
            eligible_preference_id=preferences["eligible"].preference_id,
            eligible_user_state_snapshot_id=states["eligible"].user_state_snapshot_id,
        )


def _factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_only_saved_enabled_authorized_user_gets_event_time_candidate(
    migrated_engine: Engine,
) -> None:
    factory = _factory(migrated_engine)
    service, opportunity = _prepare_pre_deadline_service(factory)
    bindings = _seed_audience(factory, opportunity)

    result = service.resolve(commands_by_id()["deadline_extension"])

    assert result.event_type == "DEADLINE_CHANGED"
    with factory() as session:
        outboxes = session.scalars(select(NotificationOutboxModel)).all()
        event = session.scalar(
            select(OpportunityEvent).where(
                OpportunityEvent.opportunity_id == opportunity.opportunity_id,
                OpportunityEvent.to_version == result.version,
            )
        )
        assert event is not None
        replay_ids = DeadlineReminderCandidateService().capture_for_event(
            session,
            event,
            created_at=event.detected_at,
        )
        session.flush()

    assert len(outboxes) == 1
    outbox = outboxes[0]
    assert replay_ids == (outbox.reminder_id,)
    assert outbox.user_id == USER_IDS["eligible"]
    assert outbox.action_snapshot_id == bindings.eligible_action_snapshot_id
    assert outbox.preference_snapshot_id == bindings.eligible_preference_snapshot_id
    assert outbox.user_state_snapshot_id == bindings.eligible_user_state_snapshot_id
    assert outbox.old_closes_on == date(2026, 9, 20)
    assert outbox.new_closes_on == date(2026, 9, 30)
    assert outbox.direction == "EXTENDED"
    assert outbox.status == "WAITING_GOVERNANCE"
    assert outbox.attempt_count == 0
    assert outbox.available_at is None


def test_later_enable_does_not_retroactively_capture_event(migrated_engine: Engine) -> None:
    factory = _factory(migrated_engine)
    service, opportunity = _prepare_pre_deadline_service(factory)
    bindings = _seed_audience(factory, opportunity, eligible_enabled=False)
    result = service.resolve(commands_by_id()["deadline_extension"])
    assert result.version is not None

    with factory() as session:
        event = session.scalar(
            select(OpportunityEvent).where(
                OpportunityEvent.opportunity_id == opportunity.opportunity_id,
                OpportunityEvent.to_version == result.version,
            )
        )
        assert event is not None
        enabled_later = _preference(
            user_id=USER_IDS["eligible"],
            preference_id=bindings.eligible_preference_id,
            version=2,
            enabled=True,
            predecessor_snapshot_id=bindings.eligible_preference_snapshot_id,
            created_at=event.detected_at + timedelta(seconds=1),
        )
        session.add(enabled_later)
        session.commit()

    with factory() as session:
        event = session.scalar(
            select(OpportunityEvent).where(
                OpportunityEvent.opportunity_id == opportunity.opportunity_id,
                OpportunityEvent.to_version == result.version,
            )
        )
        assert event is not None
        captured = DeadlineReminderCandidateService().capture_for_event(
            session,
            event,
            created_at=event.detected_at + timedelta(seconds=2),
        )
        session.flush()
        count = session.scalar(select(func.count()).select_from(NotificationOutboxModel))

    assert captured == ()
    assert count == 0


def test_concurrent_resolution_keeps_one_event_and_one_candidate(
    migrated_engine: Engine,
) -> None:
    factory = _factory(migrated_engine)
    service, opportunity = _prepare_pre_deadline_service(factory)
    _seed_audience(factory, opportunity)
    command = commands_by_id()["deadline_extension"]
    barrier = Barrier(2)

    def resolve_once() -> object:
        barrier.wait()
        return service.resolve(command)

    results: list[object] = []
    failures: list[Exception] = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(resolve_once) for _ in range(2)]
        for future in futures:
            try:
                results.append(future.result())
            except Exception as error:
                failures.append(error)

    with factory() as session:
        event_count = session.scalar(
            select(func.count())
            .select_from(OpportunityEvent)
            .where(
                OpportunityEvent.opportunity_id == opportunity.opportunity_id,
                OpportunityEvent.event_type == "DEADLINE_CHANGED",
                OpportunityEvent.source_document_id == command.document_id,
            )
        )
        outbox_count = session.scalar(select(func.count()).select_from(NotificationOutboxModel))

    assert results
    assert len(results) + len(failures) == 2
    assert event_count == 1
    assert outbox_count == 1


class FailingDeadlineCandidateService(DeadlineReminderCandidateService):
    def capture_for_event(
        self,
        session: Session,
        event: OpportunityEvent,
        *,
        created_at: datetime,
    ) -> tuple[UUID, ...]:
        del session, created_at
        if recognize_deadline_change(event) is not None:
            raise RuntimeError("injected candidate failure")
        return ()


def test_candidate_failure_rolls_back_version_event_projection_and_outbox(
    migrated_engine: Engine,
) -> None:
    factory = _factory(migrated_engine)
    service, opportunity = _prepare_pre_deadline_service(
        factory,
        candidate_service=FailingDeadlineCandidateService(),
    )
    _seed_audience(factory, opportunity)
    with factory() as session:
        current = session.get(Opportunity, opportunity.opportunity_id)
        assert current is not None
        before = (
            session.scalar(select(func.count()).select_from(OpportunityVersion)),
            session.scalar(select(func.count()).select_from(OpportunityEvent)),
            current.current_version,
        )

    with pytest.raises(RuntimeError, match="injected candidate failure"):
        service.resolve(commands_by_id()["deadline_extension"])

    with factory() as session:
        current = session.get(Opportunity, opportunity.opportunity_id)
        assert current is not None
        after = (
            session.scalar(select(func.count()).select_from(OpportunityVersion)),
            session.scalar(select(func.count()).select_from(OpportunityEvent)),
            current.current_version,
        )
        outbox_count = session.scalar(select(func.count()).select_from(NotificationOutboxModel))

    assert after == before
    assert outbox_count == 0
