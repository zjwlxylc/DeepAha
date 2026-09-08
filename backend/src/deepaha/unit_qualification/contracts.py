"""Inputs loaded by a trusted adapter from immutable facts and approval records.

These contracts verify referential consistency, not reviewer authentication or
document completeness. A caller cannot declare complete coverage with a boolean;
the current coverage policy always retains the unverified human scope blocker.
"""

import json
from collections.abc import Mapping
from datetime import date, datetime
from hashlib import sha256
from typing import Final, Literal, Self
from uuid import UUID

from pydantic import ConfigDict, Field, JsonValue, model_validator

from deepaha.contracts.common import EntityId, Instant, NonEmptyString, Sha256, VersionNumber
from deepaha.contracts.phase1 import ContractModel
from deepaha.contracts.phase4 import RuleSchemaV04

CONTRACT_VERSION: Final = "unit-qualification/2.0.0"
COVERAGE_POLICY_VERSION: Final = "unit-condition-coverage/2.0.0"


class _FrozenContract(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class UnitIdentity(_FrozenContract):
    opportunity_id: EntityId
    opportunity_version: VersionNumber
    unit_id: EntityId
    unit_version: VersionNumber
    unit_version_id: EntityId


class CoverageCondition(_FrozenContract):
    condition_id: NonEmptyString
    scope: Literal["UNIT", "ANNOUNCEMENT", "EMPLOYER_GROUP"]
    source_entity_id: NonEmptyString
    source_index: int = Field(ge=0)
    source_unit_id: EntityId | None
    source_unit_version: VersionNumber | None
    source_unit_version_id: EntityId | None
    field_name: NonEmptyString
    source_sha256: Sha256
    state: Literal[
        "KNOWN", "UNKNOWN", "CONFLICT", "UNSUPPORTED", "REJECTED", "UNLOCATED", "UNPROCESSED"
    ]
    fact_id: EntityId | None
    evidence_ref_ids: tuple[EntityId, ...]

    @model_validator(mode="after")
    def validate_source(self) -> Self:
        if self.scope == "UNIT":
            if (
                self.source_unit_id is None
                or self.source_unit_version is None
                or self.source_unit_version_id is None
            ):
                raise ValueError("unit condition requires an exact source unit version")
        elif (
            self.source_unit_id is not None
            or self.source_unit_version is not None
            or self.source_unit_version_id is not None
        ):
            raise ValueError("parent and group conditions cannot borrow a unit identity")
        _unique(self.evidence_ref_ids, "condition evidence")
        return self


class CoverageManifest(_FrozenContract):
    target: UnitIdentity
    preparation_id: EntityId
    preparation_sha256: Sha256
    conditions: tuple[CoverageCondition, ...]
    upstream_blockers: tuple[NonEmptyString, ...]
    coverage_policy_version: Literal["unit-condition-coverage/2.0.0"] = COVERAGE_POLICY_VERSION

    @model_validator(mode="after")
    def validate_denominator(self) -> Self:
        _unique(tuple(item.condition_id for item in self.conditions), "conditions")
        _unique(
            tuple(
                (item.scope, item.source_entity_id, item.source_index) for item in self.conditions
            ),
            "source rows",
        )
        _unique(self.upstream_blockers, "upstream blockers")
        for item in self.conditions:
            if item.scope == "UNIT" and (
                item.source_unit_id != self.target.unit_id
                or item.source_unit_version != self.target.unit_version
                or item.source_unit_version_id != self.target.unit_version_id
            ):
                raise ValueError("condition belongs to a different unit version")
        return self


class ConditionDisposition(_FrozenContract):
    condition_id: NonEmptyString
    kind: Literal["RULE", "NON_QUALIFICATION", "UNRESOLVED"]
    rule_ids: tuple[EntityId, ...]
    decision_id: EntityId | None
    reviewer_principal_id: NonEmptyString | None
    reason: NonEmptyString

    @model_validator(mode="after")
    def validate_disposition(self) -> Self:
        _unique(self.rule_ids, "disposition rules")
        if self.kind == "RULE" and not self.rule_ids:
            raise ValueError("RULE disposition must name actual rules")
        if self.kind != "RULE" and self.rule_ids:
            raise ValueError("only RULE disposition may name rules")
        if self.kind != "UNRESOLVED" and (
            self.decision_id is None or self.reviewer_principal_id is None
        ):
            raise ValueError("resolved disposition requires a persisted reviewer decision")
        return self


class EvidenceValidity(_FrozenContract):
    evidence_ref_id: EntityId
    valid_from: Instant
    valid_until: Instant | None

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError("evidence validity must have a positive duration")
        return self


class UnitRuleAdmission(_FrozenContract):
    """An independent rule approval and its explicitly declared applicability.

    The adapter must load these values from authenticated persisted human decisions;
    accepting this object is not itself human approval or a check of current DB state.
    """

    rule_id: EntityId
    target: UnitIdentity
    rule_sha256: Sha256
    condition_ids: tuple[NonEmptyString, ...]
    candidate_id: EntityId
    approval_decision_id: EntityId
    producer_principal_id: NonEmptyString
    reviewer_principal_id: NonEmptyString
    reviewed_at: Instant
    evidence_validity: tuple[EvidenceValidity, ...]

    @model_validator(mode="after")
    def validate_approval(self) -> Self:
        if self.producer_principal_id == self.reviewer_principal_id:
            raise ValueError("rule approval must be independent of its producer")
        _unique(self.condition_ids, "admission conditions")
        _unique(tuple(item.evidence_ref_id for item in self.evidence_validity), "evidence validity")
        return self


class UnitQualificationPlan(_FrozenContract):
    qualification_plan_id: EntityId
    version: VersionNumber
    target: UnitIdentity
    manifest: CoverageManifest
    manifest_sha256: Sha256
    dispositions: tuple[ConditionDisposition, ...]
    rules: tuple[RuleSchemaV04, ...]
    root_rule_ids: tuple[EntityId, ...]
    admissions: tuple[UnitRuleAdmission, ...]
    contract_version: Literal["unit-qualification/2.0.0"] = CONTRACT_VERSION

    @model_validator(mode="after")
    def validate_bindings(self) -> Self:
        expected_policy = COVERAGE_POLICY_VERSION
        if self.manifest.coverage_policy_version != expected_policy:
            raise ValueError("coverage policy does not match the plan contract version")
        if self.target != self.manifest.target:
            raise ValueError("manifest target does not match plan target")
        if self.manifest_sha256 != coverage_manifest_sha256(self.manifest):
            raise ValueError("manifest hash does not match the full denominator")
        _unique(tuple(item.condition_id for item in self.dispositions), "dispositions")
        _unique(tuple(item.rule_id for item in self.admissions), "rule admissions")
        conditions = {item.condition_id for item in self.manifest.conditions}
        rules = {item.rule_id: item for item in self.rules}
        for item in self.dispositions:
            if item.condition_id not in conditions:
                raise ValueError("disposition references a condition outside the manifest")
            if not set(item.rule_ids) <= rules.keys():
                raise ValueError("disposition references a nonexistent rule")
        for admission in self.admissions:
            candidate = rules.get(admission.rule_id)
            if candidate is None:
                raise ValueError("admission references a nonexistent rule")
            if admission.target != self.target:
                raise ValueError("rule admission target does not match exact unit version")
            if admission.rule_sha256 != rule_sha256(candidate):
                raise ValueError("rule admission hash does not match approved rule")
            if not set(admission.condition_ids) <= conditions:
                raise ValueError("admission references a condition outside the manifest")
            evidence = {item.evidence_ref_id: item for item in candidate.evidence}
            validity = {item.evidence_ref_id: item for item in admission.evidence_validity}
            if evidence.keys() != validity.keys():
                raise ValueError("admission must declare validity for every evidence reference")
            if any(validity[key].valid_from != item.effective_at for key, item in evidence.items()):
                raise ValueError("evidence validity must start at its declared effective_at")
        if bool(self.rules) != bool(self.root_rule_ids):
            raise ValueError("rules and root_rule_ids must both be empty or non-empty")
        return self


def coverage_manifest_sha256(manifest: CoverageManifest) -> str:
    return content_sha256(manifest.model_dump(mode="json"))


def rule_sha256(rule: RuleSchemaV04) -> str:
    return content_sha256(rule.model_dump(mode="json"))


def content_sha256(value: object) -> str:
    encoded = json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _canonical_value(value: object) -> JsonValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (UUID, date, datetime)):
        return str(value) if isinstance(value, UUID) else value.isoformat()
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("replay payload keys must be strings")
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    raise ValueError(f"unsupported replay value type: {type(value).__name__}")


def _unique(values: tuple[object, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
