import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from deepaha.contracts import FeedbackEventSchemaV06 as ExportedFeedbackEventSchemaV06
from deepaha.contracts.export import (
    PHASE7_SCHEMAS,
    render_phase1_schemas,
    render_phase2_schemas,
    render_phase3_schemas,
    render_phase4_schemas,
    render_phase6_schemas,
    render_phase7_schemas,
    write_phase7_schemas,
)
from deepaha.contracts.phase7 import (
    ApprovedFeedbackLabelSchemaV06,
    FeedbackAdjudicationSchemaV06,
    FeedbackConfidenceAssessmentSchemaV06,
    FeedbackEventSchemaV06,
    FeedbackEvidenceLinkSchemaV06,
    FeedbackReviewCaseSnapshotSchemaV06,
    HumanValidationRunSchemaV06,
    ImprovementCandidateSchemaV06,
    OfflineEvaluationCandidateSchemaV06,
    ReleaseGateDecisionSchemaV06,
    ShadowTestCandidateSchemaV06,
    SimulationValidationRunSchemaV06,
)

NOW = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)
REPOSITORY_ROOT = Path(__file__).parents[3]
V06_EXAMPLE_PATH = REPOSITORY_ROOT / "contracts" / "examples" / "v0.6.0" / "phase-7-example.json"


def entity(serial: int) -> UUID:
    return UUID(f"019b0000-0000-7000-8000-{serial:012d}")


def feedback_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "feedback_event_id": entity(601),
        "owner_user_id": entity(626),
        "ranking_snapshot_id": entity(602),
        "match_snapshot_id": entity(603),
        "opportunity_id": entity(604),
        "opportunity_version": 3,
        "user_state_snapshot_id": entity(605),
        "user_state_version": 2,
        "event_type": "STRUCTURED_CORRECTION",
        "claim_kind": "EXPLANATION_UNCLEAR",
        "user_statement": "合成反馈：这条解释没有指出仍待确认的材料。",
        "structured_reason_code": "MISSING_EVIDENCE_EXPLANATION",
        "consent_version": "phase7-feedback-consent-v1",
        "consent_scope": "FEEDBACK_REVIEW_AND_VALIDATION",
        "contract_version": "0.6.0",
        "input_sha256": "6" * 64,
        "created_at": NOW,
    }
    values.update(changes)
    return values


def evidence_link_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "feedback_evidence_link_id": entity(606),
        "feedback_event_id": entity(601),
        "evidence_ref_id": entity(607),
        "document_id": entity(608),
        "relation": "SUPPORTS",
        "actor_kind": "USER",
        "actor_id": entity(626),
        "note": "合成证据定位已由服务端验证。",
        "input_sha256": "7" * 64,
        "created_at": NOW,
    }
    values.update(changes)
    return values


def review_case_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "review_case_snapshot_id": entity(609),
        "review_case_id": entity(610),
        "feedback_event_id": entity(601),
        "version": 1,
        "status": "RECEIVED",
        "priority": 2,
        "due_at": datetime(2026, 8, 24, 10, 0, tzinfo=UTC),
        "assigned_reviewer_id": None,
        "transition_reason": "INITIAL_SUBMISSION",
        "input_sha256": "8" * 64,
        "created_at": NOW,
    }
    values.update(changes)
    return values


def confidence_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "confidence_assessment_id": entity(611),
        "review_case_id": entity(610),
        "review_case_version": 1,
        "evidence_complete": True,
        "confidence_band": "HIGH",
        "risk_level": "NORMAL",
        "conflict": False,
        "evidence_ref_ids": [entity(607)],
        "rationale": "合成证据足以确认解释缺少关键定位。",
        "reviewer_id": entity(612),
        "review_purpose": "FEEDBACK_REVIEW_AND_VALIDATION",
        "input_sha256": "9" * 64,
        "created_at": NOW,
    }
    values.update(changes)
    return values


def adjudication_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "feedback_adjudication_id": entity(613),
        "review_case_id": entity(610),
        "review_case_version": 1,
        "confidence_assessment_id": entity(611),
        "decision": "CONFIRMED",
        "evidence_ref_ids": [entity(607)],
        "reason": "合成审核确认解释清晰度纠错。",
        "adjudicator_id": entity(614),
        "review_purpose": "FEEDBACK_REVIEW_AND_VALIDATION",
        "input_sha256": "a" * 64,
        "created_at": NOW,
    }
    values.update(changes)
    return values


def label_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "approved_feedback_label_id": entity(615),
        "feedback_event_id": entity(601),
        "feedback_adjudication_id": entity(613),
        "match_snapshot_id": entity(603),
        "opportunity_id": entity(604),
        "opportunity_version": 3,
        "claim_kind": "EXPLANATION_UNCLEAR",
        "approved_target_value": "EXPLANATION_MUST_NAME_UNCERTAIN_EVIDENCE",
        "evidence_ref_ids": [entity(607)],
        "evidence_class": "SYNTHETIC_FEEDBACK_WORKFLOW_ONLY",
        "content_sha256": "b" * 64,
        "created_at": NOW,
    }
    values.update(changes)
    return values


def improvement_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "improvement_candidate_id": entity(616),
        "validation_cycle_id": entity(617),
        "approved_label_ids": [entity(615)],
        "direction": "EXPLANATION_CLARITY",
        "component": "personal-explanation-template",
        "input_manifest_sha256": "c" * 64,
        "change_statement": "只验证解释是否明确指出仍不确定的证据。",
        "candidate_sha256": "d" * 64,
        "evidence_class": "SYNTHETIC_FEEDBACK_WORKFLOW_ONLY",
        "selected": True,
        "created_at": NOW,
    }
    values.update(changes)
    return values


def offline_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "offline_evaluation_candidate_id": entity(618),
        "improvement_candidate_id": entity(616),
        "dataset_id": entity(619),
        "dataset_version": 1,
        "dataset_sha256": "e" * 64,
        "baseline_component_version": "phase6-explanation-v1",
        "candidate_component_version": "phase7-explanation-candidate-v1",
        "outcome": "PASSED",
        "result_sha256": "f" * 64,
        "evidence_class": "SYNTHETIC_SIMULATION_ONLY",
        "created_at": NOW,
    }
    values.update(changes)
    return values


def shadow_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "shadow_test_candidate_id": entity(620),
        "improvement_candidate_id": entity(616),
        "offline_evaluation_candidate_id": entity(618),
        "baseline_component_version": "phase6-explanation-v1",
        "candidate_component_version": "phase7-explanation-candidate-v1",
        "outcome": "PASSED",
        "comparison_sha256": "0" * 64,
        "evidence_class": "SYNTHETIC_SIMULATION_ONLY",
        "created_at": NOW,
    }
    values.update(changes)
    return values


def simulation_run_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "validation_run_id": entity(621),
        "validation_cycle_id": entity(617),
        "improvement_candidate_id": entity(616),
        "dataset_id": entity(622),
        "dataset_version": 1,
        "dataset_sha256": "1" * 64,
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
        "input_sha256": "2" * 64,
        "started_at": NOW,
        "completed_at": NOW,
    }
    values.update(changes)
    return values


def human_run_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "validation_run_id": entity(623),
        "validation_cycle_id": entity(617),
        "improvement_candidate_id": entity(616),
        "dataset_id": entity(624),
        "dataset_version": 1,
        "dataset_sha256": "3" * 64,
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
        "input_sha256": "4" * 64,
        "started_at": NOW,
        "completed_at": NOW,
    }
    values.update(changes)
    return values


def release_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "release_gate_decision_id": entity(625),
        "validation_cycle_id": entity(617),
        "improvement_candidate_id": entity(616),
        "offline_evaluation_candidate_id": entity(618),
        "shadow_test_candidate_id": entity(620),
        "simulation_validation_run_id": entity(621),
        "human_validation_run_id": None,
        "decision": "HOLD_MISSING_HUMAN_EVIDENCE",
        "rationale": "合成工程验证不能替代真人参与者证据。",
        "input_sha256": "5" * 64,
        "created_at": NOW,
    }
    values.update(changes)
    return values


def test_raw_feedback_is_frozen_bounded_and_contains_no_review_state() -> None:
    event = FeedbackEventSchemaV06.model_validate(feedback_values())

    assert event.owner_user_id == entity(626)
    assert "review_status" not in FeedbackEventSchemaV06.model_fields
    assert "reviewer_id" not in FeedbackEventSchemaV06.model_fields
    with pytest.raises(ValidationError, match="frozen"):
        event.user_statement = "不可修改"
    with pytest.raises(ValidationError):
        FeedbackEventSchemaV06.model_validate(feedback_values(user_id=entity(699)))
    FeedbackEventSchemaV06.model_validate(feedback_values(user_statement="字" * 500))
    with pytest.raises(ValidationError):
        FeedbackEventSchemaV06.model_validate(feedback_values(user_statement="字" * 501))


def test_review_assets_are_distinct_and_confirmed_adjudication_requires_evidence() -> None:
    FeedbackEvidenceLinkSchemaV06.model_validate(evidence_link_values())
    FeedbackReviewCaseSnapshotSchemaV06.model_validate(review_case_values())
    FeedbackConfidenceAssessmentSchemaV06.model_validate(confidence_values())
    FeedbackAdjudicationSchemaV06.model_validate(adjudication_values())
    ApprovedFeedbackLabelSchemaV06.model_validate(label_values())

    with pytest.raises(ValidationError, match="CONFIRMED"):
        FeedbackAdjudicationSchemaV06.model_validate(adjudication_values(evidence_ref_ids=[]))


def test_improvement_candidate_has_one_direction_and_separate_offline_shadow_ids() -> None:
    candidate = ImprovementCandidateSchemaV06.model_validate(improvement_values())
    offline = OfflineEvaluationCandidateSchemaV06.model_validate(offline_values())
    shadow = ShadowTestCandidateSchemaV06.model_validate(shadow_values())

    assert candidate.direction.value == "EXPLANATION_CLARITY"
    assert "rule_change" not in ImprovementCandidateSchemaV06.model_fields
    assert "ranking_change" not in ImprovementCandidateSchemaV06.model_fields
    assert shadow.offline_evaluation_candidate_id == offline.offline_evaluation_candidate_id
    with pytest.raises(ValidationError):
        ImprovementCandidateSchemaV06.model_validate(improvement_values(selected=False))


def test_synthetic_evidence_cannot_construct_human_validation() -> None:
    HumanValidationRunSchemaV06.model_validate(human_run_values())
    with pytest.raises(ValidationError):
        HumanValidationRunSchemaV06.model_validate(
            human_run_values(
                synthetic=True,
                evidence_class="SYNTHETIC_FEEDBACK_WORKFLOW_ONLY",
            )
        )


def test_simulation_metrics_remain_integer_engineering_evidence() -> None:
    run = SimulationValidationRunSchemaV06.model_validate(simulation_run_values())

    assert run.synthetic is True
    assert run.release_qualification_eligible is False
    assert "retention_rate" not in type(run.metrics).model_fields
    with pytest.raises(ValidationError):
        SimulationValidationRunSchemaV06.model_validate(
            simulation_run_values(metrics={"case_count": 2, "retention_rate": 0.8})
        )


def test_release_acceptance_requires_both_qualified_tracks() -> None:
    ReleaseGateDecisionSchemaV06.model_validate(release_values())
    with pytest.raises(ValidationError, match="both validation tracks"):
        ReleaseGateDecisionSchemaV06.model_validate(
            release_values(
                decision="CANDIDATE_ACCEPTED_FOR_FUTURE_IMPLEMENTATION",
                human_validation_run_id=None,
            )
        )


def committed_schema_bytes(version: str) -> dict[str, bytes]:
    directory = REPOSITORY_ROOT / "contracts" / "schemas" / version
    return {path.name: path.read_bytes() for path in directory.glob("*.schema.json")}


def test_phase7_export_preserves_prior_schema_bytes_and_writes_complete_v06(
    tmp_path: Path,
) -> None:
    assert render_phase1_schemas() == committed_schema_bytes("v0.1.0")
    assert render_phase2_schemas() == committed_schema_bytes("v0.2.0")
    assert render_phase3_schemas() == committed_schema_bytes("v0.3.0")
    assert render_phase4_schemas() == committed_schema_bytes("v0.4.0")
    assert render_phase6_schemas() == committed_schema_bytes("v0.5.0")

    rendered = render_phase7_schemas()
    assert set(rendered) == set(PHASE7_SCHEMAS)
    assert rendered == committed_schema_bytes("v0.6.0")
    assert len(rendered) == 11
    written = write_phase7_schemas(tmp_path)
    assert {name: path.read_bytes() for name, path in written.items()} == rendered


def test_phase7_contract_is_available_from_public_contract_package() -> None:
    assert ExportedFeedbackEventSchemaV06 is FeedbackEventSchemaV06


def test_phase7_example_is_synthetic_separated_and_held() -> None:
    example = json.loads(V06_EXAMPLE_PATH.read_text(encoding="utf-8"))

    assert example["synthetic"] is True
    assert example["contains_personal_data"] is False
    assert example["business_truth"] is False
    assert example["release_qualification_eligible"] is False
    assert example["evidence_class"] == "SYNTHETIC_FEEDBACK_WORKFLOW_ONLY"
    FeedbackEventSchemaV06.model_validate(example["feedback_event"])
    FeedbackEvidenceLinkSchemaV06.model_validate(example["feedback_evidence_link"])
    FeedbackReviewCaseSnapshotSchemaV06.model_validate(example["review_case_snapshot"])
    FeedbackConfidenceAssessmentSchemaV06.model_validate(example["confidence_assessment"])
    FeedbackAdjudicationSchemaV06.model_validate(example["adjudication"])
    ApprovedFeedbackLabelSchemaV06.model_validate(example["approved_label"])
    candidate = ImprovementCandidateSchemaV06.model_validate(example["improvement_candidate"])
    OfflineEvaluationCandidateSchemaV06.model_validate(example["offline_candidate"])
    ShadowTestCandidateSchemaV06.model_validate(example["shadow_candidate"])
    SimulationValidationRunSchemaV06.model_validate(example["simulation_validation_run"])
    decision = ReleaseGateDecisionSchemaV06.model_validate(example["release_gate_decision"])
    assert candidate.direction.value == "EXPLANATION_CLARITY"
    assert decision.decision.value == "HOLD_MISSING_HUMAN_EVIDENCE"
    assert decision.human_validation_run_id is None
