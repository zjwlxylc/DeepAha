from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import cast
from uuid import UUID

from pydantic import HttpUrl, JsonValue, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from deepaha.artifacts.models import RawArtifact
from deepaha.contracts.phase3 import (
    OpportunityEventSchemaV03,
    OpportunityFieldEvidenceSchema,
    OpportunityVersionSchemaV03,
)
from deepaha.documents.models import EvidenceRef
from deepaha.opportunities.models import Opportunity, OpportunityEvent, OpportunityVersion
from deepaha.public_catalog.cursor import InvalidCursor, decode_cursor, encode_cursor
from deepaha.public_catalog.models import PublicCatalogEntry
from deepaha.public_catalog.schemas import (
    PublicDataLabel,
    PublicEvidence,
    PublicFieldChange,
    PublicHistoryEvent,
    PublicOpportunityCard,
    PublicOpportunityDetail,
    PublicOpportunityPage,
    PublicOpportunityQuery,
    PublicOpportunitySort,
)
from deepaha.sources.models import Source

REQUIRED_EVIDENCE_FIELDS = frozenset(
    {
        "canonical_title",
        "type",
        "issuer_name",
        "jurisdiction",
        "status",
        "published_at",
        "application_window.closes_on",
        "application_url",
        "attachment_urls",
        "locations",
    }
)
OFFICIAL_SOURCE_TIERS = frozenset({"OFFICIAL_PRIMARY", "OFFICIAL_AGGREGATOR"})
AUTHORITY_BY_PRECEDENCE = {
    600: "LATEST_OFFICIAL_CORRECTION",
    500: "FORMAL_OFFICIAL_ATTACHMENT",
    400: "ORIGINAL_OFFICIAL_NOTICE",
    300: "OFFICIAL_FAQ_GUIDANCE",
}


@dataclass(frozen=True)
class _EvidenceSource:
    evidence: EvidenceRef
    official_url: HttpUrl


@dataclass(frozen=True)
class _Candidate:
    entry: PublicCatalogEntry
    opportunity: Opportunity
    version: OpportunityVersion
    contract: OpportunityVersionSchemaV03
    evidence: dict[UUID, _EvidenceSource]
    events: tuple[OpportunityEventSchemaV03, ...]
    card: PublicOpportunityCard


def _safe_http_url(value: object) -> HttpUrl | None:
    try:
        url = HttpUrl(str(value))
    except ValidationError:
        return None
    if url.username is not None or url.password is not None:
        return None
    return url


def _event_markers(events: tuple[OpportunityEventSchemaV03, ...]) -> tuple[str, ...]:
    markers: list[str] = []
    for event in events:
        marker = event.event_type.value
        if marker != "CREATED" and marker not in markers:
            markers.append(marker)
    return tuple(markers)


class PublicCatalogService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_opportunities(self, query: PublicOpportunityQuery) -> PublicOpportunityPage:
        candidates = self._load_candidates()
        cards = [candidate.card for candidate in candidates]
        cards = self._apply_filters(cards, query)
        cards = self._sort_cards(cards, query.sort)
        if query.cursor is not None:
            position = decode_cursor(query.cursor, query.sort)
            position_index = self._cursor_index(cards, position.key, position.public_id, query.sort)
            cards = cards[position_index + 1 :]

        has_next = len(cards) > query.limit
        page_items = tuple(cards[: query.limit])
        next_cursor = None
        if has_next and page_items:
            last = page_items[-1]
            cursor_key: date | datetime = (
                last.published_at
                if query.sort is PublicOpportunitySort.PUBLISHED_DESC
                else last.deadline
            )
            next_cursor = encode_cursor(query.sort, cursor_key, last.public_id)
        data_labels = tuple(sorted({item.data_label for item in page_items}, key=str))
        reproduced_at = max(
            (item.last_verified_at for item in page_items),
            default=None,
        )
        return PublicOpportunityPage(
            items=page_items,
            next_cursor=next_cursor,
            count=len(page_items),
            data_labels=data_labels,
            reproduced_at=reproduced_at,
        )

    def get_opportunity(self, public_id: str) -> PublicOpportunityDetail | None:
        candidate = next(
            (
                value
                for value in self._load_candidates()
                if value.opportunity.public_id == public_id
            ),
            None,
        )
        if candidate is None:
            return None
        snapshot = candidate.contract.snapshot
        assert snapshot.application_url is not None
        key_evidence = tuple(
            self._public_evidence(item, candidate.evidence)
            for item in sorted(
                candidate.contract.field_evidence, key=lambda value: value.field_path
            )
        )
        history = tuple(
            self._public_history(event, candidate.evidence) for event in candidate.events
        )
        return PublicOpportunityDetail(
            **candidate.card.model_dump(),
            current_version=candidate.version.version,
            application_url=snapshot.application_url,
            attachment_urls=snapshot.attachment_urls,
            key_evidence=key_evidence,
            history=history,
        )

    def _load_candidates(self) -> tuple[_Candidate, ...]:
        rows = self._session.execute(
            select(PublicCatalogEntry, Opportunity, OpportunityVersion)
            .select_from(PublicCatalogEntry)
            .join(
                Opportunity,
                Opportunity.opportunity_id == PublicCatalogEntry.opportunity_id,
            )
            .join(
                OpportunityVersion,
                (OpportunityVersion.opportunity_id == PublicCatalogEntry.opportunity_id)
                & (OpportunityVersion.version == PublicCatalogEntry.opportunity_version),
            )
            .where(
                Opportunity.publication_status == "PUBLISHED",
                Opportunity.current_version == PublicCatalogEntry.opportunity_version,
                OpportunityVersion.review_status != "REJECTED",
            )
        ).all()
        if not rows:
            return ()

        contracts: dict[UUID, OpportunityVersionSchemaV03] = {}
        for entry, opportunity, version in rows:
            try:
                contracts[opportunity.opportunity_id] = OpportunityVersionSchemaV03.model_validate(
                    {
                        "opportunity_id": version.opportunity_id,
                        "version": version.version,
                        "effective_from": version.effective_from,
                        "source_document_id": version.source_document_id,
                        "source_evidence_ref_id": version.source_evidence_ref_id,
                        "snapshot": version.snapshot,
                        "field_evidence": version.field_evidence,
                        "changes": version.changes,
                        "content_sha256": version.content_sha256,
                        "review_status": version.review_status,
                        "created_at": version.created_at,
                    }
                )
            except ValidationError:
                continue

        opportunity_ids = tuple(contracts)
        if not opportunity_ids:
            return ()
        raw_events = self._session.scalars(
            select(OpportunityEvent)
            .where(OpportunityEvent.opportunity_id.in_(opportunity_ids))
            .order_by(
                OpportunityEvent.opportunity_id,
                OpportunityEvent.to_version,
                OpportunityEvent.detected_at,
                OpportunityEvent.event_id,
            )
        ).all()
        events_by_opportunity: dict[UUID, list[OpportunityEventSchemaV03]] = {
            opportunity_id: [] for opportunity_id in opportunity_ids
        }
        for event in raw_events:
            try:
                event_contract = OpportunityEventSchemaV03.model_validate(
                    {
                        "event_id": event.event_id,
                        "opportunity_id": event.opportunity_id,
                        "from_version": event.from_version,
                        "to_version": event.to_version,
                        "event_type": event.event_type,
                        "changed_fields": event.changed_fields,
                        "changes": event.changes,
                        "source_document_id": event.source_document_id,
                        "source_evidence_ref_id": event.source_evidence_ref_id,
                        "detected_at": event.detected_at,
                    }
                )
            except ValidationError:
                continue
            events_by_opportunity[event.opportunity_id].append(event_contract)

        evidence_ids = {
            item.evidence_ref_id
            for contract in contracts.values()
            for item in contract.field_evidence
        }
        evidence_ids.update(
            event.source_evidence_ref_id
            for events in events_by_opportunity.values()
            for event in events
        )
        evidence = self._load_evidence(evidence_ids)

        candidates: list[_Candidate] = []
        for entry, opportunity, version in rows:
            contract = contracts.get(opportunity.opportunity_id)
            if contract is None:
                continue
            events = tuple(events_by_opportunity[opportunity.opportunity_id])
            if not self._is_complete(opportunity, contract, events, evidence):
                continue
            snapshot = contract.snapshot
            assert snapshot.published_at is not None
            assert snapshot.application_window.closes_on is not None
            candidates.append(
                _Candidate(
                    entry=entry,
                    opportunity=opportunity,
                    version=version,
                    contract=contract,
                    evidence=evidence,
                    events=events,
                    card=PublicOpportunityCard(
                        public_id=opportunity.public_id,
                        title=snapshot.canonical_title,
                        type=snapshot.type,
                        jurisdiction=snapshot.jurisdiction or snapshot.locations[0],
                        locations=snapshot.locations,
                        issuer_name=snapshot.issuer_name,
                        status=snapshot.status,
                        published_at=snapshot.published_at,
                        deadline=snapshot.application_window.closes_on,
                        last_verified_at=entry.last_verified_at,
                        change_markers=_event_markers(events),
                        data_label=PublicDataLabel(entry.collection_kind),
                    ),
                )
            )
        return tuple(candidates)

    def _load_evidence(self, evidence_ids: set[UUID]) -> dict[UUID, _EvidenceSource]:
        if not evidence_ids:
            return {}
        rows = self._session.execute(
            select(EvidenceRef, RawArtifact, Source)
            .select_from(EvidenceRef)
            .join(RawArtifact, RawArtifact.artifact_id == EvidenceRef.artifact_id)
            .join(Source, Source.source_id == RawArtifact.source_id)
            .where(EvidenceRef.evidence_ref_id.in_(tuple(evidence_ids)))
        ).all()
        result: dict[UUID, _EvidenceSource] = {}
        for evidence, artifact, source in rows:
            official_url = _safe_http_url(artifact.resolved_url)
            if source.tier not in OFFICIAL_SOURCE_TIERS or official_url is None:
                continue
            result[evidence.evidence_ref_id] = _EvidenceSource(
                evidence=evidence,
                official_url=official_url,
            )
        return result

    @staticmethod
    def _is_complete(
        opportunity: Opportunity,
        contract: OpportunityVersionSchemaV03,
        events: tuple[OpportunityEventSchemaV03, ...],
        evidence: dict[UUID, _EvidenceSource],
    ) -> bool:
        snapshot = contract.snapshot
        if (
            snapshot.published_at is None
            or snapshot.application_window.closes_on is None
            or snapshot.application_url is None
            or not snapshot.locations
            or not events
            or _safe_http_url(snapshot.application_url) is None
            or any(_safe_http_url(value) is None for value in snapshot.attachment_urls)
        ):
            return False
        if (
            opportunity.canonical_title != snapshot.canonical_title
            or opportunity.type != snapshot.type.value
            or opportunity.issuer_name != snapshot.issuer_name
            or opportunity.jurisdiction != snapshot.jurisdiction
            or opportunity.status != snapshot.status.value
        ):
            return False
        evidence_by_field = {item.field_path.value: item for item in contract.field_evidence}
        if not evidence_by_field.keys() >= REQUIRED_EVIDENCE_FIELDS:
            return False
        if any(item.precedence < 300 for item in contract.field_evidence):
            return False
        if any(
            evidence_by_field[field_path].evidence_ref_id not in evidence
            for field_path in REQUIRED_EVIDENCE_FIELDS
        ):
            return False
        return all(event.source_evidence_ref_id in evidence for event in events)

    @staticmethod
    def _apply_filters(
        cards: list[PublicOpportunityCard],
        query: PublicOpportunityQuery,
    ) -> list[PublicOpportunityCard]:
        result = cards
        if query.q is not None:
            token = query.q.casefold()
            result = [
                item
                for item in result
                if token in "\n".join((item.public_id, item.title, item.issuer_name)).casefold()
            ]
        if query.type is not None:
            result = [item for item in result if item.type is query.type]
        if query.status is not None:
            result = [item for item in result if item.status is query.status]
        if query.region is not None:
            token = query.region.casefold()
            result = [
                item
                for item in result
                if token in "\n".join((item.jurisdiction, *item.locations)).casefold()
            ]
        return result

    @staticmethod
    def _sort_cards(
        cards: list[PublicOpportunityCard],
        sort: PublicOpportunitySort,
    ) -> list[PublicOpportunityCard]:
        if sort is PublicOpportunitySort.DEADLINE_ASC:
            return sorted(cards, key=lambda item: (item.deadline, item.public_id))
        return sorted(cards, key=lambda item: (-item.published_at.timestamp(), item.public_id))

    @staticmethod
    def _cursor_index(
        cards: list[PublicOpportunityCard],
        key: date | datetime,
        public_id: str,
        sort: PublicOpportunitySort,
    ) -> int:
        for index, item in enumerate(cards):
            item_key: date | datetime = (
                item.published_at if sort is PublicOpportunitySort.PUBLISHED_DESC else item.deadline
            )
            if item_key == key and item.public_id == public_id:
                return index
        raise InvalidCursor("cursor position is not present in the governed catalog")

    @staticmethod
    def _public_evidence(
        field_evidence: OpportunityFieldEvidenceSchema,
        evidence: dict[UUID, _EvidenceSource],
    ) -> PublicEvidence:
        item = field_evidence
        evidence_ref_id = item.evidence_ref_id
        source = evidence[evidence_ref_id]
        model = source.evidence
        return PublicEvidence(
            field_path=item.field_path.value,
            evidence_ref_id=evidence_ref_id,
            document_id=model.document_id,
            locator_kind=model.locator_kind,
            locator_value=model.locator_value,
            locator_payload=cast(dict[str, JsonValue] | None, model.locator_payload),
            quote_sha256=model.quote_sha256,
            precedence=item.precedence,
            authority=AUTHORITY_BY_PRECEDENCE[item.precedence],
            official_url=source.official_url,
        )

    @staticmethod
    def _public_history(
        event: OpportunityEventSchemaV03,
        evidence: dict[UUID, _EvidenceSource],
    ) -> PublicHistoryEvent:
        source = evidence[event.source_evidence_ref_id]
        return PublicHistoryEvent(
            event_id=event.event_id,
            from_version=event.from_version,
            to_version=event.to_version,
            event_type=event.event_type.value,
            changed_fields=tuple(field.value for field in event.changed_fields),
            changes=tuple(
                PublicFieldChange(
                    field_path=change.field_path.value,
                    before=change.before,
                    after=change.after,
                )
                for change in event.changes
            ),
            detected_at=event.detected_at,
            evidence_ref_id=event.source_evidence_ref_id,
            document_id=event.source_document_id,
            official_url=source.official_url,
        )
