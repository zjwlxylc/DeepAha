from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid7

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.artifacts.models import RawArtifact
from deepaha.contracts.phase1 import OpportunityStatus, SourceTier
from deepaha.contracts.phase2 import OpportunityTypeV02
from deepaha.contracts.phase3 import (
    OpportunityEventType,
    OpportunityFieldEvidenceSchema,
    OpportunitySnapshotSchema,
    ResolutionDisposition,
)
from deepaha.documents.models import Document, EvidenceRef
from deepaha.opportunities.identity import (
    normalize_identity_text,
    normalize_official_url,
    weak_fingerprint,
)
from deepaha.opportunities.models import (
    DocumentOpportunityLink,
    Opportunity,
    OpportunityAlias,
    OpportunityEvent,
    OpportunityResolutionCandidate,
    OpportunityVersion,
)
from deepaha.opportunities.resolver import resolve_document
from deepaha.opportunities.types import (
    OpportunityPatch,
    ResolutionDecision,
    ResolutionDocument,
    ResolutionIndex,
    ResolutionTarget,
)
from deepaha.opportunities.versioning import (
    VersionCommand,
    VersionConflict,
    VersionPlan,
    VersionState,
    plan_version,
)
from deepaha.sources.models import Source


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    disposition: str
    opportunity_id: UUID | None
    public_id: str | None
    version: int | None
    event_type: str | None
    candidate_id: UUID | None
    reason_codes: tuple[str, ...]
    resolution_key: str


def _target_for_opportunity(
    opportunity: Opportunity,
    aliases: list[OpportunityAlias],
) -> ResolutionTarget:
    identity_keys: list[tuple[int, str]] = []
    for alias in aliases:
        if alias.alias_type == "EXTERNAL_ID" and alias.source_id is not None:
            identity_keys.append(
                (
                    0,
                    f"external:{alias.source_id}:{alias.normalized_value}",
                )
            )
        elif alias.alias_type == "URL":
            identity_keys.append((1, f"url:{alias.normalized_value}"))
    primary_identity_key = (
        min(identity_keys)[1] if identity_keys else f"public:{opportunity.public_id}"
    )
    return ResolutionTarget(
        opportunity_id=opportunity.opportunity_id,
        public_id=opportunity.public_id,
        primary_identity_key=primary_identity_key,
    )


def load_resolution_index(session: Session) -> ResolutionIndex:
    opportunities = session.scalars(select(Opportunity).order_by(Opportunity.opportunity_id)).all()
    aliases = session.scalars(
        select(OpportunityAlias).order_by(
            OpportunityAlias.opportunity_id,
            OpportunityAlias.created_at,
            OpportunityAlias.alias_id,
        )
    ).all()
    aliases_by_opportunity: dict[UUID, list[OpportunityAlias]] = defaultdict(list)
    for alias in aliases:
        aliases_by_opportunity[alias.opportunity_id].append(alias)
    targets = {
        opportunity.opportunity_id: _target_for_opportunity(
            opportunity,
            aliases_by_opportunity[opportunity.opportunity_id],
        )
        for opportunity in opportunities
    }

    document_links: dict[UUID, ResolutionTarget] = {}
    for link in session.scalars(
        select(DocumentOpportunityLink)
        .where(DocumentOpportunityLink.ended_at.is_(None))
        .order_by(DocumentOpportunityLink.document_id)
    ):
        document_links[link.document_id] = targets[link.opportunity_id]

    external_keys: dict[str, list[ResolutionTarget]] = defaultdict(list)
    url_keys: dict[str, list[ResolutionTarget]] = defaultdict(list)
    weak_candidates: dict[str, list[ResolutionTarget]] = defaultdict(list)
    public_ids: dict[str, list[ResolutionTarget]] = defaultdict(list)
    opportunities_by_id = {item.opportunity_id: item for item in opportunities}
    for opportunity in opportunities:
        public_ids[opportunity.public_id].append(targets[opportunity.opportunity_id])
    for alias in aliases:
        target = targets[alias.opportunity_id]
        if alias.alias_type == "EXTERNAL_ID" and alias.source_id is not None:
            external_keys[f"external:{alias.source_id}:{alias.normalized_value}"].append(target)
        elif alias.alias_type == "URL":
            url_keys[f"url:{alias.normalized_value}"].append(target)
        elif alias.alias_type == "TITLE":
            opportunity = opportunities_by_id[alias.opportunity_id]
            fingerprint = weak_fingerprint(
                OpportunityPatch(
                    canonical_title=alias.alias_value,
                    type=OpportunityTypeV02(opportunity.type),
                    issuer_name=opportunity.issuer_name,
                    jurisdiction=opportunity.jurisdiction,
                )
            )
            if fingerprint is not None:
                weak_candidates[fingerprint].append(target)
    for opportunity in opportunities:
        fingerprint = weak_fingerprint(
            OpportunityPatch(
                canonical_title=opportunity.canonical_title,
                type=OpportunityTypeV02(opportunity.type),
                issuer_name=opportunity.issuer_name,
                jurisdiction=opportunity.jurisdiction,
            )
        )
        if fingerprint is not None:
            weak_candidates[fingerprint].append(targets[opportunity.opportunity_id])

    return ResolutionIndex(
        document_links=document_links,
        external_keys={key: tuple(value) for key, value in external_keys.items()},
        url_keys={key: tuple(value) for key, value in url_keys.items()},
        weak_candidates={key: tuple(value) for key, value in weak_candidates.items()},
        public_ids={key: tuple(value) for key, value in public_ids.items()},
    )


class OpportunityResolutionService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        clock: Callable[[], datetime],
        id_factory: Callable[[], UUID] = uuid7,
        resolver_version: str = "0.3.0",
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._id_factory = id_factory
        self._resolver_version = resolver_version

    def resolve(self, command: ResolutionDocument) -> ResolutionResult:
        with self._session_factory() as session:
            try:
                self._validate_evidence_pair(session, command)
                previous_candidate = self._existing_candidate(session, command.document_id)
                if previous_candidate is not None:
                    session.rollback()
                    return previous_candidate
                previous_link = self._existing_link_result(session, command.document_id)
                if previous_link is not None:
                    session.rollback()
                    return previous_link

                decision = resolve_document(command, load_resolution_index(session))
                now = self._clock()
                if decision.disposition is ResolutionDisposition.NEEDS_REVIEW:
                    result = self._save_candidate(session, command, decision, now)
                    session.commit()
                    return result

                opportunity = self._resolve_opportunity(session, command, decision, now)
                link = DocumentOpportunityLink(
                    link_id=self._id_factory(),
                    document_id=command.document_id,
                    opportunity_id=opportunity.opportunity_id,
                    role=command.role.value,
                    resolution_key=decision.resolution_key,
                    resolver_version=self._resolver_version,
                    source_evidence_ref_id=command.evidence_ref_id,
                    linked_at=now,
                    ended_at=None,
                    ended_by_identity_action_id=None,
                )
                session.add(link)
                self._add_missing_aliases(session, opportunity, command, now)
                session.flush()

                current = self._load_version_state(session, opportunity)
                planned = plan_version(
                    current,
                    VersionCommand(
                        opportunity_id=opportunity.opportunity_id,
                        source_document_id=command.document_id,
                        source_evidence_ref_id=command.evidence_ref_id,
                        source_tier=command.source_tier,
                        role=command.role,
                        effective_at=command.effective_at,
                        facts=command.facts,
                    ),
                )
                if planned is None:
                    session.commit()
                    return ResolutionResult(
                        disposition=decision.disposition.value,
                        opportunity_id=opportunity.opportunity_id,
                        public_id=opportunity.public_id,
                        version=None,
                        event_type=None,
                        candidate_id=None,
                        reason_codes=(),
                        resolution_key=decision.resolution_key,
                    )
                if isinstance(planned, VersionConflict):
                    conflict_decision = ResolutionDecision(
                        disposition=ResolutionDisposition.NEEDS_REVIEW,
                        opportunity_id=None,
                        public_id=None,
                        candidate_opportunity_ids=(opportunity.opportunity_id,),
                        reason_codes=planned.reason_codes,
                        resolution_key=decision.resolution_key,
                    )
                    result = self._save_candidate(
                        session,
                        command,
                        conflict_decision,
                        now,
                    )
                    session.commit()
                    return result

                self._persist_plan(session, opportunity, planned, now)
                session.commit()
                return ResolutionResult(
                    disposition=decision.disposition.value,
                    opportunity_id=opportunity.opportunity_id,
                    public_id=opportunity.public_id,
                    version=planned.version,
                    event_type=planned.event_type.value,
                    candidate_id=None,
                    reason_codes=(),
                    resolution_key=decision.resolution_key,
                )
            except Exception:
                session.rollback()
                raise

    def _validate_evidence_pair(
        self,
        session: Session,
        command: ResolutionDocument,
    ) -> None:
        row = session.execute(
            select(EvidenceRef, RawArtifact.source_id, Source.tier)
            .join(Document, EvidenceRef.document_id == Document.document_id)
            .join(RawArtifact, Document.artifact_id == RawArtifact.artifact_id)
            .join(Source, RawArtifact.source_id == Source.source_id)
            .where(
                EvidenceRef.evidence_ref_id == command.evidence_ref_id,
                EvidenceRef.document_id == command.document_id,
            )
        ).one_or_none()
        if row is None:
            raise ValueError("EvidenceRef does not belong to the declared Document")
        _, source_id, source_tier = row
        if source_id != command.source_id or SourceTier(source_tier) is not command.source_tier:
            raise ValueError("ResolutionDocument source does not match persisted evidence source")

    def _existing_candidate(
        self,
        session: Session,
        document_id: UUID,
    ) -> ResolutionResult | None:
        candidate = session.scalar(
            select(OpportunityResolutionCandidate)
            .where(
                OpportunityResolutionCandidate.document_id == document_id,
                OpportunityResolutionCandidate.resolver_version == self._resolver_version,
            )
            .order_by(
                OpportunityResolutionCandidate.created_at,
                OpportunityResolutionCandidate.candidate_id,
            )
            .limit(1)
        )
        if candidate is None:
            return None
        return ResolutionResult(
            disposition=ResolutionDisposition.NEEDS_REVIEW.value,
            opportunity_id=None,
            public_id=None,
            version=None,
            event_type=None,
            candidate_id=candidate.candidate_id,
            reason_codes=tuple(candidate.reason_codes),
            resolution_key=f"document:{document_id}",
        )

    def _existing_link_result(
        self,
        session: Session,
        document_id: UUID,
    ) -> ResolutionResult | None:
        row = session.execute(
            select(DocumentOpportunityLink, Opportunity)
            .join(
                Opportunity,
                DocumentOpportunityLink.opportunity_id == Opportunity.opportunity_id,
            )
            .where(
                DocumentOpportunityLink.document_id == document_id,
                DocumentOpportunityLink.ended_at.is_(None),
            )
        ).one_or_none()
        if row is None:
            return None
        link, opportunity = row
        event = session.scalar(
            select(OpportunityEvent)
            .where(
                OpportunityEvent.opportunity_id == opportunity.opportunity_id,
                OpportunityEvent.source_document_id == document_id,
            )
            .order_by(OpportunityEvent.to_version.desc())
            .limit(1)
        )
        disposition = (
            ResolutionDisposition.CREATED.value
            if event is not None and event.event_type == OpportunityEventType.CREATED.value
            else ResolutionDisposition.LINKED.value
        )
        return ResolutionResult(
            disposition=disposition,
            opportunity_id=opportunity.opportunity_id,
            public_id=opportunity.public_id,
            version=None if event is None else event.to_version,
            event_type=None if event is None else event.event_type,
            candidate_id=None,
            reason_codes=(),
            resolution_key=link.resolution_key,
        )

    def _save_candidate(
        self,
        session: Session,
        command: ResolutionDocument,
        decision: ResolutionDecision,
        now: datetime,
    ) -> ResolutionResult:
        candidate_id = self._id_factory()
        session.add(
            OpportunityResolutionCandidate(
                candidate_id=candidate_id,
                document_id=command.document_id,
                candidate_opportunity_ids=[
                    str(value) for value in decision.candidate_opportunity_ids
                ],
                proposed_role=command.role.value,
                proposed_snapshot=None,
                reason_codes=list(decision.reason_codes),
                resolver_version=self._resolver_version,
                source_evidence_ref_id=command.evidence_ref_id,
                review_status="PENDING",
                created_at=now,
            )
        )
        session.flush()
        return ResolutionResult(
            disposition=ResolutionDisposition.NEEDS_REVIEW.value,
            opportunity_id=None,
            public_id=None,
            version=None,
            event_type=None,
            candidate_id=candidate_id,
            reason_codes=decision.reason_codes,
            resolution_key=decision.resolution_key,
        )

    def _resolve_opportunity(
        self,
        session: Session,
        command: ResolutionDocument,
        decision: ResolutionDecision,
        now: datetime,
    ) -> Opportunity:
        if decision.disposition is ResolutionDisposition.LINKED:
            if decision.opportunity_id is None:
                raise ValueError("LINKED resolution requires opportunity_id")
            opportunity = session.get(Opportunity, decision.opportunity_id)
            if opportunity is None:
                raise ValueError("resolved Opportunity no longer exists")
            return opportunity

        facts = command.facts
        if (
            decision.public_id is None
            or not isinstance(facts.canonical_title, str)
            or not isinstance(facts.type, OpportunityTypeV02)
            or not isinstance(facts.issuer_name, str)
            or not isinstance(facts.status, OpportunityStatus)
        ):
            raise ValueError("CREATED resolution requires complete identity facts")
        opportunity = Opportunity(
            opportunity_id=self._id_factory(),
            public_id=decision.public_id,
            type=facts.type.value,
            canonical_title=facts.canonical_title,
            issuer_name=facts.issuer_name,
            jurisdiction=(facts.jurisdiction if isinstance(facts.jurisdiction, str) else None),
            current_version=None,
            status=facts.status.value,
            publication_status="INTERNAL",
            created_at=now,
            updated_at=now,
        )
        session.add(opportunity)
        session.flush()
        return opportunity

    def _add_missing_aliases(
        self,
        session: Session,
        opportunity: Opportunity,
        command: ResolutionDocument,
        now: datetime,
    ) -> None:
        aliases: list[tuple[str, str, str, UUID | None]] = []
        if command.external_id is not None:
            normalized = normalize_identity_text(command.external_id)
            if normalized:
                aliases.append(("EXTERNAL_ID", command.external_id, normalized, command.source_id))
        if command.canonical_url is not None:
            normalized_url = normalize_official_url(command.canonical_url)
            aliases.append(("URL", command.canonical_url, normalized_url, None))
        if isinstance(command.facts.canonical_title, str):
            normalized_title = normalize_identity_text(command.facts.canonical_title)
            if normalized_title:
                aliases.append(
                    (
                        "TITLE",
                        command.facts.canonical_title,
                        normalized_title,
                        None,
                    )
                )

        for alias_type, alias_value, normalized_value, source_id in aliases:
            existing = session.scalar(
                select(OpportunityAlias.alias_id)
                .where(
                    OpportunityAlias.opportunity_id == opportunity.opportunity_id,
                    OpportunityAlias.alias_type == alias_type,
                    OpportunityAlias.normalized_value == normalized_value,
                    OpportunityAlias.source_id.is_(source_id)
                    if source_id is None
                    else OpportunityAlias.source_id == source_id,
                )
                .limit(1)
            )
            if existing is not None:
                continue
            session.add(
                OpportunityAlias(
                    alias_id=self._id_factory(),
                    opportunity_id=opportunity.opportunity_id,
                    alias_type=alias_type,
                    alias_value=alias_value,
                    normalized_value=normalized_value,
                    source_id=source_id,
                    source_document_id=command.document_id,
                    source_evidence_ref_id=command.evidence_ref_id,
                    created_at=now,
                )
            )

    def _load_version_state(
        self,
        session: Session,
        opportunity: Opportunity,
    ) -> VersionState | None:
        if opportunity.current_version is None:
            return None
        version = session.get(
            OpportunityVersion,
            (opportunity.opportunity_id, opportunity.current_version),
        )
        if version is None:
            raise ValueError("Opportunity current_version does not exist")
        snapshot = OpportunitySnapshotSchema.model_validate(version.snapshot)
        field_evidence = tuple(
            OpportunityFieldEvidenceSchema.model_validate(item) for item in version.field_evidence
        )
        return VersionState(
            opportunity_id=opportunity.opportunity_id,
            version=version.version,
            snapshot=snapshot,
            field_evidence=field_evidence,
            content_sha256=version.content_sha256,
        )

    def _persist_plan(
        self,
        session: Session,
        opportunity: Opportunity,
        planned: VersionPlan,
        now: datetime,
    ) -> None:
        created_at = max(now, planned.effective_from)
        session.add(
            OpportunityVersion(
                opportunity_id=planned.opportunity_id,
                version=planned.version,
                effective_from=planned.effective_from,
                source_document_id=planned.source_document_id,
                source_evidence_ref_id=planned.source_evidence_ref_id,
                snapshot=planned.snapshot.model_dump(mode="json"),
                field_evidence=[item.model_dump(mode="json") for item in planned.field_evidence],
                changes=[item.model_dump(mode="json") for item in planned.changes],
                content_sha256=planned.content_sha256,
                review_status="NOT_REQUIRED",
                created_at=created_at,
            )
        )
        # The composite event foreign key targets this exact version. The ORM
        # has no relationship that would otherwise communicate insert order.
        session.flush()
        session.add(
            OpportunityEvent(
                event_id=self._id_factory(),
                opportunity_id=planned.opportunity_id,
                from_version=None if planned.version == 1 else planned.version - 1,
                to_version=planned.version,
                event_type=planned.event_type.value,
                changed_fields=[item.field_path.value for item in planned.changes],
                changes=[item.model_dump(mode="json") for item in planned.changes],
                source_document_id=planned.source_document_id,
                source_evidence_ref_id=planned.source_evidence_ref_id,
                detected_at=created_at,
            )
        )
        opportunity.canonical_title = planned.snapshot.canonical_title
        opportunity.type = planned.snapshot.type.value
        opportunity.issuer_name = planned.snapshot.issuer_name
        opportunity.jurisdiction = planned.snapshot.jurisdiction
        opportunity.status = planned.snapshot.status.value
        opportunity.current_version = planned.version
        opportunity.updated_at = created_at
        session.flush()


__all__ = [
    "OpportunityResolutionService",
    "ResolutionResult",
    "load_resolution_index",
]
