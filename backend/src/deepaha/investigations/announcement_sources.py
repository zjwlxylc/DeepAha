"""Read-only announcement source assembly; never a v2 qualification input.

The caller owns authorization and the transaction. This module acquires the same
task lock as applicability writes, reconstructs the base and reads actual source
records. Missing work remains unresolved; invalid existing records raise errors.
"""

import json
from copy import deepcopy
from datetime import date, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from deepaha.documents.models import DocumentBlock
from deepaha.investigations.applicability import _command, _describe, _history, _review_context
from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.facts import _target_contract
from deepaha.investigations.models import (
    InvestigationFactAction,
    InvestigationFactPreparation,
    InvestigationRuleApplicability,
    InvestigationRuleDecision,
    InvestigationRulePreparation,
    InvestigationUnitPlan,
)
from deepaha.investigations.rule_contracts import MaterializeInvestigationUnitPlan
from deepaha.investigations.rules import RULE_BRIDGE_VERSION, _context, reviewed_rule
from deepaha.investigations.store import InvestigationStore
from deepaha.investigations.unit_snapshots import _build, _check_facts, _checked_view
from deepaha.p9b.models import (
    FactVerificationDecisionModel,
    RuleApprovalDecisionModel,
    RuleCandidateEvidence,
    RuleCandidateFact,
    RuleCandidateModel,
    VerifiedFact,
    VerifiedFactEvidence,
)

SNAPSHOT_CONTRACT_VERSION = "investigation-announcement-snapshot/1.0.0"
SNAPSHOT_ADAPTER_VERSION = "investigation-announcement-adapter/1.0.0"


def _json_default(value: object) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"Unsupported persisted value: {type(value).__name__}")


def _record(record: Any) -> dict[str, Any]:
    # Request nonces are transport identity, not source content dependencies.
    return cast(
        dict[str, Any],
        json.loads(
            json.dumps(
                {
                    column.key: getattr(record, column.key)
                    for column in record.__table__.columns
                    if column.key != "request_key_hash"
                },
                default=_json_default,
            )
        ),
    )


def build_announcement_snapshot(
    store: InvestigationStore,
    session: Session,
    task_id: UUID,
    base_plan_id: UUID,
) -> dict[str, Any]:
    store._get(session, task_id, lock=True)
    record = session.get(InvestigationUnitPlan, base_plan_id)
    if record is None:
        raise InvestigationError("UNIT_PLAN_NOT_FOUND")
    command = _command(session, task_id, record.rule_preparation_id)
    plan, context = _build(store, session, task_id, command, base_plan_id)
    base = _checked_view(record, plan, context)
    facts = session.get(InvestigationFactPreparation, command.fact_preparation_id)
    assert facts is not None  # the base reconstruction validated the exact preparation
    rows = cast(list[dict[str, Any]], facts.result["rows"])
    conditions = [c for c in base["plan"]["manifest"]["conditions"] if c["scope"] == "ANNOUNCEMENT"]
    for condition in conditions:
        row = rows[condition["source_index"]]
        if (
            row["entity_id"] != condition["source_entity_id"]
            or digest(row) != condition["source_sha256"]
        ):
            raise InvestigationError("ANNOUNCEMENT_SOURCE_DENOMINATOR_INVALID")
    sources = [
        _load_source(store, session, task_id, base_plan_id, command, facts, entity_id)
        for entity_id in sorted({c["source_entity_id"] for c in conditions})
    ]
    # A recorded applicability that no longer maps to the source set is a conflict,
    # not permission to silently discard its previous decision.
    represented = {
        decision["decision_id"]
        for source in sources
        for history in source["applicability_histories"].values()
        for decision in history
    }
    actual = {
        str(value)
        for value in session.scalars(
            select(InvestigationRuleApplicability.decision_id).where(
                InvestigationRuleApplicability.target_plan_id == base_plan_id,
            )
        )
    }
    if actual != represented:
        raise InvestigationError("ANNOUNCEMENT_SOURCE_APPLICABILITY_CONFLICT")
    return _assemble(base, sources)


def _fact_actions(
    session: Session,
    facts: InvestigationFactPreparation,
    entity_id: str,
    rows: list[dict[str, Any]],
    command: MaterializeInvestigationUnitPlan,
    now: datetime,
) -> list[dict[str, Any]]:
    result = []
    candidates = {row["candidate_id"] for row in rows if row["candidate_id"]}
    final: set[str] = set()
    for action in session.scalars(
        select(InvestigationFactAction)
        .where(
            InvestigationFactAction.preparation_id == facts.preparation_id,
            InvestigationFactAction.entity_id == entity_id,
        )
        .order_by(InvestigationFactAction.action_id)
    ):
        request = cast(dict[str, Any], action.request)
        if (
            digest(request) != action.request_hash
            or request.get("kind") != action.kind
            or request.get("preparation_id") != str(facts.preparation_id)
            or any(
                request.get(k) != str(getattr(command, k))
                for k in ("binding_id", "check_id", "delivery_hash")
            )
        ):
            raise InvestigationError("ANNOUNCEMENT_SOURCE_FACT_ACTION_CONFLICT")
        view = _record(action)
        if action.kind == "DECISION":
            decision = session.get(FactVerificationDecisionModel, action.decision_id)
            candidate_id = str(action.candidate_id)
            if (
                candidate_id not in candidates
                or request.get("candidate_id") != candidate_id
                or decision is None
                or decision.candidate_id != action.candidate_id
                or decision.decision != request.get("decision")
                or decision.verification_method != "HUMAN"
                or decision.verifier_identity != f"human:{action.reviewer_id}"
                or decision.evidence_support_result != request.get("evidence_support")
                or decision.precedence_check_result != request.get("precedence_check")
                or decision.decided_at > now
                or candidate_id in final
            ):
                raise InvestigationError("ANNOUNCEMENT_SOURCE_FACT_ACTION_CONFLICT")
            if decision.decision != "NEEDS_ADJUDICATION":
                final.add(candidate_id)
            view["verification"] = _record(decision)
        elif action.kind != "PROMOTION" or request.get("entity_id") != entity_id:
            raise InvestigationError("ANNOUNCEMENT_SOURCE_FACT_ACTION_CONFLICT")
        result.append(view)
    return result


def _source_facts(
    session: Session,
    fact_set_id: UUID,
    source_rows: list[dict[str, Any]],
    actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = {row["candidate_id"]: row for row in source_rows if row["candidate_id"]}
    verified = {action["decision_id"]: action for action in actions if action["kind"] == "DECISION"}
    expected = {
        action["candidate_id"]
        for action in verified.values()
        if action["request"]["decision"] in ("APPROVE", "UNKNOWN")
    }
    records = list(
        session.scalars(
            select(VerifiedFact)
            .where(
                VerifiedFact.verified_fact_set_id == fact_set_id,
            )
            .order_by(VerifiedFact.verified_fact_id)
        )
    )
    if {str(f.candidate_id) for f in records} != expected or len(records) != len(expected):
        raise InvestigationError("ANNOUNCEMENT_SOURCE_FACTS_CONFLICT")
    result = []
    for fact in records:
        row = rows.get(str(fact.candidate_id))
        action = verified.get(str(fact.verification_decision_id))
        if (
            row is None
            or action is None
            or action["candidate_id"] != str(fact.candidate_id)
            or fact.field_name != row["field_name"]
            or fact.raw_value != row["raw_value"]
            or fact.fact_state
            != ("KNOWN" if action["request"]["decision"] == "APPROVE" else "UNKNOWN")
            or fact.normalized_value
            != (row["normalized_value_candidate"] if fact.fact_state == "KNOWN" else None)
        ):
            raise InvestigationError("ANNOUNCEMENT_SOURCE_FACTS_CONFLICT")
        result.append(_record(fact) | {"verification": deepcopy(action["verification"])})
    return result


def _rule_rows(
    session: Session,
    prep: InvestigationRulePreparation,
    target: dict[str, Any],
) -> dict[str, RuleCandidateModel]:
    rows = cast(list[dict[str, Any]], prep.result["rows"])
    _check_facts(session, rows, prep.fact_set_id)
    candidates = {}
    for row in rows:
        evidence = list(
            session.execute(
                select(VerifiedFactEvidence, DocumentBlock)
                .join(
                    DocumentBlock,
                    DocumentBlock.block_id == VerifiedFactEvidence.block_id,
                )
                .where(VerifiedFactEvidence.verified_fact_id == UUID(row["verified_fact_id"]))
                .order_by(VerifiedFactEvidence.evidence_ref_id)
            )
        )
        expected = [
            {
                "evidence_ref_id": str(e.evidence_ref_id),
                "block_id": str(b.block_id),
                "document_id": str(b.document_id),
                "text": b.canonical_text_or_value,
                "structural_locator": b.structural_locator,
            }
            for e, b in evidence
        ]
        if row["evidence"] != expected or row["evidence_ref_ids"] != [
            e["evidence_ref_id"] for e in expected
        ]:
            raise InvestigationError("ANNOUNCEMENT_SOURCE_RULE_EVIDENCE_CONFLICT")
        key = row["rule_candidate_id"]
        if key is None:
            if row["payload"] is not None:
                raise InvestigationError("ANNOUNCEMENT_SOURCE_RULE_CANDIDATE_CONFLICT")
            continue
        candidate = session.get(RuleCandidateModel, UUID(key))
        if (
            key in candidates
            or candidate is None
            or candidate.proposed_rule_payload != row["payload"]
            or candidate.verified_fact_set_id != prep.fact_set_id
            or candidate.compiler_version != RULE_BRIDGE_VERSION
            or any(
                str(getattr(candidate, k)) != str(v) for k, v in _target_contract(target).items()
            )
            or set(
                session.scalars(
                    select(RuleCandidateFact.verified_fact_id).where(
                        RuleCandidateFact.rule_candidate_id == candidate.rule_candidate_id
                    )
                )
            )
            != {UUID(row["verified_fact_id"])}
            or set(
                session.scalars(
                    select(RuleCandidateEvidence.evidence_ref_id).where(
                        RuleCandidateEvidence.rule_candidate_id == candidate.rule_candidate_id
                    )
                )
            )
            != {e.evidence_ref_id for e, _ in evidence}
        ):
            raise InvestigationError("ANNOUNCEMENT_SOURCE_RULE_CANDIDATE_CONFLICT")
        candidates[key] = candidate
    return candidates


def _rule_decisions(
    store: InvestigationStore,
    session: Session,
    prep: InvestigationRulePreparation,
    command: MaterializeInvestigationUnitPlan,
    candidates: dict[str, RuleCandidateModel],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    # Unlike _final_decisions, this validates partial groups without declaring
    # missing final decisions to be data corruption.
    history, final = [], {}
    now = store.clock()
    for decision in session.scalars(
        select(InvestigationRuleDecision)
        .where(
            InvestigationRuleDecision.rule_preparation_id == prep.rule_preparation_id,
        )
        .order_by(InvestigationRuleDecision.decision_id)
    ):
        key = str(decision.rule_candidate_id)
        candidate = candidates.get(key)
        approval = session.get(RuleApprovalDecisionModel, decision.decision_id)
        if (
            candidate is None
            or approval is None
            or key in final
            or digest(decision.request) != decision.request_hash
            or any(str(decision.request.get(k)) != str(v) for k, v in command.model_dump().items())
            or decision.request.get("rule_candidate_id") != key
            or approval.rule_candidate_id != decision.rule_candidate_id
            or approval.decision != decision.request.get("decision")
            or approval.decision not in ("APPROVE", "REJECT", "NEEDS_ADJUDICATION")
            or approval.approval_method != "HUMAN"
            or approval.approver_identity != f"human:{decision.reviewer_id}"
            or approval.policy_version != RULE_BRIDGE_VERSION
            or approval.approver_identity == candidate.producer_identity
            or approval.decided_at > now
        ):
            raise InvestigationError("ANNOUNCEMENT_SOURCE_RULE_APPROVAL_CONFLICT")
        view = _record(decision) | {"approval": _record(approval)}
        history.append(view)
        if approval.decision != "NEEDS_ADJUDICATION":
            final[key] = view
    return history, final


def _load_source(
    store: InvestigationStore,
    session: Session,
    task_id: UUID,
    base_plan_id: UUID,
    base_command: MaterializeInvestigationUnitPlan,
    facts: InvestigationFactPreparation,
    entity_id: str,
) -> dict[str, Any]:
    rows = [
        row
        for row in cast(list[dict[str, Any]], facts.result["rows"])
        if row["entity_id"] == entity_id
    ]
    actions = _fact_actions(session, facts, entity_id, rows, base_command, store.clock())
    promotions = [action for action in actions if action["kind"] == "PROMOTION"]
    preparations = list(
        session.scalars(
            select(InvestigationRulePreparation)
            .where(
                InvestigationRulePreparation.fact_preparation_id == facts.preparation_id,
                InvestigationRulePreparation.entity_id == entity_id,
            )
            .order_by(InvestigationRulePreparation.rule_preparation_id)
        )
    )
    result: dict[str, Any] = {
        "entity_id": entity_id,
        "source_rows": deepcopy(rows),
        "fact_actions": actions,
        "fact_set": None,
        "facts": [],
        "rule_preparation": None,
        "rule_rows": [],
        "other_rule_preparations": [],
        "rule_decisions": [],
        "rule_candidates": [],
        "all_rules_final": False,
        "approved_rules": {},
        "approved_rule_decisions": {},
        "applicability_histories": {},
    }
    if not promotions:
        if preparations:
            raise InvestigationError("ANNOUNCEMENT_SOURCE_PROMOTION_CONFLICT")
        return result
    if len(promotions) != 1:
        raise InvestigationError("ANNOUNCEMENT_SOURCE_PROMOTION_CONFLICT")
    fact_set_id = UUID(promotions[0]["fact_set_id"])
    source_command = base_command.model_copy(
        update={"entity_id": entity_id, "fact_set_id": fact_set_id}
    )
    _, _, _, fact_set, target = _context(store, session, task_id, source_command)
    if target["entity_kind"] != "announcement" or target["target_scope"] != "OPPORTUNITY":
        raise InvestigationError("ANNOUNCEMENT_SOURCE_TARGET_CONFLICT")
    result["fact_set"] = _record(fact_set)
    result["facts"] = _source_facts(session, fact_set_id, rows, actions)
    current = []
    for prep in preparations:
        if digest(prep.result) != prep.result_hash or prep.fact_set_id != fact_set_id:
            raise InvestigationError("ANNOUNCEMENT_SOURCE_RULE_PREPARATION_CONFLICT")
        if prep.compiler_version == RULE_BRIDGE_VERSION:
            current.append(prep)
        else:
            result["other_rule_preparations"].append(_record(prep))
    if not current:
        return result
    if len(current) != 1:
        raise InvestigationError("ANNOUNCEMENT_SOURCE_RULE_PREPARATION_CONFLICT")
    prep = current[0]
    source_command = source_command.model_copy(
        update={"rule_preparation_id": prep.rule_preparation_id}
    )
    if (
        prep.result["target"] != target
        or prep.result["source_rows"] != facts.result["rows"]
        or prep.result["fact_preparation_hash"] != facts.result_hash
        or prep.result["binding_id"] != str(facts.binding_id)
        or prep.result["check_id"] != str(facts.check_id)
        or prep.result["delivery_hash"] != base_command.delivery_hash
        or prep.result["source_bundle_revision_id"] != str(fact_set.source_bundle_revision_id)
        or prep.result["fact_set_version"] != fact_set.version
    ):
        raise InvestigationError("ANNOUNCEMENT_SOURCE_RULE_PREPARATION_CONFLICT")
    candidates = _rule_rows(session, prep, target)
    history, final = _rule_decisions(store, session, prep, source_command, candidates)
    all_final = set(final) == set(candidates)
    result.update(
        rule_preparation=_record(prep),
        rule_rows=deepcopy(prep.result["rows"]),
        rule_candidates=[_record(candidates[key]) for key in sorted(candidates)],
        rule_decisions=history,
        all_rules_final=all_final,
    )
    for row in cast(list[dict[str, Any]], prep.result["rows"]):
        key = row["rule_candidate_id"]
        decision = final.get(key)
        if key is not None:
            result["applicability_histories"][key] = []
        if decision is None or decision["request"]["decision"] != "APPROVE":
            continue
        rule = reviewed_rule(row, decision["request"], target).model_dump(mode="json")
        result["approved_rules"][key] = rule
        result["approved_rule_decisions"][key] = decision
        if all_final:
            context, view = _review_context(
                store, session, task_id, base_plan_id, prep.rule_preparation_id, UUID(key)
            )
            if view["source_rule"] != rule:
                raise InvestigationError("ANNOUNCEMENT_SOURCE_RULE_APPROVAL_CONFLICT")
            result["applicability_histories"][key] = [
                _describe(session, r, context) for r in _history(session, context)
            ]
    return result


def _condition_view(condition: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    original = next(
        (r for r in source["source_rows"] if r["source_index"] == condition["source_index"]), None
    )
    if original is None:
        raise InvestigationError("ANNOUNCEMENT_SOURCE_DENOMINATOR_INVALID")
    fact = next((f for f in source["facts"] if f["candidate_id"] == original["candidate_id"]), None)
    row = next(
        (
            r
            for r in source["rule_rows"]
            if fact and r["verified_fact_id"] == fact["verified_fact_id"]
        ),
        None,
    )
    key = row["rule_candidate_id"] if row else None
    rule = source["approved_rules"].get(key)
    approval = source["approved_rule_decisions"].get(key)
    history = source["applicability_histories"].get(key, [])
    latest = history[-1] if history else None
    reasons = []
    if fact is None:
        rejected = any(
            a.get("candidate_id") == original["candidate_id"]
            and a["request"].get("decision") == "REJECT"
            for a in source["fact_actions"]
        )
        reasons.append("SOURCE_FACT_REJECTED" if rejected else "SOURCE_FACT_NOT_PROMOTED")
        if original["candidate_id"] is None:
            reasons.append("SOURCE_FACT_CANDIDATE_MISSING")
        state_reason = {
            "UNLOCATED": "SOURCE_EVIDENCE_UNVERIFIED",
            "UNSUPPORTED": "SOURCE_FIELD_UNSUPPORTED",
            "CONFLICT": "SOURCE_CONDITION_CONFLICT",
            "UNKNOWN": "SOURCE_CONDITION_UNKNOWN",
            "UNPROCESSED": "SOURCE_CONDITION_UNPROCESSED",
        }.get(condition["state"])
        if state_reason:
            reasons.append(state_reason)
    elif fact["fact_state"] != "KNOWN":
        reasons.append("SOURCE_FACT_UNKNOWN")
    if source["rule_preparation"] is None:
        reasons.append("SOURCE_RULE_PREPARATION_MISSING")
    elif row is None or key is None:
        reasons.append("SOURCE_RULE_CANDIDATE_MISSING")
    elif rule is None:
        rejected = any(
            d["request"].get("rule_candidate_id") == key and d["request"]["decision"] == "REJECT"
            for d in source["rule_decisions"]
        )
        reasons.append("SOURCE_RULE_REJECTED" if rejected else "SOURCE_RULE_APPROVAL_REQUIRED")
    if not source["all_rules_final"]:
        reasons.append("SOURCE_RULE_GROUP_UNRESOLVED")
    disposition = "UNRESOLVED"
    if latest is None:
        reasons.append("APPLICABILITY_NOT_REVIEWED")
    elif latest["request"]["outcome"] == "NEEDS_ADJUDICATION":
        reasons.append("APPLICABILITY_NEEDS_ADJUDICATION")
    elif not reasons and rule is not None and approval is not None:
        disposition = {"APPLIES": "INHERITED", "DOES_NOT_APPLY": "EXCLUDED"}[
            latest["request"]["outcome"]
        ]
    return {
        "condition": deepcopy(condition),
        "source_fact": deepcopy(fact),
        "source_rule": deepcopy(rule),
        "source_rule_approval": deepcopy(approval),
        "applicability": deepcopy(latest),
        "disposition": disposition,
        "reasons": reasons,
    }


def _assemble(base: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any]:
    conditions = [c for c in base["plan"]["manifest"]["conditions"] if c["scope"] == "ANNOUNCEMENT"]
    by_entity = {source["entity_id"]: source for source in sources}
    if len(by_entity) != len(sources) or set(by_entity) != {
        c["source_entity_id"] for c in conditions
    }:
        raise InvestigationError("ANNOUNCEMENT_SOURCE_DENOMINATOR_INVALID")
    rows = [_condition_view(c, by_entity[c["source_entity_id"]]) for c in conditions]
    dependencies = {
        "contract_version": SNAPSHOT_CONTRACT_VERSION,
        "adapter_version": SNAPSHOT_ADAPTER_VERSION,
        "base_plan_id": base["plan_id"],
        "base_plan_hash": base["plan_hash"],
        "base_context_hash": base["context_hash"],
        "base_v2_hash": digest(base),
        "fact_preparation_id": base["plan"]["manifest"]["preparation_id"],
        "fact_preparation_hash": base["plan"]["manifest"]["preparation_sha256"],
        "announcement_sources": deepcopy(sorted(sources, key=lambda s: s["entity_id"])),
        "announcement_conditions": deepcopy(rows),
    }
    return {
        "dependencies": dependencies,
        "dependencies_hash": digest(dependencies),
        "snapshot": {
            "scope": "DERIVED_SCOPE_SNAPSHOT_ONLY",
            "contract_version": SNAPSHOT_CONTRACT_VERSION,
            "adapter_version": SNAPSHOT_ADAPTER_VERSION,
            "base_v2": deepcopy(base),
            "announcement_conditions": rows,
            "overall_qualification": "UNCERTAIN",
        },
    }
