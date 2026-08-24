from datetime import UTC, datetime
from uuid import UUID

import pytest

from deepaha.contracts.phase9b import (
    AnswerAccessClass,
    DatasetPartition,
    GoldAnnotationSubmissionSchemaV08,
    GoldAnnotationTaskSchemaV08,
    GoldFieldJudgmentSchemaV08,
    GoldFieldState,
    GoldReviewRole,
)
from deepaha.p9b.annotation import GoldWorkflow
from deepaha.p9b.gold_import import GoldImportError, validate_gold_import

NOW = datetime(2026, 8, 24, 16, 0, tzinfo=UTC)


def uuid7(index: int) -> UUID:
    return UUID(f"019c0000-0000-7000-8000-{index:012x}")


def locked_task() -> GoldAnnotationTaskSchemaV08:
    return GoldAnnotationTaskSchemaV08(
        gold_annotation_task_id=uuid7(1),
        dataset_manifest_id=uuid7(2),
        entry_id="locked-001",
        partition=DatasetPartition.LOCKED_ACCEPTANCE,
        answer_access_class=AnswerAccessClass.LOCKED_BLIND,
        annotator_identity="human:annotator-a",
        verifier_identity="human:verifier-b",
        adjudicator_identity="human:adjudicator-c",
        curator_identity="human:curator-d",
        role_attestation_references={
            GoldReviewRole.ANNOTATOR: "synthetic-fixture:annotator-a",
            GoldReviewRole.VERIFIER: "synthetic-fixture:verifier-b",
            GoldReviewRole.ADJUDICATOR: "synthetic-fixture:adjudicator-c",
            GoldReviewRole.CURATOR: "synthetic-fixture:curator-d",
        },
        blind_started_at=NOW,
        blind_ended_at=None,
        split_seed_reference="local-secret-reference:split-seed-v1",
        status="BLIND_REVIEW",
        created_at=NOW,
    )


def submission(
    *, role: GoldReviewRole, actor: str, submission_id: int
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
                normalized_value="2026-09-01",
                evidence_block_ids=[uuid7(20)],
                high_impact=True,
                precedence_sensitive=False,
            )
        ],
        submitted_at=NOW,
    )


def import_payload() -> dict[str, object]:
    task = locked_task()
    annotation = submission(
        role=GoldReviewRole.ANNOTATOR,
        actor="human:annotator-a",
        submission_id=3,
    )
    verification = submission(
        role=GoldReviewRole.VERIFIER,
        actor="human:verifier-b",
        submission_id=4,
    )
    workflow = GoldWorkflow(task)
    workflow.accept_submission(annotation)
    workflow.accept_submission(verification)
    truth = workflow.freeze_truth(
        curator_identity="human:curator-d",
        gold_truth_version_id=uuid7(6),
        version=1,
        frozen_at=NOW,
    )
    return {
        "task": task.model_dump(mode="json"),
        "submissions": [
            annotation.model_dump(mode="json"),
            verification.model_dump(mode="json"),
        ],
        "adjudication": None,
        "truth": truth.model_dump(mode="json"),
    }


def test_import_revalidates_the_complete_governed_chain() -> None:
    bundle = validate_gold_import(import_payload(), allow_synthetic=True)

    assert bundle.truth.version == 1


def test_synthetic_identity_references_cannot_be_imported_as_real_gold() -> None:
    with pytest.raises(GoldImportError, match="synthetic"):
        validate_gold_import(import_payload())


def test_import_rejects_rewritten_truth_hash() -> None:
    payload = import_payload()
    assert isinstance(payload["truth"], dict)
    payload["truth"]["truth_hash"] = "f" * 64

    with pytest.raises(GoldImportError, match="canonical"):
        validate_gold_import(payload, allow_synthetic=True)
