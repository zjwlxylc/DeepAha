from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from deepaha.contracts.phase7 import HumanValidationMetricsSchemaV06, ReleaseGateDecision
from deepaha.review.auth import ReviewerPrincipal, ReviewerRole
from deepaha.validation.schemas import (
    HumanValidationRunWrite,
    ImprovementSelectionWrite,
    OfflineEvaluationWrite,
    ShadowEvaluationWrite,
    SimulationValidationRunWrite,
)
from deepaha.validation.service import (
    ValidationUnavailable,
    derive_gate_decision,
    improvement_input_sha256,
    required_evaluation_evidence_class,
)

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
REVIEWER_ID = UUID("019b0000-0000-7000-8000-000000000701")
CYCLE_ID = UUID("019b0000-0000-7000-8000-000000000702")
LABEL_ID = UUID("019b0000-0000-7000-8000-000000000703")
DATASET_ID = UUID("019b0000-0000-7000-8000-000000000704")


def principal() -> ReviewerPrincipal:
    return ReviewerPrincipal(
        reviewer_id=REVIEWER_ID,
        roles=frozenset({ReviewerRole.VALIDATION_REVIEWER}),
        purposes=frozenset({"FEEDBACK_REVIEW_AND_VALIDATION"}),
        synthetic=True,
    )


def selection(**changes: object) -> ImprovementSelectionWrite:
    values: dict[str, object] = {
        "approved_label_ids": [LABEL_ID],
        "direction": "EXPLANATION_CLARITY",
        "component": "personal-explanation",
        "input_manifest_sha256": "1" * 64,
        "change_statement": "只改善证据入口与不确定条件的解释呈现。",
    }
    values.update(changes)
    return ImprovementSelectionWrite.model_validate(values)


def test_phase7_selection_allows_one_explanation_change_only() -> None:
    command = selection()

    assert command.approved_label_ids == (LABEL_ID,)
    assert command.direction.value == "EXPLANATION_CLARITY"
    assert command.component == "personal-explanation"
    invalid_changes: tuple[dict[str, object], ...] = (
        {"approved_label_ids": []},
        {"approved_label_ids": [LABEL_ID, LABEL_ID]},
        {"direction": "ELIGIBILITY_RULE_CANDIDATE"},
        {"component": "rule-engine"},
        {"change_statement": "字" * 501},
        {"rule_patch": {"status": "ELIGIBLE"}},
    )
    for changes in invalid_changes:
        with pytest.raises(ValidationError):
            selection(**changes)


def test_offline_shadow_and_simulation_commands_are_fixed_and_not_arbitrary_metrics() -> None:
    offline = OfflineEvaluationWrite.model_validate(
        {
            "dataset_id": DATASET_ID,
            "dataset_version": 1,
            "dataset_sha256": "2" * 64,
            "baseline_component_version": "explanation-v0.5",
            "candidate_component_version": "explanation-v0.6-candidate-1",
            "outcome": "PASSED",
            "result_sha256": "3" * 64,
            "evidence_class": "SYNTHETIC_SIMULATION_ONLY",
        }
    )
    shadow = ShadowEvaluationWrite.model_validate(
        {
            "offline_evaluation_candidate_id": UUID("019b0000-0000-7000-8000-000000000705"),
            "baseline_component_version": offline.baseline_component_version,
            "candidate_component_version": offline.candidate_component_version,
            "outcome": "PASSED",
            "comparison_sha256": "4" * 64,
            "evidence_class": "SYNTHETIC_SIMULATION_ONLY",
        }
    )
    simulation = SimulationValidationRunWrite.model_validate(
        {
            "dataset_id": DATASET_ID,
            "dataset_version": 1,
            "dataset_sha256": "5" * 64,
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
    )

    assert shadow.evidence_class.value == offline.evidence_class.value
    assert simulation.metrics.case_count == 2
    with pytest.raises(ValidationError):
        SimulationValidationRunWrite.model_validate(
            {
                **simulation.model_dump(),
                "metrics": {
                    **simulation.metrics.model_dump(),
                    "participant_trust_rate": 0.99,
                },
            }
        )
    with pytest.raises(ValidationError):
        SimulationValidationRunWrite.model_validate(
            {**simulation.model_dump(), "release_qualification_eligible": True}
        )


def test_human_track_rejects_synthetic_shape_and_has_separate_metrics() -> None:
    human_values: dict[str, object] = {
        "dataset_id": UUID("019b0000-0000-7000-8000-000000000706"),
        "dataset_version": 1,
        "dataset_sha256": "6" * 64,
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
    human = HumanValidationRunWrite.model_validate(human_values)

    assert human.dataset_id != DATASET_ID
    assert "case_count" not in HumanValidationMetricsSchemaV06.model_fields
    for changes in (
        {"synthetic": True},
        {"evidence_class": "SYNTHETIC_SIMULATION_ONLY"},
        {"track": "SIMULATION"},
        {"metrics": {"case_count": 2}},
    ):
        with pytest.raises(ValidationError):
            HumanValidationRunWrite.model_validate({**human_values, **changes})


def test_gate_decision_is_deterministic_and_synthetic_only_never_accepts() -> None:
    assert (
        derive_gate_decision(
            offline_outcome="PASSED",
            shadow_outcome="PASSED",
            simulation_outcome="PASSED",
            human_outcome=None,
        )
        is ReleaseGateDecision.HOLD_MISSING_HUMAN_EVIDENCE
    )
    assert (
        derive_gate_decision(
            offline_outcome="FAILED",
            shadow_outcome=None,
            simulation_outcome=None,
            human_outcome=None,
        )
        is ReleaseGateDecision.HOLD_ENGINEERING_FAILURE
    )
    assert (
        derive_gate_decision(
            offline_outcome="PASSED",
            shadow_outcome="PASSED",
            simulation_outcome=None,
            human_outcome=None,
        )
        is ReleaseGateDecision.HOLD_ENGINEERING_FAILURE
    )
    assert (
        derive_gate_decision(
            offline_outcome="PASSED",
            shadow_outcome="PASSED",
            simulation_outcome="PASSED",
            human_outcome="FAILED",
        )
        is ReleaseGateDecision.REJECTED
    )
    with pytest.raises(ValidationUnavailable):
        derive_gate_decision(
            offline_outcome="PASSED",
            shadow_outcome="PASSED",
            simulation_outcome="PASSED",
            human_outcome="PASSED",
        )


def test_candidate_digest_binds_reviewer_cycle_and_single_command() -> None:
    command = selection()

    first = improvement_input_sha256(principal(), CYCLE_ID, command)
    assert first == improvement_input_sha256(principal(), CYCLE_ID, command)
    assert first != improvement_input_sha256(
        principal(),
        UUID("019b0000-0000-7000-8000-000000000799"),
        command,
    )
    assert (
        required_evaluation_evidence_class("SYNTHETIC_FEEDBACK_WORKFLOW_ONLY")
        == "SYNTHETIC_SIMULATION_ONLY"
    )
    assert (
        required_evaluation_evidence_class("CONSENTED_HUMAN_PARTICIPANT")
        == "CONSENTED_HUMAN_PARTICIPANT"
    )
