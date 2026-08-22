import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from uuid import UUID, uuid7

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from deepaha.contracts.phase4 import (
    EligibilityResultSchemaV04,
    MatchSnapshotSchemaV04,
    ProfileSnapshotSchemaV04,
    RuleEvaluationSchemaV04,
    RuleSchemaV04,
    RuleSetSchemaV04,
)
from deepaha.eligibility.engine import (
    ENGINE_VERSION,
    EligibilityDecision,
    EvaluationContext,
    evaluate_eligibility,
)
from deepaha.eligibility.models import EligibilityResultModel
from deepaha.matching.models import MatchSnapshotModel
from deepaha.opportunities.models import OpportunityVersion
from deepaha.profiles.models import ProfileSnapshotModel
from deepaha.rules.compiler import COMPILER_VERSION, compile_rule_set
from deepaha.rules.major import ApprovedMajorMapping, MajorCatalog
from deepaha.rules.models import RuleEvidenceModel, RuleModel, RuleSetModel


class MatchInputError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MatchInput:
    opportunity_id: UUID
    opportunity_version: int
    rule_set_id: UUID
    rule_set_version: int
    profile_snapshot_id: UUID
    major_catalog: MajorCatalog
    major_mapping: ApprovedMajorMapping
    evaluated_at: datetime
    created_at: datetime
    semantic_major_candidate: bool = False


@dataclass(frozen=True, slots=True)
class ReplayDifference:
    field: str
    left: object
    right: object


@dataclass(frozen=True, slots=True)
class _LoadedInput:
    opportunity_version: OpportunityVersion
    rule_set: RuleSetSchemaV04
    profile: ProfileSnapshotSchemaV04


class EligibilityService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        id_factory: Callable[[], UUID] = uuid7,
    ) -> None:
        self._session_factory = session_factory
        self._id_factory = id_factory

    def evaluate_and_save(self, match_input: MatchInput) -> MatchSnapshotSchemaV04:
        input_sha256: str | None = None
        with self._session_factory() as session:
            try:
                loaded = self._load_input(session, match_input)
                compiled = compile_rule_set(loaded.rule_set)
                input_sha256 = _input_sha256(match_input, loaded, compiled.compiled_sha256)
                existing = self._existing_by_hash(session, input_sha256)
                if existing is not None:
                    session.rollback()
                    return existing
                decision = evaluate_eligibility(
                    EvaluationContext(
                        rule_set=compiled,
                        profile_attributes=loaded.profile.attributes.model_dump(mode="python"),
                        major_catalog=match_input.major_catalog,
                        major_mapping=match_input.major_mapping,
                        scenario_clock=loaded.profile.scenario_clock,
                        semantic_major_candidate=match_input.semantic_major_candidate,
                    )
                )
                result_contract = _result_contract(
                    self._id_factory(),
                    decision,
                    match_input.evaluated_at,
                )
                snapshot_contract = MatchSnapshotSchemaV04(
                    snapshot_id=self._id_factory(),
                    opportunity_id=match_input.opportunity_id,
                    opportunity_version=match_input.opportunity_version,
                    rule_set_id=match_input.rule_set_id,
                    rule_set_version=match_input.rule_set_version,
                    profile_snapshot_id=match_input.profile_snapshot_id,
                    profile_version=loaded.profile.version,
                    eligibility_result=result_contract,
                    compiler_version=COMPILER_VERSION,
                    engine_version=ENGINE_VERSION,
                    major_catalog_version=match_input.major_catalog.version,
                    major_mapping_version=match_input.major_mapping.version,
                    scenario_clock=loaded.profile.scenario_clock,
                    input_sha256=input_sha256,
                    created_at=match_input.created_at,
                )
                self._persist(session, snapshot_contract)
                session.commit()
                return snapshot_contract
            except IntegrityError:
                session.rollback()
                if input_sha256 is not None:
                    existing = self._existing_by_hash(session, input_sha256)
                    if existing is not None:
                        return existing
                raise
            except Exception:
                session.rollback()
                raise

    def replay(self, snapshot_id: UUID) -> MatchSnapshotSchemaV04:
        with self._session_factory() as session:
            snapshot = session.get(MatchSnapshotModel, snapshot_id)
            if snapshot is None:
                raise MatchInputError(f"MatchSnapshot does not exist: {snapshot_id}")
            return self._contract_from_rows(session, snapshot)

    def diff(self, left_id: UUID, right_id: UUID) -> tuple[ReplayDifference, ...]:
        left = self.replay(left_id)
        right = self.replay(right_id)
        differences: list[ReplayDifference] = []
        left_values = left.model_dump(mode="json")
        right_values = right.model_dump(mode="json")
        for field in (
            "opportunity_id",
            "opportunity_version",
            "rule_set_id",
            "rule_set_version",
            "profile_snapshot_id",
            "profile_version",
            "compiler_version",
            "engine_version",
            "major_catalog_version",
            "major_mapping_version",
            "scenario_clock",
            "input_sha256",
        ):
            if left_values[field] != right_values[field]:
                differences.append(ReplayDifference(field, left_values[field], right_values[field]))
        if left.eligibility_result.status is not right.eligibility_result.status:
            differences.append(
                ReplayDifference(
                    "eligibility_status",
                    left.eligibility_result.status.value,
                    right.eligibility_result.status.value,
                )
            )
        left_rules = {item.rule_id: item for item in left.eligibility_result.rule_evaluations}
        right_rules = {item.rule_id: item for item in right.eligibility_result.rule_evaluations}
        for rule_id in sorted(set(left_rules) | set(right_rules), key=str):
            left_rule = left_rules.get(rule_id)
            right_rule = right_rules.get(rule_id)
            left_payload = None if left_rule is None else left_rule.model_dump(mode="json")
            right_payload = None if right_rule is None else right_rule.model_dump(mode="json")
            if left_payload != right_payload:
                differences.append(ReplayDifference(f"rule:{rule_id}", left_payload, right_payload))
        return tuple(differences)

    def _load_input(self, session: Session, match_input: MatchInput) -> _LoadedInput:
        opportunity_version = session.get(
            OpportunityVersion,
            (match_input.opportunity_id, match_input.opportunity_version),
        )
        if opportunity_version is None:
            raise MatchInputError("exact OpportunityVersion does not exist")
        rule_set_row = session.get(
            RuleSetModel,
            (match_input.rule_set_id, match_input.rule_set_version),
        )
        if rule_set_row is None:
            raise MatchInputError("exact RuleSet version does not exist")
        if (
            rule_set_row.opportunity_id != match_input.opportunity_id
            or rule_set_row.opportunity_version != match_input.opportunity_version
        ):
            raise MatchInputError("RuleSet does not belong to the exact OpportunityVersion")
        profile_row = session.get(ProfileSnapshotModel, match_input.profile_snapshot_id)
        if profile_row is None:
            raise MatchInputError("exact ProfileSnapshot does not exist")
        if not profile_row.synthetic:
            raise MatchInputError("Phase 4 accepts synthetic ProfileSnapshot only")
        rule_set = self._rule_set_contract(session, rule_set_row)
        profile = ProfileSnapshotSchemaV04.model_validate(
            {
                "profile_snapshot_id": profile_row.profile_snapshot_id,
                "profile_id": profile_row.profile_id,
                "version": profile_row.version,
                "synthetic": profile_row.synthetic,
                "persona_family_id": profile_row.persona_family_id,
                "attributes": profile_row.attributes,
                "scenario_clock": profile_row.scenario_clock,
                "profile_schema_version": profile_row.profile_schema_version,
                "created_at": profile_row.created_at,
                "created_by": profile_row.created_by,
                "reviewed_by": profile_row.reviewed_by,
                "change_note": profile_row.change_note,
            }
        )
        if match_input.major_mapping.catalog_version != match_input.major_catalog.version:
            raise MatchInputError("major mapping catalog version does not match catalog")
        return _LoadedInput(opportunity_version, rule_set, profile)

    @staticmethod
    def _rule_set_contract(
        session: Session,
        rule_set_row: RuleSetModel,
    ) -> RuleSetSchemaV04:
        rule_rows = session.scalars(
            select(RuleModel)
            .where(
                RuleModel.rule_set_id == rule_set_row.rule_set_id,
                RuleModel.rule_set_version == rule_set_row.version,
            )
            .order_by(RuleModel.rule_id)
        ).all()
        evidence_rows = session.scalars(
            select(RuleEvidenceModel)
            .where(
                RuleEvidenceModel.rule_set_id == rule_set_row.rule_set_id,
                RuleEvidenceModel.rule_set_version == rule_set_row.version,
            )
            .order_by(
                RuleEvidenceModel.rule_id,
                RuleEvidenceModel.precedence.desc(),
                RuleEvidenceModel.evidence_ref_id,
            )
        ).all()
        evidence_by_rule: dict[UUID, list[RuleEvidenceModel]] = defaultdict(list)
        for item in evidence_rows:
            evidence_by_rule[item.rule_id].append(item)
        rules = [
            RuleSchemaV04.model_validate(
                {
                    "rule_id": row.rule_id,
                    "code": row.code,
                    "operator": row.operator,
                    "field": row.field,
                    "value_type": row.value_type,
                    "value": row.value,
                    "operand_rule_ids": row.operand_rule_ids,
                    "required": row.required,
                    "reason_template": row.reason_template,
                    "evidence": [
                        {
                            "evidence_ref_id": evidence.evidence_ref_id,
                            "document_id": evidence.document_id,
                            "authority": evidence.authority,
                            "precedence": evidence.precedence,
                            "relation": evidence.relation,
                            "effective_at": evidence.effective_at,
                            "assertion_sha256": evidence.assertion_sha256,
                        }
                        for evidence in evidence_by_rule[row.rule_id]
                    ],
                }
            )
            for row in rule_rows
        ]
        return RuleSetSchemaV04.model_validate(
            {
                "rule_set_id": rule_set_row.rule_set_id,
                "version": rule_set_row.version,
                "opportunity_id": rule_set_row.opportunity_id,
                "opportunity_version": rule_set_row.opportunity_version,
                "rules": rules,
                "root_rule_ids": rule_set_row.root_rule_ids,
                "review_status": rule_set_row.review_status,
                "rule_schema_version": rule_set_row.rule_schema_version,
                "created_at": rule_set_row.created_at,
            }
        )

    @staticmethod
    def _persist(session: Session, snapshot: MatchSnapshotSchemaV04) -> None:
        result = snapshot.eligibility_result
        session.add(
            EligibilityResultModel(
                result_id=result.result_id,
                opportunity_id=snapshot.opportunity_id,
                opportunity_version=snapshot.opportunity_version,
                rule_set_id=snapshot.rule_set_id,
                rule_set_version=snapshot.rule_set_version,
                profile_snapshot_id=snapshot.profile_snapshot_id,
                status=result.status.value,
                rule_results=[item.model_dump(mode="json") for item in result.rule_evaluations],
                satisfied_rule_ids=[str(item) for item in result.satisfied_rule_ids],
                conflict_rule_ids=[str(item) for item in result.conflict_rule_ids],
                unknown_rule_ids=[str(item) for item in result.unknown_rule_ids],
                missing_fields=[item.value for item in result.missing_fields],
                review_reasons=list(result.review_reasons),
                evaluated_at=result.evaluated_at,
                engine_version=result.engine_version,
            )
        )
        session.flush()
        session.add(
            MatchSnapshotModel(
                snapshot_id=snapshot.snapshot_id,
                eligibility_result_id=result.result_id,
                opportunity_id=snapshot.opportunity_id,
                opportunity_version=snapshot.opportunity_version,
                rule_set_id=snapshot.rule_set_id,
                rule_set_version=snapshot.rule_set_version,
                profile_snapshot_id=snapshot.profile_snapshot_id,
                profile_version=snapshot.profile_version,
                compiler_version=snapshot.compiler_version,
                engine_version=snapshot.engine_version,
                major_catalog_version=snapshot.major_catalog_version,
                major_mapping_version=snapshot.major_mapping_version,
                scenario_clock=snapshot.scenario_clock,
                input_sha256=snapshot.input_sha256,
                created_at=snapshot.created_at,
            )
        )
        session.flush()

    def _existing_by_hash(
        self,
        session: Session,
        input_sha256: str,
    ) -> MatchSnapshotSchemaV04 | None:
        snapshot = session.scalar(
            select(MatchSnapshotModel).where(MatchSnapshotModel.input_sha256 == input_sha256)
        )
        if snapshot is None:
            return None
        return self._contract_from_rows(session, snapshot)

    @staticmethod
    def _contract_from_rows(
        session: Session,
        snapshot: MatchSnapshotModel,
    ) -> MatchSnapshotSchemaV04:
        result = session.get(EligibilityResultModel, snapshot.eligibility_result_id)
        if result is None:
            raise MatchInputError("MatchSnapshot references a missing EligibilityResult")
        result_contract = EligibilityResultSchemaV04.model_validate(
            {
                "result_id": result.result_id,
                "status": result.status,
                "rule_evaluations": result.rule_results,
                "satisfied_rule_ids": result.satisfied_rule_ids,
                "conflict_rule_ids": result.conflict_rule_ids,
                "unknown_rule_ids": result.unknown_rule_ids,
                "missing_fields": result.missing_fields,
                "review_reasons": result.review_reasons,
                "evaluated_at": result.evaluated_at,
                "engine_version": result.engine_version,
            }
        )
        return MatchSnapshotSchemaV04(
            snapshot_id=snapshot.snapshot_id,
            opportunity_id=snapshot.opportunity_id,
            opportunity_version=snapshot.opportunity_version,
            rule_set_id=snapshot.rule_set_id,
            rule_set_version=snapshot.rule_set_version,
            profile_snapshot_id=snapshot.profile_snapshot_id,
            profile_version=snapshot.profile_version,
            eligibility_result=result_contract,
            compiler_version=snapshot.compiler_version,
            engine_version=snapshot.engine_version,
            major_catalog_version=snapshot.major_catalog_version,
            major_mapping_version=snapshot.major_mapping_version,
            scenario_clock=snapshot.scenario_clock,
            input_sha256=snapshot.input_sha256,
            created_at=snapshot.created_at,
        )


def _result_contract(
    result_id: UUID,
    decision: EligibilityDecision,
    evaluated_at: datetime,
) -> EligibilityResultSchemaV04:
    return EligibilityResultSchemaV04(
        result_id=result_id,
        status=decision.status,
        rule_evaluations=tuple(
            RuleEvaluationSchemaV04(
                rule_id=item.rule_id,
                outcome=item.outcome,
                deterministic=item.deterministic,
                official_evidence=item.official_evidence,
                reason_code=item.reason_code,
                evidence_ref_ids=item.evidence_ref_ids,
                missing_fields=item.missing_fields,
            )
            for item in decision.rule_evaluations
        ),
        satisfied_rule_ids=decision.satisfied_rule_ids,
        conflict_rule_ids=decision.conflict_rule_ids,
        unknown_rule_ids=decision.unknown_rule_ids,
        missing_fields=decision.missing_fields,
        review_reasons=decision.review_reasons,
        evaluated_at=evaluated_at,
        engine_version=decision.engine_version,
    )


def _input_sha256(
    match_input: MatchInput,
    loaded: _LoadedInput,
    compiled_rule_set_sha256: str,
) -> str:
    catalog_entries = [
        {
            "code": entry.code,
            "name": entry.name,
            "parent_codes": list(entry.parent_codes),
        }
        for _, entry in sorted(match_input.major_catalog.entries.items())
    ]
    mapping_entries = [
        {"source_code": source, "target_codes": list(targets)}
        for source, targets in sorted(match_input.major_mapping.targets_by_source.items())
    ]
    payload = {
        "opportunity_version": {
            "opportunity_id": str(match_input.opportunity_id),
            "version": match_input.opportunity_version,
            "content_sha256": loaded.opportunity_version.content_sha256,
        },
        "rule_set": loaded.rule_set.model_dump(mode="json"),
        "compiled_rule_set_sha256": compiled_rule_set_sha256,
        "profile_snapshot": loaded.profile.model_dump(mode="json"),
        "compiler_version": COMPILER_VERSION,
        "engine_version": ENGINE_VERSION,
        "major_catalog": {
            "version": match_input.major_catalog.version,
            "entries": catalog_entries,
        },
        "major_mapping": {
            "version": match_input.major_mapping.version,
            "catalog_version": match_input.major_mapping.catalog_version,
            "approved_by": match_input.major_mapping.approved_by,
            "approved_at": match_input.major_mapping.approved_at.isoformat(),
            "entries": mapping_entries,
        },
        "scenario_clock": loaded.profile.scenario_clock.isoformat(),
        "semantic_major_candidate": match_input.semantic_major_candidate,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


__all__ = [
    "EligibilityService",
    "MatchInput",
    "MatchInputError",
    "ReplayDifference",
]
