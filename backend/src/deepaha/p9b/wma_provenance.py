"""Direct WMA provenance is a distinct source, never an acquisition observation."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid7

from sqlalchemy.orm import Session

from deepaha.artifacts.models import RawArtifact
from deepaha.documents.models import Document, EvidenceRef, ParseAttempt
from deepaha.investigations.models import InvestigationMaterial, InvestigationTask
from deepaha.p9b.models import SourceBundleMember

ACQUISITION_FIELDS = (
    "capture_observation_id",
    "acquisition_evaluation_id",
    "acquisition_validation_status",
    "acquisition_run_id",
    "recipe_id",
    "recipe_version",
    "fetch_strategy",
    "fetcher_name",
    "fetcher_version",
    "validator_name",
    "validator_version",
)


@dataclass(frozen=True)
class WmaBundleMemberSpec:
    task_id: UUID
    material_id: str
    delivery_hash: str
    document_id: UUID
    evidence_ref_id: UUID
    parse_attempt_id: UUID
    member_role: str
    precedence: int
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    relation_type: str = "PRIMARY"
    related_member_index: int | None = None


def materialize_wma_member(
    session: Session,
    revision_id: UUID,
    spec: WmaBundleMemberSpec,
) -> SourceBundleMember:
    from deepaha.p9b.provenance import BundleProvenanceError

    task = session.get(InvestigationTask, spec.task_id)
    material = session.get(InvestigationMaterial, (spec.task_id, spec.material_id))
    document = session.get(Document, spec.document_id)
    attempt = session.get(ParseAttempt, spec.parse_attempt_id)
    evidence = session.get(EvidenceRef, spec.evidence_ref_id)
    if task is None or material is None or document is None or attempt is None or evidence is None:
        raise BundleProvenanceError("WMA provenance identity does not exist")
    raw = session.get(RawArtifact, material.raw_artifact_id)
    if (
        raw is None
        or task.status != "APPROVED"
        or task.delivery_hash != spec.delivery_hash
        or task.runtime_id is None
        or task.remote_session_id is None
        or raw.source_id != task.source_id
        or document.artifact_id != raw.artifact_id
        or material.metadata_snapshot["sha256"] != raw.content_sha256
        or attempt.outcome != "SUCCEEDED"
        or attempt.document_id != document.document_id
        or attempt.artifact_id != raw.artifact_id
        or attempt.document_parse_key != document.document_parse_key
        or attempt.parser_name != document.parser_name
        or attempt.parser_version != document.parser_version
        or attempt.parse_contract_version != document.parse_contract_version
        or evidence.document_id != document.document_id
        or evidence.artifact_id != raw.artifact_id
        or evidence.locator_kind != "full_document"
        or evidence.locator_value != "*"
        or evidence.locator_schema_version != "0.1.0"
        or evidence.quote_sha256 != raw.content_sha256
    ):
        raise BundleProvenanceError("WMA exact provenance binding mismatch")
    return SourceBundleMember(
        source_bundle_member_id=uuid7(),
        source_bundle_revision_id=revision_id,
        provenance_kind="DIRECT_WMA",
        wma_task_id=task.task_id,
        wma_material_id=material.material_id,
        wma_delivery_hash=task.delivery_hash,
        wma_contract_hash=task.contract_hash,
        source_id=task.source_id,
        endpoint_id=task.endpoint_id,
        policy_version=str(task.source_snapshot["policy_version"]),
        **dict.fromkeys(ACQUISITION_FIELDS),
        raw_artifact_id=raw.artifact_id,
        raw_artifact_sha256=raw.content_sha256,
        raw_artifact_size=raw.byte_size,
        storage_bucket=raw.storage_bucket,
        object_key=raw.object_key,
        document_id=document.document_id,
        document_parse_key=document.document_parse_key,
        parser_name=document.parser_name,
        parser_version=document.parser_version,
        parse_contract_version=document.parse_contract_version,
        evidence_ref_id=spec.evidence_ref_id,
        parse_attempt_id=spec.parse_attempt_id,
        member_role=spec.member_role,
        precedence=spec.precedence,
        effective_from=spec.effective_from,
        effective_to=spec.effective_to,
        member_provenance_hash="0" * 64,
        created_at=task.updated_at,
    )
