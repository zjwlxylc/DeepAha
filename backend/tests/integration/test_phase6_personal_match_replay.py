from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid7

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.contracts.phase4 import EligibilityStatus, RuleField
from deepaha.eligibility.service import EligibilityService, MatchInput, MatchInputError
from deepaha.matching.models import MatchSnapshotModel
from deepaha.opportunities.models import Opportunity, OpportunityVersion
from deepaha.personal.auth import Principal
from deepaha.personal.matching import PersonalMatchError, PersonalMatchService
from deepaha.personal.models import (
    PersonalRankingItemModel,
    PersonalRankingSnapshotModel,
)
from deepaha.personal.profile import ProfileService
from deepaha.rules.major import load_approved_major_mapping, load_major_catalog
from deepaha.rules.models import RuleEvidenceModel, RuleModel, RuleSetModel
from tests.integration.test_phase4_persistence_contract import persist_phase4_inputs
from tests.integration.test_phase6_profile_persistence import (
    USER_A_ID,
    profile_command,
    seed_users,
)
from tests.public_catalog.support import persist_phase5_fixture, stable_uuid7

pytestmark = pytest.mark.integration
FIXTURE_DIRECTORY = Path(__file__).parents[1] / "fixtures" / "evaluation"
NOW = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)


def persist_public_rule_sets(session: Session) -> None:
    opportunities = session.scalars(
        select(Opportunity)
        .where(Opportunity.status.in_(("OPEN", "CLOSING_SOON")))
        .order_by(Opportunity.public_id)
    ).all()
    for opportunity in opportunities:
        assert opportunity.current_version is not None
        version = session.get(
            OpportunityVersion,
            (opportunity.opportunity_id, opportunity.current_version),
        )
        assert version is not None
        rule_set_id = stable_uuid7(f"phase6:{opportunity.public_id}:rule-set")
        rule_id = stable_uuid7(f"phase6:{opportunity.public_id}:education-rule")
        session.add(
            RuleSetModel(
                rule_set_id=rule_set_id,
                version=1,
                opportunity_id=opportunity.opportunity_id,
                opportunity_version=version.version,
                root_rule_ids=[str(rule_id)],
                review_status="APPROVED",
                rule_schema_version="0.4.0",
                created_at=NOW,
            )
        )
        session.flush()
        session.add(
            RuleModel(
                rule_set_id=rule_set_id,
                rule_set_version=1,
                rule_id=rule_id,
                code="phase6-education-bachelor",
                operator="EQ",
                field="education_level",
                value_type="STRING",
                value="BACHELOR",
                operand_rule_ids=[],
                required=True,
                reason_template="合成夹具：学历为本科。",
            )
        )
        session.flush()
        session.add(
            RuleEvidenceModel(
                rule_set_id=rule_set_id,
                rule_set_version=1,
                rule_id=rule_id,
                evidence_ref_id=version.source_evidence_ref_id,
                document_id=version.source_document_id,
                authority="ORIGINAL_OFFICIAL_NOTICE",
                precedence=400,
                relation="SUPPORTS",
                effective_at=NOW,
                assertion_sha256=version.content_sha256,
            )
        )
        session.flush()


def test_personal_entry_accepts_v05_profile_without_weakening_phase4_boundary(
    migrated_engine: Engine,
) -> None:
    seed_users(migrated_engine)
    factory = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    state = ProfileService(
        session_factory=factory,
        id_factory=uuid7,
        now_factory=lambda: NOW,
    ).save(
        Principal(user_id=USER_A_ID),
        profile_command(),
        idempotency_key="personal-match-profile-0001",
    )
    with Session(migrated_engine) as session:
        rule_set, _, _, _ = persist_phase4_inputs(session)
        rule_set_identity = (
            rule_set.opportunity_id,
            rule_set.opportunity_version,
            rule_set.rule_set_id,
            rule_set.version,
        )
        session.commit()

    catalog = load_major_catalog(FIXTURE_DIRECTORY / "phase4-major-catalog.json")
    mapping = load_approved_major_mapping(
        FIXTURE_DIRECTORY / "phase4-major-mapping.json",
        catalog,
    )
    opportunity_id, opportunity_version, rule_set_id, rule_set_version = rule_set_identity
    match_input = MatchInput(
        opportunity_id=opportunity_id,
        opportunity_version=opportunity_version,
        rule_set_id=rule_set_id,
        rule_set_version=rule_set_version,
        profile_snapshot_id=state.qualification_profile_snapshot_id,
        major_catalog=catalog,
        major_mapping=mapping,
        evaluated_at=NOW,
        created_at=NOW,
    )
    service = EligibilityService(session_factory=factory, id_factory=uuid7)

    with pytest.raises(MatchInputError, match="synthetic ProfileSnapshot only"):
        service.evaluate_and_save(match_input)

    first = service.evaluate_personal_and_save(match_input)
    replay = service.evaluate_personal_and_save(match_input)

    assert replay == first
    assert first.profile_snapshot_id == state.qualification_profile_snapshot_id
    assert first.profile_version == state.qualification_profile_version
    assert first.scenario_clock == state.scenario_clock
    assert service.replay(first.snapshot_id) == first

    missing_attributes = profile_command().attributes.model_dump(mode="json") | {
        "education_level": None
    }
    missing_state = ProfileService(
        session_factory=factory,
        id_factory=uuid7,
        now_factory=lambda: NOW,
    ).save(
        Principal(user_id=UUID("019b0000-0000-7000-8000-000000000502")),
        profile_command(
            attributes=missing_attributes,
            skipped_fields=[
                "birth_date",
                "certificates",
                "education_level",
                "hukou_region",
                "target_regions",
            ],
        ),
        idempotency_key="personal-match-profile-unknown-0001",
    )
    missing_input = MatchInput(
        opportunity_id=opportunity_id,
        opportunity_version=opportunity_version,
        rule_set_id=rule_set_id,
        rule_set_version=rule_set_version,
        profile_snapshot_id=missing_state.qualification_profile_snapshot_id,
        major_catalog=catalog,
        major_mapping=mapping,
        evaluated_at=NOW,
        created_at=NOW,
    )
    missing = service.evaluate_personal_and_save(missing_input)

    assert missing.eligibility_result.status is EligibilityStatus.UNCERTAIN
    assert missing.eligibility_result.missing_fields == (RuleField.EDUCATION_LEVEL,)


def test_personal_ranking_is_owner_scoped_replayable_and_preference_only(
    migrated_engine: Engine,
) -> None:
    seed_users(migrated_engine)
    with Session(migrated_engine) as session:
        persist_phase5_fixture(session)
        persist_public_rule_sets(session)
        session.commit()
    factory = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    profile_service = ProfileService(
        session_factory=factory,
        id_factory=uuid7,
        now_factory=lambda: NOW,
    )
    principal = Principal(user_id=USER_A_ID)
    first_state = profile_service.save(
        principal,
        profile_command(),
        idempotency_key="personal-ranking-profile-0001",
    )
    catalog = load_major_catalog(FIXTURE_DIRECTORY / "phase4-major-catalog.json")
    mapping = load_approved_major_mapping(
        FIXTURE_DIRECTORY / "phase4-major-mapping.json",
        catalog,
    )
    eligibility_service = EligibilityService(session_factory=factory, id_factory=uuid7)
    service = PersonalMatchService(
        session_factory=factory,
        profile_service=profile_service,
        eligibility_service=eligibility_service,
        major_catalog=catalog,
        major_mapping=mapping,
        id_factory=uuid7,
        now_factory=lambda: NOW,
    )

    first = service.run(principal)
    replay = service.run(principal)

    assert replay == first
    assert len(first.items) == 2
    assert first.qualification_profile_snapshot_id == (
        first_state.qualification_profile_snapshot_id
    )
    first_match_ids = {item.opportunity_id: item.match_snapshot_id for item in first.items}
    with Session(migrated_engine) as session:
        first_public_id = session.scalar(
            select(Opportunity.public_id).where(
                Opportunity.opportunity_id == first.items[0].opportunity_id
            )
        )
    assert first_public_id is not None
    assert service.get_match(principal, first_public_id) == eligibility_service.replay(
        first.items[0].match_snapshot_id
    )

    second_state = profile_service.save(
        principal,
        profile_command(
            preference_regions=["合成宁波市"],
            preference_types=["STATE_OWNED_ENTERPRISE_JOB"],
        ),
        idempotency_key="personal-ranking-profile-0002",
    )
    second = service.run(principal)

    assert second.ranking_snapshot_id != first.ranking_snapshot_id
    assert second_state.qualification_profile_snapshot_id == (
        first_state.qualification_profile_snapshot_id
    )
    assert [item.opportunity_id for item in second.items] == list(
        reversed([item.opportunity_id for item in first.items])
    )
    assert {item.opportunity_id: item.match_snapshot_id for item in second.items} == first_match_ids
    assert service.get_latest(Principal(user_id=USER_A_ID)) == second
    principal_b = Principal(user_id=UUID("019b0000-0000-7000-8000-000000000502"))
    assert service.get_snapshot(principal, first.ranking_snapshot_id) == first
    assert service.get_snapshot(principal_b, first.ranking_snapshot_id) is None
    assert service.get_match(principal_b, first_public_id) is None
    assert service.get_match(principal, "opp_00000000000000000000000000000000") is None
    assert service.get_snapshot(principal, uuid7()) is None
    assert service.get_latest(principal_b) is None

    profile_service.save(
        principal,
        profile_command(allowed_purposes=["ACTION_TRACKING"]),
        idempotency_key="personal-ranking-purpose-revoked-0001",
    )
    with pytest.raises(PersonalMatchError, match="personal matching unavailable"):
        service.run(principal)
    assert service.get_latest(principal) is None
    assert service.get_snapshot(principal, first.ranking_snapshot_id) is None
    assert service.get_match(principal, first_public_id) is None

    with Session(migrated_engine) as session:
        assert session.scalar(select(func.count()).select_from(MatchSnapshotModel)) == 2
        assert session.scalar(select(func.count()).select_from(PersonalRankingSnapshotModel)) == 2
        assert session.scalar(select(func.count()).select_from(PersonalRankingItemModel)) == 4


def test_public_candidate_without_exact_ruleset_is_explicitly_omitted(
    migrated_engine: Engine,
) -> None:
    seed_users(migrated_engine)
    with Session(migrated_engine) as session:
        persist_phase5_fixture(session)
        session.commit()
    factory = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    profile_service = ProfileService(
        session_factory=factory,
        id_factory=uuid7,
        now_factory=lambda: NOW,
    )
    principal = Principal(user_id=USER_A_ID)
    profile_service.save(
        principal,
        profile_command(),
        idempotency_key="personal-ranking-no-rules-profile-0001",
    )
    catalog = load_major_catalog(FIXTURE_DIRECTORY / "phase4-major-catalog.json")
    mapping = load_approved_major_mapping(
        FIXTURE_DIRECTORY / "phase4-major-mapping.json",
        catalog,
    )
    service = PersonalMatchService(
        session_factory=factory,
        profile_service=profile_service,
        eligibility_service=EligibilityService(session_factory=factory, id_factory=uuid7),
        major_catalog=catalog,
        major_mapping=mapping,
        id_factory=uuid7,
        now_factory=lambda: NOW,
    )

    ranking = service.run(principal)

    assert ranking.items == ()
    assert ranking.omitted_rule_set_count == 2
    with Session(migrated_engine) as session:
        assert session.scalar(select(func.count()).select_from(MatchSnapshotModel)) == 0
