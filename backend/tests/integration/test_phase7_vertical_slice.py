from datetime import timedelta
from urllib.parse import urlparse

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.feedback.schemas import FeedbackEvidenceWrite, FeedbackSubmissionWrite
from deepaha.feedback.service import FeedbackService
from deepaha.personal.auth import Principal
from deepaha.personal.profile import ProfileAccessError, ProfileService
from deepaha.profiles.models import ProfileSnapshotModel
from deepaha.review.auth import ReviewerPrincipal, ReviewerRole
from deepaha.review.models import FeedbackReviewCaseSnapshotModel
from deepaha.review.schemas import (
    ApprovedLabelWrite,
    ConfidenceAssessmentWrite,
    FeedbackAdjudicationWrite,
)
from deepaha.review.service import ReviewService
from deepaha.validation.schemas import (
    ImprovementSelectionWrite,
    OfflineEvaluationWrite,
    ShadowEvaluationWrite,
    SimulationValidationRunWrite,
)
from deepaha.validation.service import ValidationService
from tests.feedback.seed_phase7_browser import seed_phase7_browser
from tests.feedback.support import (
    NOW,
    load_phase7_feedback_fixture,
    persist_feedback_prerequisites,
    protected_fact_counts,
    protected_fact_digest,
    submission_body,
)
from tests.review.support import persist_reviewer, reviewer_id

pytestmark = pytest.mark.integration


def test_phase7_browser_seed_is_synthetic_runtime_only_and_refuses_reuse(
    migrated_engine: Engine,
    database_url: str,
) -> None:
    target = urlparse(database_url)
    if target.hostname != "127.0.0.1" or target.port != 55437 or target.path != "/deepaha":
        pytest.skip("requires the exact disposable Phase 7 database")

    identity = seed_phase7_browser(database_url)

    assert identity.personal_session != identity.reviewer_session
    assert identity.initial_public_id in identity.public_ids
    factory = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with pytest.raises(ProfileAccessError, match="personal profile unavailable"):
        ProfileService(session_factory=factory, now_factory=lambda: NOW).get_current(
            Principal(user_id=identity.user_id)
        )
    synthetic_state = ProfileService(
        session_factory=factory,
        now_factory=lambda: NOW,
        allow_synthetic_fixture_profile=True,
    ).get_current(Principal(user_id=identity.user_id))
    assert synthetic_state is not None
    with Session(migrated_engine) as session:
        profile = session.scalar(select(ProfileSnapshotModel))
        assert profile is not None
        assert profile.synthetic is True
        assert profile.profile_schema_version == "0.4.0"
    with pytest.raises(RuntimeError, match="empty Phase 7 fixture scope"):
        seed_phase7_browser(database_url)


def test_complete_synthetic_feedback_workflow_is_held_without_online_mutation(
    migrated_engine: Engine,
) -> None:
    fixture = load_phase7_feedback_fixture()
    reviewer_token = "phase7-vertical-synthetic-reviewer"
    with Session(migrated_engine) as session:
        owner, _ = persist_feedback_prerequisites(session)
        persist_reviewer(
            session,
            index=9,
            token=reviewer_token,
            roles=tuple(ReviewerRole),
        )
        before_digest = protected_fact_digest(session)
        before_counts = protected_fact_counts(session)
        session.commit()

    factory = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    user = Principal(user_id=owner.user_id)
    reviewer = ReviewerPrincipal(
        reviewer_id=reviewer_id(9),
        roles=frozenset(ReviewerRole),
        purposes=frozenset({"FEEDBACK_REVIEW_AND_VALIDATION"}),
        synthetic=True,
    )
    feedback = FeedbackService(session_factory=factory, now_factory=lambda: NOW)
    review = ReviewService(
        session_factory=factory,
        now_factory=lambda: NOW + timedelta(minutes=1),
    )
    validation = ValidationService(
        session_factory=factory,
        now_factory=lambda: NOW + timedelta(minutes=2),
    )

    submitted = feedback.submit(
        user,
        owner.opportunity_public_id,
        FeedbackSubmissionWrite.model_validate(
            submission_body(
                owner,
                user_statement=fixture.feedback.user_statement,
                initial_evidence_ref_ids=[],
            )
        ),
        idempotency_key="phase7-vertical-submit-0001",
    )
    evidenced = feedback.append_evidence(
        user,
        submitted.feedback.feedback_event_id,
        FeedbackEvidenceWrite.model_validate(
            {
                "evidence_ref_id": owner.evidence_ref_id,
                "relation": fixture.feedback.evidence_relation,
                "note": fixture.feedback.evidence_note,
            }
        ),
        idempotency_key="phase7-vertical-evidence-0001",
    )
    assert evidenced is not None
    with Session(migrated_engine) as session:
        case = session.scalar(
            select(FeedbackReviewCaseSnapshotModel).where(
                FeedbackReviewCaseSnapshotModel.feedback_event_id
                == submitted.feedback.feedback_event_id
            )
        )
        assert case is not None
        case_id = case.review_case_id

    assessment = review.append_assessment(
        reviewer,
        case_id,
        ConfidenceAssessmentWrite.model_validate(
            {
                **fixture.review.assessment.model_dump(),
                "evidence_ref_ids": [owner.evidence_ref_id],
            }
        ),
        idempotency_key="phase7-vertical-assessment-0001",
    )
    assert assessment is not None
    adjudication = review.append_adjudication(
        reviewer,
        case_id,
        FeedbackAdjudicationWrite.model_validate(
            {
                **fixture.review.adjudication.model_dump(),
                "confidence_assessment_id": assessment.confidence_assessment_id,
                "evidence_ref_ids": [owner.evidence_ref_id],
            }
        ),
        idempotency_key="phase7-vertical-adjudication-0001",
    )
    assert adjudication is not None
    label = review.create_label(
        reviewer,
        case_id,
        ApprovedLabelWrite.model_validate(
            {
                "feedback_adjudication_id": adjudication.feedback_adjudication_id,
                "approved_target_value": fixture.review.approved_target_value,
                "evidence_ref_ids": [owner.evidence_ref_id],
            }
        ),
        idempotency_key="phase7-vertical-label-0001",
    )
    assert label is not None

    candidate = validation.select_improvement(
        reviewer,
        fixture.validation.validation_cycle_id,
        ImprovementSelectionWrite.model_validate(
            {
                "approved_label_ids": [label.approved_feedback_label_id],
                "direction": fixture.validation.direction,
                "component": fixture.validation.component,
                "input_manifest_sha256": fixture.validation.input_manifest_sha256,
                "change_statement": fixture.validation.change_statement,
            }
        ),
    )
    offline = validation.record_offline(
        reviewer,
        candidate.improvement_candidate_id,
        OfflineEvaluationWrite.model_validate(fixture.validation.offline.model_dump()),
    )
    shadow = validation.record_shadow(
        reviewer,
        candidate.improvement_candidate_id,
        ShadowEvaluationWrite.model_validate(
            {
                **fixture.validation.shadow.model_dump(),
                "offline_evaluation_candidate_id": offline.offline_evaluation_candidate_id,
            }
        ),
    )
    simulation = validation.record_simulation_run(
        reviewer,
        fixture.validation.validation_cycle_id,
        SimulationValidationRunWrite.model_validate(
            fixture.validation.simulation.model_dump()
        ),
    )
    decision = validation.decide(reviewer, fixture.validation.validation_cycle_id)

    assert len(evidenced.evidence) == 1
    assert adjudication.decision == "CONFIRMED"
    assert label.evidence_class == "SYNTHETIC_FEEDBACK_WORKFLOW_ONLY"
    assert candidate.direction == "EXPLANATION_CLARITY"
    assert offline.outcome == shadow.outcome == simulation.outcome == "PASSED"
    assert decision.decision == fixture.validation.expected_gate_decision
    assert decision.human_validation_run_id is None
    with Session(migrated_engine) as session:
        assert protected_fact_digest(session) == before_digest
        assert protected_fact_counts(session) == before_counts
