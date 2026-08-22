from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.contracts.phase3 import OpportunityDocumentRole
from deepaha.notifications.candidates import DeadlineReminderCandidateService
from deepaha.notifications.models import NotificationOutboxModel
from deepaha.opportunities.models import Opportunity, OpportunityEvent
from deepaha.opportunities.service import OpportunityResolutionService
from deepaha.opportunities.types import OpportunityPatch
from deepaha.personal.auth import token_digest
from deepaha.personal.models import PersonalAuthSessionModel
from deepaha.public_catalog.models import PublicCatalogEntry
from tests.integration.test_opportunity_resolution_service import commands_by_id
from tests.integration.test_phase8_candidate_transaction import (
    PRE_EVENT_TIME,
    USER_IDS,
    _prepare_pre_deadline_service,
    _seed_audience,
)

FIXTURE_MARKER = "SYNTHETIC_REMINDER_DELIVERY_ONLY"
FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "reminders"
FIXTURE_PATH = FIXTURE_ROOT / "phase8-deadline-reminder.json"
MANIFEST_PATH = FIXTURE_ROOT / "phase8-deadline-reminder.manifest.json"
PHASE8_BEARER_TOKEN = "phase8-synthetic-reminder-owner-token"
PHASE8_WEB_ROUTE = "/me/reminders"


class Phase8FixtureModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Phase8OpportunityFixture(Phase8FixtureModel):
    public_id: str
    from_version: int
    to_version: int
    old_closes_on: date
    new_closes_on: date
    previous_evidence_ref_id: UUID
    current_evidence_ref_id: UUID


class Phase8EventFixture(Phase8FixtureModel):
    event_type: str
    changed_fields: tuple[str, ...]
    expected_candidate_count: int


class Phase8NonQualifyingEventFixture(Phase8EventFixture):
    case: str


class Phase8AudienceFixture(Phase8FixtureModel):
    role: str
    user_id: UUID
    expected_reminder_count: int
    reason: str


class Phase8EvidenceBoundary(Phase8FixtureModel):
    real_participants: Literal[0]
    human_track: Literal["NOT_STARTED"]
    release_qualification: Literal["NOT_STARTED"]
    release_decision: Literal["HOLD_MISSING_HUMAN_EVIDENCE"]


class Phase8DeadlineReminderFixture(Phase8FixtureModel):
    schema_version: Literal["phase8-deadline-reminder-fixture-v1"]
    marker: Literal["SYNTHETIC_REMINDER_DELIVERY_ONLY"]
    synthetic: Literal[True]
    contains_personal_data: Literal[False]
    business_truth: Literal[False]
    release_qualification_eligible: Literal[False]
    license: Literal["CC0-1.0 synthetic fixture"]
    scenario_clock: datetime
    opportunity: Phase8OpportunityFixture
    qualifying_event: Phase8EventFixture
    non_qualifying_events: tuple[Phase8NonQualifyingEventFixture, ...]
    audiences: tuple[Phase8AudienceFixture, ...]
    expected_engineering_counts: dict[str, int]
    evidence_boundary: Phase8EvidenceBoundary


class Phase8DeadlineReminderManifest(Phase8FixtureModel):
    manifest_schema_version: Literal["phase8-deadline-reminder-manifest-v1"]
    fixture: Literal["phase8-deadline-reminder.json"]
    sha256: str
    marker: Literal["SYNTHETIC_REMINDER_DELIVERY_ONLY"]
    license: Literal["CC0-1.0 synthetic fixture"]
    synthetic: Literal[True]
    contains_personal_data: Literal[False]
    business_truth: Literal[False]
    release_qualification_eligible: Literal[False]
    scenario_clock: datetime
    opportunity_public_id: str
    from_version: int
    to_version: int
    old_closes_on: date
    new_closes_on: date
    previous_evidence_ref_id: UUID
    current_evidence_ref_id: UUID
    audience_expected_reminders: dict[str, int]
    expected_engineering_counts: dict[str, int]
    human_participant_count: Literal[0]
    human_track: Literal["NOT_STARTED"]
    release_qualification: Literal["NOT_STARTED"]
    release_decision: Literal["HOLD_MISSING_HUMAN_EVIDENCE"]
    purpose: str


@dataclass(frozen=True, slots=True)
class Phase8EngineeringReport:
    audiences: int
    counterexamples: int
    candidates: int
    waiting_before_governance: int
    attempts_before_governance: int
    inbox_before_governance: int
    promoted: int
    claimed: int
    delivered: int
    delivery_attempts: int
    inbox_entries: int
    replay_mismatches: int


@dataclass(frozen=True, slots=True)
class Phase8PrechangeContext:
    service: OpportunityResolutionService
    opportunity_id: UUID
    user_id: UUID
    bearer_token: str


@dataclass(frozen=True, slots=True)
class Phase8VerticalContext:
    opportunity_id: UUID
    event_id: UUID
    reminder_id: UUID
    user_id: UUID
    bearer_token: str
    from_version: int
    to_version: int


def validate_phase8_deadline_fixture_bytes(
    fixture_bytes: bytes,
    manifest_bytes: bytes,
) -> tuple[Phase8DeadlineReminderFixture, Phase8DeadlineReminderManifest]:
    manifest = Phase8DeadlineReminderManifest.model_validate_json(manifest_bytes)
    if sha256(fixture_bytes).hexdigest() != manifest.sha256:
        raise ValueError("Phase 8 fixture hash does not match its manifest")
    fixture = Phase8DeadlineReminderFixture.model_validate_json(fixture_bytes)
    if fixture.marker != manifest.marker or fixture.license != manifest.license:
        raise ValueError("Phase 8 fixture provenance does not match its manifest")
    if (
        fixture.opportunity.public_id != manifest.opportunity_public_id
        or fixture.opportunity.from_version != manifest.from_version
        or fixture.opportunity.to_version != manifest.to_version
        or fixture.opportunity.previous_evidence_ref_id != manifest.previous_evidence_ref_id
        or fixture.opportunity.current_evidence_ref_id != manifest.current_evidence_ref_id
    ):
        raise ValueError("Phase 8 fixture binding does not match its manifest")
    return fixture, manifest


def load_phase8_deadline_fixture() -> tuple[
    Phase8DeadlineReminderFixture,
    Phase8DeadlineReminderManifest,
]:
    return validate_phase8_deadline_fixture_bytes(
        FIXTURE_PATH.read_bytes(),
        MANIFEST_PATH.read_bytes(),
    )


def prepare_phase8_prechange(
    factory: sessionmaker[Session],
    *,
    candidate_service: DeadlineReminderCandidateService | None = None,
) -> Phase8PrechangeContext:
    fixture, _manifest = load_phase8_deadline_fixture()
    service, opportunity = _prepare_pre_deadline_service(
        factory,
        candidate_service=candidate_service,
    )
    public_fields_source = commands_by_id()["duplicate"]
    service.resolve(
        replace(
            public_fields_source,
            role=OpportunityDocumentRole.CORRECTION,
            effective_at=datetime(2026, 8, 22, 9, 4, 45, tzinfo=UTC),
            facts=OpportunityPatch(
                published_at=datetime(2026, 8, 22, 9, tzinfo=UTC),
                application_url="https://example.gov/synthetic/apply",
            ),
        )
    )
    with factory() as session:
        current = session.get(Opportunity, opportunity.opportunity_id)
        if current is None:
            raise ValueError("Phase 8 prechange opportunity is unavailable")
        session.expunge(current)
    opportunity = current
    if (
        opportunity.public_id != fixture.opportunity.public_id
        or opportunity.current_version != fixture.opportunity.from_version
    ):
        raise ValueError("Phase 8 prechange opportunity does not match the fixed fixture")
    _seed_audience(factory, opportunity)
    owner_id = USER_IDS["eligible"]
    with factory() as session:
        persisted = session.get(Opportunity, opportunity.opportunity_id)
        if persisted is None:
            raise ValueError("Phase 8 opportunity is unavailable")
        persisted.publication_status = "PUBLISHED"
        session.add(
            PublicCatalogEntry(
                opportunity_id=opportunity.opportunity_id,
                opportunity_version=fixture.opportunity.from_version,
                collection_kind="LICENSE_SAFE_FIXTURE",
                dataset_id="phase8-deadline-reminder-synthetic",
                dataset_version="v1",
                content_use_basis="OPEN_LICENSE",
                reviewed_by="phase8-fixture-governance",
                approved_at=PRE_EVENT_TIME,
                last_verified_at=fixture.scenario_clock,
            )
        )
        session.add(
            PersonalAuthSessionModel(
                token_sha256=token_digest(PHASE8_BEARER_TOKEN),
                user_id=owner_id,
                expires_at=datetime(2099, 1, 1, tzinfo=fixture.scenario_clock.tzinfo),
                revoked_at=None,
                created_at=PRE_EVENT_TIME,
            )
        )
        session.commit()
    return Phase8PrechangeContext(
        service=service,
        opportunity_id=opportunity.opportunity_id,
        user_id=owner_id,
        bearer_token=PHASE8_BEARER_TOKEN,
    )


def resolve_phase8_change(
    factory: sessionmaker[Session],
    prechange: Phase8PrechangeContext,
) -> Phase8VerticalContext:
    fixture, _manifest = load_phase8_deadline_fixture()
    result = prechange.service.resolve(commands_by_id()["deadline_extension"])
    if result.version != fixture.opportunity.to_version or result.event_type != "DEADLINE_CHANGED":
        raise ValueError("Phase 8 resolved change does not match the fixed fixture")
    with factory() as session:
        event = session.scalar(
            select(OpportunityEvent).where(
                OpportunityEvent.opportunity_id == prechange.opportunity_id,
                OpportunityEvent.to_version == fixture.opportunity.to_version,
            )
        )
        outbox = session.scalar(select(NotificationOutboxModel))
        if event is None or outbox is None:
            raise ValueError("Phase 8 reminder trace is incomplete")
        if (
            outbox.user_id != prechange.user_id
            or outbox.from_version != fixture.opportunity.from_version
            or outbox.to_version != fixture.opportunity.to_version
            or outbox.previous_evidence_ref_id != fixture.opportunity.previous_evidence_ref_id
            or outbox.current_evidence_ref_id != fixture.opportunity.current_evidence_ref_id
        ):
            raise ValueError("Phase 8 reminder trace does not match the fixed fixture")
        return Phase8VerticalContext(
            opportunity_id=prechange.opportunity_id,
            event_id=event.event_id,
            reminder_id=outbox.reminder_id,
            user_id=prechange.user_id,
            bearer_token=prechange.bearer_token,
            from_version=outbox.from_version,
            to_version=outbox.to_version,
        )


def govern_phase8_fixture_version(
    factory: sessionmaker[Session],
    context: Phase8VerticalContext,
) -> None:
    fixture, _manifest = load_phase8_deadline_fixture()
    with factory() as session:
        entry = session.get(PublicCatalogEntry, context.opportunity_id)
        if entry is None:
            raise ValueError("Phase 8 fixture catalog entry is unavailable")
        entry.opportunity_version = context.to_version
        entry.last_verified_at = fixture.scenario_clock
        session.commit()


__all__ = [
    "FIXTURE_MARKER",
    "PHASE8_BEARER_TOKEN",
    "PHASE8_WEB_ROUTE",
    "Phase8EngineeringReport",
    "Phase8PrechangeContext",
    "Phase8VerticalContext",
    "govern_phase8_fixture_version",
    "load_phase8_deadline_fixture",
    "prepare_phase8_prechange",
    "resolve_phase8_change",
    "validate_phase8_deadline_fixture_bytes",
]
