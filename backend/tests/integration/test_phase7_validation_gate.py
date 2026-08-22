from datetime import timedelta
from uuid import UUID, uuid7

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.feedback.schemas import FeedbackSubmissionWrite
from deepaha.feedback.service import FeedbackService
from deepaha.personal.auth import Principal
from deepaha.review.auth import ReviewerPrincipal, ReviewerRole
from deepaha.review.models import (
    ApprovedFeedbackLabelModel,
    FeedbackReviewCaseSnapshotModel,
)
from deepaha.review.schemas import (
    ApprovedLabelWrite,
    ConfidenceAssessmentWrite,
    FeedbackAdjudicationWrite,
)
from deepaha.review.service import ReviewService
from deepaha.validation.models import (
    FeedbackImprovementCandidateModel,
    OfflineEvaluationCandidateModel,
    ReleaseGateDecisionModel,
    ShadowTestCandidateModel,
    ValidationRunModel,
)
from deepaha.validation.schemas import (
    HumanValidationRunWrite,
    ImprovementSelectionWrite,
    OfflineEvaluationWrite,
    ShadowEvaluationWrite,
    SimulationValidationRunWrite,
)
from deepaha.validation.service import (
    HumanValidationAuthorizationRequired,
    ValidationService,
    ValidationUnavailable,
)
from tests.feedback.support import (
    NOW,
    persist_feedback_prerequisites,
    protected_fact_digest,
    submission_body,
)
from tests.review.support import persist_reviewer, reviewer_id

pytestmark = pytest.mark.integration


def _session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def _reviewer_principal() -> ReviewerPrincipal:
    return ReviewerPrincipal(
        reviewer_id=reviewer_id(6),
        roles=frozenset(ReviewerRole),
        purposes=frozenset({"FEEDBACK_REVIEW_AND_VALIDATION"}),
        synthetic=True,
    )


def _create_approved_label(
    engine: Engine,
) -> tuple[UUID, str]:
    with Session(engine) as session:
        owner, _ = persist_feedback_prerequisites(session)
        persist_reviewer(
            session,
            index=6,
            token="phase7-validation-reviewer-token",
            roles=tuple(ReviewerRole),
        )
        session.commit()
    factory = _session_factory(engine)
    feedback = FeedbackService(session_factory=factory, now_factory=lambda: NOW)
    review = ReviewService(session_factory=factory, now_factory=lambda: NOW + timedelta(minutes=1))
    submitted = feedback.submit(
        Principal(user_id=owner.user_id),
        owner.opportunity_public_id,
        FeedbackSubmissionWrite.model_validate(submission_body(owner)),
        idempotency_key="phase7-validation-feedback-0001",
    )
    with Session(engine) as session:
        case = session.scalar(
            select(FeedbackReviewCaseSnapshotModel).where(
                FeedbackReviewCaseSnapshotModel.feedback_event_id
                == submitted.feedback.feedback_event_id
            )
        )
        assert case is not None
        review_case_id = case.review_case_id
    reviewer = _reviewer_principal()
    assessment = review.append_assessment(
        reviewer,
        review_case_id,
        ConfidenceAssessmentWrite.model_validate(
            {
                "evidence_complete": True,
                "confidence_band": "HIGH",
                "risk_level": "NORMAL",
                "conflict": False,
                "evidence_ref_ids": [owner.evidence_ref_id],
                "rationale": "合成审核：解释没有明确呈现现有官方证据位置。",
            }
        ),
        idempotency_key="phase7-validation-assessment-0001",
    )
    assert assessment is not None
    adjudication = review.append_adjudication(
        reviewer,
        review_case_id,
        FeedbackAdjudicationWrite.model_validate(
            {
                "confidence_assessment_id": assessment.confidence_assessment_id,
                "decision": "CONFIRMED",
                "evidence_ref_ids": [owner.evidence_ref_id],
                "reason": "合成裁决：只确认解释清晰度问题。",
            }
        ),
        idempotency_key="phase7-validation-adjudication-0001",
    )
    assert adjudication is not None
    label = review.create_label(
        reviewer,
        review_case_id,
        ApprovedLabelWrite.model_validate(
            {
                "feedback_adjudication_id": adjudication.feedback_adjudication_id,
                "approved_target_value": "解释应明确显示官方证据入口和仍不确定的条件。",
                "evidence_ref_ids": [owner.evidence_ref_id],
            }
        ),
        idempotency_key="phase7-validation-label-0001",
    )
    assert label is not None
    return label.approved_feedback_label_id, owner.opportunity_public_id


def test_one_synthetic_improvement_is_separated_and_held_without_online_mutation(
    migrated_engine: Engine,
) -> None:
    label_id, _public_id = _create_approved_label(migrated_engine)
    with Session(migrated_engine) as session:
        before = protected_fact_digest(session)
    service = ValidationService(
        session_factory=_session_factory(migrated_engine),
        now_factory=lambda: NOW + timedelta(minutes=2),
    )
    reviewer = _reviewer_principal()
    cycle_id = uuid7()
    selection = ImprovementSelectionWrite.model_validate(
        {
            "approved_label_ids": [label_id],
            "direction": "EXPLANATION_CLARITY",
            "component": "personal-explanation",
            "input_manifest_sha256": "1" * 64,
            "change_statement": "只改善证据入口与不确定条件的解释呈现。",
        }
    )
    candidate = service.select_improvement(reviewer, cycle_id, selection)
    replay = service.select_improvement(reviewer, cycle_id, selection)
    assert replay == candidate
    with pytest.raises(ValidationUnavailable):
        service.select_improvement(
            reviewer,
            cycle_id,
            ImprovementSelectionWrite.model_validate(
                {
                    **selection.model_dump(),
                    "change_statement": "同一周期不得选择第二个变体。",
                }
            ),
        )
    with pytest.raises(ValidationUnavailable):
        service.select_improvement(
            reviewer,
            uuid7(),
            ImprovementSelectionWrite.model_validate(
                {
                    **selection.model_dump(),
                    "approved_label_ids": [uuid7()],
                }
            ),
        )
    with pytest.raises(ValidationUnavailable):
        service.record_shadow(
            reviewer,
            candidate.improvement_candidate_id,
            ShadowEvaluationWrite.model_validate(
                {
                    "offline_evaluation_candidate_id": uuid7(),
                    "baseline_component_version": "explanation-v0.5",
                    "candidate_component_version": "explanation-v0.6-candidate-1",
                    "outcome": "PASSED",
                    "comparison_sha256": "2" * 64,
                    "evidence_class": "SYNTHETIC_SIMULATION_ONLY",
                }
            ),
        )
    offline = service.record_offline(
        reviewer,
        candidate.improvement_candidate_id,
        OfflineEvaluationWrite.model_validate(
            {
                "dataset_id": uuid7(),
                "dataset_version": 1,
                "dataset_sha256": "3" * 64,
                "baseline_component_version": "explanation-v0.5",
                "candidate_component_version": "explanation-v0.6-candidate-1",
                "outcome": "PASSED",
                "result_sha256": "4" * 64,
                "evidence_class": "SYNTHETIC_SIMULATION_ONLY",
            }
        ),
    )
    shadow = service.record_shadow(
        reviewer,
        candidate.improvement_candidate_id,
        ShadowEvaluationWrite.model_validate(
            {
                "offline_evaluation_candidate_id": offline.offline_evaluation_candidate_id,
                "baseline_component_version": offline.baseline_component_version,
                "candidate_component_version": offline.candidate_component_version,
                "outcome": "PASSED",
                "comparison_sha256": "5" * 64,
                "evidence_class": "SYNTHETIC_SIMULATION_ONLY",
            }
        ),
    )
    simulation_dataset_id = uuid7()
    simulation = service.record_simulation_run(
        reviewer,
        cycle_id,
        SimulationValidationRunWrite.model_validate(
            {
                "dataset_id": simulation_dataset_id,
                "dataset_version": 1,
                "dataset_sha256": "6" * 64,
                "track": "SIMULATION",
                "evidence_class": "SYNTHETIC_SIMULATION_ONLY",
                "synthetic": True,
                "release_qualification_eligible": False,
                "outcome": "PASSED",
                "metrics": {
                    "case_count": 2,
                    "expected_status_reproduced_count": 2,
                    "unexpected_ineligible_count": 0,
                    "unexpected_ineligible_case_ids": [],
                    "replay_mismatch_count": 0,
                    "candidate_difference_count": 1,
                },
                "started_at": NOW,
                "completed_at": NOW + timedelta(seconds=1),
            }
        ),
    )
    human_dataset_id = uuid7()
    assert human_dataset_id != simulation_dataset_id
    with pytest.raises(HumanValidationAuthorizationRequired):
        service.record_human_run(
            reviewer,
            cycle_id,
            HumanValidationRunWrite.model_validate(
                {
                    "dataset_id": human_dataset_id,
                    "dataset_version": 1,
                    "dataset_sha256": "7" * 64,
                    "track": "HUMAN_PARTICIPANT",
                    "evidence_class": "CONSENTED_HUMAN_PARTICIPANT",
                    "synthetic": False,
                    "release_qualification_eligible": True,
                    "outcome": "PASSED",
                    "metrics": {
                        "participant_count": 2,
                        "structured_feedback_count": 2,
                        "comprehension_review_count": 2,
                        "cognitive_load_review_count": 2,
                        "high_intent_action_count": 1,
                        "withdrawal_exclusion_count": 0,
                    },
                    "started_at": NOW,
                    "completed_at": NOW + timedelta(seconds=1),
                }
            ),
        )
    decision = service.decide(reviewer, cycle_id)

    assert candidate.direction.value == "EXPLANATION_CLARITY"
    assert candidate.component == "personal-explanation"
    assert candidate.approved_label_ids == (label_id,)
    assert candidate.evidence_class.value == "SYNTHETIC_FEEDBACK_WORKFLOW_ONLY"
    assert offline.evidence_class.value == shadow.evidence_class.value
    assert offline.evidence_class.value == "SYNTHETIC_SIMULATION_ONLY"
    assert simulation.synthetic is True
    assert simulation.release_qualification_eligible is False
    assert decision.decision.value == "HOLD_MISSING_HUMAN_EVIDENCE"
    assert decision.simulation_validation_run_id == simulation.validation_run_id
    assert decision.human_validation_run_id is None
    assert "Synthetic engineering checks passed" in decision.rationale

    with Session(migrated_engine) as session:
        assert protected_fact_digest(session) == before
        assert session.scalar(select(func.count()).select_from(ApprovedFeedbackLabelModel)) == 1
        assert (
            session.scalar(select(func.count()).select_from(FeedbackImprovementCandidateModel)) == 1
        )
        assert (
            session.scalar(select(func.count()).select_from(OfflineEvaluationCandidateModel)) == 1
        )
        assert session.scalar(select(func.count()).select_from(ShadowTestCandidateModel)) == 1
        assert session.scalar(select(func.count()).select_from(ValidationRunModel)) == 1
        assert session.scalar(select(func.count()).select_from(ReleaseGateDecisionModel)) == 1
        tracks = session.scalars(select(ValidationRunModel.track)).all()
        assert tracks == ["SIMULATION"]
