import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import cast
from uuid import UUID, uuid7

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.artifacts.models import RawArtifact
from deepaha.contracts.phase1 import OpportunityStatus, SourceTier
from deepaha.contracts.phase2 import OpportunityTypeV02
from deepaha.contracts.phase3 import ApplicationWindowSchema, OpportunityDocumentRole
from deepaha.documents.models import Document, EvidenceRef
from deepaha.opportunities.models import (
    DocumentOpportunityLink,
    Opportunity,
    OpportunityAlias,
    OpportunityEvent,
    OpportunityResolutionCandidate,
    OpportunityVersion,
)
from deepaha.opportunities.service import OpportunityResolutionService, ResolutionResult
from deepaha.opportunities.types import OpportunityPatch, ResolutionDocument
from deepaha.sources.models import Source

pytestmark = pytest.mark.integration
FIXTURE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "opportunities" / "phase3-resolution-cases.json"
)
CLOCK_TIME = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
SOURCE_ONE_ID = UUID("019b0000-0000-7000-8000-000000000001")
SOURCE_TWO_ID = UUID("019b0000-0000-7000-8000-000000000002")
OTHER_OPPORTUNITY_ID = UUID("019b0000-0000-7000-8000-000000000021")
PUBLIC_ID = "opp_63be197cc6ef3632650c5f69b5938f0b"


def load_fixture_cases() -> list[dict[str, object]]:
    fixture: dict[str, object] = json.loads(FIXTURE_PATH.read_text("utf-8"))
    assert fixture["synthetic"] is True
    cases = fixture["cases"]
    assert isinstance(cases, list)
    assert all(isinstance(case, dict) for case in cases)
    return cast(list[dict[str, object]], cases)


def command_from_case(case: dict[str, object]) -> ResolutionDocument:
    raw_facts = case["facts"]
    assert isinstance(raw_facts, dict)
    facts: dict[str, object] = dict(raw_facts)
    if "type" in facts:
        facts["type"] = OpportunityTypeV02(str(facts["type"]))
    if "status" in facts:
        facts["status"] = OpportunityStatus(str(facts["status"]))
    if "application_window" in facts:
        facts["application_window"] = ApplicationWindowSchema.model_validate(
            facts["application_window"]
        )
    for name in ("attachment_urls", "locations"):
        if name in facts:
            value = facts[name]
            assert isinstance(value, list)
            facts[name] = tuple(str(item) for item in value)
    references = case["references_document_ids"]
    assert isinstance(references, list)
    return ResolutionDocument(
        document_id=UUID(str(case["document_id"])),
        source_id=UUID(str(case["source_id"])),
        source_tier=SourceTier(str(case["source_tier"])),
        evidence_ref_id=UUID(str(case["evidence_ref_id"])),
        role=OpportunityDocumentRole(str(case["role"])),
        canonical_url=None if case["canonical_url"] is None else str(case["canonical_url"]),
        external_id=None if case["external_id"] is None else str(case["external_id"]),
        references_document_ids=tuple(UUID(str(item)) for item in references),
        effective_at=datetime.fromisoformat(str(case["effective_at"])),
        facts=OpportunityPatch(**facts),  # type: ignore[arg-type]
    )


def commands_by_id() -> dict[str, ResolutionDocument]:
    return {str(case["case_id"]): command_from_case(case) for case in load_fixture_cases()}


def seed_fixture_documents(session_factory: sessionmaker[Session]) -> None:
    cases = load_fixture_cases()
    with session_factory() as session:
        for source_id, suffix in ((SOURCE_ONE_ID, "1"), (SOURCE_TWO_ID, "2")):
            session.add(
                Source(
                    source_id=source_id,
                    public_id=f"src_{source_id.hex}",
                    canonical_url=f"https://phase3-source-{suffix}.example.gov/",
                    authority_name=f"Synthetic Phase 3 Authority {suffix}",
                    tier=(
                        "OFFICIAL_PRIMARY" if source_id == SOURCE_ONE_ID else "TRUSTED_SECONDARY"
                    ),
                    jurisdiction=None,
                    active=True,
                    created_at=CLOCK_TIME,
                    updated_at=CLOCK_TIME,
                )
            )
        session.flush()
        for index, case in enumerate(cases, start=1):
            artifact_id = UUID(f"019b0000-0000-7000-8000-{0x100 + index:012x}")
            content_hash = sha256(str(case["case_id"]).encode()).hexdigest()
            artifact = RawArtifact(
                artifact_id=artifact_id,
                source_id=UUID(str(case["source_id"])),
                requested_url=f"https://example.gov/synthetic/{case['case_id']}",
                resolved_url=f"https://example.gov/synthetic/{case['case_id']}",
                retrieved_at=CLOCK_TIME,
                http_status=200,
                media_type="application/json",
                content_sha256=content_hash,
                storage_bucket="deepaha-raw",
                object_key=f"raw/sha256/{content_hash[:2]}/{content_hash}",
                byte_size=128,
                collector_version="phase3-synthetic/0.3.0",
                metadata_schema_version="0.2.0",
            )
            document = Document(
                document_id=UUID(str(case["document_id"])),
                artifact_id=artifact_id,
                title=f"Synthetic {case['case_id']}",
                published_at=datetime.fromisoformat(str(case["effective_at"])),
                language="und",
                extracted_text_uri=None,
                parser_name="phase3_synthetic",
                parser_version="0.3.0",
                parse_confidence=None,
                created_at=CLOCK_TIME,
            )
            evidence = EvidenceRef(
                evidence_ref_id=UUID(str(case["evidence_ref_id"])),
                document_id=document.document_id,
                artifact_id=artifact_id,
                locator_kind="full_document",
                locator_value="*",
                locator_schema_version="0.1.0",
                locator_payload=None,
                quote_sha256=content_hash,
            )
            session.add(artifact)
            session.flush()
            session.add(document)
            session.flush()
            session.add(evidence)
        session.commit()


@pytest.fixture
def phase3_session_factory(migrated_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(migrated_engine, expire_on_commit=False)


@pytest.fixture
def seeded_session_factory(
    phase3_session_factory: sessionmaker[Session],
) -> sessionmaker[Session]:
    seed_fixture_documents(phase3_session_factory)
    return phase3_session_factory


@pytest.fixture
def service(
    seeded_session_factory: sessionmaker[Session],
) -> OpportunityResolutionService:
    return OpportunityResolutionService(
        session_factory=seeded_session_factory,
        clock=lambda: CLOCK_TIME,
        id_factory=uuid7,
    )


def happy_path_commands() -> list[ResolutionDocument]:
    commands = commands_by_id()
    return [
        commands[name]
        for name in (
            "primary",
            "duplicate",
            "attachment",
            "position_table",
            "correction",
            "deadline_extension",
            "cancellation",
        )
    ]


def test_notice_attachment_table_correction_extension_and_cancel_share_one_public_id(
    service: OpportunityResolutionService,
) -> None:
    results = [service.resolve(command) for command in happy_path_commands()]

    assert {result.public_id for result in results} == {PUBLIC_ID}
    assert [result.event_type for result in results if result.event_type] == [
        "CREATED",
        "ATTACHMENT_REPLACED",
        "ATTACHMENT_REPLACED",
        "CORRECTED",
        "DEADLINE_CHANGED",
        "CANCELLED",
    ]
    assert results[1].version is None


def test_same_document_replay_is_idempotent(
    service: OpportunityResolutionService,
    seeded_session_factory: sessionmaker[Session],
) -> None:
    command = commands_by_id()["primary"]
    first = service.resolve(command)
    second = service.resolve(command)

    assert second == first
    with seeded_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Opportunity)) == 1
        assert session.scalar(select(func.count()).select_from(DocumentOpportunityLink)) == 1
        assert session.scalar(select(func.count()).select_from(OpportunityVersion)) == 1
        assert session.scalar(select(func.count()).select_from(OpportunityEvent)) == 1


def test_duplicate_announcement_links_without_a_version(
    service: OpportunityResolutionService,
    seeded_session_factory: sessionmaker[Session],
) -> None:
    commands = commands_by_id()
    service.resolve(commands["primary"])
    duplicate = service.resolve(commands["duplicate"])

    assert duplicate.disposition == "LINKED"
    assert duplicate.version is None
    assert duplicate.event_type is None
    with seeded_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(DocumentOpportunityLink)) == 2
        assert session.scalar(select(func.count()).select_from(OpportunityVersion)) == 1
        assert session.scalar(select(func.count()).select_from(OpportunityEvent)) == 1


def test_document_evidence_mismatch_rolls_back(
    service: OpportunityResolutionService,
    seeded_session_factory: sessionmaker[Session],
) -> None:
    commands = commands_by_id()
    invalid = commands["primary"]
    invalid = ResolutionDocument(
        document_id=invalid.document_id,
        source_id=invalid.source_id,
        source_tier=invalid.source_tier,
        evidence_ref_id=commands["duplicate"].evidence_ref_id,
        role=invalid.role,
        canonical_url=invalid.canonical_url,
        external_id=invalid.external_id,
        references_document_ids=invalid.references_document_ids,
        effective_at=invalid.effective_at,
        facts=invalid.facts,
    )

    with pytest.raises(ValueError, match="EvidenceRef.*Document"):
        service.resolve(invalid)

    with seeded_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Opportunity)) == 0
        assert session.scalar(select(func.count()).select_from(DocumentOpportunityLink)) == 0
        assert session.scalar(select(func.count()).select_from(OpportunityResolutionCandidate)) == 0


def seed_conflict_target(session_factory: sessionmaker[Session]) -> None:
    commands = commands_by_id()
    conflict = commands["lower_priority_conflict"]
    with session_factory() as session:
        opportunity = Opportunity(
            opportunity_id=OTHER_OPPORTUNITY_ID,
            public_id="opp_019b0000000070008000000000000021",
            type="YOUTH_DEVELOPMENT_PROGRAM",
            canonical_title="Synthetic other opportunity",
            issuer_name="Synthetic Other Authority",
            jurisdiction=None,
            current_version=None,
            status="OPEN",
            publication_status="INTERNAL",
            created_at=CLOCK_TIME,
            updated_at=CLOCK_TIME,
        )
        alias = OpportunityAlias(
            alias_id=uuid7(),
            opportunity_id=opportunity.opportunity_id,
            alias_type="EXTERNAL_ID",
            alias_value="OTHER-001",
            normalized_value="other-001",
            source_id=SOURCE_TWO_ID,
            source_document_id=conflict.document_id,
            source_evidence_ref_id=conflict.evidence_ref_id,
            created_at=CLOCK_TIME,
        )
        session.add(opportunity)
        session.flush()
        session.add(alias)
        session.commit()


def projection(session_factory: sessionmaker[Session]) -> tuple[object, ...]:
    with session_factory() as session:
        opportunity = session.scalar(select(Opportunity).where(Opportunity.public_id == PUBLIC_ID))
        assert opportunity is not None
        return (
            opportunity.canonical_title,
            opportunity.status,
            opportunity.current_version,
            session.scalar(select(func.count()).select_from(OpportunityVersion)),
            session.scalar(select(func.count()).select_from(OpportunityEvent)),
        )


def test_conflict_and_false_merge_candidates_do_not_change_projection(
    service: OpportunityResolutionService,
    seeded_session_factory: sessionmaker[Session],
) -> None:
    for command in happy_path_commands():
        service.resolve(command)
    seed_conflict_target(seeded_session_factory)
    before = projection(seeded_session_factory)
    commands = commands_by_id()

    conflict = service.resolve(commands["lower_priority_conflict"])
    false_merge = service.resolve(commands["possible_false_merge"])

    assert conflict.disposition == false_merge.disposition == "NEEDS_REVIEW"
    assert conflict.reason_codes == ("STRONG_KEY_CONFLICT",)
    assert false_merge.reason_codes == ("POSSIBLE_DUPLICATE",)
    assert projection(seeded_session_factory) == before
    with seeded_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(OpportunityResolutionCandidate)) == 2


def test_public_id_collision_creates_candidate_without_reusing_id(
    service: OpportunityResolutionService,
    seeded_session_factory: sessionmaker[Session],
) -> None:
    commands = commands_by_id()
    primary = commands["primary"]
    with seeded_session_factory() as session:
        collision = Opportunity(
            opportunity_id=OTHER_OPPORTUNITY_ID,
            public_id=PUBLIC_ID,
            type="YOUTH_DEVELOPMENT_PROGRAM",
            canonical_title="Synthetic collision",
            issuer_name="Synthetic Other Authority",
            jurisdiction=None,
            current_version=None,
            status="OPEN",
            publication_status="INTERNAL",
            created_at=CLOCK_TIME,
            updated_at=CLOCK_TIME,
        )
        alias = OpportunityAlias(
            alias_id=uuid7(),
            opportunity_id=collision.opportunity_id,
            alias_type="EXTERNAL_ID",
            alias_value="DIFFERENT-KEY",
            normalized_value="different-key",
            source_id=SOURCE_ONE_ID,
            source_document_id=primary.document_id,
            source_evidence_ref_id=primary.evidence_ref_id,
            created_at=CLOCK_TIME,
        )
        session.add(collision)
        session.flush()
        session.add(alias)
        session.commit()

    result = service.resolve(primary)

    assert result.disposition == "NEEDS_REVIEW"
    assert result.reason_codes == ("PUBLIC_ID_COLLISION",)
    with seeded_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Opportunity)) == 1
        assert session.scalar(select(func.count()).select_from(OpportunityVersion)) == 0


def test_transaction_failure_preserves_old_versions_and_events(
    service: OpportunityResolutionService,
    seeded_session_factory: sessionmaker[Session],
) -> None:
    commands = commands_by_id()
    for name in ("primary", "attachment"):
        service.resolve(commands[name])
    with seeded_session_factory() as session:
        existing_event_id = session.scalar(
            select(OpportunityEvent.event_id).order_by(OpportunityEvent.to_version)
        )
        assert existing_event_id is not None
    before = projection(seeded_session_factory)
    failing_service = OpportunityResolutionService(
        session_factory=seeded_session_factory,
        clock=lambda: CLOCK_TIME,
        id_factory=lambda: existing_event_id,
    )

    with pytest.raises(Exception):
        failing_service.resolve(commands["correction"])

    assert projection(seeded_session_factory) == before


def test_service_returns_detached_value_objects(
    service: OpportunityResolutionService,
) -> None:
    result = service.resolve(commands_by_id()["primary"])

    assert isinstance(result, ResolutionResult)
    assert result.public_id == PUBLIC_ID
