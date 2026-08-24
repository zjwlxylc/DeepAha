from datetime import datetime
from uuid import UUID

from deepaha.contracts.phase9b import (
    DatasetPartition,
    GoldAdjudicationDecisionSchemaV08,
    GoldAnnotationSubmissionSchemaV08,
    GoldAnnotationTaskSchemaV08,
    GoldReviewRole,
    GoldTruthVersionSchemaV08,
)
from deepaha.p9b.hashing import gold_truth_hash


class GoldGovernanceError(ValueError):
    pass


class GoldWorkflow:
    """Enforce the human responsibility and blind-state contract in memory.

    Persistence repeats these checks at the database boundary; this object is the
    deterministic contract used by annotation import tooling before any write.
    """

    def __init__(self, task: GoldAnnotationTaskSchemaV08) -> None:
        self.task = task
        self._submissions: dict[GoldReviewRole, GoldAnnotationSubmissionSchemaV08] = {}
        self._adjudication: GoldAdjudicationDecisionSchemaV08 | None = None

    def accept_submission(self, submission: GoldAnnotationSubmissionSchemaV08) -> None:
        if submission.gold_annotation_task_id != self.task.gold_annotation_task_id:
            raise GoldGovernanceError("submission belongs to another Gold task")
        expected_identity = {
            GoldReviewRole.ANNOTATOR: self.task.annotator_identity,
            GoldReviewRole.VERIFIER: self.task.verifier_identity,
        }[submission.review_role]
        if submission.actor_identity != expected_identity:
            raise GoldGovernanceError("submission actor does not own the assigned review role")
        if submission.assisted_calibration and self.task.partition != DatasetPartition.CALIBRATION:
            raise GoldGovernanceError("assistance is permitted only for CALIBRATION")
        if submission.review_role in self._submissions:
            raise GoldGovernanceError("review role already has an immutable submission")
        self._submissions[submission.review_role] = submission

    def visible_submissions(
        self, actor_identity: str
    ) -> tuple[GoldAnnotationSubmissionSchemaV08, ...]:
        annotation = self._submissions.get(GoldReviewRole.ANNOTATOR)
        verification = self._submissions.get(GoldReviewRole.VERIFIER)
        available = tuple(value for value in (annotation, verification) if value is not None)
        if actor_identity == self.task.annotator_identity:
            return (annotation,) if annotation is not None else ()
        if actor_identity == self.task.verifier_identity:
            return available if verification is not None else ()
        if actor_identity == self.task.adjudicator_identity:
            if annotation is None or verification is None:
                raise GoldGovernanceError(
                    "adjudicator unlock requires both independent submissions"
                )
            return available
        if actor_identity == self.task.curator_identity:
            return available if annotation is not None and verification is not None else ()
        raise GoldGovernanceError("actor has no Gold answer access")

    @property
    def requires_adjudication(self) -> bool:
        annotation = self._submissions.get(GoldReviewRole.ANNOTATOR)
        verification = self._submissions.get(GoldReviewRole.VERIFIER)
        return bool(
            annotation is not None
            and verification is not None
            and annotation.judgments != verification.judgments
        )

    def accept_adjudication(self, decision: GoldAdjudicationDecisionSchemaV08) -> None:
        annotation = self._submissions.get(GoldReviewRole.ANNOTATOR)
        verification = self._submissions.get(GoldReviewRole.VERIFIER)
        if annotation is None or verification is None:
            raise GoldGovernanceError("adjudication requires both independent submissions")
        if decision.gold_annotation_task_id != self.task.gold_annotation_task_id:
            raise GoldGovernanceError("adjudication belongs to another Gold task")
        if decision.adjudicator_identity != self.task.adjudicator_identity:
            raise GoldGovernanceError("only the assigned adjudicator may decide")
        if (
            decision.annotation_submission_id != annotation.gold_annotation_submission_id
            or decision.verification_submission_id != verification.gold_annotation_submission_id
        ):
            raise GoldGovernanceError("adjudication must bind the two independent submissions")
        if self._adjudication is not None:
            raise GoldGovernanceError("adjudication decision is immutable")
        self._adjudication = decision

    def freeze_truth(
        self,
        *,
        curator_identity: str,
        gold_truth_version_id: UUID,
        version: int,
        frozen_at: datetime,
        supersedes_truth_version_id: UUID | None = None,
        revision_reason_code: str = "INITIAL_FREEZE",
    ) -> GoldTruthVersionSchemaV08:
        if curator_identity != self.task.curator_identity:
            raise GoldGovernanceError("only the assigned curator may freeze Gold truth")
        annotation = self._submissions.get(GoldReviewRole.ANNOTATOR)
        verification = self._submissions.get(GoldReviewRole.VERIFIER)
        if annotation is None or verification is None:
            raise GoldGovernanceError("Gold truth requires both independent submissions")
        if self.requires_adjudication and self._adjudication is None:
            raise GoldGovernanceError("conflicting submissions require independent adjudication")
        judgments = (
            self._adjudication.judgments if self._adjudication is not None else annotation.judgments
        )
        payload = {
            "gold_annotation_task_id": str(self.task.gold_annotation_task_id),
            "version": version,
            "supersedes_truth_version_id": (
                str(supersedes_truth_version_id)
                if supersedes_truth_version_id is not None
                else None
            ),
            "revision_reason_code": revision_reason_code,
            "source_submission_ids": [
                str(annotation.gold_annotation_submission_id),
                str(verification.gold_annotation_submission_id),
            ],
            "adjudication_decision_id": (
                str(self._adjudication.gold_adjudication_decision_id)
                if self._adjudication is not None
                else None
            ),
            "judgments": [item.model_dump(mode="json") for item in judgments],
        }
        return GoldTruthVersionSchemaV08(
            gold_truth_version_id=gold_truth_version_id,
            gold_annotation_task_id=self.task.gold_annotation_task_id,
            version=version,
            supersedes_truth_version_id=supersedes_truth_version_id,
            revision_reason_code=revision_reason_code,
            source_submission_ids=[
                annotation.gold_annotation_submission_id,
                verification.gold_annotation_submission_id,
            ],
            adjudication_decision_id=(
                self._adjudication.gold_adjudication_decision_id
                if self._adjudication is not None
                else None
            ),
            curator_identity=curator_identity,
            judgments=judgments,
            truth_hash=gold_truth_hash(payload),
            frozen_at=frozen_at,
        )


__all__ = ["GoldGovernanceError", "GoldWorkflow"]
