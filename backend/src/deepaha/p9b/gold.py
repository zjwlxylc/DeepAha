from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid7

from sqlalchemy import select
from sqlalchemy.orm import Session

from deepaha.contracts.phase9b import (
    GoldAdjudicationDecisionSchemaV08,
    GoldAnnotationSubmissionSchemaV08,
    GoldAnnotationTaskSchemaV08,
    GoldFieldJudgmentSchemaV08,
    GoldTruthVersionSchemaV08,
)
from deepaha.p9b.hashing import gold_truth_hash
from deepaha.p9b.models import (
    GoldAdjudicationDecision,
    GoldAnnotationSubmission,
    GoldAnnotationTask,
    GoldAnswerAccessEvent,
    GoldTruthVersion,
)


class GoldPersistenceError(ValueError):
    pass


@dataclass(frozen=True)
class GoldEvidenceSummary:
    frozen_truth_count: int
    distinct_human_identity_count: int
    status: str


def _judgments(
    values: Sequence[GoldFieldJudgmentSchemaV08],
) -> list[dict[str, object]]:
    return [item.model_dump(mode="json") for item in values]


def _truth_hash_payload(truth: GoldTruthVersionSchemaV08) -> dict[str, object]:
    return {
        "gold_annotation_task_id": str(truth.gold_annotation_task_id),
        "version": truth.version,
        "supersedes_truth_version_id": (
            str(truth.supersedes_truth_version_id)
            if truth.supersedes_truth_version_id is not None
            else None
        ),
        "revision_reason_code": truth.revision_reason_code,
        "source_submission_ids": [str(value) for value in truth.source_submission_ids],
        "adjudication_decision_id": (
            str(truth.adjudication_decision_id)
            if truth.adjudication_decision_id is not None
            else None
        ),
        "judgments": _judgments(truth.judgments),
    }


class GoldRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def persist_task(self, task: GoldAnnotationTaskSchemaV08) -> GoldAnnotationTask:
        row = GoldAnnotationTask(
            gold_annotation_task_id=task.gold_annotation_task_id,
            dataset_manifest_id=task.dataset_manifest_id,
            entry_id=task.entry_id,
            partition=task.partition.value,
            answer_access_class=task.answer_access_class.value,
            annotator_identity=task.annotator_identity,
            verifier_identity=task.verifier_identity,
            adjudicator_identity=task.adjudicator_identity,
            curator_identity=task.curator_identity,
            role_attestation_references={
                role.value: reference
                for role, reference in task.role_attestation_references.items()
            },
            blind_started_at=task.blind_started_at,
            blind_ended_at=task.blind_ended_at,
            split_seed_reference=task.split_seed_reference,
            status=task.status,
            created_at=task.created_at,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def persist_submission(
        self, submission: GoldAnnotationSubmissionSchemaV08
    ) -> GoldAnnotationSubmission:
        row = GoldAnnotationSubmission(
            gold_annotation_submission_id=submission.gold_annotation_submission_id,
            gold_annotation_task_id=submission.gold_annotation_task_id,
            review_role=submission.review_role.value,
            actor_identity=submission.actor_identity,
            assisted_calibration=submission.assisted_calibration,
            judgments=_judgments(submission.judgments),
            submitted_at=submission.submitted_at,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def persist_adjudication(
        self, decision: GoldAdjudicationDecisionSchemaV08
    ) -> GoldAdjudicationDecision:
        row = GoldAdjudicationDecision(
            gold_adjudication_decision_id=decision.gold_adjudication_decision_id,
            gold_annotation_task_id=decision.gold_annotation_task_id,
            annotation_submission_id=decision.annotation_submission_id,
            verification_submission_id=decision.verification_submission_id,
            adjudicator_identity=decision.adjudicator_identity,
            judgments=_judgments(decision.judgments),
            reason_code=decision.reason_code,
            decided_at=decision.decided_at,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def persist_truth(self, truth: GoldTruthVersionSchemaV08) -> GoldTruthVersion:
        if gold_truth_hash(_truth_hash_payload(truth)) != truth.truth_hash:
            raise GoldPersistenceError("Gold truth hash does not match canonical content")
        self.record_answer_access(
            task_id=truth.gold_annotation_task_id,
            requester_identity=truth.curator_identity,
            requester_role="CURATOR",
            access_kind="GOLD_ANSWER",
            decision="GRANTED",
            reason_code="BLIND_REVIEW_COMPLETED_AFTER_TWO_SUBMISSIONS",
            occurred_at=truth.frozen_at,
        )
        row = GoldTruthVersion(
            gold_truth_version_id=truth.gold_truth_version_id,
            gold_annotation_task_id=truth.gold_annotation_task_id,
            version=truth.version,
            supersedes_truth_version_id=truth.supersedes_truth_version_id,
            revision_reason_code=truth.revision_reason_code,
            annotation_submission_id=truth.source_submission_ids[0],
            verification_submission_id=truth.source_submission_ids[1],
            adjudication_decision_id=truth.adjudication_decision_id,
            curator_identity=truth.curator_identity,
            judgments=_judgments(truth.judgments),
            truth_hash=truth.truth_hash,
            frozen_at=truth.frozen_at,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def record_answer_access(
        self,
        *,
        task_id: UUID,
        requester_identity: str,
        requester_role: str,
        access_kind: str,
        decision: str,
        reason_code: str,
        occurred_at: datetime,
    ) -> GoldAnswerAccessEvent:
        row = GoldAnswerAccessEvent(
            gold_answer_access_event_id=uuid7(),
            gold_annotation_task_id=task_id,
            requester_identity=requester_identity,
            requester_role=requester_role,
            access_kind=access_kind,
            decision=decision,
            reason_code=reason_code,
            occurred_at=occurred_at,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def evidence_summary(self) -> GoldEvidenceSummary:
        identities: set[str] = set()
        real_task_ids: set[UUID] = set()
        for task in self._session.scalars(select(GoldAnnotationTask)):
            references = task.role_attestation_references.values()
            if any(
                reference.startswith(("synthetic:", "synthetic-fixture:"))
                for reference in references
            ):
                continue
            real_task_ids.add(task.gold_annotation_task_id)
            identities.update(
                {
                    task.annotator_identity,
                    task.verifier_identity,
                    task.adjudicator_identity,
                    task.curator_identity,
                }
            )
        truth_count = sum(
            truth.gold_annotation_task_id in real_task_ids
            for truth in self._session.scalars(select(GoldTruthVersion))
        )
        return GoldEvidenceSummary(
            frozen_truth_count=truth_count,
            distinct_human_identity_count=len(identities),
            status="OBSERVED" if truth_count else "NOT_OBSERVED",
        )


__all__ = [
    "GoldEvidenceSummary",
    "GoldPersistenceError",
    "GoldRepository",
]
