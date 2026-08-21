from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4, uuid7

import pytest
from sqlalchemy import Engine, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from deepaha.artifacts.models import RawArtifact
from deepaha.documents.models import Document, EvidenceRef
from deepaha.opportunities.models import (
    DocumentOpportunityLink,
    Opportunity,
    OpportunityAlias,
    OpportunityEvent,
    OpportunityIdentityAction,
    OpportunityIdentityActionMember,
    OpportunityResolutionCandidate,
    OpportunityVersion,
)
from deepaha.sources.models import Source

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)
SHA_ONE = "1" * 64
SHA_TWO = "2" * 64
PHASE3_TABLES = {
    "opportunity_versions",
    "opportunity_events",
    "document_opportunity_links",
    "opportunity_resolution_candidates",
    "opportunity_aliases",
    "opportunity_identity_actions",
    "opportunity_identity_action_members",
}


def make_source(*, suffix: str = "1") -> Source:
    source_id = uuid7()
    return Source(
        source_id=source_id,
        public_id=f"src_{source_id.hex}",
        canonical_url=f"https://phase3-{suffix}.example.gov/",
        authority_name=f"Synthetic Phase 3 Authority {suffix}",
        tier="OFFICIAL_PRIMARY",
        jurisdiction=None,
        active=True,
        created_at=NOW,
        updated_at=NOW,
    )


def make_artifact(source: Source, *, sha256: str = SHA_ONE) -> RawArtifact:
    return RawArtifact(
        artifact_id=uuid7(),
        source_id=source.source_id,
        requested_url="https://phase3.example.gov/notices/1",
        resolved_url="https://phase3.example.gov/notices/1",
        retrieved_at=NOW,
        http_status=200,
        media_type="text/html",
        content_sha256=sha256,
        storage_bucket="deepaha-raw",
        object_key=f"raw/sha256/{sha256[:2]}/{sha256}",
        byte_size=128,
        collector_version="phase3-test/0.3.0",
        metadata_schema_version="0.2.0",
    )


def make_document(artifact: RawArtifact) -> Document:
    return Document(
        document_id=uuid7(),
        artifact_id=artifact.artifact_id,
        title="Synthetic Phase 3 notice",
        published_at=NOW,
        language="und",
        extracted_text_uri=None,
        parser_name="phase3_synthetic",
        parser_version="0.3.0",
        parse_confidence=None,
        created_at=NOW,
    )


def make_evidence(document: Document, artifact: RawArtifact) -> EvidenceRef:
    return EvidenceRef(
        evidence_ref_id=uuid7(),
        document_id=document.document_id,
        artifact_id=artifact.artifact_id,
        locator_kind="full_document",
        locator_value="*",
        locator_schema_version="0.1.0",
        locator_payload=None,
        quote_sha256=artifact.content_sha256,
    )


def make_opportunity(*, current_version: int | None = None) -> Opportunity:
    opportunity_id = uuid7()
    return Opportunity(
        opportunity_id=opportunity_id,
        public_id=f"opp_{opportunity_id.hex}",
        type="YOUTH_DEVELOPMENT_PROGRAM",
        canonical_title="Synthetic Phase 3 opportunity",
        issuer_name="Synthetic Phase 3 Authority",
        jurisdiction=None,
        current_version=current_version,
        status="OPEN",
        publication_status="INTERNAL",
        created_at=NOW,
        updated_at=NOW,
    )


def make_version(
    opportunity: Opportunity,
    document: Document,
    evidence: EvidenceRef,
    *,
    version: int = 1,
    content_sha256: str = SHA_ONE,
) -> OpportunityVersion:
    change = {
        "field_path": "canonical_title",
        "before": None,
        "after": opportunity.canonical_title,
        "evidence_ref_id": str(evidence.evidence_ref_id),
    }
    return OpportunityVersion(
        opportunity_id=opportunity.opportunity_id,
        version=version,
        effective_from=NOW,
        source_document_id=document.document_id,
        source_evidence_ref_id=evidence.evidence_ref_id,
        snapshot={
            "canonical_title": opportunity.canonical_title,
            "type": opportunity.type,
            "issuer_name": opportunity.issuer_name,
            "jurisdiction": None,
            "status": opportunity.status,
            "published_at": NOW.isoformat(),
            "application_window": {
                "opens_on": None,
                "closes_on": None,
                "timezone": None,
            },
            "application_url": None,
            "attachment_urls": [],
            "locations": [],
        },
        field_evidence=[
            {
                "field_path": "canonical_title",
                "precedence": 600,
                "evidence_ref_id": str(evidence.evidence_ref_id),
                "effective_at": NOW.isoformat(),
            }
        ],
        changes=[change],
        content_sha256=content_sha256,
        review_status="NOT_REQUIRED",
        created_at=NOW,
    )


def make_event(
    opportunity: Opportunity,
    document: Document,
    evidence: EvidenceRef,
    *,
    event_id: UUID | None = None,
    event_type: str = "CREATED",
    from_version: int | None = None,
    to_version: int = 1,
    source_document_id: UUID | None = None,
    source_evidence_ref_id: UUID | None = None,
) -> OpportunityEvent:
    change = {
        "field_path": "canonical_title",
        "before": None,
        "after": opportunity.canonical_title,
        "evidence_ref_id": str(evidence.evidence_ref_id),
    }
    return OpportunityEvent(
        event_id=event_id or uuid7(),
        opportunity_id=opportunity.opportunity_id,
        from_version=from_version,
        to_version=to_version,
        event_type=event_type,
        changed_fields=["canonical_title"],
        changes=[change],
        source_document_id=source_document_id or document.document_id,
        source_evidence_ref_id=source_evidence_ref_id or evidence.evidence_ref_id,
        detected_at=NOW,
    )


def persist_graph(
    session: Session,
) -> tuple[Source, RawArtifact, Document, EvidenceRef, Opportunity]:
    source = make_source()
    artifact = make_artifact(source)
    document = make_document(artifact)
    evidence = make_evidence(document, artifact)
    opportunity = make_opportunity()
    session.add(source)
    session.flush()
    session.add(artifact)
    session.flush()
    session.add_all([document, opportunity])
    session.flush()
    session.add(evidence)
    session.flush()
    return source, artifact, document, evidence, opportunity


def test_phase3_tables_exist(migrated_engine: Engine) -> None:
    assert set(inspect(migrated_engine).get_table_names()) >= PHASE3_TABLES


def test_current_version_must_reference_same_opportunity_version(session: Session) -> None:
    opportunity = make_opportunity(current_version=1)
    session.add(opportunity)
    session.flush()

    with pytest.raises(IntegrityError):
        session.execute(text("set constraints all immediate"))


def test_event_rejects_evidence_from_another_document(session: Session) -> None:
    _, _, document, evidence, opportunity = persist_graph(session)
    # Build the second graph explicitly so its EvidenceRef belongs to another Document.
    other_source = make_source(suffix="2")
    other_artifact = make_artifact(other_source, sha256=SHA_TWO)
    other_document = make_document(other_artifact)
    other_evidence = make_evidence(other_document, other_artifact)
    session.add(other_source)
    session.flush()
    session.add(other_artifact)
    session.flush()
    session.add(other_document)
    session.flush()
    session.add(other_evidence)
    session.flush()
    session.add(make_version(opportunity, document, evidence))
    session.flush()
    session.add(
        make_event(
            opportunity,
            document,
            evidence,
            source_evidence_ref_id=other_evidence.evidence_ref_id,
        )
    )

    with pytest.raises(IntegrityError):
        session.flush()


def test_one_document_cannot_have_two_active_opportunity_links(session: Session) -> None:
    _, _, document, evidence, first = persist_graph(session)
    second = make_opportunity()
    session.add(second)
    session.flush()
    for opportunity in (first, second):
        session.add(
            DocumentOpportunityLink(
                link_id=uuid7(),
                document_id=document.document_id,
                opportunity_id=opportunity.opportunity_id,
                role="PRIMARY_NOTICE",
                resolution_key="external:synthetic:001",
                resolver_version="0.3.0",
                source_evidence_ref_id=evidence.evidence_ref_id,
                linked_at=NOW,
                ended_at=None,
                ended_by_identity_action_id=None,
            )
        )

    with pytest.raises(IntegrityError):
        session.flush()


@pytest.mark.parametrize(
    ("changes", "content_sha256"),
    [
        ([], SHA_ONE),
        ([{"field_path": "status"}], "A" * 64),
    ],
)
def test_version_rejects_empty_changes_and_bad_sha(
    session: Session,
    changes: list[dict[str, object]],
    content_sha256: str,
) -> None:
    _, _, document, evidence, opportunity = persist_graph(session)
    invalid = make_version(opportunity, document, evidence)
    invalid.changes = changes
    invalid.content_sha256 = content_sha256
    session.add(invalid)
    with pytest.raises(IntegrityError):
        session.flush()


def test_version_rejects_duplicate_content_hash(session: Session) -> None:
    _, _, document, evidence, opportunity = persist_graph(session)
    session.add(make_version(opportunity, document, evidence))
    session.flush()
    session.add(make_version(opportunity, document, evidence, version=2))
    with pytest.raises(IntegrityError):
        session.flush()


@pytest.mark.parametrize(
    ("event_id", "event_type", "from_version", "to_version"),
    [
        (uuid4(), "CREATED", None, 1),
        (uuid7(), "UNKNOWN", None, 1),
        (uuid7(), "UPDATED", None, 1),
        (uuid7(), "UPDATED", 1, 3),
    ],
)
def test_event_enforces_uuid7_type_and_transition(
    session: Session,
    event_id: UUID,
    event_type: str,
    from_version: int | None,
    to_version: int,
) -> None:
    _, _, document, evidence, opportunity = persist_graph(session)
    session.add(make_version(opportunity, document, evidence))
    session.flush()
    session.add(
        make_event(
            opportunity,
            document,
            evidence,
            event_id=event_id,
            event_type=event_type,
            from_version=from_version,
            to_version=to_version,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_event_allows_only_one_event_per_target_version(session: Session) -> None:
    _, _, document, evidence, opportunity = persist_graph(session)
    session.add(make_version(opportunity, document, evidence))
    session.flush()
    session.add(make_event(opportunity, document, evidence))
    session.flush()
    session.add(make_event(opportunity, document, evidence))
    with pytest.raises(IntegrityError):
        session.flush()


@pytest.mark.parametrize(
    ("candidate_ids", "reason_codes", "review_status"),
    [
        (cast(list[str], {"not": "an array"}), ["STRONG_KEY_CONFLICT"], "PENDING"),
        ([], [], "PENDING"),
        ([], ["STRONG_KEY_CONFLICT"], "APPROVED"),
    ],
)
def test_candidate_requires_json_arrays_and_pending_status(
    session: Session,
    candidate_ids: list[str],
    reason_codes: list[str],
    review_status: str,
) -> None:
    _, _, document, evidence, opportunity = persist_graph(session)
    session.add(
        OpportunityResolutionCandidate(
            candidate_id=uuid7(),
            document_id=document.document_id,
            candidate_opportunity_ids=candidate_ids,
            proposed_role="CORRECTION",
            proposed_snapshot=None,
            reason_codes=reason_codes,
            resolver_version="0.3.0",
            source_evidence_ref_id=evidence.evidence_ref_id,
            review_status=review_status,
            created_at=NOW,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def make_alias(
    opportunity: Opportunity,
    source: Source,
    document: Document,
    evidence: EvidenceRef,
    *,
    alias_type: str,
    normalized_value: str,
) -> OpportunityAlias:
    return OpportunityAlias(
        alias_id=uuid7(),
        opportunity_id=opportunity.opportunity_id,
        alias_type=alias_type,
        alias_value=normalized_value.upper(),
        normalized_value=normalized_value,
        source_id=source.source_id,
        source_document_id=document.document_id,
        source_evidence_ref_id=evidence.evidence_ref_id,
        created_at=NOW,
    )


def test_external_alias_rejects_duplicate_in_same_source(session: Session) -> None:
    source, _, document, evidence, first = persist_graph(session)
    second = make_opportunity()
    session.add(second)
    session.flush()
    for opportunity in (first, second):
        session.add(
            make_alias(
                opportunity,
                source,
                document,
                evidence,
                alias_type="EXTERNAL_ID",
                normalized_value="synthetic-001",
            )
        )
    with pytest.raises(IntegrityError):
        session.flush()


def test_external_alias_allows_same_value_in_another_source(session: Session) -> None:
    source, _, document, evidence, first = persist_graph(session)
    second_source = make_source(suffix="2")
    second = make_opportunity()
    session.add_all([second_source, second])
    session.flush()
    session.add_all(
        [
            make_alias(
                first,
                source,
                document,
                evidence,
                alias_type="EXTERNAL_ID",
                normalized_value="synthetic-001",
            ),
            make_alias(
                second,
                second_source,
                document,
                evidence,
                alias_type="EXTERNAL_ID",
                normalized_value="synthetic-001",
            ),
        ]
    )
    session.flush()


def test_url_alias_is_globally_unique(session: Session) -> None:
    source, _, document, evidence, first = persist_graph(session)
    second = make_opportunity()
    session.add(second)
    session.flush()
    session.add_all(
        [
            make_alias(
                opportunity,
                source,
                document,
                evidence,
                alias_type="URL",
                normalized_value="https://phase3.example.gov/notices/1",
            )
            for opportunity in (first, second)
        ]
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_identity_action_requires_reversal_shape_and_member_roles(session: Session) -> None:
    _, _, document, evidence, opportunity = persist_graph(session)
    action = OpportunityIdentityAction(
        action_id=uuid7(),
        action_type="MERGE_REVERSAL",
        reversal_of_action_id=None,
        actor="phase3-test",
        reason="Synthetic reversal",
        source_document_id=document.document_id,
        source_evidence_ref_id=evidence.evidence_ref_id,
        occurred_at=NOW,
    )
    session.add(action)
    with pytest.raises(IntegrityError):
        session.flush()

    session.rollback()
    _, _, document, evidence, opportunity = persist_graph(session)
    action = OpportunityIdentityAction(
        action_id=uuid7(),
        action_type="MERGE",
        reversal_of_action_id=None,
        actor="phase3-test",
        reason="Synthetic merge",
        source_document_id=document.document_id,
        source_evidence_ref_id=evidence.evidence_ref_id,
        occurred_at=NOW,
    )
    session.add(action)
    session.flush()
    session.add(
        OpportunityIdentityActionMember(
            action_id=action.action_id,
            opportunity_id=opportunity.opportunity_id,
            role="UNKNOWN",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_valid_phase3_history_persists(session: Session) -> None:
    _, _, document, evidence, opportunity = persist_graph(session)
    session.add(make_version(opportunity, document, evidence))
    session.flush()
    session.add(make_event(opportunity, document, evidence))
    opportunity.current_version = 1
    session.flush()
    session.execute(text("set constraints all immediate"))

    assert session.scalar(select(func.count()).select_from(OpportunityVersion)) == 1
    assert session.scalar(select(func.count()).select_from(OpportunityEvent)) == 1
