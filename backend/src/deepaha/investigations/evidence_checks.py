"""Append mechanical checks beside the frozen delivery, with persistent evidence IDs."""

from dataclasses import asdict, replace
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid7

from sqlalchemy import select
from sqlalchemy.orm import Session

from deepaha.artifacts.models import RawArtifact
from deepaha.artifacts.object_store import ObjectStore
from deepaha.contracts.evidence_anchor import READER_BLOCK_CONTRACT
from deepaha.evidence_verification.adapters.defaults import default_registry
from deepaha.evidence_verification.binding import PreparedDocumentEvidence
from deepaha.evidence_verification.contracts import VERIFIER_VERSION, ArtifactInput
from deepaha.evidence_verification.verifier import EvidenceVerifier
from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.documents import describe_documents
from deepaha.investigations.models import (
    InvestigationEvidenceCheck,
    InvestigationMaterial,
    InvestigationTask,
)

CHECK_VERSION = "investigation-evidence-check/1"


def append_check(
    session: Session,
    objects: ObjectStore,
    task: InvestigationTask,
    materials: list[InvestigationMaterial],
    checked_by: UUID,
    created_at: datetime,
) -> None:
    """Caller holds the task lock and has rechecked authority, policy and bytes."""
    registry = default_registry()
    verifier = EvidenceVerifier(registry)
    preparation = describe_documents(session, materials)
    documents = {row["material_id"]: row for row in preparation["materials"]}
    artifacts: dict[str, ArtifactInput] = {}
    prepared: dict[str, PreparedDocumentEvidence] = {}
    for material in materials:
        raw = session.get(RawArtifact, material.raw_artifact_id)
        if raw is None or raw.media_type is None:
            raise InvestigationError("STORED_MATERIAL_INTEGRITY_FAILED")
        artifacts[material.material_id] = ArtifactInput(
            material.material_id,
            raw.media_type,
            str(material.metadata_snapshot["url"]),
            raw.content_sha256,
            objects.get_bytes(key=raw.object_key),
        )
        row = documents[material.material_id]
        if row["outcome"] == "SUCCEEDED" and row["parse_contract_version"] == READER_BLOCK_CONTRACT:
            # Reject damaged persistence; never recategorize storage errors as a
            # quote mistake or silently fall back to an unbound text-only PASS.
            try:
                prepared[material.material_id] = PreparedDocumentEvidence(
                    session,
                    objects,
                    registry,
                    document_id=UUID(row["document_id"]),
                    source_url=artifacts[material.material_id].source_url,
                )
            except LookupError as error:
                raise InvestigationError("PREPARED_EVIDENCE_INTEGRITY_FAILED") from error
    references: list[dict[str, Any]] = []
    counts = {"PASS": 0, "FAIL": 0, "UNVERIFIED": 0}
    delivery = cast(dict[str, Any], task.delivery or {})
    for fact_index, fact in enumerate(delivery.get("facts", [])):
        for reference_index, reference in enumerate(fact["evidence"]):
            artifact_id = reference["artifact_id"]
            artifact = artifacts[artifact_id]
            binding: dict[str, Any] | None = None
            if artifact_id in prepared:
                bound = prepared[artifact_id].verify(reference["quote"], reference["locator"])
                result = replace(bound.verification, artifact_id=artifact_id)
                if bound.evidence_ref_id is not None:
                    binding = {
                        "document_id": str(bound.document_id),
                        "document_parse_key": bound.document_parse_key,
                        "parse_attempt_id": str(bound.parse_attempt_id),
                        "block_id": str(bound.block_id),
                        "evidence_ref_id": str(bound.evidence_ref_id),
                        "evidence_binding_hash": bound.evidence_binding_hash,
                    }
            else:
                result = verifier.verify(artifact, reference["quote"], reference["locator"])
            verdict = result.verdict
            if verdict == "PASS" and binding is None:
                verdict = "UNVERIFIED"
            counts[verdict] += 1
            references.append(
                {
                    "fact_index": fact_index,
                    "reference_index": reference_index,
                    "entity_id": fact["entity_id"],
                    "field": fact["field"],
                    "artifact_id": artifact_id,
                    "verification": asdict(result),
                    "persistent_binding": binding,
                    "verdict": verdict,
                    "binding_reason": None if binding else "PERSISTENT_BINDING_UNAVAILABLE",
                }
            )
    inputs = {
        "check_version": CHECK_VERSION,
        "verifier_version": VERIFIER_VERSION,
        "delivery_hash": task.delivery_hash,
        "readers": [asdict(adapter.identity) for adapter in registry.active_adapters],
        "materials": [
            {
                "material_id": m.material_id,
                "raw_artifact_id": str(m.raw_artifact_id),
                "sha256": m.metadata_snapshot["sha256"],
            }
            for m in materials
        ],
        "documents": preparation["materials"],
    }
    payload: dict[str, Any] = {
        "inputs": inputs,
        "scope": "MECHANICAL_EVIDENCE_ONLY",
        "counts": counts,
        "verdict": "FAIL"
        if counts["FAIL"]
        else ("UNVERIFIED" if counts["UNVERIFIED"] or not references else "PASS"),
        "references": references,
    }
    input_hash, result_hash = digest(inputs), digest(payload)
    existing = session.scalar(
        select(InvestigationEvidenceCheck).where(
            InvestigationEvidenceCheck.task_id == task.task_id,
            InvestigationEvidenceCheck.input_hash == input_hash,
        )
    )
    if existing is not None:
        if existing.result_hash != result_hash:
            raise InvestigationError("EVIDENCE_CHECK_REPLAY_CHANGED")
        return
    assert task.delivery_hash is not None
    session.add(
        InvestigationEvidenceCheck(
            check_id=uuid7(),
            task_id=task.task_id,
            delivery_hash=task.delivery_hash,
            input_hash=input_hash,
            result_hash=result_hash,
            payload=payload,
            checked_by=checked_by,
            created_at=created_at,
        )
    )
    session.flush()


def describe_checks(session: Session, task: InvestigationTask) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(InvestigationEvidenceCheck)
        .where(
            InvestigationEvidenceCheck.task_id == task.task_id,
        )
        .order_by(InvestigationEvidenceCheck.check_id.desc())
    )
    results: list[dict[str, Any]] = []
    for row in rows:
        if (
            row.delivery_hash != task.delivery_hash
            or digest(row.payload) != row.result_hash
            or digest(row.payload["inputs"]) != row.input_hash
        ):
            raise InvestigationError("EVIDENCE_CHECK_INTEGRITY_FAILED")
        results.append(
            dict(row.payload)
            | {
                "check_id": str(row.check_id),
                "input_hash": row.input_hash,
                "result_hash": row.result_hash,
                "delivery_hash": row.delivery_hash,
                "checked_by": str(row.checked_by),
                "created_at": row.created_at.isoformat(),
            }
        )
    return results
