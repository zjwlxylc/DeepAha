import json
from collections.abc import Callable
from datetime import datetime
from hashlib import sha256
from uuid import UUID, uuid7

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.contracts.phase7 import (
    FeedbackEvidenceClass,
    ImprovementCandidateSchemaV06,
    OfflineEvaluationCandidateSchemaV06,
    ReleaseGateDecision,
    ReleaseGateDecisionSchemaV06,
    ShadowTestCandidateSchemaV06,
    SimulationValidationRunSchemaV06,
    ValidationOutcome,
)
from deepaha.review.auth import ReviewerPrincipal, ReviewerRole, require_reviewer_authority
from deepaha.review.models import ApprovedFeedbackLabelModel
from deepaha.validation.models import (
    FeedbackImprovementCandidateModel,
    OfflineEvaluationCandidateModel,
    ReleaseGateDecisionModel,
    ShadowTestCandidateModel,
    ValidationRunModel,
)
from deepaha.validation.schemas import (
    HumanValidationRunWrite,
    ImprovementSelectionWrite,
    OfflineEvaluationWrite,
    ShadowEvaluationWrite,
    SimulationValidationRunWrite,
)


class ValidationUnavailable(ValueError):
    pass


class HumanValidationAuthorizationRequired(ValidationUnavailable):
    pass


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def improvement_input_sha256(
    principal: ReviewerPrincipal,
    validation_cycle_id: UUID,
    command: ImprovementSelectionWrite,
) -> str:
    return _canonical_sha256(
        {
            "reviewer_id": str(principal.reviewer_id),
            "validation_cycle_id": str(validation_cycle_id),
            "command": command.model_dump(mode="json"),
        }
    )


def required_evaluation_evidence_class(label_evidence_class: str) -> str:
    if label_evidence_class == FeedbackEvidenceClass.SYNTHETIC_FEEDBACK_WORKFLOW_ONLY:
        return FeedbackEvidenceClass.SYNTHETIC_SIMULATION_ONLY.value
    if label_evidence_class == FeedbackEvidenceClass.CONSENTED_HUMAN_PARTICIPANT:
        return FeedbackEvidenceClass.CONSENTED_HUMAN_PARTICIPANT.value
    raise ValidationUnavailable("validation unavailable")


def derive_gate_decision(
    *,
    offline_outcome: str,
    shadow_outcome: str | None,
    simulation_outcome: str | None,
    human_outcome: str | None,
) -> ReleaseGateDecision:
    if offline_outcome != ValidationOutcome.PASSED or shadow_outcome != ValidationOutcome.PASSED:
        return ReleaseGateDecision.HOLD_ENGINEERING_FAILURE
    if simulation_outcome != ValidationOutcome.PASSED:
        return ReleaseGateDecision.HOLD_ENGINEERING_FAILURE
    if human_outcome is None:
        return ReleaseGateDecision.HOLD_MISSING_HUMAN_EVIDENCE
    if human_outcome != ValidationOutcome.PASSED:
        return ReleaseGateDecision.REJECTED
    raise ValidationUnavailable("Phase 7 cannot accept a release candidate")


class ValidationService:
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

    def select_improvement(
        self,
        principal: ReviewerPrincipal,
        validation_cycle_id: UUID,
        command: ImprovementSelectionWrite,
    ) -> ImprovementCandidateSchemaV06:
        require_reviewer_authority(principal, ReviewerRole.VALIDATION_REVIEWER)
        candidate_sha256 = improvement_input_sha256(principal, validation_cycle_id, command)
        created_at = self._now_factory()
        with self._session_factory() as session:
            try:
                existing = session.scalar(
                    select(FeedbackImprovementCandidateModel).where(
                        FeedbackImprovementCandidateModel.validation_cycle_id == validation_cycle_id
                    )
                )
                if existing is not None:
                    if existing.candidate_sha256 != candidate_sha256:
                        raise ValidationUnavailable("validation unavailable")
                    session.rollback()
                    return self._candidate_result(existing)
                labels = session.scalars(
                    select(ApprovedFeedbackLabelModel).where(
                        ApprovedFeedbackLabelModel.approved_feedback_label_id.in_(
                            command.approved_label_ids
                        )
                    )
                ).all()
                if len(labels) != len(command.approved_label_ids):
                    raise ValidationUnavailable("validation unavailable")
                evidence_classes = {label.evidence_class for label in labels}
                if len(evidence_classes) != 1:
                    raise ValidationUnavailable("validation unavailable")
                evidence_class = evidence_classes.pop()
                row = FeedbackImprovementCandidateModel(
                    improvement_candidate_id=self._id_factory(),
                    validation_cycle_id=validation_cycle_id,
                    approved_label_ids=[str(value) for value in command.approved_label_ids],
                    direction=command.direction.value,
                    component=command.component,
                    input_manifest_sha256=command.input_manifest_sha256,
                    change_statement=command.change_statement,
                    candidate_sha256=candidate_sha256,
                    evidence_class=evidence_class,
                    selected=True,
                    created_by_reviewer_id=principal.reviewer_id,
                    created_at=created_at,
                )
                session.add(row)
                session.commit()
                return self._candidate_result(row)
            except Exception:
                session.rollback()
                raise

    def record_offline(
        self,
        principal: ReviewerPrincipal,
        improvement_candidate_id: UUID,
        command: OfflineEvaluationWrite,
    ) -> OfflineEvaluationCandidateSchemaV06:
        require_reviewer_authority(principal, ReviewerRole.VALIDATION_REVIEWER)
        created_at = self._now_factory()
        with self._session_factory() as session:
            try:
                candidate = session.get(
                    FeedbackImprovementCandidateModel,
                    improvement_candidate_id,
                )
                if candidate is None or command.evidence_class.value != (
                    required_evaluation_evidence_class(candidate.evidence_class)
                ):
                    raise ValidationUnavailable("validation unavailable")
                existing = session.scalar(
                    select(OfflineEvaluationCandidateModel).where(
                        OfflineEvaluationCandidateModel.improvement_candidate_id
                        == improvement_candidate_id
                    )
                )
                if existing is not None:
                    if (
                        existing.dataset_id != command.dataset_id
                        or existing.dataset_version != command.dataset_version
                        or existing.dataset_sha256 != command.dataset_sha256
                        or existing.baseline_component_version != command.baseline_component_version
                        or existing.candidate_component_version
                        != command.candidate_component_version
                        or existing.outcome != command.outcome.value
                        or existing.result_sha256 != command.result_sha256
                        or existing.evidence_class != command.evidence_class.value
                    ):
                        raise ValidationUnavailable("validation unavailable")
                    session.rollback()
                    return self._offline_result(existing)
                row = OfflineEvaluationCandidateModel(
                    offline_evaluation_candidate_id=self._id_factory(),
                    improvement_candidate_id=improvement_candidate_id,
                    dataset_id=command.dataset_id,
                    dataset_version=command.dataset_version,
                    dataset_sha256=command.dataset_sha256,
                    baseline_component_version=command.baseline_component_version,
                    candidate_component_version=command.candidate_component_version,
                    outcome=command.outcome.value,
                    result_sha256=command.result_sha256,
                    evidence_class=command.evidence_class.value,
                    created_by_reviewer_id=principal.reviewer_id,
                    created_at=created_at,
                )
                session.add(row)
                session.commit()
                return self._offline_result(row)
            except Exception:
                session.rollback()
                raise

    def record_shadow(
        self,
        principal: ReviewerPrincipal,
        improvement_candidate_id: UUID,
        command: ShadowEvaluationWrite,
    ) -> ShadowTestCandidateSchemaV06:
        require_reviewer_authority(principal, ReviewerRole.VALIDATION_REVIEWER)
        created_at = self._now_factory()
        with self._session_factory() as session:
            try:
                offline = session.get(
                    OfflineEvaluationCandidateModel,
                    command.offline_evaluation_candidate_id,
                )
                if (
                    offline is None
                    or offline.improvement_candidate_id != improvement_candidate_id
                    or offline.outcome != ValidationOutcome.PASSED
                    or offline.baseline_component_version != command.baseline_component_version
                    or offline.candidate_component_version != command.candidate_component_version
                    or offline.evidence_class != command.evidence_class.value
                ):
                    raise ValidationUnavailable("validation unavailable")
                existing = session.scalar(
                    select(ShadowTestCandidateModel).where(
                        ShadowTestCandidateModel.offline_evaluation_candidate_id
                        == offline.offline_evaluation_candidate_id
                    )
                )
                if existing is not None:
                    if (
                        existing.baseline_component_version != command.baseline_component_version
                        or existing.candidate_component_version
                        != command.candidate_component_version
                        or existing.outcome != command.outcome.value
                        or existing.comparison_sha256 != command.comparison_sha256
                        or existing.evidence_class != command.evidence_class.value
                    ):
                        raise ValidationUnavailable("validation unavailable")
                    session.rollback()
                    return self._shadow_result(existing)
                row = ShadowTestCandidateModel(
                    shadow_test_candidate_id=self._id_factory(),
                    improvement_candidate_id=improvement_candidate_id,
                    offline_evaluation_candidate_id=offline.offline_evaluation_candidate_id,
                    baseline_component_version=command.baseline_component_version,
                    candidate_component_version=command.candidate_component_version,
                    outcome=command.outcome.value,
                    comparison_sha256=command.comparison_sha256,
                    evidence_class=command.evidence_class.value,
                    created_by_reviewer_id=principal.reviewer_id,
                    created_at=created_at,
                )
                session.add(row)
                session.commit()
                return self._shadow_result(row)
            except Exception:
                session.rollback()
                raise

    def record_simulation_run(
        self,
        principal: ReviewerPrincipal,
        validation_cycle_id: UUID,
        command: SimulationValidationRunWrite,
    ) -> SimulationValidationRunSchemaV06:
        require_reviewer_authority(principal, ReviewerRole.VALIDATION_REVIEWER)
        with self._session_factory() as session:
            try:
                candidate = self._cycle_candidate(session, validation_cycle_id)
                offline, shadow = self._evaluation_chain(
                    session,
                    candidate.improvement_candidate_id,
                )
                if (
                    offline.outcome != ValidationOutcome.PASSED
                    or shadow.outcome != ValidationOutcome.PASSED
                    or command.evidence_class.value
                    != FeedbackEvidenceClass.SYNTHETIC_SIMULATION_ONLY
                ):
                    raise ValidationUnavailable("validation unavailable")
                input_sha256 = _canonical_sha256(
                    {
                        "reviewer_id": str(principal.reviewer_id),
                        "validation_cycle_id": str(validation_cycle_id),
                        "improvement_candidate_id": str(candidate.improvement_candidate_id),
                        "command": command.model_dump(mode="json"),
                    }
                )
                existing = session.scalar(
                    select(ValidationRunModel).where(
                        ValidationRunModel.validation_cycle_id == validation_cycle_id,
                        ValidationRunModel.track == "SIMULATION",
                    )
                )
                if existing is not None:
                    if existing.input_sha256 != input_sha256:
                        raise ValidationUnavailable("validation unavailable")
                    session.rollback()
                    return self._simulation_result(existing)
                row = ValidationRunModel(
                    validation_run_id=self._id_factory(),
                    validation_cycle_id=validation_cycle_id,
                    improvement_candidate_id=candidate.improvement_candidate_id,
                    dataset_id=command.dataset_id,
                    dataset_version=command.dataset_version,
                    dataset_sha256=command.dataset_sha256,
                    track=command.track,
                    evidence_class=command.evidence_class.value,
                    synthetic=command.synthetic,
                    release_qualification_eligible=command.release_qualification_eligible,
                    outcome=command.outcome.value,
                    metrics=command.metrics.model_dump(mode="json"),
                    input_sha256=input_sha256,
                    created_by_reviewer_id=principal.reviewer_id,
                    started_at=command.started_at,
                    completed_at=command.completed_at,
                )
                session.add(row)
                session.commit()
                return self._simulation_result(row)
            except Exception:
                session.rollback()
                raise

    def record_human_run(
        self,
        principal: ReviewerPrincipal,
        validation_cycle_id: UUID,
        command: HumanValidationRunWrite,
    ) -> None:
        require_reviewer_authority(principal, ReviewerRole.VALIDATION_REVIEWER)
        with self._session_factory() as session:
            candidate = self._cycle_candidate(session, validation_cycle_id)
            simulation = session.scalar(
                select(ValidationRunModel).where(
                    ValidationRunModel.validation_cycle_id == validation_cycle_id,
                    ValidationRunModel.track == "SIMULATION",
                )
            )
            if simulation is not None and simulation.dataset_id == command.dataset_id:
                raise ValidationUnavailable("validation tracks require separate datasets")
            if candidate.evidence_class == FeedbackEvidenceClass.SYNTHETIC_FEEDBACK_WORKFLOW_ONLY:
                raise HumanValidationAuthorizationRequired(
                    "synthetic feedback cannot enter the human track"
                )
            raise HumanValidationAuthorizationRequired(
                "human participant authorization is not available in Phase 7 engineering"
            )

    def decide(
        self,
        principal: ReviewerPrincipal,
        validation_cycle_id: UUID,
    ) -> ReleaseGateDecisionSchemaV06:
        require_reviewer_authority(principal, ReviewerRole.VALIDATION_REVIEWER)
        created_at = self._now_factory()
        with self._session_factory() as session:
            try:
                existing = session.scalar(
                    select(ReleaseGateDecisionModel).where(
                        ReleaseGateDecisionModel.validation_cycle_id == validation_cycle_id
                    )
                )
                if existing is not None:
                    session.rollback()
                    return self._gate_result(existing)
                candidate = self._cycle_candidate(session, validation_cycle_id)
                offline, shadow = self._evaluation_chain(
                    session,
                    candidate.improvement_candidate_id,
                )
                simulation = session.scalar(
                    select(ValidationRunModel).where(
                        ValidationRunModel.validation_cycle_id == validation_cycle_id,
                        ValidationRunModel.track == "SIMULATION",
                    )
                )
                human = session.scalar(
                    select(ValidationRunModel).where(
                        ValidationRunModel.validation_cycle_id == validation_cycle_id,
                        ValidationRunModel.track == "HUMAN_PARTICIPANT",
                    )
                )
                decision = derive_gate_decision(
                    offline_outcome=offline.outcome,
                    shadow_outcome=shadow.outcome,
                    simulation_outcome=None if simulation is None else simulation.outcome,
                    human_outcome=None if human is None else human.outcome,
                )
                rationale = self._decision_rationale(decision)
                input_sha256 = _canonical_sha256(
                    {
                        "validation_cycle_id": str(validation_cycle_id),
                        "improvement_candidate_id": str(candidate.improvement_candidate_id),
                        "offline_evaluation_candidate_id": str(
                            offline.offline_evaluation_candidate_id
                        ),
                        "shadow_test_candidate_id": str(shadow.shadow_test_candidate_id),
                        "simulation_validation_run_id": (
                            None if simulation is None else str(simulation.validation_run_id)
                        ),
                        "human_validation_run_id": (
                            None if human is None else str(human.validation_run_id)
                        ),
                        "decision": decision.value,
                    }
                )
                row = ReleaseGateDecisionModel(
                    release_gate_decision_id=self._id_factory(),
                    validation_cycle_id=validation_cycle_id,
                    improvement_candidate_id=candidate.improvement_candidate_id,
                    offline_evaluation_candidate_id=offline.offline_evaluation_candidate_id,
                    shadow_test_candidate_id=shadow.shadow_test_candidate_id,
                    simulation_validation_run_id=(
                        None if simulation is None else simulation.validation_run_id
                    ),
                    human_validation_run_id=None if human is None else human.validation_run_id,
                    decision=decision.value,
                    rationale=rationale,
                    input_sha256=input_sha256,
                    decided_by_reviewer_id=principal.reviewer_id,
                    created_at=created_at,
                )
                session.add(row)
                session.commit()
                return self._gate_result(row)
            except Exception:
                session.rollback()
                raise

    @staticmethod
    def _cycle_candidate(
        session: Session,
        validation_cycle_id: UUID,
    ) -> FeedbackImprovementCandidateModel:
        candidate = session.scalar(
            select(FeedbackImprovementCandidateModel).where(
                FeedbackImprovementCandidateModel.validation_cycle_id == validation_cycle_id
            )
        )
        if candidate is None:
            raise ValidationUnavailable("validation unavailable")
        return candidate

    @staticmethod
    def _evaluation_chain(
        session: Session,
        improvement_candidate_id: UUID,
    ) -> tuple[OfflineEvaluationCandidateModel, ShadowTestCandidateModel]:
        offline = session.scalar(
            select(OfflineEvaluationCandidateModel).where(
                OfflineEvaluationCandidateModel.improvement_candidate_id == improvement_candidate_id
            )
        )
        if offline is None:
            raise ValidationUnavailable("validation unavailable")
        shadow = session.scalar(
            select(ShadowTestCandidateModel).where(
                ShadowTestCandidateModel.offline_evaluation_candidate_id
                == offline.offline_evaluation_candidate_id
            )
        )
        if shadow is None:
            raise ValidationUnavailable("validation unavailable")
        return offline, shadow

    @staticmethod
    def _decision_rationale(decision: ReleaseGateDecision) -> str:
        if decision is ReleaseGateDecision.HOLD_MISSING_HUMAN_EVIDENCE:
            return (
                "Synthetic engineering checks passed; no authorized human-participant "
                "validation exists, so release qualification remains NOT_STARTED."
            )
        if decision is ReleaseGateDecision.HOLD_ENGINEERING_FAILURE:
            return "At least one offline, shadow or simulation engineering check did not pass."
        return "The governed human-participant validation did not pass."

    @staticmethod
    def _candidate_result(
        row: FeedbackImprovementCandidateModel,
    ) -> ImprovementCandidateSchemaV06:
        return ImprovementCandidateSchemaV06.model_validate(
            {
                "improvement_candidate_id": row.improvement_candidate_id,
                "validation_cycle_id": row.validation_cycle_id,
                "approved_label_ids": row.approved_label_ids,
                "direction": row.direction,
                "component": row.component,
                "input_manifest_sha256": row.input_manifest_sha256,
                "change_statement": row.change_statement,
                "candidate_sha256": row.candidate_sha256,
                "evidence_class": row.evidence_class,
                "selected": row.selected,
                "created_at": row.created_at,
            }
        )

    @staticmethod
    def _offline_result(
        row: OfflineEvaluationCandidateModel,
    ) -> OfflineEvaluationCandidateSchemaV06:
        return OfflineEvaluationCandidateSchemaV06.model_validate(
            {
                "offline_evaluation_candidate_id": row.offline_evaluation_candidate_id,
                "improvement_candidate_id": row.improvement_candidate_id,
                "dataset_id": row.dataset_id,
                "dataset_version": row.dataset_version,
                "dataset_sha256": row.dataset_sha256,
                "baseline_component_version": row.baseline_component_version,
                "candidate_component_version": row.candidate_component_version,
                "outcome": row.outcome,
                "result_sha256": row.result_sha256,
                "evidence_class": row.evidence_class,
                "created_at": row.created_at,
            }
        )

    @staticmethod
    def _shadow_result(row: ShadowTestCandidateModel) -> ShadowTestCandidateSchemaV06:
        return ShadowTestCandidateSchemaV06.model_validate(
            {
                "shadow_test_candidate_id": row.shadow_test_candidate_id,
                "improvement_candidate_id": row.improvement_candidate_id,
                "offline_evaluation_candidate_id": row.offline_evaluation_candidate_id,
                "baseline_component_version": row.baseline_component_version,
                "candidate_component_version": row.candidate_component_version,
                "outcome": row.outcome,
                "comparison_sha256": row.comparison_sha256,
                "evidence_class": row.evidence_class,
                "created_at": row.created_at,
            }
        )

    @staticmethod
    def _simulation_result(row: ValidationRunModel) -> SimulationValidationRunSchemaV06:
        return SimulationValidationRunSchemaV06.model_validate(
            {
                "validation_run_id": row.validation_run_id,
                "validation_cycle_id": row.validation_cycle_id,
                "improvement_candidate_id": row.improvement_candidate_id,
                "dataset_id": row.dataset_id,
                "dataset_version": row.dataset_version,
                "dataset_sha256": row.dataset_sha256,
                "track": row.track,
                "evidence_class": row.evidence_class,
                "synthetic": row.synthetic,
                "release_qualification_eligible": row.release_qualification_eligible,
                "outcome": row.outcome,
                "metrics": row.metrics,
                "input_sha256": row.input_sha256,
                "started_at": row.started_at,
                "completed_at": row.completed_at,
            }
        )

    @staticmethod
    def _gate_result(row: ReleaseGateDecisionModel) -> ReleaseGateDecisionSchemaV06:
        return ReleaseGateDecisionSchemaV06.model_validate(
            {
                "release_gate_decision_id": row.release_gate_decision_id,
                "validation_cycle_id": row.validation_cycle_id,
                "improvement_candidate_id": row.improvement_candidate_id,
                "offline_evaluation_candidate_id": row.offline_evaluation_candidate_id,
                "shadow_test_candidate_id": row.shadow_test_candidate_id,
                "simulation_validation_run_id": row.simulation_validation_run_id,
                "human_validation_run_id": row.human_validation_run_id,
                "decision": row.decision,
                "rationale": row.rationale,
                "input_sha256": row.input_sha256,
                "created_at": row.created_at,
            }
        )


__all__ = [
    "HumanValidationAuthorizationRequired",
    "ValidationService",
    "ValidationUnavailable",
    "derive_gate_decision",
    "improvement_input_sha256",
    "required_evaluation_evidence_class",
]
