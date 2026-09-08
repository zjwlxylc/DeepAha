"""Human entity association, distinct from independent field verification."""

from hashlib import sha256
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit
from uuid import UUID, uuid7

from sqlalchemy import select
from sqlalchemy.orm import Session

from deepaha.artifacts.models import RawArtifact
from deepaha.artifacts.object_store import ObjectIntegrityError
from deepaha.documents.models import Document, EvidenceRef
from deepaha.documents.normalization import build_derived_text_key
from deepaha.investigations.contracts import (
    BindInvestigation,
    CreateInvestigation,
    InvestigationError,
    digest,
)
from deepaha.investigations.documents import describe_documents
from deepaha.investigations.models import (
    InvestigationBinding,
    InvestigationMaterial,
    InvestigationTask,
)
from deepaha.local_human_test.review import require_human_fact_reviewer, validate_idempotency_key
from deepaha.opportunities.models import Opportunity, OpportunityVersion
from deepaha.p9b.models import OpportunityUnit, OpportunityUnitVersion, SourceBundleRevision
from deepaha.p9b.provenance import BundleMemberSpec, BundleService
from deepaha.p9b.wma_provenance import WmaBundleMemberSpec
from deepaha.review.auth import ReviewerPrincipal, ReviewerRole
from deepaha.review.models import ReviewerAccountModel

if TYPE_CHECKING:
    from deepaha.investigations.store import InvestigationStore


def _latest(session: Session, task_id: UUID) -> InvestigationBinding | None:
    return session.scalar(
        select(InvestigationBinding)
        .where(
            InvestigationBinding.task_id == task_id,
        )
        .order_by(InvestigationBinding.sequence.desc())
        .limit(1)
    )


def describe_bindings(session: Session, task: InvestigationTask) -> list[dict[str, Any]]:
    return [
        _receipt(session, task, row)
        for row in session.scalars(
            select(InvestigationBinding)
            .where(InvestigationBinding.task_id == task.task_id)
            .order_by(InvestigationBinding.sequence.desc())
        )
    ]


def _receipt(
    session: Session, task: InvestigationTask, row: InvestigationBinding
) -> dict[str, Any]:
    from deepaha.p9b.provenance import _instant

    positions = row.request["positions"]
    assert isinstance(positions, list)
    mapped = {item["entity_id"] for item in positions}
    entities = (task.delivery or {}).get("evidence", {})
    assert isinstance(entities, dict)
    revision = session.get(SourceBundleRevision, row.source_bundle_revision_id)
    opportunity = session.get(Opportunity, row.opportunity_id)
    version = session.get(OpportunityVersion, (row.opportunity_id, row.opportunity_version))
    return {
        "scope": "ENTITY_ASSOCIATION_ONLY",
        "binding_id": str(row.binding_id),
        "sequence": row.sequence,
        "delivery_hash": row.delivery_hash,
        "source_bundle_revision_id": str(row.source_bundle_revision_id),
        "canonical_bundle_hash": revision.canonical_bundle_hash if revision else None,
        "bundle_status": revision.status if revision else "MISSING",
        "opportunity_id": str(row.opportunity_id),
        "opportunity_version": row.opportunity_version,
        "opportunity_public_id": opportunity.public_id if opportunity else None,
        "opportunity_title": (version.snapshot.get("canonical_title") if version else None)
        or (opportunity.public_id if opportunity else None),
        "positions": positions,
        "unmapped_position_ids": sorted(
            e["id"]
            for e in entities.get("entities", [])
            if e["kind"] == "position" and e["id"] not in mapped
        ),
        "reason": row.request["reason"],
        "reviewer_id": str(row.reviewer_id),
        "created_at": _instant(row.created_at),
        "previous_binding_id": row.request["previous_binding_id"],
    }


def binding_targets(store: InvestigationStore) -> list[dict[str, Any]]:
    with store.factory() as session:
        targets = []
        for opportunity in session.scalars(
            select(Opportunity)
            .where(
                Opportunity.current_version.is_not(None),
            )
            .order_by(Opportunity.updated_at.desc())
            .limit(200)
        ):
            units = session.execute(
                select(OpportunityUnit, OpportunityUnitVersion)
                .join(
                    OpportunityUnitVersion,
                    OpportunityUnit.current_version_id
                    == OpportunityUnitVersion.opportunity_unit_version_id,
                )
                .where(
                    OpportunityUnit.opportunity_id == opportunity.opportunity_id,
                    OpportunityUnit.opportunity_version == opportunity.current_version,
                    OpportunityUnit.lifecycle_status == "ACTIVE",
                    OpportunityUnit.unit_kind == "POSITION",
                    OpportunityUnitVersion.status == "ACTIVE",
                )
                .order_by(OpportunityUnit.current_unit_key)
            )
            targets.append(
                {
                    "opportunity_id": str(opportunity.opportunity_id),
                    "public_id": opportunity.public_id,
                    "version": opportunity.current_version,
                    "title": opportunity.canonical_title,
                    "positions": [
                        {
                            "unit_id": str(unit.opportunity_unit_id),
                            "version_id": str(version.opportunity_unit_version_id),
                            "public_id": unit.public_id,
                            "key": unit.current_unit_key,
                            "label": version.canonical_label,
                        }
                        for unit, version in units
                    ],
                }
            )
        return targets


def bind(
    store: InvestigationStore,
    task_id: UUID,
    command: BindInvestigation,
    principal: ReviewerPrincipal,
    key: str,
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    key_hash = sha256(validate_idempotency_key(key).encode()).hexdigest()
    request = command.model_dump(mode="json")
    request_hash = digest(request)
    with store.factory() as session, session.begin():
        account = session.scalar(
            select(ReviewerAccountModel)
            .where(
                ReviewerAccountModel.reviewer_id == principal.reviewer_id,
            )
            .with_for_update()
        )
        if account is None or not account.active or account.synthetic:
            raise InvestigationError("HUMAN_VALIDATION_AUTHORITY_REQUIRED")
        require_human_fact_reviewer(
            ReviewerPrincipal(
                account.reviewer_id,
                frozenset(ReviewerRole(role) for role in account.roles),
                frozenset(account.allowed_purposes),
                account.synthetic,
            )
        )
        task = store._get(session, task_id, lock=True)
        existing = session.scalar(
            select(InvestigationBinding).where(
                InvestigationBinding.task_id == task_id,
                InvestigationBinding.reviewer_id == principal.reviewer_id,
                InvestigationBinding.request_key_hash == key_hash,
            )
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise InvestigationError("BINDING_IDEMPOTENCY_CONFLICT")
            return store._view(session, task) | {
                "binding_receipt": _receipt(session, task, existing)
            }
        if task.status != "APPROVED" or task.delivery_hash != command.delivery_hash:
            raise InvestigationError("BINDING_DELIVERY_CONFLICT")
        previous = _latest(session, task_id)
        if command.previous_binding_id != (previous.binding_id if previous else None):
            raise InvestigationError("BINDING_REVISION_CONFLICT")
        source_command = CreateInvestigation.model_validate(task.request)
        if digest(store._source(session, source_command)) != digest(task.source_snapshot):
            raise InvestigationError("SOURCE_POLICY_CHANGED")
        opportunity = session.scalar(
            select(Opportunity)
            .where(
                Opportunity.opportunity_id == command.opportunity_id,
            )
            .with_for_update()
        )
        version = session.get(
            OpportunityVersion, (command.opportunity_id, command.opportunity_version)
        )
        if (
            opportunity is None
            or version is None
            or opportunity.current_version != command.opportunity_version
        ):
            raise InvestigationError("BINDING_TARGET_VERSION_CONFLICT")
        _check_positions(session, task, command)
        materials = list(
            session.scalars(
                select(InvestigationMaterial)
                .where(
                    InvestigationMaterial.task_id == task_id,
                )
                .order_by(InvestigationMaterial.material_id)
            )
        )
        if len(materials) != (task.delivery or {}).get("material_count"):
            raise InvestigationError("STORED_MATERIAL_INTEGRITY_FAILED")
        try:
            store._verify_stored_bytes(session, task)
            specs = _members(store, session, task, materials)
        except (OSError, ObjectIntegrityError) as error:
            raise InvestigationError("STORED_MATERIAL_INTEGRITY_FAILED") from error
        service = BundleService(session)
        revision = service.create_revision(
            opportunity_id=command.opportunity_id,
            opportunity_version=command.opportunity_version,
            effective_as_of=store.clock(),
            members=specs,
        )
        service.freeze_revision(revision.source_bundle_revision_id, frozen_at=store.clock())
        row = InvestigationBinding(
            binding_id=uuid7(),
            task_id=task_id,
            sequence=1 if previous is None else previous.sequence + 1,
            delivery_hash=command.delivery_hash,
            source_bundle_revision_id=revision.source_bundle_revision_id,
            opportunity_id=command.opportunity_id,
            opportunity_version=command.opportunity_version,
            reviewer_id=principal.reviewer_id,
            request_key_hash=key_hash,
            request_hash=request_hash,
            request=request,
            created_at=store.clock(),
        )
        session.add(row)
        session.flush()
        return store._view(session, task) | {"binding_receipt": _receipt(session, task, row)}


def _check_positions(session: Session, task: InvestigationTask, command: BindInvestigation) -> None:
    evidence = (task.delivery or {}).get("evidence", {})
    assert isinstance(evidence, dict)
    valid_ids = {e["id"] for e in evidence.get("entities", []) if e["kind"] == "position"}
    if len({p.entity_id for p in command.positions}) != len(command.positions) or len(
        {p.opportunity_unit_id for p in command.positions}
    ) != len(command.positions):
        raise InvestigationError("BINDING_POSITION_DUPLICATE")
    for item in sorted(command.positions, key=lambda p: p.opportunity_unit_id):
        unit = session.scalar(
            select(OpportunityUnit)
            .where(
                OpportunityUnit.opportunity_unit_id == item.opportunity_unit_id,
            )
            .with_for_update()
        )
        version = session.get(OpportunityUnitVersion, item.opportunity_unit_version_id)
        if (
            item.entity_id not in valid_ids
            or unit is None
            or version is None
            or unit.opportunity_id != command.opportunity_id
            or unit.opportunity_version != command.opportunity_version
            or unit.unit_kind != "POSITION"
            or unit.lifecycle_status != "ACTIVE"
            or unit.current_version_id != item.opportunity_unit_version_id
            or version.opportunity_unit_id != item.opportunity_unit_id
            or version.status != "ACTIVE"
            or version.opportunity_id != command.opportunity_id
            or version.opportunity_version != command.opportunity_version
        ):
            raise InvestigationError("BINDING_POSITION_VERSION_CONFLICT")


def _members(
    store: InvestigationStore,
    session: Session,
    task: InvestigationTask,
    materials: list[InvestigationMaterial],
) -> list[BundleMemberSpec | WmaBundleMemberSpec]:
    preparation = describe_documents(session, materials)
    if preparation["status"] != "PREPARED":
        raise InvestigationError("BINDING_DOCUMENTS_NOT_READY")
    prepared = {item["material_id"]: item for item in preparation["materials"]}
    specs: list[BundleMemberSpec | WmaBundleMemberSpec] = []
    # The whole-file reference anchors original bytes. It does not claim any
    # field quote matches a parsed block, which remains a separate review step.
    for material in materials:
        row = prepared[material.material_id]
        document = session.get(Document, UUID(row["document_id"]))
        raw = session.get(RawArtifact, material.raw_artifact_id)
        assert document is not None and raw is not None and task.delivery_hash is not None
        uri = urlsplit(document.extracted_text_uri or "")
        key = uri.path.lstrip("/")
        expected_key = build_derived_text_key(
            raw.content_sha256,
            document.parser_name,
            document.parser_version,
            document.parse_contract_version,
        )
        if uri.scheme != "s3" or uri.netloc != raw.storage_bucket or key != expected_key:
            raise InvestigationError("STORED_DOCUMENT_INTEGRITY_FAILED")
        metadata = store.objects.stat(key=key)
        content = store.objects.get_bytes(key=key)
        if (
            metadata.bucket != uri.netloc
            or metadata.key != key
            or metadata.byte_size != len(content)
            or metadata.sha256 != sha256(content).hexdigest()
        ):
            raise InvestigationError("STORED_DOCUMENT_INTEGRITY_FAILED")
        anchor = session.scalar(
            select(EvidenceRef)
            .where(
                EvidenceRef.document_id == document.document_id,
                EvidenceRef.artifact_id == raw.artifact_id,
                EvidenceRef.locator_kind == "full_document",
                EvidenceRef.locator_value == "*",
                EvidenceRef.locator_schema_version == "0.1.0",
                EvidenceRef.quote_sha256 == raw.content_sha256,
            )
            .order_by(EvidenceRef.evidence_ref_id)
            .limit(1)
        )
        if anchor is None:
            anchor = EvidenceRef(
                evidence_ref_id=uuid7(),
                document_id=document.document_id,
                artifact_id=raw.artifact_id,
                locator_kind="full_document",
                locator_value="*",
                locator_schema_version="0.1.0",
                locator_payload=None,
                quote_sha256=raw.content_sha256,
            )
            session.add(anchor)
            session.flush()
        specs.append(
            WmaBundleMemberSpec(
                task.task_id,
                material.material_id,
                task.delivery_hash,
                document.document_id,
                anchor.evidence_ref_id,
                UUID(row["parse_attempt_id"]),
                "PRIMARY_NOTICE"
                if material.metadata_snapshot["url"] == task.request["notice_url"]
                else "ATTACHMENT",
                0,
            )
        )
    return specs
