import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid7

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Table, select
from sqlalchemy.orm import Session

from deepaha.contracts.phase7 import SimulationValidationMetricsSchemaV06
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
PHASE7_FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "feedback"
PHASE7_FIXTURE_PATH = PHASE7_FIXTURE_ROOT / "phase7-feedback.json"
PHASE7_MANIFEST_PATH = PHASE7_FIXTURE_ROOT / "phase7-feedback.manifest.json"


class Phase7FixtureModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Phase7FeedbackInput(Phase7FixtureModel):
    claim_kind: Literal["EXPLANATION_UNCLEAR"]
    user_statement: str
    evidence_relation: Literal["SUPPORTS"]
    evidence_note: str


class Phase7AssessmentInput(Phase7FixtureModel):
    evidence_complete: Literal[True]
    confidence_band: Literal["HIGH"]
    risk_level: Literal["NORMAL"]
    conflict: Literal[False]
    rationale: str


class Phase7AdjudicationInput(Phase7FixtureModel):
    decision: Literal["CONFIRMED"]
    reason: str


class Phase7ReviewInput(Phase7FixtureModel):
    assessment: Phase7AssessmentInput
    adjudication: Phase7AdjudicationInput
    approved_target_value: str


class Phase7OfflineInput(Phase7FixtureModel):
    dataset_id: UUID
    dataset_version: Literal[1]
    dataset_sha256: str
    baseline_component_version: Literal["explanation-v0.5"]
    candidate_component_version: Literal["explanation-v0.6-candidate-1"]
    outcome: Literal["PASSED"]
    result_sha256: str
    evidence_class: Literal["SYNTHETIC_SIMULATION_ONLY"]


class Phase7ShadowInput(Phase7FixtureModel):
    baseline_component_version: Literal["explanation-v0.5"]
    candidate_component_version: Literal["explanation-v0.6-candidate-1"]
    outcome: Literal["PASSED"]
    comparison_sha256: str
    evidence_class: Literal["SYNTHETIC_SIMULATION_ONLY"]


class Phase7SimulationInput(Phase7FixtureModel):
    dataset_id: UUID
    dataset_version: Literal[1]
    dataset_sha256: str
    track: Literal["SIMULATION"]
    evidence_class: Literal["SYNTHETIC_SIMULATION_ONLY"]
    synthetic: Literal[True]
    release_qualification_eligible: Literal[False]
    outcome: Literal["PASSED"]
    metrics: SimulationValidationMetricsSchemaV06
    started_at: datetime
    completed_at: datetime


class Phase7ValidationInput(Phase7FixtureModel):
    validation_cycle_id: UUID
    direction: Literal["EXPLANATION_CLARITY"]
    component: Literal["personal-explanation"]
    input_manifest_sha256: str
    change_statement: str
    offline: Phase7OfflineInput
    shadow: Phase7ShadowInput
    simulation: Phase7SimulationInput
    expected_gate_decision: Literal["HOLD_MISSING_HUMAN_EVIDENCE"]


class Phase7FeedbackFixture(Phase7FixtureModel):
    schema_version: Literal["phase7-feedback-fixture-v1"]
    synthetic: Literal[True]
    contains_personal_data: Literal[False]
    business_truth: Literal[False]
    release_qualification_eligible: Literal[False]
    license: Literal["CC0-1.0 synthetic fixture"]
    scenario_clock: datetime
    feedback: Phase7FeedbackInput
    review: Phase7ReviewInput
    validation: Phase7ValidationInput


class Phase7FixtureManifest(Phase7FixtureModel):
    manifest_schema_version: Literal["phase7-feedback-manifest-v1"]
    fixture: Literal["phase7-feedback.json"]
    sha256: str
    license: Literal["CC0-1.0 synthetic fixture"]
    synthetic: Literal[True]
    contains_personal_data: Literal[False]
    business_truth: Literal[False]
    release_qualification_eligible: Literal[False]
    workflow_count: Literal[1]
    direction_count: Literal[1]
    human_participant_count: Literal[0]
    purpose: str


def validate_phase7_feedback_fixture_bytes(
    fixture_bytes: bytes,
    manifest_bytes: bytes,
) -> Phase7FeedbackFixture:
    manifest = Phase7FixtureManifest.model_validate_json(manifest_bytes)
    if sha256(fixture_bytes).hexdigest() != manifest.sha256:
        raise ValueError("Phase 7 fixture hash does not match its manifest")
    fixture = Phase7FeedbackFixture.model_validate_json(fixture_bytes)
    if fixture.license != manifest.license:
        raise ValueError("Phase 7 fixture license does not match its manifest")
    return fixture


def load_phase7_feedback_fixture() -> Phase7FeedbackFixture:
    return validate_phase7_feedback_fixture_bytes(
        PHASE7_FIXTURE_PATH.read_bytes(),
        PHASE7_MANIFEST_PATH.read_bytes(),
    )


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


def protected_fact_counts(session: Session) -> dict[str, int]:
    result: dict[str, int] = {}
    for table in PROTECTED_TABLES:
        assert isinstance(table, Table)
        result[table.name] = len(session.execute(select(table)).all())
    return result


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
    "PHASE7_FIXTURE_PATH",
    "PHASE7_MANIFEST_PATH",
    "Phase7FeedbackFixture",
    "load_phase7_feedback_fixture",
    "persist_feedback_prerequisites",
    "protected_fact_counts",
    "protected_fact_digest",
    "submission_body",
    "validate_phase7_feedback_fixture_bytes",
]
