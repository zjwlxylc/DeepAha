"""Atomic, internal identity registration from a reviewed WMA delivery."""

from hashlib import sha256
from typing import Any
from uuid import UUID, uuid7

from sqlalchemy import select, text

from deepaha.contracts.phase1 import OpportunityStatus, SourceTier
from deepaha.contracts.phase3 import (
    OpportunityDocumentRole,
    OpportunityReviewStatus,
    ResolutionDisposition,
)
from deepaha.documents.models import Document
from deepaha.investigations.bindings import (
    _authorize,
    _check_positions,
    _latest,
    _receipt,
    _validated_members,
)
from deepaha.investigations.contracts import (
    BindInvestigation,
    CreateInvestigation,
    InvestigationError,
    InvestigationPositionBinding,
    RegisterInvestigationIdentity,
    RegisterInvestigationPositions,
    digest,
)
from deepaha.investigations.models import InvestigationBinding
from deepaha.investigations.store import InvestigationStore
from deepaha.local_human_test.review import require_human_fact_reviewer, validate_idempotency_key
from deepaha.opportunities.identity import normalize_identity_text, normalize_official_url
from deepaha.opportunities.models import Opportunity
from deepaha.opportunities.resolver import resolve_document
from deepaha.opportunities.service import OpportunityResolutionService, load_resolution_index
from deepaha.opportunities.types import OpportunityPatch, ResolutionDocument
from deepaha.p9b.identity import (
    OpportunityUnitService,
    UnitIdentityError,
    UnitSeed,
    normalize_unit_key,
)
from deepaha.p9b.provenance import BundleService
from deepaha.review.auth import ReviewerPrincipal


def register_identity(
    store: InvestigationStore,
    task_id: UUID,
    command: RegisterInvestigationIdentity,
    principal: ReviewerPrincipal,
    key: str,
) -> dict[str, Any]:
    return _register(store, task_id, command, principal, key)


def register_positions(
    store: InvestigationStore,
    task_id: UUID,
    command: RegisterInvestigationPositions,
    principal: ReviewerPrincipal,
    key: str,
) -> dict[str, Any]:
    return _register(store, task_id, command, principal, key)


def _register(
    store: InvestigationStore,
    task_id: UUID,
    command: RegisterInvestigationIdentity | RegisterInvestigationPositions,
    principal: ReviewerPrincipal,
    key: str,
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    key_hash = sha256(validate_idempotency_key(key).encode()).hexdigest()
    registration = {
        "kind": "NEW_IDENTITY"
        if isinstance(command, RegisterInvestigationIdentity)
        else "ADD_POSITIONS",
        "command": command.model_dump(mode="json"),
    }
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        task = store._get(session, task_id, lock=True)
        existing = session.scalar(
            select(InvestigationBinding).where(
                InvestigationBinding.task_id == task_id,
                InvestigationBinding.reviewer_id == principal.reviewer_id,
                InvestigationBinding.request_key_hash == key_hash,
            )
        )
        if existing is not None:
            if existing.request.get("registration") != registration:
                raise InvestigationError("BINDING_IDEMPOTENCY_CONFLICT")
            return store._view(session, task) | {
                "binding_receipt": _receipt(session, task, existing)
            }
        if task.status != "APPROVED" or task.delivery_hash != command.delivery_hash:
            raise InvestigationError("BINDING_DELIVERY_CONFLICT")
        previous = _latest(session, task_id)
        expected = (
            None
            if isinstance(command, RegisterInvestigationIdentity)
            else command.previous_binding_id
        )
        if expected != (previous.binding_id if previous else None):
            raise InvestigationError("BINDING_REVISION_CONFLICT")
        source_command = CreateInvestigation.model_validate(task.request)
        if digest(store._source(session, source_command)) != digest(task.source_snapshot):
            raise InvestigationError("SOURCE_POLICY_CHANGED")
        evidence = (task.delivery or {}).get("evidence", {})
        assert isinstance(evidence, dict)
        entities = evidence.get("entities", [])
        valid_ids = {e["id"] for e in entities if e["kind"] == "position"}
        previous_positions = previous.request["positions"] if previous else []
        assert isinstance(previous_positions, list)
        mapped = {p["entity_id"] for p in previous_positions}
        ids = [p.entity_id for p in command.positions]
        keys = [normalize_unit_key(p.unit_key) for p in command.positions]
        if (
            len(set(ids)) != len(ids)
            or len(set(keys)) != len(keys)
            or any(entity not in valid_ids or entity in mapped for entity in ids)
        ):
            raise InvestigationError("REGISTRATION_POSITION_INVALID")
        specs = _validated_members(store, session, task)
        if isinstance(command, RegisterInvestigationIdentity):
            # Serializes this intake path across tasks; the resolver still owns identity semantics.
            identity_fields = (
                command.type.value,
                normalize_identity_text(command.issuer_name),
                normalize_identity_text(command.canonical_title),
            )
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {
                    "key": "investigation-identity-fields:" + digest(identity_fields),
                },
            )
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {
                    "key": "investigation-identity:"
                    + normalize_official_url(source_command.notice_url),
                },
            )
            primary = next((m for m in specs if m.member_role == "PRIMARY_NOTICE"), None)
            if primary is None or primary.evidence_ref_id is None:
                raise InvestigationError("REGISTRATION_PRIMARY_NOTICE_REQUIRED")
            session.scalar(
                select(Document)
                .where(Document.document_id == primary.document_id)
                .with_for_update()
            )
            for existing_opportunity in session.scalars(
                select(Opportunity).where(Opportunity.type == command.type.value)
            ):
                if (
                    normalize_identity_text(existing_opportunity.issuer_name) == identity_fields[1]
                    and normalize_identity_text(existing_opportunity.canonical_title)
                    == identity_fields[2]
                ):
                    # Missing jurisdiction is uncertainty, not proof of a distinct identity.
                    raise InvestigationError("REGISTRATION_EXISTING_IDENTITY_OR_REVIEW_REQUIRED")
            resolution = ResolutionDocument(
                document_id=primary.document_id,
                source_id=source_command.source_id,
                source_tier=SourceTier.OFFICIAL_PRIMARY,
                evidence_ref_id=primary.evidence_ref_id,
                role=OpportunityDocumentRole.PRIMARY_NOTICE,
                canonical_url=source_command.notice_url,
                external_id=None,
                references_document_ids=(),
                effective_at=store.clock(),
                facts=OpportunityPatch(
                    canonical_title=command.canonical_title,
                    type=command.type,
                    issuer_name=command.issuer_name,
                    status=OpportunityStatus.UNKNOWN,
                ),
            )
            index = load_resolution_index(session)
            if (
                resolution.document_id in index.document_links
                or resolution.document_id in index.decisions_by_document
            ):
                raise InvestigationError("REGISTRATION_EXISTING_IDENTITY_OR_REVIEW_REQUIRED")
            decision = resolve_document(resolution, index)
            if decision.disposition is not ResolutionDisposition.CREATED:
                raise InvestigationError("REGISTRATION_EXISTING_IDENTITY_OR_REVIEW_REQUIRED")
            result = OpportunityResolutionService(
                session_factory=store.factory,
                clock=store.clock,
                version_review_status=OpportunityReviewStatus.PENDING,
            ).resolve_in_session(session, resolution)
            if (
                result.disposition != "CREATED"
                or result.opportunity_id is None
                or result.version != 1
            ):
                raise InvestigationError("REGISTRATION_EXISTING_IDENTITY_OR_REVIEW_REQUIRED")
            opportunity_id, version = result.opportunity_id, result.version
            positions: list[InvestigationPositionBinding] = []
        else:
            assert previous is not None
            opportunity_id, version = previous.opportunity_id, previous.opportunity_version
            opportunity = session.scalar(
                select(Opportunity)
                .where(
                    Opportunity.opportunity_id == opportunity_id,
                )
                .with_for_update()
            )
            if opportunity is None or opportunity.current_version != version:
                raise InvestigationError("BINDING_TARGET_VERSION_CONFLICT")
            positions = [InvestigationPositionBinding.model_validate(p) for p in previous_positions]
        bundle = BundleService(session)
        revision = bundle.create_revision(
            opportunity_id=opportunity_id,
            opportunity_version=version,
            effective_as_of=store.clock(),
            members=specs,
        )
        bundle.freeze_revision(revision.source_bundle_revision_id, frozen_at=store.clock())
        for item in command.positions:
            try:
                unit = OpportunityUnitService(session).create_unit(
                    opportunity_id=opportunity_id,
                    opportunity_version=version,
                    source_bundle_revision_id=revision.source_bundle_revision_id,
                    seed=UnitSeed(
                        current_unit_key=item.unit_key,
                        unit_kind="POSITION",
                        canonical_label=item.label,
                        identity_fingerprint=digest(
                            {
                                "opportunity_id": str(opportunity_id),
                                "unit_key": normalize_unit_key(item.unit_key),
                            }
                        ),
                    ),
                    effective_from=store.clock(),
                )
            except UnitIdentityError as error:
                raise InvestigationError("REGISTRATION_POSITION_KEY_CONFLICT") from error
            assert unit.current_version_id is not None
            positions.append(
                InvestigationPositionBinding(
                    entity_id=item.entity_id,
                    opportunity_unit_id=unit.opportunity_unit_id,
                    opportunity_unit_version_id=unit.current_version_id,
                )
            )
        binding_command = BindInvestigation(
            delivery_hash=command.delivery_hash,
            opportunity_id=opportunity_id,
            opportunity_version=version,
            positions=tuple(positions),
            previous_binding_id=expected,
            reason=command.reason,
        )
        _check_positions(session, task, binding_command)
        request = binding_command.model_dump(mode="json") | {"registration": registration}
        row = InvestigationBinding(
            binding_id=uuid7(),
            task_id=task_id,
            sequence=1 if previous is None else previous.sequence + 1,
            delivery_hash=command.delivery_hash,
            source_bundle_revision_id=revision.source_bundle_revision_id,
            opportunity_id=opportunity_id,
            opportunity_version=version,
            reviewer_id=principal.reviewer_id,
            request_key_hash=key_hash,
            request_hash=digest(request),
            request=request,
            created_at=store.clock(),
        )
        session.add(row)
        session.flush()
        return store._view(session, task) | {"binding_receipt": _receipt(session, task, row)}
