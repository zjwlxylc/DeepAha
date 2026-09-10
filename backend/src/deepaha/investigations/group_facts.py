"""Exact group facts through independent P9B review, never inherited position facts."""

from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
from typing import Any, cast
from uuid import UUID, uuid7

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from deepaha.contracts.phase9b import (
    ExtractionCandidateSchemaV08,
    ExtractionRunSchemaV08,
    FactVerificationDecisionSchemaV08,
)
from deepaha.documents.models import DocumentBlock
from deepaha.investigations.bindings import _authorize
from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.delivery import DeliveryEvidence, DeliveryFact
from deepaha.investigations.facts import _current_check
from deepaha.investigations.field_mapping import map_field_value
from deepaha.investigations.group_bindings import _view as group_view
from deepaha.investigations.group_fact_contracts import (
    GROUP_FACT_VERSION,
    DecideGroupFact,
    GroupFactRecord,
    GroupFactResult,
    PrepareGroupFacts,
    PromoteGroupFacts,
)
from deepaha.investigations.group_sources import build_group_source
from deepaha.investigations.models import (
    InvestigationBinding,
    InvestigationGroupBinding,
    InvestigationGroupFactAction,
    InvestigationGroupFactPreparation,
)
from deepaha.investigations.store import InvestigationStore
from deepaha.local_human_test.review import require_human_fact_reviewer, validate_idempotency_key
from deepaha.p9b.facts import (
    FactLifecycleError,
    FactLifecycleService,
    extraction_input_block_set_hash,
)
from deepaha.p9b.hashing import extraction_evidence_binding_hash
from deepaha.p9b.models import FactVerificationDecisionModel, VersionedVerifiedFactSet
from deepaha.review.auth import ReviewerPrincipal


def _context(
    store: InvestigationStore, session: Session, task_id: UUID, group_id: UUID, check_id: UUID
) -> tuple[dict[str, Any], dict[str, Any]]:
    task = store._get(session, task_id, lock=True)
    group = session.get(InvestigationGroupBinding, group_id)
    if group is None or group.task_id != task_id:
        raise InvestigationError("GROUP_FACT_SOURCE_NOT_FOUND")
    source = group_view(
        session, group, build_group_source(store, session, task_id, group.source_entity_id)
    )
    binding = session.get(InvestigationBinding, group.binding_id)
    assert binding is not None
    check = _current_check(store, session, task, binding, check_id)
    delivery = cast(dict[str, Any], task.delivery)
    refs = {
        (r["fact_index"], r["reference_index"]): r
        for r in cast(list[dict[str, Any]], check.payload["references"])
    }
    rows, excluded = [], []
    for index, original in enumerate(delivery["facts"]):
        if original["entity_id"] != group.source_entity_id:
            excluded.append(
                {
                    "source_index": index,
                    "entity_id": original["entity_id"],
                    "source_hash": digest(original),
                    "reason": "DIFFERENT_ENTITY_SCOPE",
                }
            )
            continue
        fact = DeliveryFact(
            **(original | {"evidence": tuple(DeliveryEvidence(**e) for e in original["evidence"])})
        )
        mapped = map_field_value(fact, scope="UNIT", issues=[], mapping_version=GROUP_FACT_VERSION)
        row = asdict(mapped) | {
            "source_index": index,
            "original": deepcopy(original),
            "candidate_id": None,
            "evidence": [],
        }
        row["issue_codes"] = list(row["issue_codes"])
        for ref_index, original_ref in enumerate(original["evidence"]):
            ref = refs[index, ref_index]
            bound = None
            if ref["verdict"] == "PASS" and ref["persistent_binding"] is not None:
                block = session.get(DocumentBlock, UUID(ref["persistent_binding"]["block_id"]))
                if block is None:
                    raise InvestigationError("PREPARED_EVIDENCE_INTEGRITY_FAILED")
                bound = dict(ref["persistent_binding"]) | {
                    "material_id": ref["artifact_id"],
                    "structural_locator": block.structural_locator,
                    "block_text": block.canonical_text_or_value,
                }
            row["evidence"].append(
                {"reference": original_ref, "check_reference": ref, "binding": bound}
            )
            if bound is None:
                row["issue_codes"].append("UNKNOWN_EVIDENCE_" + ref["verdict"])
        if not row["evidence"]:
            row["issue_codes"].append("UNKNOWN_EVIDENCE_MISSING")
        row["ready_for_persistence"] = bool(
            row["field_name"]
            and row["evidence"]
            and all(e["binding"] for e in row["evidence"])
            and fact.status != "UNPROCESSED"
        )
        if row["issue_codes"]:
            row.update(
                abstained=True,
                normalized_value_candidate=None,
                candidate_reason_code=row["issue_codes"][0],
            )
        rows.append(row)
    result = {
        "contract_version": GROUP_FACT_VERSION,
        "scope": "GROUP_FACT_REVIEW_ONLY",
        "group_source": source,
        "check_id": str(check_id),
        "check_hash": check.result_hash,
        "source_row_count": len(delivery["facts"]),
        "rows": rows,
        "excluded_rows": excluded,
        "extraction_run_id": None,
    }
    return GroupFactResult.model_validate(result).model_dump(mode="json"), source


def _persist_candidates(
    store: InvestigationStore, session: Session, result: dict[str, Any]
) -> None:
    rows = [row for row in result["rows"] if row["ready_for_persistence"]]
    if not rows:
        return
    group = result["group_source"]
    identity, provenance = group["group_identity"], group["source"]
    target = {
        "target_scope": "UNIT",
        "opportunity_id": provenance["opportunity_id"],
        "opportunity_version": provenance["opportunity_version"],
        "opportunity_unit_id": identity["unit_id"],
        "opportunity_unit_version_id": identity["unit_version_id"],
    }
    bindings = {
        UUID(e["binding"]["block_id"]): e["binding"] for row in rows for e in row["evidence"]
    }
    blocks = sorted(bindings)
    run_id, now = uuid7(), store.clock()
    service = FactLifecycleService(session)
    service.persist_run(
        ExtractionRunSchemaV08.model_validate(
            target
            | {
                "extraction_run_id": run_id,
                "source_bundle_revision_id": provenance["source_bundle_revision_id"],
                "unit_segmentation_version": f"group-binding:{group['group_binding_id']}",
                "task_spec_version": GROUP_FACT_VERSION,
                "extractor_kind": "HYBRID",
                "component_version": GROUP_FACT_VERSION,
                "producer_identity": f"component:{GROUP_FACT_VERSION}:wma:{provenance['task_id']}",
                "producer_response_id": None,
                "ordered_input_block_ids": blocks,
                "input_block_set_hash": extraction_input_block_set_hash(blocks),
                "evidence_binding_hash": extraction_evidence_binding_hash(
                    [(bid, bindings[bid]["evidence_binding_hash"]) for bid in blocks]
                ),
                "started_at": now,
                "completed_at": now,
                "status": "ABSTAINED" if all(r["abstained"] for r in rows) else "SUCCEEDED",
            }
        )
    )
    result["extraction_run_id"] = str(run_id)
    for row in rows:
        refs = {e["binding"]["block_id"]: e["binding"]["evidence_ref_id"] for e in row["evidence"]}
        candidate_id = uuid7()
        service.record_candidate(
            ExtractionCandidateSchemaV08.model_validate(
                target
                | {
                    "candidate_id": candidate_id,
                    "extraction_run_id": run_id,
                    "field_name": row["field_name"],
                    "raw_value": row["raw_value"],
                    "normalized_value_candidate": row["normalized_value_candidate"],
                    "evidence_block_ids": list(refs),
                    "evidence_ref_ids": list(refs.values()),
                    "confidence": None,
                    "abstained": row["abstained"],
                    "candidate_reason_code": row["candidate_reason_code"],
                    "schema_version": "0.8.0",
                    "created_at": now,
                }
            )
        )
        row["candidate_id"] = str(candidate_id)


def _checked(
    store: InvestigationStore, session: Session, task_id: UUID, prep_id: UUID
) -> InvestigationGroupFactPreparation:
    prep = session.get(InvestigationGroupFactPreparation, prep_id)
    if prep is None:
        raise InvestigationError("GROUP_FACT_PREPARATION_NOT_FOUND")
    result, _ = _context(store, session, task_id, prep.group_binding_id, prep.check_id)
    expected = deepcopy(prep.result)
    expected["extraction_run_id"] = None
    for row in expected["rows"]:
        row["candidate_id"] = None
    if (
        prep.mapping_version != GROUP_FACT_VERSION
        or digest(prep.result) != prep.result_hash
        or expected != result
        or prep.created_at > store.clock()
    ):
        raise InvestigationError("GROUP_FACT_PREPARATION_CONFLICT")
    return prep


def _describe(
    store: InvestigationStore, session: Session, prep: InvestigationGroupFactPreparation
) -> dict[str, Any]:
    _check_materialization(store, session, prep.preparation_id)
    decisions, history, fact_set = {}, [], None
    for action in session.scalars(
        select(InvestigationGroupFactAction)
        .where(InvestigationGroupFactAction.preparation_id == prep.preparation_id)
        .order_by(InvestigationGroupFactAction.created_at, InvestigationGroupFactAction.action_id)
    ):
        if action.created_at > store.clock() or action.request_hash != digest(action.request):
            raise InvestigationError("GROUP_FACT_ACTION_INTEGRITY_FAILED")
        if action.decision_id:
            decision = session.get(FactVerificationDecisionModel, action.decision_id)
            if decision is None or decision.decided_at > store.clock():
                raise InvestigationError("GROUP_FACT_ACTION_INTEGRITY_FAILED")
            item = {
                "decision_id": str(decision.decision_id),
                "candidate_id": str(decision.candidate_id),
                "decision": decision.decision,
                "reason": action.request["reason"],
                "reviewer_id": str(action.reviewer_id),
                "created_at": action.created_at.isoformat(),
            }
            decisions[str(decision.candidate_id)] = item
            history.append(item)
        else:
            _check_materialization(store, session, prep.preparation_id, action.fact_set_id)
            saved = session.get(VersionedVerifiedFactSet, action.fact_set_id)
            if saved is None:
                raise InvestigationError("GROUP_FACT_ACTION_INTEGRITY_FAILED")
            fact_set = {
                "fact_set_id": str(saved.verified_fact_set_id),
                "status": saved.status,
                "version": saved.version,
                "reason": action.request["reason"],
            }
    return GroupFactRecord.model_validate(
        {
            "preparation_id": str(prep.preparation_id),
            "result": prep.result,
            "result_hash": prep.result_hash,
            "reviewer_id": str(prep.reviewer_id),
            "created_at": prep.created_at,
            "decisions": decisions,
            "history": history,
            "fact_set": fact_set,
        }
    ).model_dump(mode="json")


def _check_materialization(
    store: InvestigationStore, session: Session, prep_id: UUID, set_id: UUID | None = None
) -> None:
    if not session.scalar(
        text("SELECT investigation_group_fact_materialization_valid(:prep, :set_id, :as_of)"),
        {"prep": prep_id, "set_id": set_id, "as_of": store.clock()},
    ):
        raise InvestigationError("GROUP_FACT_MATERIALIZATION_INTEGRITY_FAILED")


def prepare_group_facts(
    store: InvestigationStore,
    task_id: UUID,
    group_id: UUID,
    command: PrepareGroupFacts,
    principal: ReviewerPrincipal,
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        result, source = _context(store, session, task_id, group_id, command.check_id)
        if source["source_hash"] != command.expected_source_hash:
            raise InvestigationError("GROUP_FACT_SOURCE_CHANGED")
        existing = session.scalar(
            select(InvestigationGroupFactPreparation).where(
                InvestigationGroupFactPreparation.group_binding_id == group_id,
                InvestigationGroupFactPreparation.check_id == command.check_id,
                InvestigationGroupFactPreparation.mapping_version == GROUP_FACT_VERSION,
            )
        )
        if existing is not None:
            return _describe(
                store, session, _checked(store, session, task_id, existing.preparation_id)
            )
        _persist_candidates(store, session, result)
        prep = InvestigationGroupFactPreparation(
            preparation_id=uuid7(),
            group_binding_id=group_id,
            check_id=command.check_id,
            mapping_version=GROUP_FACT_VERSION,
            result=result,
            result_hash=digest(result),
            reviewer_id=principal.reviewer_id,
            created_at=store.clock(),
        )
        session.add(prep)
        session.flush()
        return _describe(store, session, prep)


def load_group_facts(
    store: InvestigationStore, task_id: UUID, prep_id: UUID, principal: ReviewerPrincipal
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        return _describe(store, session, _checked(store, session, task_id, prep_id))


def act_on_group_facts(
    store: InvestigationStore,
    task_id: UUID,
    prep_id: UUID,
    command: DecideGroupFact | PromoteGroupFacts,
    principal: ReviewerPrincipal,
    key: str,
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    key_hash = sha256(validate_idempotency_key(key).encode()).hexdigest()
    kind = "DECISION" if isinstance(command, DecideGroupFact) else "PROMOTION"
    request = command.model_dump(mode="json") | {"kind": kind}
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        prep = _checked(store, session, task_id, prep_id)
        current = _describe(store, session, prep)
        if command.expected_preparation_hash != prep.result_hash or not command.reason.strip():
            raise InvestigationError("GROUP_FACT_PREPARATION_CONFLICT")
        existing = session.scalar(
            select(InvestigationGroupFactAction).where(
                InvestigationGroupFactAction.preparation_id == prep_id,
                InvestigationGroupFactAction.reviewer_id == principal.reviewer_id,
                InvestigationGroupFactAction.request_key_hash == key_hash,
            )
        )
        if existing:
            if existing.request_hash != digest(request):
                raise InvestigationError("GROUP_FACT_IDEMPOTENCY_CONFLICT")
            return current
        service = FactLifecycleService(session)
        candidate_id = decision_id = fact_set_id = None
        try:
            if isinstance(command, DecideGroupFact):
                candidate_id = command.candidate_id
                if not any(row["candidate_id"] == str(candidate_id) for row in prep.result["rows"]):
                    raise InvestigationError("GROUP_FACT_CANDIDATE_INVALID")
                if session.scalar(
                    select(FactVerificationDecisionModel).where(
                        FactVerificationDecisionModel.candidate_id == candidate_id,
                        FactVerificationDecisionModel.decision != "NEEDS_ADJUDICATION",
                    )
                ):
                    raise InvestigationError("GROUP_FACT_CANDIDATE_ALREADY_DECIDED")
                decision_id = uuid7()
                service.verify_candidate(
                    FactVerificationDecisionSchemaV08.model_validate(
                        {
                            "candidate_id": candidate_id,
                            "decision_id": decision_id,
                            "decision": command.decision,
                            "verification_method": "HUMAN",
                            "verifier_identity": f"human:{principal.reviewer_id}",
                            "verifier_response_id": None,
                            "reason_code": f"HUMAN_{command.decision}",
                            "evidence_support_result": command.evidence_support,
                            "precedence_check_result": command.precedence_check,
                            "decided_at": store.clock(),
                        }
                    )
                )
            else:
                ids = {row["candidate_id"] for row in prep.result["rows"] if row["candidate_id"]}
                decisions = current["decisions"]
                if (
                    not ids
                    or set(decisions) != ids
                    or any(d["decision"] == "NEEDS_ADJUDICATION" for d in decisions.values())
                ):
                    raise InvestigationError("GROUP_FACT_ALL_CANDIDATES_REQUIRE_DECISION")
                if current["fact_set"] is not None:
                    raise InvestigationError("GROUP_FACT_ALREADY_PROMOTED")
                accepted = [
                    UUID(d["decision_id"])
                    for d in decisions.values()
                    if d["decision"] in {"APPROVE", "UNKNOWN"}
                ]
                if not accepted:
                    raise InvestigationError("GROUP_FACT_NOTHING_TO_PROMOTE")
                fact_set_id = uuid7()
                service.promote(
                    decision_ids=accepted,
                    verified_fact_set_id=fact_set_id,
                    reference_dataset_versions={"group_fact_bridge": GROUP_FACT_VERSION},
                    created_at=store.clock(),
                    supersedes_id=command.supersedes_id,
                    actor_identity=f"human:{principal.reviewer_id}",
                )
        except (FactLifecycleError, ValidationError) as error:
            raise InvestigationError("GROUP_FACT_DECISION_OR_PROMOTION_INVALID") from error
        session.add(
            InvestigationGroupFactAction(
                action_id=uuid7(),
                preparation_id=prep_id,
                kind=kind,
                candidate_id=candidate_id,
                decision_id=decision_id,
                fact_set_id=fact_set_id,
                reviewer_id=principal.reviewer_id,
                request_key_hash=key_hash,
                request_hash=digest(request),
                request=request,
                created_at=store.clock(),
            )
        )
        session.flush()
        return _describe(store, session, prep)
