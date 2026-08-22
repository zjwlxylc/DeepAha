import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid7

from sqlalchemy import Table, select
from sqlalchemy.orm import Session

from deepaha.eligibility.models import EligibilityResultModel
from deepaha.matching.models import MatchSnapshotModel
from deepaha.opportunities.models import Opportunity, OpportunityVersion
from deepaha.personal.auth import token_digest
from deepaha.personal.models import (
    PersonalAuthSessionModel,
    PersonalRankingItemModel,
    PersonalRankingSnapshotModel,
    PersonalUserModel,
    UserStateSnapshotModel,
)
from deepaha.rules.models import RuleSetModel
from tests.integration.test_phase4_persistence_contract import persist_complete_phase4_graph

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
EXPIRES_AT = datetime(2099, 1, 1, tzinfo=UTC)
TOKEN_A = "phase7-personal-token-owner-a"
TOKEN_B = "phase7-personal-token-owner-b"


@dataclass(frozen=True, slots=True)
class FeedbackOwnerFixture:
    user_id: UUID
    token: str
    ranking_snapshot_id: UUID
    match_snapshot_id: UUID
    opportunity_public_id: str
    opportunity_version: int
    user_state_version: int
    evidence_ref_id: UUID


def _owner_id(index: int) -> UUID:
    return UUID(f"019b0000-0000-7000-8000-{720 + index:012d}")


def persist_feedback_prerequisites(
    session: Session,
) -> tuple[FeedbackOwnerFixture, FeedbackOwnerFixture]:
    rule_set, profile, match, _ = persist_complete_phase4_graph(session)
    opportunity = session.get(Opportunity, match.opportunity_id)
    version = session.get(
        OpportunityVersion,
        (match.opportunity_id, match.opportunity_version),
    )
    if opportunity is None or version is None:
        raise ValueError("feedback fixture opportunity graph is incomplete")
    fixtures: list[FeedbackOwnerFixture] = []
    for index, token in enumerate((TOKEN_A, TOKEN_B), start=1):
        user_id = _owner_id(index)
        user_state_id = _owner_id(index + 10)
        session.add(
            PersonalUserModel(
                user_id=user_id,
                user_state_id=user_state_id,
                active=True,
                created_at=NOW,
            )
        )
        session.flush()
        session.add(
            PersonalAuthSessionModel(
                token_sha256=token_digest(token),
                user_id=user_id,
                expires_at=EXPIRES_AT,
                revoked_at=None,
                created_at=NOW,
            )
        )
        state = UserStateSnapshotModel(
            user_state_snapshot_id=uuid7(),
            user_state_id=user_state_id,
            user_id=user_id,
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
            input_sha256=sha256(f"phase7-state-{index}".encode()).hexdigest(),
            created_at=NOW,
        )
        session.add(state)
        session.flush()
        ranking = PersonalRankingSnapshotModel(
            ranking_snapshot_id=uuid7(),
            user_id=user_id,
            user_state_snapshot_id=state.user_state_snapshot_id,
            qualification_profile_snapshot_id=profile.profile_snapshot_id,
            qualification_profile_version=profile.version,
            scenario_clock=match.scenario_clock,
            window_end=match.scenario_clock + timedelta(days=90),
            ranker_version="phase7-feedback-fixture-v1",
            input_sha256=sha256(f"phase7-ranking-{index}".encode()).hexdigest(),
            omitted_rule_set_count=0,
            created_at=NOW,
        )
        session.add(ranking)
        session.flush()
        session.add(
            PersonalRankingItemModel(
                ranking_snapshot_id=ranking.ranking_snapshot_id,
                ordinal=1,
                user_id=user_id,
                opportunity_id=match.opportunity_id,
                opportunity_version=match.opportunity_version,
                match_snapshot_id=match.snapshot_id,
                eligibility_status="ELIGIBLE",
                reason_codes=["ELIGIBILITY_ELIGIBLE"],
                deadline=match.scenario_clock + timedelta(days=30),
            )
        )
        fixtures.append(
            FeedbackOwnerFixture(
                user_id=user_id,
                token=token,
                ranking_snapshot_id=ranking.ranking_snapshot_id,
                match_snapshot_id=match.snapshot_id,
                opportunity_public_id=opportunity.public_id,
                opportunity_version=match.opportunity_version,
                user_state_version=state.version,
                evidence_ref_id=version.source_evidence_ref_id,
            )
        )
    session.flush()
    assert rule_set.opportunity_id == match.opportunity_id
    return fixtures[0], fixtures[1]


PROTECTED_TABLES = (
    RuleSetModel.__table__,
    EligibilityResultModel.__table__,
    MatchSnapshotModel.__table__,
    PersonalRankingSnapshotModel.__table__,
    PersonalRankingItemModel.__table__,
)


def protected_fact_digest(session: Session) -> str:
    payload: dict[str, list[dict[str, object]]] = {}
    for table in PROTECTED_TABLES:
        assert isinstance(table, Table)
        rows = [dict(row) for row in session.execute(select(table)).mappings()]
        payload[table.name] = sorted(
            rows,
            key=lambda value: json.dumps(value, default=str, sort_keys=True),
        )
    encoded = json.dumps(payload, default=str, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def submission_body(
    fixture: FeedbackOwnerFixture,
    **changes: object,
) -> dict[str, object]:
    values: dict[str, object] = {
        "ranking_snapshot_id": str(fixture.ranking_snapshot_id),
        "match_snapshot_id": str(fixture.match_snapshot_id),
        "opportunity_version": fixture.opportunity_version,
        "user_state_version": fixture.user_state_version,
        "event_type": "STRUCTURED_CORRECTION",
        "claim_kind": "EXPLANATION_UNCLEAR",
        "user_statement": "合成反馈：解释没有指出证据位置。",
        "structured_reason_code": "MISSING_EVIDENCE_EXPLANATION",
        "initial_evidence_ref_ids": [str(fixture.evidence_ref_id)],
        "consent_version": "phase7-feedback-consent-v1",
        "consent_scope": "FEEDBACK_REVIEW_AND_VALIDATION",
    }
    values.update(changes)
    return values


__all__ = [
    "FeedbackOwnerFixture",
    "NOW",
    "persist_feedback_prerequisites",
    "protected_fact_digest",
    "submission_body",
]
