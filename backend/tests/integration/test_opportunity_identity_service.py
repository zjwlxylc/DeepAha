from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid7

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.opportunities.identity import IdentityReplayError
from deepaha.opportunities.models import (
    Opportunity,
    OpportunityAlias,
    OpportunityEvent,
    OpportunityIdentityAction,
    OpportunityIdentityActionMember,
    OpportunityVersion,
)
from deepaha.opportunities.service import (
    OpportunityIdentityService,
    OpportunityResolutionService,
    load_resolution_index,
)

from .test_opportunity_resolution_service import (
    CLOCK_TIME,
    happy_path_commands,
    load_fixture_cases,
    seed_fixture_documents,
)

pytestmark = pytest.mark.integration
MERGE_SOURCE_ID = UUID("019b0000-0000-7000-8000-000000000061")
MERGE_TARGET_ID = UUID("019b0000-0000-7000-8000-000000000062")
SPLIT_PARENT_ID = UUID("019b0000-0000-7000-8000-000000000063")
CHILD_ONE_ID = UUID("019b0000-0000-7000-8000-000000000064")
CHILD_TWO_ID = UUID("019b0000-0000-7000-8000-000000000065")
ACTOR = "phase3-synthetic-test"
DOCUMENT_ID = UUID(str(load_fixture_cases()[0]["document_id"]))
EVIDENCE_REF_ID = UUID(str(load_fixture_cases()[0]["evidence_ref_id"]))
OTHER_DOCUMENT_ID = UUID(str(load_fixture_cases()[1]["document_id"]))
OTHER_EVIDENCE_REF_ID = UUID(str(load_fixture_cases()[1]["evidence_ref_id"]))


@dataclass(frozen=True)
class IdentityCounts:
    opportunities: int
    versions: int
    events: int
    public_ids: int
    identity_actions: int


@pytest.fixture
def identity_session_factory(migrated_engine: Engine) -> sessionmaker[Session]:
    factory = sessionmaker(migrated_engine, expire_on_commit=False)
    seed_fixture_documents(factory)
    resolver = OpportunityResolutionService(
        session_factory=factory,
        clock=lambda: CLOCK_TIME,
        id_factory=uuid7,
    )
    for command in happy_path_commands():
        resolver.resolve(command)

    with factory() as session:
        for index, opportunity_id in enumerate(
            (
                MERGE_SOURCE_ID,
                MERGE_TARGET_ID,
                SPLIT_PARENT_ID,
                CHILD_ONE_ID,
                CHILD_TWO_ID,
            ),
            start=1,
        ):
            session.add(
                Opportunity(
                    opportunity_id=opportunity_id,
                    public_id=f"opp_{index:032x}",
                    type="PUBLIC_INSTITUTION_JOB",
                    canonical_title=f"Synthetic identity opportunity {index}",
                    issuer_name="Synthetic Phase 3 Authority",
                    jurisdiction="Zhejiang",
                    current_version=None,
                    status="OPEN",
                    publication_status="INTERNAL",
                    created_at=CLOCK_TIME,
                    updated_at=CLOCK_TIME,
                )
            )
        session.flush()
        session.add_all(
            [
                OpportunityAlias(
                    alias_id=uuid7(),
                    opportunity_id=MERGE_SOURCE_ID,
                    alias_type="TITLE",
                    alias_value="Source alias",
                    normalized_value="source alias",
                    source_id=None,
                    source_document_id=DOCUMENT_ID,
                    source_evidence_ref_id=EVIDENCE_REF_ID,
                    created_at=CLOCK_TIME,
                ),
                OpportunityAlias(
                    alias_id=uuid7(),
                    opportunity_id=MERGE_TARGET_ID,
                    alias_type="TITLE",
                    alias_value="Target alias",
                    normalized_value="target alias",
                    source_id=None,
                    source_document_id=DOCUMENT_ID,
                    source_evidence_ref_id=EVIDENCE_REF_ID,
                    created_at=CLOCK_TIME,
                ),
            ]
        )
        session.commit()
    return factory


@pytest.fixture
def identity_service(
    identity_session_factory: sessionmaker[Session],
) -> OpportunityIdentityService:
    return OpportunityIdentityService(
        session_factory=identity_session_factory,
        clock=lambda: datetime(2026, 8, 22, 13, 0, tzinfo=UTC),
        id_factory=uuid7,
    )


def persisted_identity_counts(factory: sessionmaker[Session]) -> IdentityCounts:
    with factory() as session:
        return IdentityCounts(
            opportunities=session.scalar(select(func.count()).select_from(Opportunity)) or 0,
            versions=session.scalar(select(func.count()).select_from(OpportunityVersion)) or 0,
            events=session.scalar(select(func.count()).select_from(OpportunityEvent)) or 0,
            public_ids=session.scalar(select(func.count(func.distinct(Opportunity.public_id))))
            or 0,
            identity_actions=session.scalar(
                select(func.count()).select_from(OpportunityIdentityAction)
            )
            or 0,
        )


def merge(identity_service: OpportunityIdentityService) -> UUID:
    return identity_service.merge(
        target_id=MERGE_TARGET_ID,
        source_ids=(MERGE_SOURCE_ID,),
        document_id=DOCUMENT_ID,
        evidence_ref_id=EVIDENCE_REF_ID,
        actor=ACTOR,
        reason="synthetic duplicate correction",
    )


def test_merge_split_reversal_never_delete_public_ids_or_history(
    identity_service: OpportunityIdentityService,
    identity_session_factory: sessionmaker[Session],
) -> None:
    baseline = persisted_identity_counts(identity_session_factory)
    merge_id = merge(identity_service)
    identity_service.reverse_identity_action(
        action_id=merge_id,
        document_id=DOCUMENT_ID,
        evidence_ref_id=EVIDENCE_REF_ID,
        actor=ACTOR,
        reason="synthetic merge reversal",
    )
    split_id = identity_service.split(
        parent_id=SPLIT_PARENT_ID,
        child_ids=(CHILD_ONE_ID, CHILD_TWO_ID),
        document_id=DOCUMENT_ID,
        evidence_ref_id=EVIDENCE_REF_ID,
        actor=ACTOR,
        reason="synthetic composite opportunity correction",
    )
    identity_service.reverse_identity_action(
        action_id=split_id,
        document_id=DOCUMENT_ID,
        evidence_ref_id=EVIDENCE_REF_ID,
        actor=ACTOR,
        reason="synthetic split reversal",
    )

    after = persisted_identity_counts(identity_session_factory)
    assert after.opportunities == baseline.opportunities
    assert after.versions == baseline.versions
    assert after.events == baseline.events
    assert after.public_ids == baseline.public_ids
    assert after.identity_actions == 4


def test_merge_and_reversal_change_only_canonical_resolution(
    identity_service: OpportunityIdentityService,
    identity_session_factory: sessionmaker[Session],
) -> None:
    merge_id = merge(identity_service)

    assert identity_service.resolve_canonical_opportunity_id(MERGE_SOURCE_ID) == MERGE_TARGET_ID
    with identity_session_factory() as session:
        aliases = session.scalars(
            select(OpportunityAlias)
            .where(OpportunityAlias.opportunity_id.in_((MERGE_SOURCE_ID, MERGE_TARGET_ID)))
            .order_by(OpportunityAlias.normalized_value)
        ).all()
        assert [(item.opportunity_id, item.normalized_value) for item in aliases] == [
            (MERGE_SOURCE_ID, "source alias"),
            (MERGE_TARGET_ID, "target alias"),
        ]

    identity_service.reverse_identity_action(
        action_id=merge_id,
        document_id=DOCUMENT_ID,
        evidence_ref_id=EVIDENCE_REF_ID,
        actor=ACTOR,
        reason="synthetic merge reversal",
    )
    assert identity_service.resolve_canonical_opportunity_id(MERGE_SOURCE_ID) == MERGE_SOURCE_ID


def test_resolution_index_maps_merged_alias_owner_to_canonical_target(
    identity_service: OpportunityIdentityService,
    identity_session_factory: sessionmaker[Session],
) -> None:
    normalized_url = "https://phase3-identity.example.gov/source"
    with identity_session_factory() as session:
        session.add(
            OpportunityAlias(
                alias_id=uuid7(),
                opportunity_id=MERGE_SOURCE_ID,
                alias_type="URL",
                alias_value=normalized_url,
                normalized_value=normalized_url,
                source_id=None,
                source_document_id=DOCUMENT_ID,
                source_evidence_ref_id=EVIDENCE_REF_ID,
                created_at=CLOCK_TIME,
            )
        )
        session.commit()

    merge_id = merge(identity_service)
    with identity_session_factory() as session:
        merged_index = load_resolution_index(session)
    assert merged_index.url_keys[f"url:{normalized_url}"][0].opportunity_id == MERGE_TARGET_ID

    identity_service.reverse_identity_action(
        action_id=merge_id,
        document_id=DOCUMENT_ID,
        evidence_ref_id=EVIDENCE_REF_ID,
        actor=ACTOR,
        reason="synthetic merge reversal",
    )
    with identity_session_factory() as session:
        reversed_index = load_resolution_index(session)
    assert reversed_index.url_keys[f"url:{normalized_url}"][0].opportunity_id == MERGE_SOURCE_ID


def test_cycle_failure_is_atomic_and_does_not_append_an_action(
    identity_service: OpportunityIdentityService,
    identity_session_factory: sessionmaker[Session],
) -> None:
    merge(identity_service)

    with pytest.raises(IdentityReplayError, match="cycle"):
        identity_service.merge(
            target_id=MERGE_SOURCE_ID,
            source_ids=(MERGE_TARGET_ID,),
            document_id=DOCUMENT_ID,
            evidence_ref_id=EVIDENCE_REF_ID,
            actor=ACTOR,
            reason="synthetic invalid cycle",
        )

    assert persisted_identity_counts(identity_session_factory).identity_actions == 1


@pytest.mark.parametrize("field", ["actor", "reason"])
def test_actor_and_reason_are_required(
    identity_service: OpportunityIdentityService,
    identity_session_factory: sessionmaker[Session],
    field: str,
) -> None:
    arguments = {
        "target_id": MERGE_TARGET_ID,
        "source_ids": (MERGE_SOURCE_ID,),
        "document_id": DOCUMENT_ID,
        "evidence_ref_id": EVIDENCE_REF_ID,
        "actor": ACTOR,
        "reason": "synthetic duplicate correction",
    }
    arguments[field] = "  "

    with pytest.raises(ValueError, match=field):
        identity_service.merge(**arguments)  # type: ignore[arg-type]

    assert persisted_identity_counts(identity_session_factory).identity_actions == 0


def test_evidence_pair_and_members_must_exist(
    identity_service: OpportunityIdentityService,
    identity_session_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(ValueError, match="both be set"):
        identity_service.merge(
            target_id=MERGE_TARGET_ID,
            source_ids=(MERGE_SOURCE_ID,),
            document_id=DOCUMENT_ID,
            evidence_ref_id=None,
            actor=ACTOR,
            reason="synthetic invalid evidence pair",
        )
    with pytest.raises(ValueError, match="does not belong"):
        identity_service.merge(
            target_id=MERGE_TARGET_ID,
            source_ids=(MERGE_SOURCE_ID,),
            document_id=DOCUMENT_ID,
            evidence_ref_id=OTHER_EVIDENCE_REF_ID,
            actor=ACTOR,
            reason="synthetic mismatched evidence",
        )
    with pytest.raises(ValueError, match="does not exist"):
        identity_service.merge(
            target_id=MERGE_TARGET_ID,
            source_ids=(UUID("019b0000-0000-7000-8000-000000000099"),),
            document_id=OTHER_DOCUMENT_ID,
            evidence_ref_id=OTHER_EVIDENCE_REF_ID,
            actor=ACTOR,
            reason="synthetic missing source",
        )

    assert persisted_identity_counts(identity_session_factory).identity_actions == 0


def test_reversal_copies_members_and_cannot_repeat_or_target_a_reversal(
    identity_service: OpportunityIdentityService,
    identity_session_factory: sessionmaker[Session],
) -> None:
    original_id = merge(identity_service)
    reversal_id = identity_service.reverse_identity_action(
        action_id=original_id,
        document_id=DOCUMENT_ID,
        evidence_ref_id=EVIDENCE_REF_ID,
        actor=ACTOR,
        reason="synthetic merge reversal",
    )

    with identity_session_factory() as session:
        rows = session.execute(
            select(
                OpportunityIdentityActionMember.action_id,
                OpportunityIdentityActionMember.opportunity_id,
                OpportunityIdentityActionMember.role,
            ).order_by(
                OpportunityIdentityActionMember.action_id,
                OpportunityIdentityActionMember.opportunity_id,
            )
        ).all()
    original_members = {
        (row.opportunity_id, row.role) for row in rows if row.action_id == original_id
    }
    reversal_members = {
        (row.opportunity_id, row.role) for row in rows if row.action_id == reversal_id
    }
    assert reversal_members == original_members

    with pytest.raises(IdentityReplayError, match="already reversed"):
        identity_service.reverse_identity_action(
            action_id=original_id,
            document_id=DOCUMENT_ID,
            evidence_ref_id=EVIDENCE_REF_ID,
            actor=ACTOR,
            reason="synthetic duplicate reversal",
        )
    with pytest.raises(IdentityReplayError, match="reversal of a reversal"):
        identity_service.reverse_identity_action(
            action_id=reversal_id,
            document_id=DOCUMENT_ID,
            evidence_ref_id=EVIDENCE_REF_ID,
            actor=ACTOR,
            reason="synthetic reversal of reversal",
        )

    assert persisted_identity_counts(identity_session_factory).identity_actions == 2


def test_database_reload_replay_is_deterministic(
    identity_service: OpportunityIdentityService,
) -> None:
    merge(identity_service)
    identity_service.split(
        parent_id=SPLIT_PARENT_ID,
        child_ids=(CHILD_TWO_ID, CHILD_ONE_ID),
        document_id=DOCUMENT_ID,
        evidence_ref_id=EVIDENCE_REF_ID,
        actor=ACTOR,
        reason="synthetic deterministic split",
    )

    first = identity_service.load_identity_state()
    second = identity_service.load_identity_state()

    assert first == second
    assert first.split_children_by_parent[SPLIT_PARENT_ID] == (
        CHILD_ONE_ID,
        CHILD_TWO_ID,
    )
