from datetime import UTC, datetime
from uuid import UUID

import pytest

from deepaha.contracts.phase9b import (
    AnswerAccessClass,
    DatasetPartition,
    GoldAdjudicationDecisionSchemaV08,
    GoldAnnotationSubmissionSchemaV08,
    GoldAnnotationTaskSchemaV08,
    GoldFieldJudgmentSchemaV08,
    GoldFieldState,
    GoldReviewRole,
)
from deepaha.p9b.annotation import GoldGovernanceError, GoldWorkflow

NOW = datetime(2026, 8, 24, 16, 0, tzinfo=UTC)


def uuid7(index: int) -> UUID:
    return UUID(f"019c0000-0000-7000-8000-{index:012x}")


def locked_task(**updates: object) -> GoldAnnotationTaskSchemaV08:
    values: dict[str, object] = {
        "gold_annotation_task_id": uuid7(1),
        "dataset_manifest_id": uuid7(2),
        "entry_id": "locked-001",
        "partition": DatasetPartition.LOCKED_ACCEPTANCE,
        "answer_access_class": AnswerAccessClass.LOCKED_BLIND,
        "annotator_identity": "human:annotator-a",
        "verifier_identity": "human:verifier-b",
        "adjudicator_identity": "human:adjudicator-c",
        "curator_identity": "human:curator-d",
        "role_attestation_references": {
            "ANNOTATOR": "synthetic-fixture:annotator-a",
            "VERIFIER": "synthetic-fixture:verifier-b",
            "ADJUDICATOR": "synthetic-fixture:adjudicator-c",
            "CURATOR": "synthetic-fixture:curator-d",
        },
        "blind_started_at": NOW,
        "blind_ended_at": None,
        "split_seed_reference": "local-secret-reference:split-seed-v1",
        "status": "BLIND_REVIEW",
        "created_at": NOW,
    }
    values.update(updates)
    return GoldAnnotationTaskSchemaV08.model_validate(values)


def submission(
    *, role: GoldReviewRole, actor: str, value: str, submission_id: int
) -> GoldAnnotationSubmissionSchemaV08:
    return GoldAnnotationSubmissionSchemaV08(
        gold_annotation_submission_id=uuid7(submission_id),
        gold_annotation_task_id=uuid7(1),
        review_role=role,
        actor_identity=actor,
        assisted_calibration=False,
        judgments=[
            GoldFieldJudgmentSchemaV08(
                field_name="application_deadline",
                gold_state=GoldFieldState.KNOWN_SUPPORTED,
                normalized_value=value,
                evidence_block_ids=[uuid7(20)],
                high_impact=True,
                precedence_sensitive=False,
            )
        ],
        submitted_at=NOW,
    )


def test_locked_task_requires_four_distinct_human_responsibility_identities() -> None:
    with pytest.raises(ValueError, match="distinct"):
        locked_task(verifier_identity="human:annotator-a")
    with pytest.raises(ValueError, match="human responsibility identity"):
        locked_task(adjudicator_identity="model:provider:model-a")
    with pytest.raises(ValueError, match="attestation"):
        locked_task(role_attestation_references={})


def test_assistance_is_calibration_only_and_cannot_enter_locked() -> None:
    assisted = submission(
        role=GoldReviewRole.ANNOTATOR,
        actor="human:annotator-a",
        value="2026-09-01",
        submission_id=3,
    ).model_copy(update={"assisted_calibration": True})

    with pytest.raises(GoldGovernanceError, match="CALIBRATION"):
        GoldWorkflow(locked_task()).accept_submission(assisted)


def test_locked_verifier_and_adjudicator_stay_blind_until_independent_submissions() -> None:
    workflow = GoldWorkflow(locked_task())
    annotation = submission(
        role=GoldReviewRole.ANNOTATOR,
        actor="human:annotator-a",
        value="2026-09-01",
        submission_id=3,
    )
    workflow.accept_submission(annotation)

    assert workflow.visible_submissions("human:verifier-b") == ()
    with pytest.raises(GoldGovernanceError, match="both independent"):
        workflow.visible_submissions("human:adjudicator-c")

    verification = submission(
        role=GoldReviewRole.VERIFIER,
        actor="human:verifier-b",
        value="2026-09-02",
        submission_id=4,
    )
    workflow.accept_submission(verification)

    assert workflow.visible_submissions("human:verifier-b") == (annotation, verification)
    assert workflow.visible_submissions("human:adjudicator-c") == (annotation, verification)
    assert workflow.requires_adjudication is True


def test_gold_field_state_never_forces_a_value_for_ambiguous_or_not_observed() -> None:
    with pytest.raises(ValueError, match="normalized_value"):
        GoldFieldJudgmentSchemaV08(
            field_name="major_directory",
            gold_state=GoldFieldState.AMBIGUOUS,
            normalized_value="0809",
            evidence_block_ids=[uuid7(30)],
            high_impact=True,
            precedence_sensitive=False,
        )


def test_conflict_requires_independent_adjudication_before_curator_freeze() -> None:
    workflow = GoldWorkflow(locked_task())
    annotation = submission(
        role=GoldReviewRole.ANNOTATOR,
        actor="human:annotator-a",
        value="2026-09-01",
        submission_id=3,
    )
    verification = submission(
        role=GoldReviewRole.VERIFIER,
        actor="human:verifier-b",
        value="2026-09-02",
        submission_id=4,
    )
    workflow.accept_submission(annotation)
    workflow.accept_submission(verification)

    with pytest.raises(GoldGovernanceError, match="adjudication"):
        workflow.freeze_truth(
            curator_identity="human:curator-d",
            gold_truth_version_id=uuid7(6),
            version=1,
            frozen_at=NOW,
        )

    decision = GoldAdjudicationDecisionSchemaV08(
        gold_adjudication_decision_id=uuid7(5),
        gold_annotation_task_id=uuid7(1),
        annotation_submission_id=uuid7(3),
        verification_submission_id=uuid7(4),
        adjudicator_identity="human:adjudicator-c",
        judgments=annotation.judgments,
        reason_code="OFFICIAL_PRECEDENCE_CONFIRMED",
        decided_at=NOW,
    )
    workflow.accept_adjudication(decision)
    truth = workflow.freeze_truth(
        curator_identity="human:curator-d",
        gold_truth_version_id=uuid7(6),
        version=1,
        frozen_at=NOW,
    )

    assert truth.version == 1
    assert truth.judgments == annotation.judgments
    assert len(truth.truth_hash) == 64


def test_only_assigned_adjudicator_and_curator_can_finalize_truth() -> None:
    workflow = GoldWorkflow(locked_task())
    workflow.accept_submission(
        submission(
            role=GoldReviewRole.ANNOTATOR,
            actor="human:annotator-a",
            value="2026-09-01",
            submission_id=3,
        )
    )
    workflow.accept_submission(
        submission(
            role=GoldReviewRole.VERIFIER,
            actor="human:verifier-b",
            value="2026-09-01",
            submission_id=4,
        )
    )

    with pytest.raises(GoldGovernanceError, match="curator"):
        workflow.freeze_truth(
            curator_identity="human:annotator-a",
            gold_truth_version_id=uuid7(6),
            version=1,
            frozen_at=NOW,
        )
