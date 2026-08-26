from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import UUID, uuid7

from pydantic import JsonValue, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.artifacts.models import RawArtifact
from deepaha.contracts.phase3 import (
    OpportunityDocumentRole,
    OpportunityFieldChangeSchema,
    OpportunityFieldEvidenceSchema,
    OpportunitySnapshotSchema,
    SnapshotField,
)
from deepaha.documents.models import Document, EvidenceRef
from deepaha.local_human_test.contracts import ItemStatus, ReviewDecisionKind
from deepaha.local_human_test.models import (
    LocalHumanTestItem,
    LocalHumanTestReviewDecision,
)
from deepaha.local_human_test.review import (
    require_human_fact_reviewer,
    validate_idempotency_key,
)
from deepaha.opportunities.models import Opportunity, OpportunityEvent, OpportunityVersion
from deepaha.opportunities.versioning import (
    canonical_content_sha256,
    classify_event_type,
)
from deepaha.p9b.hashing import model_request_hash
from deepaha.p9b.models import (
    FactVerificationDecisionModel,
    RuleApprovalDecisionModel,
    RuleCandidateModel,
    VerifiedFact,
    VerifiedFactEvidence,
    VersionedVerifiedFactSet,
)
from deepaha.public_catalog.models import PublicCatalogEntry
from deepaha.review.auth import ReviewerPrincipal
from deepaha.sources.models import Source, SourceEndpoint

PUBLICATION_FACT_NAMES = frozenset(
    {
        "canonical_title",
        "type",
        "issuer_name",
        "jurisdiction",
        "status",
        "published_at",
        "application_window",
        "application_url",
        "attachment_urls",
        "locations",
    }
)


class LocalPublicationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PublicationFact:
    field_name: str
    normalized_value: JsonValue
    evidence_ref_id: UUID
    effective_at: datetime

    def __post_init__(self) -> None:
        if self.effective_at.tzinfo is None or self.effective_at.utcoffset() is None:
            raise ValueError("effective_at must include timezone information")


@dataclass(frozen=True, slots=True)
class PublicationMaterial:
    snapshot: OpportunitySnapshotSchema
    field_evidence: tuple[OpportunityFieldEvidenceSchema, ...]
    content_sha256: str


@dataclass(frozen=True, slots=True)
class PublicationPreview:
    item_id: UUID
    opportunity_id: UUID
    base_version: int
    approved_field_names: tuple[str, ...]
    missing_field_names: tuple[str, ...]
    content_use_basis: str | None
    official_evidence_complete: bool
    eligibility_ceiling: str
    blocker_codes: tuple[str, ...]
    material: PublicationMaterial | None

    @property
    def eligible(self) -> bool:
        return not self.blocker_codes and self.material is not None


@dataclass(frozen=True, slots=True)
class PublicationResult:
    decision_id: UUID
    item_id: UUID
    opportunity_id: UUID
    opportunity_version: int
    content_sha256: str
    repeated: bool


@dataclass(frozen=True, slots=True)
class _PreparedVersion:
    current: OpportunityVersion
    current_snapshot: OpportunitySnapshotSchema
    changes: tuple[OpportunityFieldChangeSchema, ...]
    merged_evidence: tuple[OpportunityFieldEvidenceSchema, ...]


class PublicationIdempotencyConflict(LocalPublicationError):
    pass


def _utc_now() -> datetime:
    return datetime.now(UTC)


def build_publication_material(
    facts: tuple[PublicationFact, ...],
) -> PublicationMaterial:
    public_facts = tuple(fact for fact in facts if fact.field_name in PUBLICATION_FACT_NAMES)
    by_name = {fact.field_name: fact for fact in public_facts}
    if len(by_name) != len(public_facts):
        raise LocalPublicationError("DUPLICATE_PUBLICATION_FACT")
    if by_name.keys() != PUBLICATION_FACT_NAMES:
        raise LocalPublicationError("PUBLICATION_FACTS_INCOMPLETE")

    values = {name: fact.normalized_value for name, fact in by_name.items()}
    try:
        snapshot = OpportunitySnapshotSchema.model_validate(
            {
                "canonical_title": values["canonical_title"],
                "type": values["type"],
                "issuer_name": values["issuer_name"],
                "jurisdiction": values["jurisdiction"],
                "status": values["status"],
                "published_at": values["published_at"],
                "application_window": values["application_window"],
                "application_url": values["application_url"],
                "attachment_urls": values["attachment_urls"],
                "locations": values["locations"],
            }
        )
        field_evidence = tuple(
            OpportunityFieldEvidenceSchema(
                field_path=field_path,
                precedence=400,
                evidence_ref_id=by_name[fact_name].evidence_ref_id,
                effective_at=by_name[fact_name].effective_at,
            )
            for field_path, fact_name in (
                (SnapshotField.CANONICAL_TITLE, "canonical_title"),
                (SnapshotField.TYPE, "type"),
                (SnapshotField.ISSUER_NAME, "issuer_name"),
                (SnapshotField.JURISDICTION, "jurisdiction"),
                (SnapshotField.STATUS, "status"),
                (SnapshotField.PUBLISHED_AT, "published_at"),
                (SnapshotField.APPLICATION_WINDOW_OPENS_ON, "application_window"),
                (SnapshotField.APPLICATION_WINDOW_CLOSES_ON, "application_window"),
                (SnapshotField.APPLICATION_WINDOW_TIMEZONE, "application_window"),
                (SnapshotField.APPLICATION_URL, "application_url"),
                (SnapshotField.ATTACHMENT_URLS, "attachment_urls"),
                (SnapshotField.LOCATIONS, "locations"),
            )
        )
        digest = canonical_content_sha256(snapshot, field_evidence)
    except (TypeError, ValueError, ValidationError) as error:
        raise LocalPublicationError("PUBLICATION_FACT_VALUE_INVALID") from error
    return PublicationMaterial(
        snapshot=snapshot,
        field_evidence=field_evidence,
        content_sha256=digest,
    )


def _snapshot_values(snapshot: OpportunitySnapshotSchema) -> dict[SnapshotField, JsonValue]:
    value = snapshot.model_dump(mode="json")
    window = value["application_window"]
    assert isinstance(window, dict)
    return {
        SnapshotField.CANONICAL_TITLE: value["canonical_title"],
        SnapshotField.TYPE: value["type"],
        SnapshotField.ISSUER_NAME: value["issuer_name"],
        SnapshotField.JURISDICTION: value["jurisdiction"],
        SnapshotField.STATUS: value["status"],
        SnapshotField.PUBLISHED_AT: value["published_at"],
        SnapshotField.APPLICATION_WINDOW_OPENS_ON: window["opens_on"],
        SnapshotField.APPLICATION_WINDOW_CLOSES_ON: window["closes_on"],
        SnapshotField.APPLICATION_WINDOW_TIMEZONE: window["timezone"],
        SnapshotField.APPLICATION_URL: value["application_url"],
        SnapshotField.ATTACHMENT_URLS: value["attachment_urls"],
        SnapshotField.LOCATIONS: value["locations"],
    }


class LocalCatalogPublicationService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    def preview(self, item_id: UUID) -> PublicationPreview:
        with self._session_factory() as session:
            return self._load_preview(session, item_id, lock=False)

    def publish(
        self,
        item_id: UUID,
        principal: ReviewerPrincipal,
        idempotency_key: str,
    ) -> PublicationResult:
        require_human_fact_reviewer(principal)
        key = validate_idempotency_key(idempotency_key)
        with self._session_factory.begin() as session:
            preview = self._load_preview(session, item_id, lock=True)
            if preview.material is None:
                raise LocalPublicationError("PUBLICATION_PREVIEW_INCOMPLETE")
            request_hash = model_request_hash(
                {
                    "item_id": str(item_id),
                    "opportunity_id": str(preview.opportunity_id),
                    "base_version": preview.base_version,
                    "content_sha256": preview.material.content_sha256,
                    "reviewer_id": str(principal.reviewer_id),
                }
            )
            existing = session.scalar(
                select(LocalHumanTestReviewDecision).where(
                    LocalHumanTestReviewDecision.item_id == item_id,
                    LocalHumanTestReviewDecision.decision_kind == ReviewDecisionKind.PUBLISH.value,
                    LocalHumanTestReviewDecision.idempotency_key == key,
                )
            )
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise PublicationIdempotencyConflict("PUBLICATION_IDEMPOTENCY_CONFLICT")
                entry = session.get(PublicCatalogEntry, preview.opportunity_id)
                version = (
                    None
                    if entry is None
                    else session.get(
                        OpportunityVersion,
                        (entry.opportunity_id, entry.opportunity_version),
                    )
                )
                if entry is None or version is None:
                    raise LocalPublicationError("PUBLICATION_DECISION_BINDING_MISSING")
                return PublicationResult(
                    decision_id=existing.decision_id,
                    item_id=item_id,
                    opportunity_id=entry.opportunity_id,
                    opportunity_version=entry.opportunity_version,
                    content_sha256=version.content_sha256,
                    repeated=True,
                )
            if preview.blocker_codes:
                raise LocalPublicationError(preview.blocker_codes[0])

            item = session.get(LocalHumanTestItem, item_id)
            opportunity = session.get(Opportunity, preview.opportunity_id)
            if (
                item is None
                or ItemStatus(item.status) is not ItemStatus.READY_TO_PUBLISH
                or opportunity is None
                or opportunity.current_version != preview.base_version
            ):
                raise LocalPublicationError("PUBLICATION_BASE_VERSION_CONFLICT")
            if session.get(PublicCatalogEntry, opportunity.opportunity_id) is not None:
                raise LocalPublicationError("PUBLIC_CATALOG_ENTRY_ALREADY_EXISTS")
            published_version = self._persist_version(
                session,
                opportunity=opportunity,
                material=preview.material,
            )
            now = self._clock()
            decision_id = uuid7()
            reviewed_by = f"human:{principal.reviewer_id}"
            session.add(
                PublicCatalogEntry(
                    opportunity_id=opportunity.opportunity_id,
                    opportunity_version=published_version.version,
                    collection_kind="LOCAL_HUMAN_REVIEWED",
                    dataset_id="local-human-test",
                    dataset_version=str(item.run_id),
                    content_use_basis=preview.content_use_basis,
                    reviewed_by=reviewed_by,
                    approved_at=now,
                    last_verified_at=now,
                )
            )
            session.add(
                LocalHumanTestReviewDecision(
                    decision_id=decision_id,
                    item_id=item_id,
                    decision_kind=ReviewDecisionKind.PUBLISH.value,
                    reviewer_id=principal.reviewer_id,
                    idempotency_key=key,
                    request_hash=request_hash,
                    reason="人工确认发布到本地测试目录。",
                    created_at=now,
                )
            )
            item.status = ItemStatus.COMPLETED.value
            item.updated_at = now
            opportunity.publication_status = "PUBLISHED"
            opportunity.current_version = published_version.version
            opportunity.canonical_title = preview.material.snapshot.canonical_title
            opportunity.type = preview.material.snapshot.type.value
            opportunity.issuer_name = preview.material.snapshot.issuer_name
            opportunity.jurisdiction = preview.material.snapshot.jurisdiction
            opportunity.status = preview.material.snapshot.status.value
            opportunity.updated_at = now
            session.flush()
            return PublicationResult(
                decision_id=decision_id,
                item_id=item_id,
                opportunity_id=opportunity.opportunity_id,
                opportunity_version=published_version.version,
                content_sha256=published_version.content_sha256,
                repeated=False,
            )

    def _load_preview(
        self,
        session: Session,
        item_id: UUID,
        *,
        lock: bool,
    ) -> PublicationPreview:
        statement = select(LocalHumanTestItem).where(LocalHumanTestItem.item_id == item_id)
        if lock:
            statement = statement.with_for_update()
        item = session.scalar(statement)
        if item is None or item.verified_fact_set_id is None or item.opportunity_id is None:
            raise LocalPublicationError("PUBLICATION_TARGET_INVALID")
        fact_set = session.get(VersionedVerifiedFactSet, item.verified_fact_set_id)
        if fact_set is None or fact_set.status != "ACTIVE":
            raise LocalPublicationError("ACTIVE_VERIFIED_FACT_SET_REQUIRED")
        blockers: set[str] = set()
        endpoint = None
        if item.endpoint_id is not None:
            endpoint = session.get(SourceEndpoint, item.endpoint_id)
        content_use_basis = None if endpoint is None else endpoint.content_use_basis
        if (
            endpoint is None
            or not endpoint.active
            or endpoint.source_id != item.source_id
            or endpoint.robots_decision not in {"ALLOWED", "NOT_APPLICABLE"}
            or endpoint.content_use_basis not in {"OPEN_LICENSE", "OFFICIAL_PUBLIC_ACCESS"}
        ):
            blockers.add("PUBLICATION_CONTENT_USE_NOT_APPROVED")

        candidate_rows = tuple(
            session.execute(
                select(
                    VerifiedFact,
                    FactVerificationDecisionModel,
                    LocalHumanTestReviewDecision,
                )
                .join(
                    FactVerificationDecisionModel,
                    FactVerificationDecisionModel.decision_id
                    == VerifiedFact.verification_decision_id,
                )
                .join(
                    LocalHumanTestReviewDecision,
                    LocalHumanTestReviewDecision.decision_id
                    == FactVerificationDecisionModel.decision_id,
                )
                .where(
                    VerifiedFact.verified_fact_set_id == item.verified_fact_set_id,
                    VerifiedFact.fact_state == "KNOWN",
                    FactVerificationDecisionModel.decision == "APPROVE",
                    FactVerificationDecisionModel.verification_method == "HUMAN",
                    LocalHumanTestReviewDecision.item_id == item_id,
                    LocalHumanTestReviewDecision.decision_kind == ReviewDecisionKind.FACT.value,
                )
                .order_by(VerifiedFact.field_name)
            )
        )
        approved_rows = tuple(
            (fact, decision)
            for fact, decision, local_decision in candidate_rows
            if decision.verifier_identity == f"human:{local_decision.reviewer_id}"
        )
        approved_names = tuple(
            fact.field_name
            for fact, _decision in approved_rows
            if fact.field_name in PUBLICATION_FACT_NAMES
        )
        missing = tuple(sorted(PUBLICATION_FACT_NAMES.difference(approved_names)))
        if missing:
            blockers.add("PUBLICATION_FACTS_INCOMPLETE")

        publication_facts: list[PublicationFact] = []
        allowed_hosts = set() if endpoint is None else set(endpoint.allowed_hosts)
        for fact, _decision in approved_rows:
            if fact.field_name not in PUBLICATION_FACT_NAMES:
                continue
            evidence = self._official_evidence(session, item, fact)
            if evidence is None:
                blockers.add("PUBLICATION_OFFICIAL_EVIDENCE_INCOMPLETE")
                continue
            evidence_ref, document = evidence
            publication_facts.append(
                PublicationFact(
                    field_name=fact.field_name,
                    normalized_value=fact.normalized_value,
                    evidence_ref_id=evidence_ref.evidence_ref_id,
                    effective_at=document.published_at or document.created_at,
                )
            )
            if fact.field_name in {"application_url", "attachment_urls"} and not (
                self._urls_allowed(fact.normalized_value, allowed_hosts)
            ):
                blockers.add("PUBLICATION_URL_OUTSIDE_ALLOWED_HOSTS")

        material = None
        if not missing and len(publication_facts) == len(PUBLICATION_FACT_NAMES):
            try:
                material = build_publication_material(tuple(publication_facts))
            except LocalPublicationError as error:
                blockers.add(str(error))

        opportunity_statement = select(Opportunity).where(
            Opportunity.opportunity_id == item.opportunity_id
        )
        if lock:
            opportunity_statement = opportunity_statement.with_for_update()
        opportunity = session.scalar(opportunity_statement)
        if opportunity is None or opportunity.current_version != fact_set.opportunity_version:
            blockers.add("PUBLICATION_BASE_VERSION_CONFLICT")
        elif material is not None:
            try:
                self._prepare_version(session, opportunity, material)
            except LocalPublicationError as error:
                blockers.add(str(error))

        approved_rule = session.scalar(
            select(RuleApprovalDecisionModel.rule_approval_decision_id)
            .join(
                RuleCandidateModel,
                RuleApprovalDecisionModel.rule_candidate_id == RuleCandidateModel.rule_candidate_id,
            )
            .where(
                RuleCandidateModel.verified_fact_set_id == item.verified_fact_set_id,
                RuleApprovalDecisionModel.decision == "APPROVE",
            )
        )
        return PublicationPreview(
            item_id=item_id,
            opportunity_id=item.opportunity_id,
            base_version=fact_set.opportunity_version,
            approved_field_names=approved_names,
            missing_field_names=missing,
            content_use_basis=content_use_basis,
            official_evidence_complete=(len(publication_facts) == len(PUBLICATION_FACT_NAMES)),
            eligibility_ceiling=("RULE_EVALUATED" if approved_rule is not None else "UNCERTAIN"),
            blocker_codes=tuple(sorted(blockers)),
            material=material,
        )

    @staticmethod
    def _official_evidence(
        session: Session,
        item: LocalHumanTestItem,
        fact: VerifiedFact,
    ) -> tuple[EvidenceRef, Document] | None:
        rows = session.execute(
            select(EvidenceRef, Document, RawArtifact, Source)
            .select_from(VerifiedFactEvidence)
            .join(
                EvidenceRef,
                EvidenceRef.evidence_ref_id == VerifiedFactEvidence.evidence_ref_id,
            )
            .join(Document, Document.document_id == EvidenceRef.document_id)
            .join(RawArtifact, RawArtifact.artifact_id == EvidenceRef.artifact_id)
            .join(Source, Source.source_id == RawArtifact.source_id)
            .where(VerifiedFactEvidence.verified_fact_id == fact.verified_fact_id)
            .order_by(EvidenceRef.evidence_ref_id)
        ).all()
        for evidence_ref, document, artifact, source in rows:
            resolved = urlsplit(artifact.resolved_url)
            if (
                source.source_id == item.source_id
                and source.tier in {"OFFICIAL_PRIMARY", "OFFICIAL_AGGREGATOR"}
                and resolved.scheme in {"http", "https"}
                and resolved.hostname is not None
                and resolved.username is None
                and resolved.password is None
            ):
                return evidence_ref, document
        return None

    @staticmethod
    def _urls_allowed(value: object, allowed_hosts: set[str]) -> bool:
        values = value if isinstance(value, list) else [value]
        for url in values:
            if not isinstance(url, str):
                return False
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or parsed.hostname not in allowed_hosts:
                return False
        return True

    def _persist_version(
        self,
        session: Session,
        *,
        opportunity: Opportunity,
        material: PublicationMaterial,
    ) -> OpportunityVersion:
        prepared = self._prepare_version(session, opportunity, material)
        current = prepared.current
        changes = prepared.changes
        merged_evidence = prepared.merged_evidence
        if not changes:
            current.review_status = "APPROVED"
            session.flush()
            return current

        source_evidence = session.get(EvidenceRef, changes[0].evidence_ref_id)
        if source_evidence is None:
            raise LocalPublicationError("PUBLICATION_SOURCE_EVIDENCE_MISSING")
        now = self._clock()
        version_number = current.version + 1
        content_sha256 = canonical_content_sha256(material.snapshot, merged_evidence)
        version = OpportunityVersion(
            opportunity_id=opportunity.opportunity_id,
            version=version_number,
            effective_from=now,
            source_document_id=source_evidence.document_id,
            source_evidence_ref_id=source_evidence.evidence_ref_id,
            snapshot=material.snapshot.model_dump(mode="json"),
            field_evidence=[item.model_dump(mode="json") for item in merged_evidence],
            changes=[item.model_dump(mode="json") for item in changes],
            content_sha256=content_sha256,
            review_status="APPROVED",
            created_at=now,
        )
        session.add(version)
        session.flush()
        session.add(
            OpportunityEvent(
                event_id=uuid7(),
                opportunity_id=opportunity.opportunity_id,
                from_version=current.version,
                to_version=version_number,
                event_type=classify_event_type(
                    version_number,
                    OpportunityDocumentRole.PRIMARY_NOTICE,
                    changes,
                ).value,
                changed_fields=[item.field_path.value for item in changes],
                changes=[item.model_dump(mode="json") for item in changes],
                source_document_id=source_evidence.document_id,
                source_evidence_ref_id=source_evidence.evidence_ref_id,
                detected_at=now,
            )
        )
        session.flush()
        return version

    @staticmethod
    def _prepare_version(
        session: Session,
        opportunity: Opportunity,
        material: PublicationMaterial,
    ) -> _PreparedVersion:
        if opportunity.current_version is None:
            raise LocalPublicationError("PUBLICATION_BASE_VERSION_INVALID")
        current = session.get(
            OpportunityVersion,
            (opportunity.opportunity_id, opportunity.current_version),
        )
        if current is None or current.review_status == "REJECTED":
            raise LocalPublicationError("PUBLICATION_BASE_VERSION_INVALID")
        try:
            current_snapshot = OpportunitySnapshotSchema.model_validate(current.snapshot)
            current_evidence = {
                item.field_path: item
                for item in (
                    OpportunityFieldEvidenceSchema.model_validate(value)
                    for value in current.field_evidence
                )
            }
        except ValidationError as error:
            raise LocalPublicationError("PUBLICATION_BASE_VERSION_INVALID") from error

        current_values = _snapshot_values(current_snapshot)
        desired_values = _snapshot_values(material.snapshot)
        desired_evidence = {item.field_path: item for item in material.field_evidence}
        changes = tuple(
            OpportunityFieldChangeSchema(
                field_path=field,
                before=current_values[field],
                after=desired_values[field],
                evidence_ref_id=desired_evidence[field].evidence_ref_id,
            )
            for field in SnapshotField
            if current_values[field] != desired_values[field]
        )
        for change in changes:
            current_evidence[change.field_path] = desired_evidence[change.field_path]
        if set(SnapshotField).difference(current_evidence):
            raise LocalPublicationError("PUBLICATION_VERSION_EVIDENCE_INCOMPLETE")
        merged_evidence = tuple(current_evidence[field] for field in SnapshotField)
        if (
            not changes
            and canonical_content_sha256(current_snapshot, merged_evidence)
            != current.content_sha256
        ):
            raise LocalPublicationError("PUBLICATION_BASE_CONTENT_HASH_INVALID")
        return _PreparedVersion(
            current=current,
            current_snapshot=current_snapshot,
            changes=changes,
            merged_evidence=merged_evidence,
        )


__all__ = [
    "LocalPublicationError",
    "LocalCatalogPublicationService",
    "PUBLICATION_FACT_NAMES",
    "PublicationIdempotencyConflict",
    "PublicationFact",
    "PublicationMaterial",
    "PublicationPreview",
    "PublicationResult",
    "build_publication_material",
]
