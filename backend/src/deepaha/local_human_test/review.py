from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID, uuid7

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.contracts.phase4 import RuleField, RuleOperator, RuleValueType
from deepaha.contracts.phase9b import (
    EvidenceSupportResult,
    ExtractionTargetScope,
    FactVerificationDecision,
    FactVerificationDecisionSchemaV08,
    PrecedenceCheckResult,
    ProposedRulePayloadSchemaV08,
    RuleApprovalDecisionSchemaV08,
    RuleApprovalDecisionValue,
    RuleApprovalMethod,
    RuleCandidateSchemaV08,
    RuleCandidateStatus,
    VerificationMethod,
)
from deepaha.local_human_test.contracts import ItemStatus, ReviewDecisionKind
from deepaha.local_human_test.models import (
    LocalHumanTestItem,
    LocalHumanTestReviewDecision,
)
from deepaha.local_human_test.runs import assert_item_transition
from deepaha.p9b.facts import FactLifecycleService
from deepaha.p9b.hashing import model_request_hash
from deepaha.p9b.models import (
    ExtractionCandidate,
    FactVerificationDecisionModel,
    RuleApprovalDecisionModel,
    RuleCandidateEvidence,
    RuleCandidateFact,
    RuleCandidateModel,
    VerifiedFact,
    VerifiedFactEvidence,
    VersionedVerifiedFactSet,
)
from deepaha.p9b.rules import RulePromotionService
from deepaha.review.auth import (
    OPPORTUNITY_FACT_VALIDATION_PURPOSE,
    ReviewerAuthenticationError,
    ReviewerPrincipal,
    ReviewerRole,
    require_reviewer_authority,
)

RULE_DERIVATION_VERSION = "1.0.1"


class HumanReviewError(ValueError):
    pass


class ReviewIdempotencyConflict(HumanReviewError):
    pass


class FactDecisionCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: UUID
    candidate_id: UUID
    decision: Literal["APPROVE", "REJECT", "UNKNOWN"]
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("reason must not have surrounding whitespace")
        return value


class RuleDecisionCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: UUID
    rule_candidate_id: UUID
    decision: Literal["APPROVE", "REJECT", "NEEDS_ADJUDICATION"]
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("reason must not have surrounding whitespace")
        return value


@dataclass(frozen=True, slots=True)
class FactDecisionResult:
    decision_id: UUID
    candidate_id: UUID
    decision: str


@dataclass(frozen=True, slots=True)
class FactPromotionResult:
    item_id: UUID
    verified_fact_set_id: UUID
    promoted_field_names: tuple[str, ...]
    retained_unpromoted_decision_count: int


@dataclass(frozen=True, slots=True)
class RuleCandidateView:
    rule_candidate_id: UUID
    field_name: str
    proposed_rule_payload: dict[str, object]
    verified_fact_ids: tuple[UUID, ...]
    evidence_ref_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class RuleProposalResult:
    item_id: UUID
    candidates: tuple[RuleCandidateView, ...]
    eligibility_ceiling: Literal["RULE_EVALUATED", "UNCERTAIN"]


@dataclass(frozen=True, slots=True)
class RuleDecisionResult:
    decision_id: UUID
    rule_candidate_id: UUID
    decision: str
    eligibility_ceiling: Literal["RULE_EVALUATED", "UNCERTAIN"]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def validate_idempotency_key(value: str) -> str:
    if (
        not 1 <= len(value) <= 128
        or value != value.strip()
        or any(not character.isprintable() for character in value)
    ):
        raise ValueError("idempotency key is invalid")
    return value


def require_human_fact_reviewer(principal: ReviewerPrincipal) -> None:
    try:
        require_reviewer_authority(
            principal,
            ReviewerRole.VALIDATION_REVIEWER,
            OPPORTUNITY_FACT_VALIDATION_PURPOSE,
        )
    except ReviewerAuthenticationError as error:
        raise HumanReviewError("HUMAN_VALIDATION_AUTHORITY_REQUIRED") from error
    if principal.synthetic:
        raise HumanReviewError("HUMAN_VALIDATION_AUTHORITY_REQUIRED")


def _string_list(value: object, key: str) -> list[str] | None:
    if not isinstance(value, dict) or set(value) != {key}:
        return None
    items = value[key]
    if (
        not isinstance(items, list)
        or not items
        or any(not isinstance(item, str) or not item.strip() for item in items)
    ):
        return None
    normalized = sorted(set(items))
    return normalized if len(normalized) == len(items) else None


def build_rule_payload(
    *,
    field_name: str,
    normalized_value: object,
) -> ProposedRulePayloadSchemaV08 | None:
    values: tuple[RuleOperator, RuleField, RuleValueType, JsonValue, str] | None = None
    if (
        field_name == "education_requirements"
        and isinstance(normalized_value, dict)
        and set(normalized_value) == {"minimum_level"}
        and isinstance(normalized_value["minimum_level"], str)
        and normalized_value["minimum_level"]
        in {"SECONDARY", "ASSOCIATE", "BACHELOR", "MASTER", "DOCTORATE"}
    ):
        values = (
            RuleOperator.GTE,
            RuleField.EDUCATION_LEVEL,
            RuleValueType.STRING,
            normalized_value["minimum_level"],
            "学历必须满足官方最低要求",
        )
    elif field_name == "major_requirements" and (
        items := _string_list(normalized_value, "allowed_codes")
    ):
        values = (
            RuleOperator.IN,
            RuleField.MAJOR_CODE,
            RuleValueType.STRING,
            cast(JsonValue, items),
            "专业代码必须属于官方允许范围",
        )
    elif field_name == "credential_requirements" and (
        items := _string_list(normalized_value, "required_certificates")
    ):
        values = (
            RuleOperator.CONTAINS_ALL,
            RuleField.CERTIFICATES,
            RuleValueType.STRING_SET,
            cast(JsonValue, items),
            "必须具备官方要求的证书",
        )
    elif field_name == "household_registration_requirements" and (
        items := _string_list(normalized_value, "allowed_regions")
    ):
        values = (
            RuleOperator.IN,
            RuleField.HUKOU_REGION,
            RuleValueType.STRING,
            cast(JsonValue, items),
            "户籍必须属于官方允许范围",
        )
    elif field_name == "applicant_scope" and (
        items := _string_list(normalized_value, "student_statuses")
    ):
        values = (
            RuleOperator.IN,
            RuleField.STUDENT_STATUS,
            RuleValueType.STRING,
            cast(JsonValue, items),
            "在读或毕业状态必须属于官方允许范围",
        )
    elif (
        field_name == "age_requirements"
        and isinstance(normalized_value, dict)
        and set(normalized_value) == {"birth_date_between"}
        and isinstance(normalized_value["birth_date_between"], list)
        and len(normalized_value["birth_date_between"]) == 2
        and all(
            isinstance(item, str) and item.strip()
            for item in normalized_value["birth_date_between"]
        )
    ):
        values = (
            RuleOperator.BETWEEN,
            RuleField.BIRTH_DATE,
            RuleValueType.DATE,
            cast(JsonValue, normalized_value["birth_date_between"]),
            "出生日期必须处于官方允许区间",
        )
    if values is None:
        return None
    operator, field, value_type, value, reason = values
    return ProposedRulePayloadSchemaV08(
        code=f"local-human-{field.value}",
        operator=operator,
        field=field,
        value_type=value_type,
        value=value,
        required=True,
        reason_template=reason,
    )


class HumanFactReviewService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    def decide(
        self,
        command: FactDecisionCommand,
        principal: ReviewerPrincipal,
        idempotency_key: str,
    ) -> FactDecisionResult:
        require_human_fact_reviewer(principal)
        key = validate_idempotency_key(idempotency_key)
        request_hash = model_request_hash(command.model_dump(mode="json"))
        with self._session_factory.begin() as session:
            item = session.get(LocalHumanTestItem, command.item_id)
            candidate = session.get(ExtractionCandidate, command.candidate_id)
            if (
                item is None
                or item.extraction_run_id is None
                or candidate is None
                or candidate.extraction_run_id != item.extraction_run_id
            ):
                raise HumanReviewError("FACT_REVIEW_TARGET_INVALID")
            existing_local = self._existing_local(
                session,
                item_id=command.item_id,
                kind=ReviewDecisionKind.FACT,
                key=key,
            )
            if existing_local is not None:
                if existing_local.request_hash != request_hash:
                    raise ReviewIdempotencyConflict("FACT_DECISION_IDEMPOTENCY_CONFLICT")
                existing = session.get(
                    FactVerificationDecisionModel,
                    existing_local.decision_id,
                )
                if existing is None:
                    raise HumanReviewError("FACT_DECISION_BINDING_MISSING")
                return FactDecisionResult(
                    decision_id=existing.decision_id,
                    candidate_id=existing.candidate_id,
                    decision=existing.decision,
                )
            if ItemStatus(item.status) is not ItemStatus.FACT_REVIEW:
                raise HumanReviewError("FACT_REVIEW_TARGET_INVALID")
            prior = session.scalar(
                select(FactVerificationDecisionModel).where(
                    FactVerificationDecisionModel.candidate_id == command.candidate_id
                )
            )
            if prior is not None:
                raise HumanReviewError("FACT_CANDIDATE_ALREADY_DECIDED")
            support, precedence = self._fact_results(command.decision)
            decision_id = uuid7()
            persisted = FactLifecycleService(session).verify_candidate(
                FactVerificationDecisionSchemaV08(
                    decision_id=decision_id,
                    candidate_id=command.candidate_id,
                    decision=FactVerificationDecision(command.decision),
                    verification_method=VerificationMethod.HUMAN,
                    verifier_identity=f"human:{principal.reviewer_id}",
                    verifier_response_id=None,
                    reason_code=f"HUMAN_{command.decision}",
                    evidence_support_result=support,
                    precedence_check_result=precedence,
                    decided_at=self._clock(),
                )
            )
            session.add(
                LocalHumanTestReviewDecision(
                    decision_id=decision_id,
                    item_id=command.item_id,
                    decision_kind=ReviewDecisionKind.FACT.value,
                    reviewer_id=principal.reviewer_id,
                    idempotency_key=key,
                    request_hash=request_hash,
                    reason=command.reason,
                    created_at=self._clock(),
                )
            )
            session.flush()
            return FactDecisionResult(
                decision_id=persisted.decision_id,
                candidate_id=persisted.candidate_id,
                decision=persisted.decision,
            )

    def promote(
        self,
        item_id: UUID,
        principal: ReviewerPrincipal,
    ) -> FactPromotionResult:
        require_human_fact_reviewer(principal)
        with self._session_factory.begin() as session:
            item = session.scalar(
                select(LocalHumanTestItem)
                .where(LocalHumanTestItem.item_id == item_id)
                .with_for_update()
            )
            if item is None:
                raise HumanReviewError("FACT_PROMOTION_TARGET_INVALID")
            if item.verified_fact_set_id is not None:
                if ItemStatus(item.status) in {
                    ItemStatus.RULE_REVIEW,
                    ItemStatus.READY_TO_PUBLISH,
                    ItemStatus.COMPLETED,
                }:
                    return self._promotion_result(session, item)
                raise HumanReviewError("FACT_PROMOTION_TARGET_INVALID")
            if ItemStatus(item.status) is not ItemStatus.FACT_REVIEW:
                raise HumanReviewError("FACT_PROMOTION_TARGET_INVALID")
            if item.extraction_run_id is None:
                raise HumanReviewError("EXTRACTION_RUN_BINDING_MISSING")
            candidates = tuple(
                session.scalars(
                    select(ExtractionCandidate)
                    .where(ExtractionCandidate.extraction_run_id == item.extraction_run_id)
                    .order_by(ExtractionCandidate.field_name)
                )
            )
            decisions = tuple(
                session.scalars(
                    select(FactVerificationDecisionModel).where(
                        FactVerificationDecisionModel.candidate_id.in_(
                            [candidate.candidate_id for candidate in candidates]
                        )
                    )
                )
            )
            if not candidates or len(decisions) != len(candidates):
                raise HumanReviewError("ALL_FACT_CANDIDATES_REQUIRE_DECISION")
            if len({decision.candidate_id for decision in decisions}) != len(decisions):
                raise HumanReviewError("FACT_CANDIDATE_DECISION_AMBIGUOUS")
            approved = tuple(decision for decision in decisions if decision.decision == "APPROVE")
            if not approved:
                raise HumanReviewError("AT_LEAST_ONE_APPROVED_FACT_REQUIRED")
            fact_set = FactLifecycleService(session).promote(
                decision_ids=[decision.decision_id for decision in approved],
                verified_fact_set_id=uuid7(),
                reference_dataset_versions={"local_human_review": "1.0.0"},
                created_at=self._clock(),
                actor_identity=f"human:{principal.reviewer_id}",
            )
            assert_item_transition(ItemStatus.FACT_REVIEW, ItemStatus.RULE_REVIEW)
            item.verified_fact_set_id = fact_set.verified_fact_set_id
            item.status = ItemStatus.RULE_REVIEW.value
            item.updated_at = self._clock()
            session.flush()
            return self._promotion_result(session, item)

    @staticmethod
    def _fact_results(
        decision: str,
    ) -> tuple[EvidenceSupportResult, PrecedenceCheckResult]:
        if decision == "APPROVE":
            return EvidenceSupportResult.SUPPORTED, PrecedenceCheckResult.PASSED
        if decision == "REJECT":
            return EvidenceSupportResult.UNSUPPORTED, PrecedenceCheckResult.FAILED
        return EvidenceSupportResult.UNKNOWN, PrecedenceCheckResult.UNKNOWN

    @staticmethod
    def _existing_local(
        session: Session,
        *,
        item_id: UUID,
        kind: ReviewDecisionKind,
        key: str,
    ) -> LocalHumanTestReviewDecision | None:
        return session.scalar(
            select(LocalHumanTestReviewDecision).where(
                LocalHumanTestReviewDecision.item_id == item_id,
                LocalHumanTestReviewDecision.decision_kind == kind.value,
                LocalHumanTestReviewDecision.idempotency_key == key,
            )
        )

    @staticmethod
    def _promotion_result(
        session: Session,
        item: LocalHumanTestItem,
    ) -> FactPromotionResult:
        assert item.verified_fact_set_id is not None
        fields = tuple(
            session.scalars(
                select(VerifiedFact.field_name)
                .where(VerifiedFact.verified_fact_set_id == item.verified_fact_set_id)
                .order_by(VerifiedFact.field_name)
            )
        )
        total = session.scalars(
            select(FactVerificationDecisionModel)
            .join(
                ExtractionCandidate,
                FactVerificationDecisionModel.candidate_id == ExtractionCandidate.candidate_id,
            )
            .where(ExtractionCandidate.extraction_run_id == item.extraction_run_id)
        ).all()
        return FactPromotionResult(
            item_id=item.item_id,
            verified_fact_set_id=item.verified_fact_set_id,
            promoted_field_names=fields,
            retained_unpromoted_decision_count=sum(
                decision.decision != "APPROVE" for decision in total
            ),
        )


class HumanRuleReviewService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    def propose_from_verified_facts(self, item_id: UUID) -> RuleProposalResult:
        with self._session_factory.begin() as session:
            item = session.scalar(
                select(LocalHumanTestItem)
                .where(LocalHumanTestItem.item_id == item_id)
                .with_for_update()
            )
            status = None if item is None else ItemStatus(item.status)
            if (
                item is None
                or status
                not in {
                    ItemStatus.RULE_REVIEW,
                    ItemStatus.READY_TO_PUBLISH,
                    ItemStatus.COMPLETED,
                }
                or item.verified_fact_set_id is None
            ):
                raise HumanReviewError("RULE_PROPOSAL_TARGET_INVALID")
            existing = tuple(
                session.scalars(
                    select(RuleCandidateModel).where(
                        RuleCandidateModel.verified_fact_set_id == item.verified_fact_set_id
                    )
                )
            )
            if not existing and status is ItemStatus.RULE_REVIEW:
                fact_set = session.get(VersionedVerifiedFactSet, item.verified_fact_set_id)
                if fact_set is None or fact_set.status != "ACTIVE":
                    raise HumanReviewError("ACTIVE_VERIFIED_FACT_SET_REQUIRED")
                facts = tuple(
                    session.scalars(
                        select(VerifiedFact)
                        .where(
                            VerifiedFact.verified_fact_set_id == item.verified_fact_set_id,
                            VerifiedFact.fact_state == "KNOWN",
                        )
                        .order_by(VerifiedFact.field_name)
                    )
                )
                promotion = RulePromotionService(session)
                for fact in facts:
                    payload = build_rule_payload(
                        field_name=fact.field_name,
                        normalized_value=fact.normalized_value,
                    )
                    if payload is None:
                        continue
                    evidence_ids = list(
                        session.scalars(
                            select(VerifiedFactEvidence.evidence_ref_id)
                            .where(VerifiedFactEvidence.verified_fact_id == fact.verified_fact_id)
                            .order_by(VerifiedFactEvidence.evidence_ref_id)
                        )
                    )
                    promotion.propose(
                        RuleCandidateSchemaV08(
                            rule_candidate_id=uuid7(),
                            target_scope=ExtractionTargetScope.OPPORTUNITY,
                            opportunity_id=fact_set.opportunity_id,
                            opportunity_version=fact_set.opportunity_version,
                            opportunity_unit_id=None,
                            opportunity_unit_version_id=None,
                            verified_fact_ids=[fact.verified_fact_id],
                            rule_type="ATOMIC_QUALIFICATION",
                            proposed_rule_payload=payload,
                            evidence_ref_ids=evidence_ids,
                            compiler_version=f"local-human-fact-rule-{RULE_DERIVATION_VERSION}",
                            producer_identity=f"component:local-human-fact-rule/{RULE_DERIVATION_VERSION}",
                            status=RuleCandidateStatus.PROPOSED,
                            created_at=self._clock(),
                        ),
                        verified_fact_set_id=item.verified_fact_set_id,
                    )
                existing = tuple(
                    session.scalars(
                        select(RuleCandidateModel).where(
                            RuleCandidateModel.verified_fact_set_id == item.verified_fact_set_id
                        )
                    )
                )
            if not existing and status is ItemStatus.RULE_REVIEW:
                assert_item_transition(ItemStatus.RULE_REVIEW, ItemStatus.READY_TO_PUBLISH)
                item.status = ItemStatus.READY_TO_PUBLISH.value
                item.updated_at = self._clock()
            return RuleProposalResult(
                item_id=item_id,
                candidates=tuple(self._candidate_view(session, value) for value in existing),
                eligibility_ceiling="UNCERTAIN",
            )

    def decide(
        self,
        command: RuleDecisionCommand,
        principal: ReviewerPrincipal,
        idempotency_key: str,
    ) -> RuleDecisionResult:
        require_human_fact_reviewer(principal)
        key = validate_idempotency_key(idempotency_key)
        request_hash = model_request_hash(command.model_dump(mode="json"))
        with self._session_factory.begin() as session:
            item = session.scalar(
                select(LocalHumanTestItem)
                .where(LocalHumanTestItem.item_id == command.item_id)
                .with_for_update()
            )
            candidate = session.get(RuleCandidateModel, command.rule_candidate_id)
            if (
                item is None
                or item.verified_fact_set_id is None
                or candidate is None
                or candidate.verified_fact_set_id != item.verified_fact_set_id
            ):
                raise HumanReviewError("RULE_REVIEW_TARGET_INVALID")
            existing_local = HumanFactReviewService._existing_local(
                session,
                item_id=command.item_id,
                kind=ReviewDecisionKind.RULE,
                key=key,
            )
            if existing_local is not None:
                if existing_local.request_hash != request_hash:
                    raise ReviewIdempotencyConflict("RULE_DECISION_IDEMPOTENCY_CONFLICT")
                existing = session.get(RuleApprovalDecisionModel, existing_local.decision_id)
                if existing is None:
                    raise HumanReviewError("RULE_DECISION_BINDING_MISSING")
                return self._decision_result(session, item, existing)
            if ItemStatus(item.status) is not ItemStatus.RULE_REVIEW:
                raise HumanReviewError("RULE_REVIEW_TARGET_INVALID")
            prior = session.scalar(
                select(RuleApprovalDecisionModel).where(
                    RuleApprovalDecisionModel.rule_candidate_id == command.rule_candidate_id
                )
            )
            if prior is not None:
                raise HumanReviewError("RULE_CANDIDATE_ALREADY_DECIDED")
            decision_id = uuid7()
            persisted = RulePromotionService(session).decide(
                RuleApprovalDecisionSchemaV08(
                    rule_approval_decision_id=decision_id,
                    rule_candidate_id=command.rule_candidate_id,
                    decision=RuleApprovalDecisionValue(command.decision),
                    approver_identity=f"human:{principal.reviewer_id}",
                    approval_method=RuleApprovalMethod.HUMAN,
                    reason_code=f"HUMAN_{command.decision}",
                    decided_at=self._clock(),
                    policy_version="local-human-rule-review-1.0.0",
                )
            )
            session.add(
                LocalHumanTestReviewDecision(
                    decision_id=decision_id,
                    item_id=command.item_id,
                    decision_kind=ReviewDecisionKind.RULE.value,
                    reviewer_id=principal.reviewer_id,
                    idempotency_key=key,
                    request_hash=request_hash,
                    reason=command.reason,
                    created_at=self._clock(),
                )
            )
            session.flush()
            undecided_exists = session.scalar(
                select(RuleCandidateModel.rule_candidate_id).where(
                    RuleCandidateModel.verified_fact_set_id == item.verified_fact_set_id,
                    ~RuleCandidateModel.rule_candidate_id.in_(
                        select(RuleApprovalDecisionModel.rule_candidate_id)
                    ),
                )
            )
            if undecided_exists is None:
                assert_item_transition(ItemStatus.RULE_REVIEW, ItemStatus.READY_TO_PUBLISH)
                item.status = ItemStatus.READY_TO_PUBLISH.value
                item.updated_at = self._clock()
            session.flush()
            return self._decision_result(session, item, persisted)

    @staticmethod
    def _candidate_view(session: Session, candidate: RuleCandidateModel) -> RuleCandidateView:
        fact_ids = tuple(
            session.scalars(
                select(RuleCandidateFact.verified_fact_id).where(
                    RuleCandidateFact.rule_candidate_id == candidate.rule_candidate_id
                )
            )
        )
        evidence_ids = tuple(
            session.scalars(
                select(RuleCandidateEvidence.evidence_ref_id).where(
                    RuleCandidateEvidence.rule_candidate_id == candidate.rule_candidate_id
                )
            )
        )
        payload = dict(candidate.proposed_rule_payload)
        return RuleCandidateView(
            rule_candidate_id=candidate.rule_candidate_id,
            field_name=str(payload["field"]),
            proposed_rule_payload=payload,
            verified_fact_ids=fact_ids,
            evidence_ref_ids=evidence_ids,
        )

    @staticmethod
    def _decision_result(
        session: Session,
        item: LocalHumanTestItem,
        decision: RuleApprovalDecisionModel,
    ) -> RuleDecisionResult:
        assert item.verified_fact_set_id is not None
        approved = session.scalar(
            select(RuleApprovalDecisionModel.rule_approval_decision_id)
            .join(
                RuleCandidateModel,
                RuleApprovalDecisionModel.rule_candidate_id == RuleCandidateModel.rule_candidate_id,
            )
            .where(
                RuleCandidateModel.verified_fact_set_id == item.verified_fact_set_id,
                RuleApprovalDecisionModel.decision == "APPROVE",
            )
        )
        return RuleDecisionResult(
            decision_id=decision.rule_approval_decision_id,
            rule_candidate_id=decision.rule_candidate_id,
            decision=decision.decision,
            eligibility_ceiling="RULE_EVALUATED" if approved is not None else "UNCERTAIN",
        )


__all__ = [
    "FactDecisionCommand",
    "FactDecisionResult",
    "FactPromotionResult",
    "HumanFactReviewService",
    "HumanReviewError",
    "HumanRuleReviewService",
    "ReviewIdempotencyConflict",
    "RuleCandidateView",
    "RuleDecisionCommand",
    "RuleDecisionResult",
    "RuleProposalResult",
    "build_rule_payload",
    "require_human_fact_reviewer",
    "validate_idempotency_key",
]
