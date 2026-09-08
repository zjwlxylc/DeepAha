from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from deepaha.contracts.common import normalize_instant, require_uuid7
from deepaha.contracts.phase4 import EligibilityStatus, RuleField, RuleOutcome
from deepaha.eligibility.engine import (
    ENGINE_VERSION,
    EvaluatedRule,
    EvaluationContext,
    evaluate_eligibility,
)
from deepaha.rules.major import ApprovedMajorMapping, MajorCatalog
from deepaha.rules.types import CompiledRule
from deepaha.unit_qualification.compiler import (
    UNIT_COMPILER_VERSION,
    CoverageBlocker,
    compile_unit_qualification,
)
from deepaha.unit_qualification.contracts import (
    CONTRACT_VERSION,
    COVERAGE_POLICY_VERSION,
    UnitIdentity,
    UnitQualificationPlan,
    content_sha256,
)


@dataclass(frozen=True, slots=True)
class UnitEvaluationInput:
    plan: UnitQualificationPlan
    expected_target: UnitIdentity
    profile_snapshot_id: UUID
    profile_version: int
    profile_schema_version: str
    profile_attributes: Mapping[str, object]
    major_catalog: MajorCatalog
    major_mapping: ApprovedMajorMapping
    scenario_clock: date
    evidence_as_of: datetime


@dataclass(frozen=True, slots=True)
class UnitQualificationResult:
    target: UnitIdentity
    qualification_plan_id: UUID
    qualification_plan_version: int
    status: EligibilityStatus
    engine_status: EligibilityStatus
    rule_evaluations: tuple[EvaluatedRule, ...]
    satisfied_rule_ids: tuple[UUID, ...]
    conflict_rule_ids: tuple[UUID, ...]
    unknown_rule_ids: tuple[UUID, ...]
    diagnostic_rule_ids: tuple[UUID, ...]
    missing_fields: tuple[RuleField, ...]
    review_reasons: tuple[str, ...]
    coverage_blockers: tuple[CoverageBlocker, ...]
    status_cap: EligibilityStatus | None
    applied_status_cap: EligibilityStatus | None
    profile_snapshot_id: UUID
    profile_version: int
    profile_schema_version: str
    major_catalog_version: str
    major_mapping_version: str
    scenario_clock: date
    evidence_as_of: datetime
    input_sha256: str
    compiled_sha256: str
    engine_version: str = ENGINE_VERSION
    compiler_version: str = UNIT_COMPILER_VERSION
    coverage_policy_version: str = COVERAGE_POLICY_VERSION
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class _DiagnosticGraph:
    rules: tuple[CompiledRule, ...]
    root_rule_ids: tuple[UUID, ...]


def evaluate_unit_qualification(request: UnitEvaluationInput) -> UnitQualificationResult:
    """Evaluate a trusted, persisted admission snapshot without DB or model calls.

    Authentication, active fact/version checks and the real human approval remain the
    adapter's responsibility. This evaluator never manufactures those observations.
    """
    if request.expected_target != request.plan.target:
        raise ValueError("requested target differs from the approved plan target")
    require_uuid7(request.profile_snapshot_id)
    if (
        type(request.profile_version) is not int
        or request.profile_version < 1
        or not request.profile_schema_version.strip()
    ):
        raise ValueError("profile must have a positive version and schema version")
    if not isinstance(request.scenario_clock, date) or isinstance(request.scenario_clock, datetime):
        raise ValueError("scenario_clock must be a date")
    evidence_as_of = normalize_instant(request.evidence_as_of)
    if request.major_mapping.catalog_version != request.major_catalog.version:
        raise ValueError("major mapping catalog version does not match catalog")
    if normalize_instant(request.major_mapping.approved_at) > evidence_as_of:
        raise ValueError("major mapping approval is after evidence_as_of")
    compiled = compile_unit_qualification(request.plan, evidence_as_of=evidence_as_of)
    evaluations_by_id: dict[UUID, EvaluatedRule] = {}
    engine_status = EligibilityStatus.UNCERTAIN
    review_reasons: tuple[str, ...] = ()
    if compiled.rules:
        decision = evaluate_eligibility(
            EvaluationContext(
                rule_set=compiled,
                profile_attributes=request.profile_attributes,
                major_catalog=request.major_catalog,
                major_mapping=request.major_mapping,
                scenario_clock=request.scenario_clock,
            )
        )
        evaluations_by_id = {item.rule_id: item for item in decision.rule_evaluations}
        engine_status = decision.status
        review_reasons = decision.review_reasons
    if compiled.diagnostic_rules:
        diagnostics = evaluate_eligibility(
            EvaluationContext(
                rule_set=_DiagnosticGraph(
                    compiled.diagnostic_rules,
                    tuple(rule.rule_id for rule in compiled.diagnostic_rules),
                ),
                profile_attributes=request.profile_attributes,
                major_catalog=request.major_catalog,
                major_mapping=request.major_mapping,
                scenario_clock=request.scenario_clock,
            )
        )
        # Intentionally discard the diagnostics' aggregate status. Their
        # leaves cannot replace an unavailable, independently approved root.
        evaluations_by_id.update({item.rule_id: item for item in diagnostics.rule_evaluations})
    for rule_id in compiled.skipped_rule_ids:
        evaluations_by_id[rule_id] = EvaluatedRule(
            rule_id=rule_id,
            outcome=RuleOutcome.UNKNOWN,
            deterministic=False,
            official_evidence=False,
            reason_code="RULE_NOT_EXECUTABLE",
            evidence_ref_ids=(),
            missing_fields=(),
        )
    evaluations = tuple(evaluations_by_id[item.rule_id] for item in compiled.all_rules)
    status = engine_status
    cap = EligibilityStatus.UNCERTAIN if compiled.coverage_blockers else None
    applied_cap = None
    if cap is not None and status in {
        EligibilityStatus.ELIGIBLE,
        EligibilityStatus.LIKELY_ELIGIBLE,
    }:
        status = cap
        applied_cap = cap
    if cap is not None and status is EligibilityStatus.INELIGIBLE:
        # A deterministic comparison is not proof that an unchecked exception
        # cannot apply. Keep the rule conflict visible without a final denial.
        status = cap
        applied_cap = cap
        review_reasons += ("NEGATIVE_CONCLUSION_REQUIRES_SCOPE_REVIEW",)
    review_reasons = tuple(
        dict.fromkeys(
            (
                *review_reasons,
                *(item.code for item in compiled.coverage_blockers),
            )
        )
    )
    return UnitQualificationResult(
        target=compiled.target,
        qualification_plan_id=compiled.qualification_plan_id,
        qualification_plan_version=compiled.version,
        status=status,
        engine_status=engine_status,
        rule_evaluations=evaluations,
        satisfied_rule_ids=tuple(
            item.rule_id for item in evaluations if item.outcome is RuleOutcome.SATISFIED
        ),
        conflict_rule_ids=tuple(
            item.rule_id for item in evaluations if item.outcome is RuleOutcome.CONFLICT
        ),
        unknown_rule_ids=tuple(
            item.rule_id for item in evaluations if item.outcome is RuleOutcome.UNKNOWN
        ),
        diagnostic_rule_ids=tuple(item.rule_id for item in compiled.diagnostic_rules),
        missing_fields=tuple(
            sorted({field for item in evaluations for field in item.missing_fields})
        ),
        review_reasons=review_reasons,
        coverage_blockers=compiled.coverage_blockers,
        status_cap=cap,
        applied_status_cap=applied_cap,
        profile_snapshot_id=request.profile_snapshot_id,
        profile_version=request.profile_version,
        profile_schema_version=request.profile_schema_version,
        major_catalog_version=request.major_catalog.version,
        major_mapping_version=request.major_mapping.version,
        scenario_clock=request.scenario_clock,
        evidence_as_of=evidence_as_of,
        input_sha256=_input_hash(request, compiled.compiled_sha256, evidence_as_of),
        compiled_sha256=compiled.compiled_sha256,
        compiler_version=compiled.compiler_version,
        coverage_policy_version=request.plan.manifest.coverage_policy_version,
        contract_version=request.plan.contract_version,
    )


def _input_hash(
    request: UnitEvaluationInput, compiled_sha256: str, evidence_as_of: datetime
) -> str:
    catalog, mapping = request.major_catalog, request.major_mapping
    return content_sha256(
        {
            "compiled_sha256": compiled_sha256,
            "engine_version": ENGINE_VERSION,
            "contract_version": request.plan.contract_version,
            "profile_snapshot_id": request.profile_snapshot_id,
            "profile_version": request.profile_version,
            "profile_schema_version": request.profile_schema_version,
            "profile_attributes": request.profile_attributes,
            "scenario_clock": request.scenario_clock,
            "evidence_as_of": evidence_as_of,
            "major_catalog": {
                "version": catalog.version,
                "synthetic_only": catalog.synthetic_only,
                "license": catalog.license,
                "entries": {
                    key: {
                        "code": entry.code,
                        "name": entry.name,
                        "parent_codes": entry.parent_codes,
                    }
                    for key, entry in catalog.entries.items()
                },
            },
            "major_mapping": {
                "version": mapping.version,
                "catalog_version": mapping.catalog_version,
                "synthetic_only": mapping.synthetic_only,
                "license": mapping.license,
                "approved_by": mapping.approved_by,
                "approved_at": mapping.approved_at,
                "targets_by_source": mapping.targets_by_source,
            },
        }
    )
