import json
from collections.abc import Callable
from datetime import datetime
from hashlib import sha256
from uuid import UUID, uuid7

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.contracts.phase7 import FeedbackAdjudicationDecision
from deepaha.documents.models import EvidenceRef
from deepaha.feedback.models import FeedbackEventModel, FeedbackEvidenceLinkModel
from deepaha.opportunities.models import Opportunity
from deepaha.personal.models import UserStateSnapshotModel
from deepaha.personal.profile import idempotency_key_sha256
from deepaha.profiles.models import ProfileSnapshotModel
from deepaha.review.auth import (
    REVIEW_PURPOSE,
    ReviewerPrincipal,
    ReviewerRole,
    require_reviewer_authority,
)
from deepaha.review.models import (
    ApprovedFeedbackLabelModel,
    FeedbackAdjudicationModel,
    FeedbackConfidenceAssessmentModel,
    FeedbackReviewCaseSnapshotModel,
    ReviewerIdempotencyRecordModel,
)
from deepaha.review.schemas import (
    ApprovedLabelResult,
    ApprovedLabelWrite,
    ConfidenceAssessmentResult,
    ConfidenceAssessmentWrite,
    FeedbackAdjudicationResult,
    FeedbackAdjudicationWrite,
    ReviewCaseDetail,
    ReviewCaseHistoryItem,
    ReviewEvidenceItem,
    ReviewQueueItem,
    ReviewQueuePage,
)

ASSESS_OPERATION = "FEEDBACK_ASSESS"
ADJUDICATE_OPERATION = "FEEDBACK_ADJUDICATE"
LABEL_OPERATION = "FEEDBACK_LABEL"
TERMINAL_STATUSES = frozenset({"CONFIRMED", "REJECTED"})
QUEUE_LIMIT = 100


class ReviewIdempotencyConflict(ValueError):
    pass


class ReviewUnavailable(ValueError):
    pass


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _review_input_sha256(
    principal: ReviewerPrincipal,
    review_case_id: UUID,
    operation: str,
    command: ConfidenceAssessmentWrite | FeedbackAdjudicationWrite | ApprovedLabelWrite,
) -> str:
    return _canonical_sha256(
        {
            "reviewer_id": str(principal.reviewer_id),
            "review_case_id": str(review_case_id),
            "operation": operation,
            "command": command.model_dump(mode="json"),
        }
    )


def assessment_input_sha256(
    principal: ReviewerPrincipal,
    review_case_id: UUID,
    command: ConfidenceAssessmentWrite,
) -> str:
    return _review_input_sha256(principal, review_case_id, ASSESS_OPERATION, command)


def adjudication_input_sha256(
    principal: ReviewerPrincipal,
    review_case_id: UUID,
    command: FeedbackAdjudicationWrite,
) -> str:
    return _review_input_sha256(principal, review_case_id, ADJUDICATE_OPERATION, command)


def label_input_sha256(
    principal: ReviewerPrincipal,
    review_case_id: UUID,
    command: ApprovedLabelWrite,
) -> str:
    return _review_input_sha256(principal, review_case_id, LABEL_OPERATION, command)


def evidence_class_for_profile(*, synthetic: bool) -> str:
    if synthetic:
        return "SYNTHETIC_FEEDBACK_WORKFLOW_ONLY"
    return "CONSENTED_HUMAN_PARTICIPANT"


def assert_adjudication_consistent(
    assessment: ConfidenceAssessmentWrite,
    command: FeedbackAdjudicationWrite,
    *,
    linked_evidence_ids: frozenset[UUID],
) -> None:
    evidence_ids = set(command.evidence_ref_ids)
    if not evidence_ids <= linked_evidence_ids:
        raise ReviewUnavailable("review unavailable")
    if not evidence_ids <= set(assessment.evidence_ref_ids):
        raise ReviewUnavailable("review unavailable")
    if command.decision is FeedbackAdjudicationDecision.CONFIRMED and (
        not assessment.evidence_complete or assessment.conflict or not evidence_ids
    ):
        raise ReviewUnavailable("review unavailable")
    if (
        command.decision is FeedbackAdjudicationDecision.NEEDS_EVIDENCE
        and assessment.evidence_complete
    ):
        raise ReviewUnavailable("review unavailable")
    if command.decision is FeedbackAdjudicationDecision.CONFLICT and not assessment.conflict:
        raise ReviewUnavailable("review unavailable")


class ReviewService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        now_factory: Callable[[], datetime],
        id_factory: Callable[[], UUID] = uuid7,
    ) -> None:
        self._session_factory = session_factory
        self._now_factory = now_factory
        self._id_factory = id_factory

    def list_queue(self, principal: ReviewerPrincipal) -> ReviewQueuePage:
        require_reviewer_authority(principal, ReviewerRole.FEEDBACK_REVIEWER)
        with self._session_factory() as session:
            latest = (
                select(
                    FeedbackReviewCaseSnapshotModel.review_case_id,
                    func.max(FeedbackReviewCaseSnapshotModel.version).label("version"),
                )
                .group_by(FeedbackReviewCaseSnapshotModel.review_case_id)
                .subquery()
            )
            rows = session.execute(
                select(FeedbackReviewCaseSnapshotModel, FeedbackEventModel, Opportunity)
                .join(
                    latest,
                    (latest.c.review_case_id == FeedbackReviewCaseSnapshotModel.review_case_id)
                    & (latest.c.version == FeedbackReviewCaseSnapshotModel.version),
                )
                .join(
                    FeedbackEventModel,
                    FeedbackEventModel.feedback_event_id
                    == FeedbackReviewCaseSnapshotModel.feedback_event_id,
                )
                .join(Opportunity, Opportunity.opportunity_id == FeedbackEventModel.opportunity_id)
                .where(
                    FeedbackReviewCaseSnapshotModel.status.not_in(TERMINAL_STATUSES),
                    FeedbackEventModel.consent_scope == REVIEW_PURPOSE,
                )
                .order_by(
                    FeedbackReviewCaseSnapshotModel.priority,
                    FeedbackReviewCaseSnapshotModel.due_at,
                    FeedbackReviewCaseSnapshotModel.review_case_id,
                )
                .limit(QUEUE_LIMIT)
            ).all()
            now = self._now_factory()
            return ReviewQueuePage(
                items=tuple(
                    self._queue_item(snapshot, event, opportunity, now)
                    for snapshot, event, opportunity in rows
                )
            )

    def get_case(
        self,
        principal: ReviewerPrincipal,
        review_case_id: UUID,
    ) -> ReviewCaseDetail | None:
        require_reviewer_authority(principal, ReviewerRole.FEEDBACK_REVIEWER)
        with self._session_factory() as session:
            context = self._case_context(session, review_case_id)
            if context is None:
                return None
            snapshot, event = context
            return self._case_detail(session, snapshot, event)

    def append_assessment(
        self,
        principal: ReviewerPrincipal,
        review_case_id: UUID,
        command: ConfidenceAssessmentWrite,
        *,
        idempotency_key: str,
    ) -> ConfidenceAssessmentResult | None:
        require_reviewer_authority(principal, ReviewerRole.FEEDBACK_REVIEWER)
        request_sha256 = assessment_input_sha256(principal, review_case_id, command)
        key_sha256 = idempotency_key_sha256(idempotency_key)
        created_at = self._now_factory()
        with self._session_factory() as session:
            try:
                replay = self._replay(
                    session,
                    principal,
                    ASSESS_OPERATION,
                    key_sha256,
                    request_sha256,
                    FeedbackConfidenceAssessmentModel,
                )
                if replay is not None:
                    session.rollback()
                    return self._assessment_result(replay)
                context = self._case_context(session, review_case_id)
                if context is None or context[0].status in TERMINAL_STATUSES:
                    session.rollback()
                    return None
                snapshot, event = context
                linked = self._linked_evidence_ids(session, event.feedback_event_id)
                if not set(command.evidence_ref_ids) <= linked:
                    raise ReviewUnavailable("review unavailable")
                row = FeedbackConfidenceAssessmentModel(
                    confidence_assessment_id=self._id_factory(),
                    review_case_id=review_case_id,
                    review_case_version=snapshot.version,
                    evidence_complete=command.evidence_complete,
                    confidence_band=command.confidence_band.value,
                    risk_level=command.risk_level.value,
                    conflict=command.conflict,
                    evidence_ref_ids=[str(value) for value in command.evidence_ref_ids],
                    rationale=command.rationale,
                    reviewer_id=principal.reviewer_id,
                    review_purpose=REVIEW_PURPOSE,
                    input_sha256=request_sha256,
                    created_at=created_at,
                )
                session.add(row)
                session.flush()
                self._record_idempotency(
                    session,
                    principal,
                    ASSESS_OPERATION,
                    key_sha256,
                    request_sha256,
                    "ASSESSMENT",
                    row.confidence_assessment_id,
                    created_at,
                )
                session.commit()
                return self._assessment_result(row)
            except Exception:
                session.rollback()
                raise

    def append_adjudication(
        self,
        principal: ReviewerPrincipal,
        review_case_id: UUID,
        command: FeedbackAdjudicationWrite,
        *,
        idempotency_key: str,
    ) -> FeedbackAdjudicationResult | None:
        require_reviewer_authority(principal, ReviewerRole.FEEDBACK_ADJUDICATOR)
        request_sha256 = adjudication_input_sha256(principal, review_case_id, command)
        key_sha256 = idempotency_key_sha256(idempotency_key)
        created_at = self._now_factory()
        with self._session_factory() as session:
            try:
                replay = self._replay(
                    session,
                    principal,
                    ADJUDICATE_OPERATION,
                    key_sha256,
                    request_sha256,
                    FeedbackAdjudicationModel,
                )
                if replay is not None:
                    session.rollback()
                    return self._adjudication_result(replay)
                context = self._case_context(session, review_case_id)
                if context is None or context[0].status in TERMINAL_STATUSES:
                    session.rollback()
                    return None
                snapshot, event = context
                if snapshot.status == command.decision.value:
                    raise ReviewUnavailable("review unavailable")
                assessment = session.get(
                    FeedbackConfidenceAssessmentModel,
                    command.confidence_assessment_id,
                )
                latest_assessment = session.scalar(
                    select(FeedbackConfidenceAssessmentModel)
                    .where(
                        FeedbackConfidenceAssessmentModel.review_case_id == review_case_id,
                        FeedbackConfidenceAssessmentModel.review_case_version == snapshot.version,
                    )
                    .order_by(
                        FeedbackConfidenceAssessmentModel.created_at.desc(),
                        FeedbackConfidenceAssessmentModel.confidence_assessment_id.desc(),
                    )
                    .limit(1)
                )
                if (
                    assessment is None
                    or latest_assessment is None
                    or assessment.confidence_assessment_id
                    != latest_assessment.confidence_assessment_id
                ):
                    raise ReviewUnavailable("review unavailable")
                assessment_command = ConfidenceAssessmentWrite.model_validate(
                    {
                        "evidence_complete": assessment.evidence_complete,
                        "confidence_band": assessment.confidence_band,
                        "risk_level": assessment.risk_level,
                        "conflict": assessment.conflict,
                        "evidence_ref_ids": assessment.evidence_ref_ids,
                        "rationale": assessment.rationale,
                    }
                )
                assert_adjudication_consistent(
                    assessment_command,
                    command,
                    linked_evidence_ids=self._linked_evidence_ids(
                        session,
                        event.feedback_event_id,
                    ),
                )
                adjudication = FeedbackAdjudicationModel(
                    feedback_adjudication_id=self._id_factory(),
                    review_case_id=review_case_id,
                    review_case_version=snapshot.version,
                    confidence_assessment_id=assessment.confidence_assessment_id,
                    decision=command.decision.value,
                    evidence_ref_ids=[str(value) for value in command.evidence_ref_ids],
                    reason=command.reason,
                    adjudicator_id=principal.reviewer_id,
                    review_purpose=REVIEW_PURPOSE,
                    input_sha256=request_sha256,
                    created_at=created_at,
                )
                session.add(adjudication)
                session.add(
                    FeedbackReviewCaseSnapshotModel(
                        review_case_snapshot_id=self._id_factory(),
                        review_case_id=review_case_id,
                        feedback_event_id=event.feedback_event_id,
                        version=snapshot.version + 1,
                        status=command.decision.value,
                        priority=snapshot.priority,
                        due_at=snapshot.due_at,
                        assigned_reviewer_id=snapshot.assigned_reviewer_id,
                        transition_reason=f"HUMAN_ADJUDICATION_{command.decision.value}",
                        input_sha256=_canonical_sha256(
                            {
                                "review_case_id": str(review_case_id),
                                "version": snapshot.version + 1,
                                "adjudication_input_sha256": request_sha256,
                            }
                        ),
                        created_at=created_at,
                    )
                )
                session.flush()
                self._record_idempotency(
                    session,
                    principal,
                    ADJUDICATE_OPERATION,
                    key_sha256,
                    request_sha256,
                    "ADJUDICATION",
                    adjudication.feedback_adjudication_id,
                    created_at,
                )
                session.commit()
                return self._adjudication_result(adjudication)
            except Exception:
                session.rollback()
                raise

    def create_label(
        self,
        principal: ReviewerPrincipal,
        review_case_id: UUID,
        command: ApprovedLabelWrite,
        *,
        idempotency_key: str,
    ) -> ApprovedLabelResult | None:
        require_reviewer_authority(principal, ReviewerRole.LABEL_CURATOR)
        request_sha256 = label_input_sha256(principal, review_case_id, command)
        key_sha256 = idempotency_key_sha256(idempotency_key)
        created_at = self._now_factory()
        with self._session_factory() as session:
            try:
                replay = self._replay(
                    session,
                    principal,
                    LABEL_OPERATION,
                    key_sha256,
                    request_sha256,
                    ApprovedFeedbackLabelModel,
                )
                if replay is not None:
                    session.rollback()
                    return self._label_result(replay)
                context = self._case_context(session, review_case_id)
                if context is None or context[0].status != "CONFIRMED":
                    session.rollback()
                    return None
                snapshot, event = context
                adjudication = session.get(
                    FeedbackAdjudicationModel,
                    command.feedback_adjudication_id,
                )
                if (
                    adjudication is None
                    or adjudication.review_case_id != review_case_id
                    or adjudication.review_case_version + 1 != snapshot.version
                    or adjudication.decision != "CONFIRMED"
                    or not set(command.evidence_ref_ids)
                    <= set(UUID(value) for value in adjudication.evidence_ref_ids)
                    or not set(command.evidence_ref_ids)
                    <= self._linked_evidence_ids(session, event.feedback_event_id)
                ):
                    raise ReviewUnavailable("review unavailable")
                state = session.get(UserStateSnapshotModel, event.user_state_snapshot_id)
                profile = (
                    None
                    if state is None
                    else session.get(ProfileSnapshotModel, state.qualification_profile_snapshot_id)
                )
                if profile is None:
                    raise ReviewUnavailable("review unavailable")
                evidence_class = evidence_class_for_profile(synthetic=profile.synthetic)
                content_sha256 = _canonical_sha256(
                    {
                        "feedback_event_id": str(event.feedback_event_id),
                        "feedback_adjudication_id": str(adjudication.feedback_adjudication_id),
                        "match_snapshot_id": str(event.match_snapshot_id),
                        "opportunity_id": str(event.opportunity_id),
                        "opportunity_version": event.opportunity_version,
                        "claim_kind": event.claim_kind,
                        "approved_target_value": command.approved_target_value,
                        "evidence_ref_ids": [str(value) for value in command.evidence_ref_ids],
                        "evidence_class": evidence_class,
                    }
                )
                label = ApprovedFeedbackLabelModel(
                    approved_feedback_label_id=self._id_factory(),
                    feedback_event_id=event.feedback_event_id,
                    feedback_adjudication_id=adjudication.feedback_adjudication_id,
                    match_snapshot_id=event.match_snapshot_id,
                    opportunity_id=event.opportunity_id,
                    opportunity_version=event.opportunity_version,
                    claim_kind=event.claim_kind,
                    approved_target_value=command.approved_target_value,
                    evidence_ref_ids=[str(value) for value in command.evidence_ref_ids],
                    evidence_class=evidence_class,
                    curator_id=principal.reviewer_id,
                    content_sha256=content_sha256,
                    created_at=created_at,
                )
                session.add(label)
                session.flush()
                self._record_idempotency(
                    session,
                    principal,
                    LABEL_OPERATION,
                    key_sha256,
                    request_sha256,
                    "LABEL",
                    label.approved_feedback_label_id,
                    created_at,
                )
                session.commit()
                return self._label_result(label)
            except Exception:
                session.rollback()
                raise

    @staticmethod
    def _latest_case(
        session: Session,
        review_case_id: UUID,
    ) -> FeedbackReviewCaseSnapshotModel | None:
        return session.scalar(
            select(FeedbackReviewCaseSnapshotModel)
            .where(FeedbackReviewCaseSnapshotModel.review_case_id == review_case_id)
            .order_by(FeedbackReviewCaseSnapshotModel.version.desc())
            .limit(1)
        )

    @classmethod
    def _case_context(
        cls,
        session: Session,
        review_case_id: UUID,
    ) -> tuple[FeedbackReviewCaseSnapshotModel, FeedbackEventModel] | None:
        snapshot = cls._latest_case(session, review_case_id)
        if snapshot is None:
            return None
        event = session.get(FeedbackEventModel, snapshot.feedback_event_id)
        if event is None or event.consent_scope != REVIEW_PURPOSE:
            return None
        return snapshot, event

    @staticmethod
    def _linked_evidence_ids(session: Session, feedback_event_id: UUID) -> frozenset[UUID]:
        return frozenset(
            session.scalars(
                select(FeedbackEvidenceLinkModel.evidence_ref_id).where(
                    FeedbackEvidenceLinkModel.feedback_event_id == feedback_event_id
                )
            ).all()
        )

    @staticmethod
    def _replay[
        ModelT: FeedbackConfidenceAssessmentModel
        | FeedbackAdjudicationModel
        | ApprovedFeedbackLabelModel
    ](
        session: Session,
        principal: ReviewerPrincipal,
        operation: str,
        key_sha256: str,
        request_sha256: str,
        model: type[ModelT],
    ) -> ModelT | None:
        record = session.get(
            ReviewerIdempotencyRecordModel,
            (principal.reviewer_id, operation, key_sha256),
        )
        if record is None:
            return None
        if record.request_sha256 != request_sha256:
            raise ReviewIdempotencyConflict("idempotency key conflict")
        resource = session.get(model, record.resource_id)
        if resource is None:
            raise ReviewUnavailable("review unavailable")
        return resource

    @staticmethod
    def _record_idempotency(
        session: Session,
        principal: ReviewerPrincipal,
        operation: str,
        key_sha256: str,
        request_sha256: str,
        resource_kind: str,
        resource_id: UUID,
        created_at: datetime,
    ) -> None:
        session.add(
            ReviewerIdempotencyRecordModel(
                reviewer_id=principal.reviewer_id,
                operation=operation,
                key_sha256=key_sha256,
                request_sha256=request_sha256,
                resource_kind=resource_kind,
                resource_id=resource_id,
                created_at=created_at,
            )
        )
        session.flush()

    def _case_detail(
        self,
        session: Session,
        snapshot: FeedbackReviewCaseSnapshotModel,
        event: FeedbackEventModel,
    ) -> ReviewCaseDetail:
        opportunity = session.get(Opportunity, event.opportunity_id)
        if opportunity is None:
            raise ReviewUnavailable("review unavailable")
        history = session.scalars(
            select(FeedbackReviewCaseSnapshotModel)
            .where(FeedbackReviewCaseSnapshotModel.review_case_id == snapshot.review_case_id)
            .order_by(FeedbackReviewCaseSnapshotModel.version)
        ).all()
        evidence_rows = session.execute(
            select(FeedbackEvidenceLinkModel, EvidenceRef)
            .join(
                EvidenceRef,
                EvidenceRef.evidence_ref_id == FeedbackEvidenceLinkModel.evidence_ref_id,
            )
            .where(FeedbackEvidenceLinkModel.feedback_event_id == event.feedback_event_id)
            .order_by(
                FeedbackEvidenceLinkModel.created_at,
                FeedbackEvidenceLinkModel.feedback_evidence_link_id,
            )
        ).all()
        assessment = session.scalar(
            select(FeedbackConfidenceAssessmentModel)
            .where(FeedbackConfidenceAssessmentModel.review_case_id == snapshot.review_case_id)
            .order_by(
                FeedbackConfidenceAssessmentModel.created_at.desc(),
                FeedbackConfidenceAssessmentModel.confidence_assessment_id.desc(),
            )
            .limit(1)
        )
        adjudication = session.scalar(
            select(FeedbackAdjudicationModel)
            .where(FeedbackAdjudicationModel.review_case_id == snapshot.review_case_id)
            .order_by(
                FeedbackAdjudicationModel.created_at.desc(),
                FeedbackAdjudicationModel.feedback_adjudication_id.desc(),
            )
            .limit(1)
        )
        label = (
            None
            if adjudication is None
            else session.scalar(
                select(ApprovedFeedbackLabelModel).where(
                    ApprovedFeedbackLabelModel.feedback_adjudication_id
                    == adjudication.feedback_adjudication_id
                )
            )
        )
        return ReviewCaseDetail(
            case=self._queue_item(snapshot, event, opportunity, self._now_factory()),
            user_statement=event.user_statement,
            structured_reason_code=event.structured_reason_code,
            match_snapshot_id=event.match_snapshot_id,
            history=tuple(
                ReviewCaseHistoryItem.model_validate(
                    {
                        "version": item.version,
                        "status": item.status,
                        "priority": item.priority,
                        "due_at": item.due_at,
                        "transition_reason": item.transition_reason,
                        "created_at": item.created_at,
                    }
                )
                for item in history
            ),
            evidence=tuple(
                ReviewEvidenceItem.model_validate(
                    {
                        "evidence_ref_id": link.evidence_ref_id,
                        "document_id": evidence.document_id,
                        "locator_kind": evidence.locator_kind,
                        "locator_value": evidence.locator_value,
                        "relation": link.relation,
                        "actor_kind": link.actor_kind,
                        "note": link.note,
                        "created_at": link.created_at,
                    }
                )
                for link, evidence in evidence_rows
            ),
            latest_assessment=None if assessment is None else self._assessment_result(assessment),
            latest_adjudication=(
                None if adjudication is None else self._adjudication_result(adjudication)
            ),
            approved_label_id=None if label is None else label.approved_feedback_label_id,
        )

    @staticmethod
    def _queue_item(
        snapshot: FeedbackReviewCaseSnapshotModel,
        event: FeedbackEventModel,
        opportunity: Opportunity,
        now: datetime,
    ) -> ReviewQueueItem:
        return ReviewQueueItem.model_validate(
            {
                "review_case_id": snapshot.review_case_id,
                "feedback_event_id": event.feedback_event_id,
                "version": snapshot.version,
                "status": snapshot.status,
                "priority": snapshot.priority,
                "due_at": snapshot.due_at,
                "overdue": snapshot.status not in TERMINAL_STATUSES and snapshot.due_at < now,
                "claim_kind": event.claim_kind,
                "opportunity_public_id": opportunity.public_id,
                "opportunity_title": opportunity.canonical_title,
                "opportunity_version": event.opportunity_version,
                "created_at": snapshot.created_at,
            }
        )

    @staticmethod
    def _assessment_result(
        row: FeedbackConfidenceAssessmentModel,
    ) -> ConfidenceAssessmentResult:
        return ConfidenceAssessmentResult.model_validate(
            {
                "confidence_assessment_id": row.confidence_assessment_id,
                "review_case_id": row.review_case_id,
                "review_case_version": row.review_case_version,
                "evidence_complete": row.evidence_complete,
                "confidence_band": row.confidence_band,
                "risk_level": row.risk_level,
                "conflict": row.conflict,
                "evidence_ref_ids": row.evidence_ref_ids,
                "rationale": row.rationale,
                "created_at": row.created_at,
            }
        )

    @staticmethod
    def _adjudication_result(row: FeedbackAdjudicationModel) -> FeedbackAdjudicationResult:
        return FeedbackAdjudicationResult.model_validate(
            {
                "feedback_adjudication_id": row.feedback_adjudication_id,
                "review_case_id": row.review_case_id,
                "review_case_version": row.review_case_version,
                "confidence_assessment_id": row.confidence_assessment_id,
                "decision": row.decision,
                "evidence_ref_ids": row.evidence_ref_ids,
                "reason": row.reason,
                "created_at": row.created_at,
                "resulting_case_version": row.review_case_version + 1,
            }
        )

    @staticmethod
    def _label_result(row: ApprovedFeedbackLabelModel) -> ApprovedLabelResult:
        return ApprovedLabelResult.model_validate(
            {
                "approved_feedback_label_id": row.approved_feedback_label_id,
                "feedback_event_id": row.feedback_event_id,
                "feedback_adjudication_id": row.feedback_adjudication_id,
                "claim_kind": row.claim_kind,
                "approved_target_value": row.approved_target_value,
                "evidence_ref_ids": row.evidence_ref_ids,
                "evidence_class": row.evidence_class,
                "created_at": row.created_at,
            }
        )


__all__ = [
    "ReviewIdempotencyConflict",
    "ReviewService",
    "ReviewUnavailable",
    "adjudication_input_sha256",
    "assert_adjudication_consistent",
    "assessment_input_sha256",
    "evidence_class_for_profile",
    "label_input_sha256",
]
