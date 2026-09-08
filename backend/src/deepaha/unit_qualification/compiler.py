from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from deepaha.contracts.common import normalize_instant
from deepaha.contracts.phase4 import RuleOperator
from deepaha.rules.compiler import COMPILER_VERSION, compile_rule_graph
from deepaha.rules.types import CompiledRule
from deepaha.unit_qualification.contracts import (
    CoverageCondition,
    EvidenceValidity,
    UnitIdentity,
    UnitQualificationPlan,
    content_sha256,
)

UNIT_COMPILER_VERSION = "unit-qualification-compiler/2.0.0"


@dataclass(frozen=True, slots=True)
class CoverageBlocker:
    code: str
    condition_id: str | None = None
    rule_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class CompiledUnitQualification:
    qualification_plan_id: UUID
    version: int
    target: UnitIdentity
    rules: tuple[CompiledRule, ...]
    root_rule_ids: tuple[UUID, ...]
    all_rules: tuple[CompiledRule, ...]
    diagnostic_rules: tuple[CompiledRule, ...]
    skipped_rule_ids: tuple[UUID, ...]
    coverage_blockers: tuple[CoverageBlocker, ...]
    compiled_sha256: str
    evidence_as_of: datetime
    compiler_version: str = UNIT_COMPILER_VERSION


def compile_unit_qualification(
    plan: UnitQualificationPlan, *, evidence_as_of: datetime
) -> CompiledUnitQualification:
    # Revalidate nested objects too: model_copy is deliberately not a validation API.
    plan = UnitQualificationPlan.model_validate(plan.model_dump())
    compiler_version = UNIT_COMPILER_VERSION
    evidence_as_of = normalize_instant(evidence_as_of)
    graph = compile_rule_graph(plan.rules, plan.root_rule_ids) if plan.rules else ()
    conditions = {item.condition_id: item for item in plan.manifest.conditions}
    dispositions = {item.condition_id: item for item in plan.dispositions}
    admissions = {item.rule_id: item for item in plan.admissions}
    blockers = [CoverageBlocker("HUMAN_SCOPE_REVIEW_UNVERIFIED")]
    blockers.extend(CoverageBlocker(code) for code in plan.manifest.upstream_blockers)
    unresolved: set[str] = set()
    for condition in plan.manifest.conditions:
        reason = _condition_blocker(condition)
        disposition = dispositions.get(condition.condition_id)
        if reason is None and (disposition is None or disposition.kind == "UNRESOLVED"):
            reason = (
                "CONDITION_DISPOSITION_MISSING" if disposition is None else "CONDITION_UNRESOLVED"
            )
        if (
            reason is None
            and disposition is not None
            and disposition.kind == "RULE"
            and any(
                key not in admissions or condition.condition_id not in admissions[key].condition_ids
                for key in disposition.rule_ids
            )
        ):
            reason = "CONDITION_RULE_BINDING_MISMATCH"
        if reason is not None:
            unresolved.add(condition.condition_id)
            blockers.append(CoverageBlocker(reason, condition.condition_id))

    disabled: set[UUID] = set()
    current_rules: list[CompiledRule] = []
    for rule in graph:
        admission = admissions.get(rule.rule_id)
        reason = None
        if admission is None:
            reason = "RULE_APPROVAL_MISSING"
        elif admission.reviewed_at > evidence_as_of:
            reason = "RULE_APPROVAL_NOT_CURRENT"
        elif rule.operator is RuleOperator.NOT_EXISTS:
            # Current profile input cannot distinguish unknown from confirmed
            # absence. Legacy NOT(NOT_EXISTS(missing)) would otherwise hard-deny.
            reason = "ABSENCE_NOT_PROVEN"
        elif not rule.operand_rule_ids:
            if not admission.condition_ids:
                reason = "RULE_CONDITION_BINDING_MISSING"
            elif any(key in unresolved for key in admission.condition_ids):
                reason = "RULE_CONDITION_UNRESOLVED"
            elif any(
                key not in dispositions
                or dispositions[key].kind != "RULE"
                or rule.rule_id not in dispositions[key].rule_ids
                for key in admission.condition_ids
            ):
                reason = "RULE_DISPOSITION_MISMATCH"
            elif any(
                conditions[key].fact_id is None or not conditions[key].evidence_ref_ids
                for key in admission.condition_ids
            ):
                reason = "FACT_EVIDENCE_MISSING"
            else:
                fact_evidence_ids = {
                    evidence_id
                    for key in admission.condition_ids
                    for evidence_id in conditions[key].evidence_ref_ids
                }
                if not {item.evidence_ref_id for item in rule.evidence} <= fact_evidence_ids:
                    reason = "RULE_EVIDENCE_NOT_IN_FACTS"
                elif any(
                    not set(conditions[key].evidence_ref_ids).intersection(
                        item.evidence_ref_id for item in rule.evidence
                    )
                    for key in admission.condition_ids
                ):
                    reason = "CONDITION_EVIDENCE_NOT_IN_RULE"
        if reason is not None:
            disabled.add(rule.rule_id)
            blockers.append(CoverageBlocker(reason, rule_id=rule.rule_id))
            current_rules.append(rule)
            continue
        if rule.operand_rule_ids:
            current_rules.append(rule)
            continue
        assert admission is not None
        validity = {item.evidence_ref_id: item for item in admission.evidence_validity}
        active_evidence = tuple(
            item
            for item in rule.evidence
            if _active_at(validity[item.evidence_ref_id], evidence_as_of)
        )
        if not active_evidence:
            disabled.add(rule.rule_id)
            blockers.append(CoverageBlocker("NO_CURRENT_EVIDENCE", rule_id=rule.rule_id))
        active_ids = {item.evidence_ref_id for item in active_evidence}
        for condition_id in admission.condition_ids:
            if not active_ids.intersection(conditions[condition_id].evidence_ref_ids):
                disabled.add(rule.rule_id)
                blockers.append(
                    CoverageBlocker("CONDITION_EVIDENCE_NOT_CURRENT", condition_id, rule.rule_id)
                )
        precedence = active_evidence[0].precedence if active_evidence else None
        current_rules.append(
            replace(
                rule,
                evidence=active_evidence,
                effective_precedence=precedence,
                evidence_conflicted=len(
                    {item.relation for item in active_evidence if item.precedence == precedence}
                )
                > 1,
            )
        )

    # A partially executable composite must remain unknown. Do not silently drop
    # an AND/OR operand and change the meaning of the independently approved graph.
    for rule in current_rules:
        if rule.rule_id not in disabled and any(key in disabled for key in rule.operand_rule_ids):
            disabled.add(rule.rule_id)
            blockers.append(CoverageBlocker("DEPENDENCY_NOT_EXECUTABLE", rule_id=rule.rule_id))
    roots = tuple(key for key in plan.root_rule_ids if key not in disabled)
    by_id = {item.rule_id: item for item in current_rules}
    included: set[UUID] = set()

    def include(rule_id: UUID) -> None:
        if rule_id in included:
            return
        included.add(rule_id)
        for operand in by_id[rule_id].operand_rule_ids:
            include(operand)

    for root in roots:
        include(root)
    executable = tuple(item for item in current_rules if item.rule_id in included)
    # An approved, current atomic leaf can still explain a local conflict or
    # missing profile field when its composite cannot run. These diagnostics
    # must never become substitute roots or affect the aggregate decision.
    diagnostics = tuple(
        item
        for item in current_rules
        if not item.operand_rule_ids
        and item.rule_id not in disabled
        and item.rule_id not in included
    )
    diagnostic_ids = {item.rule_id for item in diagnostics}
    if not executable:
        blockers.append(CoverageBlocker("NO_EXECUTABLE_RULES"))
    compiled_hash = content_sha256(
        {
            "plan": plan.model_dump(mode="json"),
            "evidence_as_of": evidence_as_of,
            "compiler_version": compiler_version,
            "graph_compiler_version": COMPILER_VERSION,
            "coverage_policy_version": plan.manifest.coverage_policy_version,
            "executable_roots": roots,
            "diagnostic_rules": [item.rule_id for item in diagnostics],
            "current_evidence": {
                str(item.rule_id): [evidence.evidence_ref_id for evidence in item.evidence]
                for item in (*executable, *diagnostics)
            },
        }
    )
    return CompiledUnitQualification(
        qualification_plan_id=plan.qualification_plan_id,
        version=plan.version,
        target=plan.target,
        rules=executable,
        root_rule_ids=roots,
        all_rules=graph,
        diagnostic_rules=diagnostics,
        skipped_rule_ids=tuple(
            item.rule_id for item in graph if item.rule_id not in included | diagnostic_ids
        ),
        coverage_blockers=tuple(dict.fromkeys(blockers)),
        compiled_sha256=compiled_hash,
        evidence_as_of=evidence_as_of,
        compiler_version=compiler_version,
    )


def _condition_blocker(condition: CoverageCondition) -> str | None:
    if condition.scope != "UNIT":
        return "SCOPE_NOT_SUPPORTED"
    if condition.state != "KNOWN":
        return "CONDITION_UNRESOLVED"
    return None


def _active_at(validity: EvidenceValidity, evidence_as_of: datetime) -> bool:
    return validity.valid_from <= evidence_as_of and (
        validity.valid_until is None or evidence_as_of < validity.valid_until
    )
