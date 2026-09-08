"""WMA candidate bridge and independent human facts, scoped to one exact binding."""

import json
from dataclasses import asdict
from hashlib import sha256
from typing import Any, cast
from uuid import UUID, uuid7

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from deepaha.contracts.phase9b import (
    EvidenceSupportResult,
    ExtractionCandidateSchemaV08,
    ExtractionRunSchemaV08,
    ExtractionRunStatus,
    ExtractorKind,
    FactVerificationDecision,
    FactVerificationDecisionSchemaV08,
    PrecedenceCheckResult,
    VerificationMethod,
)
from deepaha.documents.models import DocumentBlock
from deepaha.investigations.bindings import (
    _authorize,
    _check_positions,
    _latest,
    _validated_members,
)
from deepaha.investigations.contracts import (
    BindInvestigation,
    CreateInvestigation,
    DecideInvestigationFact,
    InvestigationError,
    PrepareInvestigationFacts,
    PromoteInvestigationFacts,
    digest,
)
from deepaha.investigations.delivery import DeliveryEvidence, DeliveryFact
from deepaha.investigations.evidence_checks import evaluate_check
from deepaha.investigations.field_mapping import (
    FIELD_MAPPING_VERSION,
    FieldTarget,
    map_field_candidate,
)
from deepaha.investigations.models import (
    InvestigationBinding,
    InvestigationEvidenceCheck,
    InvestigationFactAction,
    InvestigationFactPreparation,
    InvestigationMaterial,
    InvestigationTask,
)
from deepaha.investigations.store import InvestigationStore
from deepaha.local_human_test.review import require_human_fact_reviewer, validate_idempotency_key
from deepaha.opportunities.models import Opportunity
from deepaha.p9b.facts import (
    FactLifecycleError,
    FactLifecycleService,
    extraction_input_block_set_hash,
)
from deepaha.p9b.hashing import extraction_evidence_binding_hash
from deepaha.p9b.models import (
    FactVerificationDecisionModel,
    SourceBundleMember,
    SourceBundleRevision,
    VersionedVerifiedFactSet,
)
from deepaha.p9b.wma_provenance import WmaBundleMemberSpec
from deepaha.review.auth import ReviewerPrincipal


def _current(
    store: InvestigationStore,
    session: Session,
    task_id: UUID,
    command: PrepareInvestigationFacts,
) -> tuple[InvestigationTask, InvestigationBinding]:
    task = store._get(session, task_id, lock=True)
    binding = _latest(session, task_id)
    if (
        task.status != "APPROVED"
        or task.delivery_hash != command.delivery_hash
        or binding is None
        or binding.binding_id != command.binding_id
    ):
        raise InvestigationError("FACT_BINDING_CONFLICT")
    opportunity = session.scalar(
        select(Opportunity)
        .where(Opportunity.opportunity_id == binding.opportunity_id)
        .with_for_update()
    )
    revision = session.scalar(
        select(SourceBundleRevision)
        .where(SourceBundleRevision.source_bundle_revision_id == binding.source_bundle_revision_id)
        .with_for_update()
    )
    if (
        opportunity is None
        or opportunity.current_version != binding.opportunity_version
        or revision is None
        or revision.status != "FROZEN"
    ):
        raise InvestigationError("FACT_TARGET_VERSION_CONFLICT")
    _check_positions(
        session,
        task,
        BindInvestigation.model_validate(
            {key: value for key, value in binding.request.items() if key != "registration"}
        ),
    )
    if digest(store._source(session, CreateInvestigation.model_validate(task.request))) != digest(
        task.source_snapshot
    ):
        raise InvestigationError("SOURCE_POLICY_CHANGED")
    return task, binding


def _targets(task: InvestigationTask, binding: InvestigationBinding) -> dict[str, dict[str, Any]]:
    delivery = cast(dict[str, Any], task.delivery)
    positions = cast(list[dict[str, Any]], binding.request["positions"])
    mapped = {item["entity_id"]: item for item in positions}
    targets = {}
    for entity in delivery["evidence"]["entities"]:
        kind, entity_id = entity["kind"], entity["id"]
        if kind != "announcement" and entity_id not in mapped:
            continue
        unit = mapped.get(entity_id)
        targets[entity_id] = {
            "entity_id": entity_id,
            "name": entity["name"],
            "entity_kind": kind,
            "target_scope": "UNIT" if unit else "OPPORTUNITY",
            "opportunity_id": str(binding.opportunity_id),
            "opportunity_version": binding.opportunity_version,
            "opportunity_unit_id": unit["opportunity_unit_id"] if unit else None,
            "opportunity_unit_version_id": unit["opportunity_unit_version_id"] if unit else None,
            "extraction_run_id": None,
        }
    return targets


def _target_contract(target: dict[str, Any]) -> dict[str, Any]:
    return {
        key: target[key]
        for key in (
            "target_scope",
            "opportunity_id",
            "opportunity_version",
            "opportunity_unit_id",
            "opportunity_unit_version_id",
        )
    }


def _current_check(
    store: InvestigationStore,
    session: Session,
    task: InvestigationTask,
    binding: InvestigationBinding,
    check_id: UUID,
) -> InvestigationEvidenceCheck:
    specs = _validated_members(store, session, task)
    members = list(
        session.scalars(
            select(SourceBundleMember).where(
                SourceBundleMember.source_bundle_revision_id == binding.source_bundle_revision_id
            )
        )
    )
    if any(not isinstance(spec, WmaBundleMemberSpec) for spec in specs):
        raise InvestigationError("FACT_BINDING_DOCUMENTS_CHANGED")
    expected = {
        (
            cast(WmaBundleMemberSpec, s).material_id,
            s.document_id,
            s.evidence_ref_id,
            s.parse_attempt_id,
        )
        for s in specs
    }
    actual = {
        (m.wma_material_id, m.document_id, m.evidence_ref_id, m.parse_attempt_id) for m in members
    }
    if expected != actual or len(specs) != len(members):
        raise InvestigationError("FACT_BINDING_DOCUMENTS_CHANGED")
    check = session.get(InvestigationEvidenceCheck, check_id)
    if check is None or check.task_id != task.task_id or check.delivery_hash != task.delivery_hash:
        raise InvestigationError("FACT_EVIDENCE_CHECK_CONFLICT")
    materials = list(
        session.scalars(
            select(InvestigationMaterial)
            .where(InvestigationMaterial.task_id == task.task_id)
            .order_by(InvestigationMaterial.raw_artifact_id, InvestigationMaterial.material_id)
        )
    )
    current = evaluate_check(session, store.objects, task, materials)
    if (
        digest(current) != check.result_hash
        or digest(check.payload) != check.result_hash
        or digest(current["inputs"]) != check.input_hash
    ):
        raise InvestigationError("FACT_EVIDENCE_CHECK_REFRESH_REQUIRED")
    return check


def prepare_facts(
    store: InvestigationStore,
    task_id: UUID,
    command: PrepareInvestigationFacts,
    principal: ReviewerPrincipal,
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        task, binding = _current(store, session, task_id, command)
        check = _current_check(store, session, task, binding, command.check_id)
        existing = session.scalar(
            select(InvestigationFactPreparation).where(
                InvestigationFactPreparation.binding_id == binding.binding_id,
                InvestigationFactPreparation.check_id == command.check_id,
                InvestigationFactPreparation.mapping_version == FIELD_MAPPING_VERSION,
            )
        )
        if existing is not None:
            return describe_facts(session, task_id, binding.binding_id)
        references = cast(list[dict[str, Any]], check.payload["references"])
        references_by_index = {
            (reference["fact_index"], reference["reference_index"]): reference
            for reference in references
        }
        block_rows: dict[UUID, DocumentBlock] = {}
        for reference in references:
            if reference["persistent_binding"] is not None:
                block_id = UUID(reference["persistent_binding"]["block_id"])
                block = session.get(DocumentBlock, block_id)
                if block is None:
                    raise InvestigationError("PREPARED_EVIDENCE_INTEGRITY_FAILED")
                block_rows[block_id] = block
        documents = cast(dict[str, Any], check.payload["inputs"])["documents"]
        targets = _targets(task, binding)
        delivery = cast(dict[str, Any], task.delivery)
        kinds = {entity["id"]: entity["kind"] for entity in delivery["evidence"]["entities"]}
        rows = []
        for index, original in enumerate(delivery["facts"]):
            fact = DeliveryFact(
                **(
                    original
                    | {"evidence": tuple(DeliveryEvidence(**e) for e in original["evidence"])}
                )
            )
            mapped = map_field_candidate(
                fact,
                target=FieldTarget(fact.entity_id, kinds[fact.entity_id]),
            )
            row = json.loads(json.dumps(asdict(mapped), default=str)) | {
                "source_index": index,
                "original": original,
                "candidate_id": None,
                "extraction_run_id": None,
            }
            row["evidence"] = []
            for ref_index, original_ref in enumerate(original["evidence"]):
                ref = references_by_index[index, ref_index]
                bound = None
                if ref["verdict"] == "PASS" and ref["persistent_binding"] is not None:
                    bound = dict(ref["persistent_binding"])
                    block = block_rows[UUID(bound["block_id"])]
                    bound.update(
                        material_id=ref["artifact_id"],
                        structural_locator=block.structural_locator,
                        block_text=block.canonical_text_or_value,
                    )
                row["evidence"].append(
                    {"reference": original_ref, "check_reference": ref, "binding": bound}
                )
                if bound is None:
                    row["issue_codes"].append("UNKNOWN_EVIDENCE_" + ref["verdict"])
            row["ready_for_persistence"] = bool(
                row["target_scope"]
                and row["field_name"]
                and row["evidence"]
                and all(e["binding"] for e in row["evidence"])
                and fact.status != "UNPROCESSED"
            )
            if not row["evidence"]:
                row["issue_codes"].append("UNKNOWN_EVIDENCE_MISSING")
            if mapped.entity_id not in targets:
                row["ready_for_persistence"] = False
                row["issue_codes"].append("UNKNOWN_ENTITY_UNBOUND")
            if row["issue_codes"]:
                row["abstained"] = True
                row["normalized_value_candidate"] = None
                row["candidate_reason_code"] = row["issue_codes"][0]
            rows.append(row)
        service = FactLifecycleService(session)
        for target in targets.values():
            eligible_rows = [
                row
                for row in rows
                if row["entity_id"] == target["entity_id"] and row["ready_for_persistence"]
            ]
            if not eligible_rows:
                continue
            block_ids = sorted(
                {UUID(e["binding"]["block_id"]) for row in eligible_rows for e in row["evidence"]}
            )
            run_id = uuid7()
            now = store.clock()
            run = ExtractionRunSchemaV08.model_validate(
                _target_contract(target)
                | {
                    "extraction_run_id": run_id,
                    "source_bundle_revision_id": binding.source_bundle_revision_id,
                    "unit_segmentation_version": f"investigation-binding:{binding.binding_id}"
                    if target["target_scope"] == "UNIT"
                    else None,
                    "task_spec_version": FIELD_MAPPING_VERSION,
                    "extractor_kind": ExtractorKind.HYBRID,
                    "component_version": FIELD_MAPPING_VERSION,
                    "producer_identity": f"component:{FIELD_MAPPING_VERSION}:wma:{task_id}",
                    "producer_response_id": None,
                    "ordered_input_block_ids": block_ids,
                    "input_block_set_hash": extraction_input_block_set_hash(block_ids),
                    "evidence_binding_hash": extraction_evidence_binding_hash(
                        [(bid, block_rows[bid].evidence_binding_hash) for bid in block_ids]
                    ),
                    "started_at": now,
                    "completed_at": now,
                    "status": ExtractionRunStatus.ABSTAINED
                    if all(row["abstained"] for row in eligible_rows)
                    else ExtractionRunStatus.SUCCEEDED,
                }
            )
            service.persist_run(run)
            target["extraction_run_id"] = str(run_id)
            for row in eligible_rows:
                bindings = {e["binding"]["block_id"]: e["binding"] for e in row["evidence"]}
                candidate_id = uuid7()
                service.record_candidate(
                    ExtractionCandidateSchemaV08.model_validate(
                        _target_contract(target)
                        | {
                            "candidate_id": candidate_id,
                            "extraction_run_id": run_id,
                            "field_name": row["field_name"],
                            "raw_value": row["raw_value"],
                            "normalized_value_candidate": row["normalized_value_candidate"],
                            "evidence_block_ids": list(bindings),
                            "evidence_ref_ids": [b["evidence_ref_id"] for b in bindings.values()],
                            "confidence": None,
                            "abstained": row["abstained"],
                            "candidate_reason_code": row["candidate_reason_code"],
                            "schema_version": "0.8.0",
                            "created_at": now,
                        }
                    )
                )
                row.update(candidate_id=str(candidate_id), extraction_run_id=str(run_id))
        receipt = {"rows": rows, "targets": list(targets.values()), "documents": documents}
        session.add(
            InvestigationFactPreparation(
                preparation_id=uuid7(),
                task_id=task_id,
                binding_id=binding.binding_id,
                check_id=command.check_id,
                mapping_version=FIELD_MAPPING_VERSION,
                reviewer_id=principal.reviewer_id,
                result=receipt,
                result_hash=digest(receipt),
                created_at=store.clock(),
            )
        )
        session.flush()
        return describe_facts(session, task_id, binding.binding_id)


def describe_facts(session: Session, task_id: UUID, binding_id: UUID | None) -> dict[str, Any]:
    preparations = list(
        session.scalars(
            select(InvestigationFactPreparation)
            .where(InvestigationFactPreparation.task_id == task_id)
            .order_by(
                InvestigationFactPreparation.created_at.desc(),
                InvestigationFactPreparation.preparation_id.desc(),
            )
        )
    )
    current = next(
        (
            p
            for p in preparations
            if p.binding_id == binding_id and p.mapping_version == FIELD_MAPPING_VERSION
        ),
        None,
    )
    history = [
        {
            "preparation_id": str(p.preparation_id),
            "binding_id": str(p.binding_id),
            "mapping_version": p.mapping_version,
            "created_at": p.created_at.isoformat(),
        }
        for p in preparations
    ]
    if current is None:
        return {"current": None, "history": history}
    actions = list(
        session.scalars(
            select(InvestigationFactAction)
            .where(InvestigationFactAction.preparation_id == current.preparation_id)
            .order_by(InvestigationFactAction.created_at, InvestigationFactAction.action_id)
        )
    )
    decisions = {}
    promotions = {}
    active_fact_sets = {}
    for target in cast(list[dict[str, Any]], current.result["targets"]):
        statement = select(VersionedVerifiedFactSet).where(
            VersionedVerifiedFactSet.status == "ACTIVE",
            VersionedVerifiedFactSet.target_scope == target["target_scope"],
            VersionedVerifiedFactSet.opportunity_id == UUID(target["opportunity_id"]),
            VersionedVerifiedFactSet.opportunity_version == target["opportunity_version"],
        )
        if target["target_scope"] == "UNIT":
            statement = statement.where(
                VersionedVerifiedFactSet.opportunity_unit_id == UUID(target["opportunity_unit_id"]),
                VersionedVerifiedFactSet.opportunity_unit_version_id
                == UUID(target["opportunity_unit_version_id"]),
            )
        active = session.scalar(statement)
        if active is not None:
            active_fact_sets[target["entity_id"]] = {
                "fact_set_id": str(active.verified_fact_set_id),
                "version": active.version,
                "source_bundle_revision_id": str(active.source_bundle_revision_id),
            }
    for action in actions:
        if action.decision_id:
            decision = session.get(FactVerificationDecisionModel, action.decision_id)
            assert decision is not None
            decisions[str(action.candidate_id)] = {
                "decision_id": str(decision.decision_id),
                "decision": decision.decision,
                "reason": action.request["reason"],
                "reviewer_id": str(action.reviewer_id),
                "created_at": action.created_at.isoformat(),
            }
        if action.fact_set_id:
            fact_set = session.get(VersionedVerifiedFactSet, action.fact_set_id)
            promotions[action.entity_id] = {
                "fact_set_id": str(action.fact_set_id),
                "status": fact_set.status if fact_set else "MISSING",
                "reason": action.request["reason"],
            }
    return {
        "current": {
            "preparation_id": str(current.preparation_id),
            "binding_id": str(current.binding_id),
            "mapping_version": current.mapping_version,
            "check_id": str(current.check_id),
            "result_hash": current.result_hash,
            **current.result,
            "decisions": decisions,
            "promotions": promotions,
            "active_fact_sets": active_fact_sets,
        },
        "history": history,
    }


def act_on_facts(
    store: InvestigationStore,
    task_id: UUID,
    command: DecideInvestigationFact | PromoteInvestigationFacts,
    principal: ReviewerPrincipal,
    key: str,
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    key_hash = sha256(validate_idempotency_key(key).encode()).hexdigest()
    request = command.model_dump(mode="json")
    kind = "DECISION" if isinstance(command, DecideInvestigationFact) else "PROMOTION"
    request["kind"] = kind
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        task, binding = _current(store, session, task_id, command)
        check = _current_check(store, session, task, binding, command.check_id)
        prep = session.get(InvestigationFactPreparation, command.preparation_id)
        if (
            prep is None
            or prep.binding_id != binding.binding_id
            or prep.mapping_version != FIELD_MAPPING_VERSION
            or prep.check_id != check.check_id
            or digest(prep.result) != prep.result_hash
        ):
            raise InvestigationError("FACT_PREPARATION_CONFLICT")
        existing = session.scalar(
            select(InvestigationFactAction).where(
                InvestigationFactAction.preparation_id == prep.preparation_id,
                InvestigationFactAction.reviewer_id == principal.reviewer_id,
                InvestigationFactAction.request_key_hash == key_hash,
            )
        )
        if existing:
            if existing.request_hash != digest(request):
                raise InvestigationError("FACT_IDEMPOTENCY_CONFLICT")
            return describe_facts(session, task_id, binding.binding_id)
        if not command.reason.strip():
            raise InvestigationError("FACT_REVIEW_REASON_REQUIRED")
        _validated_members(store, session, task)
        rows = cast(list[dict[str, Any]], prep.result["rows"])
        service = FactLifecycleService(session)
        candidate_id = decision_id = fact_set_id = None
        try:
            if isinstance(command, DecideInvestigationFact):
                row = next(
                    (r for r in rows if r["candidate_id"] == str(command.candidate_id)), None
                )
                if row is None:
                    raise InvestigationError("FACT_CANDIDATE_INVALID")
                if session.scalar(
                    select(FactVerificationDecisionModel).where(
                        FactVerificationDecisionModel.candidate_id == command.candidate_id,
                        FactVerificationDecisionModel.decision != "NEEDS_ADJUDICATION",
                    )
                ):
                    raise InvestigationError("FACT_CANDIDATE_ALREADY_DECIDED")
                entity_id = row["entity_id"]
                candidate_id, decision_id = command.candidate_id, uuid7()
                service.verify_candidate(
                    FactVerificationDecisionSchemaV08(
                        candidate_id=candidate_id,
                        decision_id=decision_id,
                        decision=FactVerificationDecision(command.decision),
                        verification_method=VerificationMethod.HUMAN,
                        verifier_identity=f"human:{principal.reviewer_id}",
                        verifier_response_id=None,
                        reason_code=f"HUMAN_{command.decision}",
                        evidence_support_result=EvidenceSupportResult(command.evidence_support),
                        precedence_check_result=PrecedenceCheckResult(command.precedence_check),
                        decided_at=store.clock(),
                    )
                )
            else:
                entity_id = command.entity_id
                candidates = [
                    UUID(r["candidate_id"])
                    for r in rows
                    if r["entity_id"] == entity_id and r["candidate_id"]
                ]
                prior_promotion = session.scalar(
                    select(InvestigationFactAction).where(
                        InvestigationFactAction.preparation_id == prep.preparation_id,
                        InvestigationFactAction.kind == "PROMOTION",
                        InvestigationFactAction.entity_id == entity_id,
                    )
                )
                if prior_promotion is not None:
                    raise InvestigationError("FACT_TARGET_ALREADY_PROMOTED")
                decisions = list(
                    session.scalars(
                        select(FactVerificationDecisionModel)
                        .join(
                            InvestigationFactAction,
                            InvestigationFactAction.decision_id
                            == FactVerificationDecisionModel.decision_id,
                        )
                        .where(
                            InvestigationFactAction.preparation_id == prep.preparation_id,
                            InvestigationFactAction.entity_id == entity_id,
                            FactVerificationDecisionModel.candidate_id.in_(candidates),
                            FactVerificationDecisionModel.decision != "NEEDS_ADJUDICATION",
                        )
                    )
                )
                if (
                    not candidates
                    or len(decisions) != len(candidates)
                    or {d.candidate_id for d in decisions} != set(candidates)
                    or any(d.decision == "NEEDS_ADJUDICATION" for d in decisions)
                ):
                    raise InvestigationError("FACT_ALL_CANDIDATES_REQUIRE_DECISION")
                accepted = [
                    d.decision_id for d in decisions if d.decision in ("APPROVE", "UNKNOWN")
                ]
                if not accepted:
                    raise InvestigationError("FACT_NOTHING_TO_PROMOTE")
                fact_set_id = uuid7()
                service.promote(
                    decision_ids=accepted,
                    verified_fact_set_id=fact_set_id,
                    reference_dataset_versions={
                        "investigation_field_mapping": FIELD_MAPPING_VERSION
                    },
                    created_at=store.clock(),
                    supersedes_id=command.supersedes_id,
                    actor_identity=f"human:{principal.reviewer_id}",
                )
        except (FactLifecycleError, ValidationError) as error:
            raise InvestigationError("FACT_DECISION_OR_PROMOTION_INVALID") from error
        session.add(
            InvestigationFactAction(
                action_id=uuid7(),
                preparation_id=prep.preparation_id,
                kind=kind,
                entity_id=entity_id,
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
        return describe_facts(session, task_id, binding.binding_id)
