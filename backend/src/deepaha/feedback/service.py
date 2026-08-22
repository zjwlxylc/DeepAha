import json
from collections.abc import Callable
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid7

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.contracts.phase7 import FeedbackClaimKind
from deepaha.documents.models import EvidenceRef
from deepaha.feedback.models import (
    FeedbackEventModel,
    FeedbackEvidenceLinkModel,
    FeedbackIdempotencyRecordModel,
)
from deepaha.feedback.schemas import (
    FeedbackEvidenceSummary,
    FeedbackEvidenceWrite,
    FeedbackStatusDetail,
    FeedbackStatusPage,
    FeedbackStatusSummary,
    FeedbackSubmissionWrite,
)
from deepaha.matching.models import MatchSnapshotModel
from deepaha.opportunities.models import Opportunity, OpportunityVersion
from deepaha.personal.auth import Principal
from deepaha.personal.models import (
    PersonalRankingItemModel,
    PersonalRankingSnapshotModel,
    PersonalUserModel,
    UserStateSnapshotModel,
)
from deepaha.personal.profile import idempotency_key_sha256
from deepaha.review.models import FeedbackReviewCaseSnapshotModel

SUBMIT_OPERATION = "FEEDBACK_SUBMIT"
EVIDENCE_OPERATION = "FEEDBACK_EVIDENCE_APPEND"
PURPOSE_BY_CLAIM = {
    FeedbackClaimKind.ELIGIBILITY_CORRECTION: "ELIGIBILITY",
    FeedbackClaimKind.OPPORTUNITY_FACT_CORRECTION: "ELIGIBILITY",
    FeedbackClaimKind.EXPLANATION_UNCLEAR: "ELIGIBILITY",
    FeedbackClaimKind.RANKING_IRRELEVANT: "PERSONAL_RANKING",
}


class FeedbackIdempotencyConflict(ValueError):
    pass


class FeedbackUnavailable(ValueError):
    pass


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def feedback_input_sha256(
    principal: Principal,
    public_id: str,
    command: FeedbackSubmissionWrite,
) -> str:
    return _canonical_sha256(
        {
            "owner_user_id": str(principal.user_id),
            "opportunity_public_id": public_id,
            "command": command.model_dump(mode="json"),
        }
    )


def evidence_input_sha256(
    principal: Principal,
    feedback_event_id: UUID,
    command: FeedbackEvidenceWrite,
) -> str:
    return _canonical_sha256(
        {
            "owner_user_id": str(principal.user_id),
            "feedback_event_id": str(feedback_event_id),
            "command": command.model_dump(mode="json"),
        }
    )


def required_user_purpose(claim_kind: FeedbackClaimKind | str) -> str:
    return PURPOSE_BY_CLAIM[FeedbackClaimKind(claim_kind)]


def governed_evidence_ids(
    source_evidence_ref_id: UUID,
    field_evidence: list[dict[str, Any]],
) -> frozenset[UUID]:
    values = {source_evidence_ref_id}
    for item in field_evidence:
        candidate = item.get("evidence_ref_id")
        if candidate is None:
            raise ValueError("field evidence requires evidence_ref_id")
        values.add(UUID(str(candidate)))
    return frozenset(values)


class FeedbackService:
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

    def submit(
        self,
        principal: Principal,
        public_id: str,
        command: FeedbackSubmissionWrite,
        *,
        idempotency_key: str,
    ) -> FeedbackStatusDetail:
        request_sha256 = feedback_input_sha256(principal, public_id, command)
        key_sha256 = idempotency_key_sha256(idempotency_key)
        created_at = self._now_factory()
        with self._session_factory() as session:
            try:
                recorded = self._idempotency_record(
                    session,
                    principal.user_id,
                    SUBMIT_OPERATION,
                    key_sha256,
                )
                if recorded is not None:
                    if recorded.request_sha256 != request_sha256:
                        raise FeedbackIdempotencyConflict("idempotency key conflict")
                    event = self._owned_event(session, principal.user_id, recorded.resource_id)
                    if event is None:
                        raise FeedbackUnavailable("feedback unavailable")
                    session.rollback()
                    return self._detail(session, event)

                context = self._submission_context(session, principal, public_id, command)
                existing = session.scalar(
                    select(FeedbackEventModel).where(
                        FeedbackEventModel.owner_user_id == principal.user_id,
                        FeedbackEventModel.input_sha256 == request_sha256,
                    )
                )
                if existing is not None:
                    self._record_idempotency(
                        session,
                        principal.user_id,
                        SUBMIT_OPERATION,
                        key_sha256,
                        request_sha256,
                        "FEEDBACK_EVENT",
                        existing.feedback_event_id,
                        created_at,
                    )
                    session.commit()
                    return self._detail(session, existing)

                opportunity, version, ranking, item, state = context
                allowed_evidence = governed_evidence_ids(
                    version.source_evidence_ref_id,
                    version.field_evidence,
                )
                if not set(command.initial_evidence_ref_ids) <= allowed_evidence:
                    raise FeedbackUnavailable("feedback unavailable")

                event_id = self._id_factory()
                event = FeedbackEventModel(
                    feedback_event_id=event_id,
                    owner_user_id=principal.user_id,
                    ranking_snapshot_id=ranking.ranking_snapshot_id,
                    match_snapshot_id=item.match_snapshot_id,
                    opportunity_id=opportunity.opportunity_id,
                    opportunity_version=item.opportunity_version,
                    user_state_snapshot_id=state.user_state_snapshot_id,
                    user_state_version=state.version,
                    event_type=command.event_type.value,
                    claim_kind=command.claim_kind.value,
                    user_statement=command.user_statement,
                    structured_reason_code=command.structured_reason_code.value,
                    consent_version=command.consent_version,
                    consent_scope=command.consent_scope.value,
                    contract_version="0.6.0",
                    input_sha256=request_sha256,
                    created_at=created_at,
                )
                session.add(event)
                session.flush()
                for evidence_ref_id in command.initial_evidence_ref_ids:
                    evidence = self._governed_evidence_row(
                        session,
                        evidence_ref_id,
                        allowed_evidence,
                    )
                    session.add(
                        self._evidence_link(
                            principal,
                            event_id,
                            evidence,
                            relation="SUPPORTS",
                            note=None,
                            created_at=created_at,
                        )
                    )
                review_case_id = self._id_factory()
                session.add(
                    FeedbackReviewCaseSnapshotModel(
                        review_case_snapshot_id=self._id_factory(),
                        review_case_id=review_case_id,
                        feedback_event_id=event_id,
                        version=1,
                        status="RECEIVED",
                        priority=self._priority(command.claim_kind),
                        due_at=created_at + timedelta(days=2),
                        assigned_reviewer_id=None,
                        transition_reason="INITIAL_SUBMISSION",
                        input_sha256=_canonical_sha256(
                            {
                                "review_case_id": str(review_case_id),
                                "feedback_event_id": str(event_id),
                                "version": 1,
                                "status": "RECEIVED",
                            }
                        ),
                        created_at=created_at,
                    )
                )
                self._record_idempotency(
                    session,
                    principal.user_id,
                    SUBMIT_OPERATION,
                    key_sha256,
                    request_sha256,
                    "FEEDBACK_EVENT",
                    event_id,
                    created_at,
                )
                session.commit()
                return self._detail(session, event)
            except Exception:
                session.rollback()
                raise

    def append_evidence(
        self,
        principal: Principal,
        feedback_event_id: UUID,
        command: FeedbackEvidenceWrite,
        *,
        idempotency_key: str,
    ) -> FeedbackStatusDetail | None:
        request_sha256 = evidence_input_sha256(principal, feedback_event_id, command)
        key_sha256 = idempotency_key_sha256(idempotency_key)
        created_at = self._now_factory()
        with self._session_factory() as session:
            try:
                event = self._owned_event(session, principal.user_id, feedback_event_id)
                if event is None:
                    session.rollback()
                    return None
                recorded = self._idempotency_record(
                    session,
                    principal.user_id,
                    EVIDENCE_OPERATION,
                    key_sha256,
                )
                if recorded is not None:
                    if recorded.request_sha256 != request_sha256:
                        raise FeedbackIdempotencyConflict("idempotency key conflict")
                    session.rollback()
                    return self._detail(session, event)
                version = session.get(
                    OpportunityVersion,
                    (event.opportunity_id, event.opportunity_version),
                )
                if version is None:
                    raise FeedbackUnavailable("feedback unavailable")
                allowed = governed_evidence_ids(
                    version.source_evidence_ref_id,
                    version.field_evidence,
                )
                evidence = self._governed_evidence_row(
                    session,
                    command.evidence_ref_id,
                    allowed,
                )
                existing = session.scalar(
                    select(FeedbackEvidenceLinkModel).where(
                        FeedbackEvidenceLinkModel.feedback_event_id == feedback_event_id,
                        FeedbackEvidenceLinkModel.input_sha256 == request_sha256,
                    )
                )
                if existing is None:
                    link = self._evidence_link(
                        principal,
                        feedback_event_id,
                        evidence,
                        relation=command.relation.value,
                        note=command.note,
                        created_at=created_at,
                        input_sha256=request_sha256,
                    )
                    session.add(link)
                    session.flush()
                    link_id = link.feedback_evidence_link_id
                else:
                    link_id = existing.feedback_evidence_link_id
                self._record_idempotency(
                    session,
                    principal.user_id,
                    EVIDENCE_OPERATION,
                    key_sha256,
                    request_sha256,
                    "EVIDENCE_LINK",
                    link_id,
                    created_at,
                )
                session.commit()
                return self._detail(session, event)
            except Exception:
                session.rollback()
                raise

    def list_owned(self, principal: Principal) -> FeedbackStatusPage:
        with self._session_factory() as session:
            events = session.scalars(
                select(FeedbackEventModel)
                .where(FeedbackEventModel.owner_user_id == principal.user_id)
                .order_by(
                    FeedbackEventModel.created_at.desc(),
                    FeedbackEventModel.feedback_event_id,
                )
            ).all()
            return FeedbackStatusPage(
                items=tuple(self._summary(session, event) for event in events)
            )

    def get_owned(
        self,
        principal: Principal,
        feedback_event_id: UUID,
    ) -> FeedbackStatusDetail | None:
        with self._session_factory() as session:
            event = self._owned_event(session, principal.user_id, feedback_event_id)
            return None if event is None else self._detail(session, event)

    def _submission_context(
        self,
        session: Session,
        principal: Principal,
        public_id: str,
        command: FeedbackSubmissionWrite,
    ) -> tuple[
        Opportunity,
        OpportunityVersion,
        PersonalRankingSnapshotModel,
        PersonalRankingItemModel,
        UserStateSnapshotModel,
    ]:
        user = session.get(PersonalUserModel, principal.user_id)
        opportunity = session.scalar(select(Opportunity).where(Opportunity.public_id == public_id))
        ranking = session.scalar(
            select(PersonalRankingSnapshotModel).where(
                PersonalRankingSnapshotModel.ranking_snapshot_id == command.ranking_snapshot_id,
                PersonalRankingSnapshotModel.user_id == principal.user_id,
            )
        )
        if user is None or not user.active or opportunity is None or ranking is None:
            raise FeedbackUnavailable("feedback unavailable")
        item = session.scalar(
            select(PersonalRankingItemModel).where(
                PersonalRankingItemModel.ranking_snapshot_id == ranking.ranking_snapshot_id,
                PersonalRankingItemModel.match_snapshot_id == command.match_snapshot_id,
                PersonalRankingItemModel.opportunity_id == opportunity.opportunity_id,
                PersonalRankingItemModel.opportunity_version == command.opportunity_version,
            )
        )
        state = session.get(UserStateSnapshotModel, ranking.user_state_snapshot_id)
        match = session.get(MatchSnapshotModel, command.match_snapshot_id)
        version = session.get(
            OpportunityVersion,
            (opportunity.opportunity_id, command.opportunity_version),
        )
        current_state = session.scalar(
            select(UserStateSnapshotModel)
            .where(UserStateSnapshotModel.user_id == principal.user_id)
            .order_by(UserStateSnapshotModel.version.desc())
            .limit(1)
        )
        purpose = required_user_purpose(command.claim_kind)
        if (
            item is None
            or state is None
            or state.user_id != principal.user_id
            or state.version != command.user_state_version
            or match is None
            or match.opportunity_id != opportunity.opportunity_id
            or match.opportunity_version != command.opportunity_version
            or version is None
            or current_state is None
            or purpose not in current_state.allowed_purposes
        ):
            raise FeedbackUnavailable("feedback unavailable")
        return opportunity, version, ranking, item, state

    @staticmethod
    def _idempotency_record(
        session: Session,
        owner_user_id: UUID,
        operation: str,
        key_sha256: str,
    ) -> FeedbackIdempotencyRecordModel | None:
        return session.get(
            FeedbackIdempotencyRecordModel,
            (owner_user_id, operation, key_sha256),
        )

    @staticmethod
    def _owned_event(
        session: Session,
        owner_user_id: UUID,
        feedback_event_id: UUID,
    ) -> FeedbackEventModel | None:
        return session.scalar(
            select(FeedbackEventModel).where(
                FeedbackEventModel.feedback_event_id == feedback_event_id,
                FeedbackEventModel.owner_user_id == owner_user_id,
            )
        )

    @staticmethod
    def _record_idempotency(
        session: Session,
        owner_user_id: UUID,
        operation: str,
        key_sha256: str,
        request_sha256: str,
        resource_kind: str,
        resource_id: UUID,
        created_at: datetime,
    ) -> None:
        session.add(
            FeedbackIdempotencyRecordModel(
                owner_user_id=owner_user_id,
                operation=operation,
                key_sha256=key_sha256,
                request_sha256=request_sha256,
                resource_kind=resource_kind,
                resource_id=resource_id,
                response_version=1,
                created_at=created_at,
            )
        )
        session.flush()

    def _evidence_link(
        self,
        principal: Principal,
        feedback_event_id: UUID,
        evidence: EvidenceRef,
        *,
        relation: str,
        note: str | None,
        created_at: datetime,
        input_sha256: str | None = None,
    ) -> FeedbackEvidenceLinkModel:
        link_id = self._id_factory()
        digest = input_sha256 or _canonical_sha256(
            {
                "feedback_event_id": str(feedback_event_id),
                "evidence_ref_id": str(evidence.evidence_ref_id),
                "relation": relation,
                "actor_user_id": str(principal.user_id),
            }
        )
        return FeedbackEvidenceLinkModel(
            feedback_evidence_link_id=link_id,
            feedback_event_id=feedback_event_id,
            evidence_ref_id=evidence.evidence_ref_id,
            document_id=evidence.document_id,
            relation=relation,
            actor_kind="USER",
            actor_user_id=principal.user_id,
            actor_reviewer_id=None,
            note=note,
            input_sha256=digest,
            created_at=created_at,
        )

    @staticmethod
    def _governed_evidence_row(
        session: Session,
        evidence_ref_id: UUID,
        allowed: frozenset[UUID],
    ) -> EvidenceRef:
        if evidence_ref_id not in allowed:
            raise FeedbackUnavailable("feedback unavailable")
        evidence = session.get(EvidenceRef, evidence_ref_id)
        if evidence is None:
            raise FeedbackUnavailable("feedback unavailable")
        return evidence

    @staticmethod
    def _priority(claim_kind: FeedbackClaimKind) -> int:
        if claim_kind is FeedbackClaimKind.ELIGIBILITY_CORRECTION:
            return 1
        if claim_kind is FeedbackClaimKind.OPPORTUNITY_FACT_CORRECTION:
            return 2
        return 3

    def _summary(
        self,
        session: Session,
        event: FeedbackEventModel,
    ) -> FeedbackStatusSummary:
        opportunity = session.get(Opportunity, event.opportunity_id)
        latest = session.scalar(
            select(FeedbackReviewCaseSnapshotModel)
            .where(FeedbackReviewCaseSnapshotModel.feedback_event_id == event.feedback_event_id)
            .order_by(FeedbackReviewCaseSnapshotModel.version.desc())
            .limit(1)
        )
        if opportunity is None or latest is None:
            raise FeedbackUnavailable("feedback unavailable")
        return FeedbackStatusSummary.model_validate(
            {
                "feedback_event_id": event.feedback_event_id,
                "opportunity_public_id": opportunity.public_id,
                "opportunity_version": event.opportunity_version,
                "event_type": event.event_type,
                "claim_kind": event.claim_kind,
                "status": latest.status,
                "created_at": event.created_at,
                "status_updated_at": latest.created_at,
            }
        )

    def _detail(
        self,
        session: Session,
        event: FeedbackEventModel,
    ) -> FeedbackStatusDetail:
        rows = session.scalars(
            select(FeedbackEvidenceLinkModel)
            .where(FeedbackEvidenceLinkModel.feedback_event_id == event.feedback_event_id)
            .order_by(
                FeedbackEvidenceLinkModel.created_at,
                FeedbackEvidenceLinkModel.feedback_evidence_link_id,
            )
        ).all()
        return FeedbackStatusDetail(
            feedback=self._summary(session, event),
            evidence=tuple(
                FeedbackEvidenceSummary.model_validate(
                    {
                        "feedback_evidence_link_id": row.feedback_evidence_link_id,
                        "evidence_ref_id": row.evidence_ref_id,
                        "relation": row.relation,
                        "note": row.note if row.actor_kind == "USER" else None,
                        "created_at": row.created_at,
                    }
                )
                for row in rows
            ),
        )


__all__ = [
    "FeedbackIdempotencyConflict",
    "FeedbackService",
    "FeedbackUnavailable",
    "evidence_input_sha256",
    "feedback_input_sha256",
    "governed_evidence_ids",
    "required_user_purpose",
]
