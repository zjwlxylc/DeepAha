from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import JsonValue

from deepaha.contracts.phase1 import OpportunityStatus, SourceTier
from deepaha.contracts.phase2 import OpportunityTypeV02
from deepaha.contracts.phase3 import (
    ApplicationWindowSchema,
    OpportunityDocumentRole,
    OpportunityEventType,
    OpportunityFieldChangeSchema,
    OpportunityFieldEvidenceSchema,
    OpportunitySnapshotSchema,
    SnapshotField,
)
from deepaha.opportunities.types import OpportunityPatch
from deepaha.opportunities.versioning import (
    VersionCommand,
    VersionConflict,
    VersionPlan,
    VersionState,
    canonical_content_sha256,
    classify_event_type,
    derive_precedence,
    plan_version,
)

NOW = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)
OPPORTUNITY_ID = UUID("019b0000-0000-7000-8000-000000000020")
DOCUMENT_ID = UUID("019b0000-0000-7000-8000-000000000010")
EVIDENCE_REF_ID = UUID("019b0000-0000-7000-8000-000000000011")


def current_snapshot(**changes: object) -> OpportunitySnapshotSchema:
    values: dict[str, object] = {
        "canonical_title": "Synthetic youth opportunity",
        "type": OpportunityTypeV02.YOUTH_DEVELOPMENT_PROGRAM,
        "issuer_name": "Synthetic Example Authority",
        "jurisdiction": "Synthetic Region",
        "status": OpportunityStatus.OPEN,
        "published_at": NOW,
        "application_window": ApplicationWindowSchema(
            opens_on=date(2026, 8, 22),
            closes_on=date(2026, 9, 10),
            timezone="Asia/Shanghai",
        ),
        "application_url": "https://example.gov/apply",
        "attachment_urls": ("https://example.gov/files/notice.pdf",),
        "locations": ("Synthetic Location",),
    }
    values.update(changes)
    return OpportunitySnapshotSchema.model_validate(values)


def evidence(
    field_path: SnapshotField,
    *,
    precedence: int = 400,
    effective_at: datetime = NOW,
    evidence_ref_id: UUID = EVIDENCE_REF_ID,
) -> OpportunityFieldEvidenceSchema:
    return OpportunityFieldEvidenceSchema(
        field_path=field_path,
        precedence=precedence,
        evidence_ref_id=evidence_ref_id,
        effective_at=effective_at,
    )


def current_state() -> VersionState:
    snapshot = current_snapshot()
    field_evidence = tuple(
        evidence(field_path)
        for field_path in (
            SnapshotField.CANONICAL_TITLE,
            SnapshotField.TYPE,
            SnapshotField.ISSUER_NAME,
            SnapshotField.JURISDICTION,
            SnapshotField.STATUS,
            SnapshotField.PUBLISHED_AT,
            SnapshotField.APPLICATION_WINDOW_OPENS_ON,
            SnapshotField.APPLICATION_WINDOW_CLOSES_ON,
            SnapshotField.APPLICATION_WINDOW_TIMEZONE,
            SnapshotField.APPLICATION_URL,
            SnapshotField.ATTACHMENT_URLS,
            SnapshotField.LOCATIONS,
        )
    )
    return VersionState(
        opportunity_id=OPPORTUNITY_ID,
        version=1,
        snapshot=snapshot,
        field_evidence=field_evidence,
        content_sha256=canonical_content_sha256(snapshot, field_evidence),
    )


def command(
    *,
    role: OpportunityDocumentRole,
    facts: OpportunityPatch,
    source_tier: SourceTier = SourceTier.OFFICIAL_PRIMARY,
    effective_at: datetime = NOW + timedelta(hours=1),
    document_id: UUID = DOCUMENT_ID,
    evidence_ref_id: UUID = EVIDENCE_REF_ID,
) -> VersionCommand:
    return VersionCommand(
        opportunity_id=OPPORTUNITY_ID,
        source_document_id=document_id,
        source_evidence_ref_id=evidence_ref_id,
        source_tier=source_tier,
        role=role,
        effective_at=effective_at,
        facts=facts,
    )


def deadline_extension(**changes: object) -> VersionCommand:
    values: dict[str, object] = {
        "role": OpportunityDocumentRole.DEADLINE_EXTENSION,
        "facts": OpportunityPatch(
            application_window=ApplicationWindowSchema(
                opens_on=date(2026, 8, 22),
                closes_on=date(2026, 9, 20),
                timezone="Asia/Shanghai",
            )
        ),
    }
    values.update(changes)
    return command(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("tier", "role", "expected"),
    [
        (SourceTier.OFFICIAL_PRIMARY, OpportunityDocumentRole.CORRECTION, 600),
        (SourceTier.OFFICIAL_PRIMARY, OpportunityDocumentRole.DEADLINE_EXTENSION, 600),
        (SourceTier.OFFICIAL_PRIMARY, OpportunityDocumentRole.CANCELLATION, 600),
        (SourceTier.OFFICIAL_PRIMARY, OpportunityDocumentRole.POSITION_TABLE, 500),
        (SourceTier.OFFICIAL_PRIMARY, OpportunityDocumentRole.ATTACHMENT, 500),
        (SourceTier.OFFICIAL_PRIMARY, OpportunityDocumentRole.PRIMARY_NOTICE, 400),
        (SourceTier.OFFICIAL_PRIMARY, OpportunityDocumentRole.RESULT, 400),
        (SourceTier.OFFICIAL_PRIMARY, OpportunityDocumentRole.OFFICIAL_GUIDANCE, 300),
        (SourceTier.OFFICIAL_AGGREGATOR, OpportunityDocumentRole.PRIMARY_NOTICE, 250),
    ],
)
def test_precedence_is_derived_only_from_tier_and_role(
    tier: SourceTier,
    role: OpportunityDocumentRole,
    expected: int,
) -> None:
    assert derive_precedence(tier, role) == expected


@pytest.mark.parametrize("tier", [SourceTier.TRUSTED_SECONDARY, SourceTier.COMMUNITY_SIGNAL])
def test_untrusted_source_has_no_formal_precedence(tier: SourceTier) -> None:
    assert derive_precedence(tier, OpportunityDocumentRole.PRIMARY_NOTICE) is None


def test_latest_official_deadline_extension_wins_and_emits_deadline_event() -> None:
    plan = plan_version(current_state(), deadline_extension())

    assert isinstance(plan, VersionPlan)
    assert plan.version == 2
    assert plan.event_type is OpportunityEventType.DEADLINE_CHANGED
    assert [(change.field_path.value, change.before, change.after) for change in plan.changes] == [
        ("application_window.closes_on", "2026-09-10", "2026-09-20")
    ]


def test_lower_priority_conflict_never_partially_applies_patch() -> None:
    conflict = plan_version(
        current_state(),
        command(
            source_tier=SourceTier.OFFICIAL_AGGREGATOR,
            role=OpportunityDocumentRole.PRIMARY_NOTICE,
            facts=OpportunityPatch(
                canonical_title="Lower priority title",
                locations=("Would otherwise change",),
            ),
        ),
    )

    assert conflict == VersionConflict(reason_codes=("NON_AUTHORITATIVE_VERSION_SOURCE",))


def test_lower_official_precedence_conflict_never_partially_applies_patch() -> None:
    state = current_state()
    title_evidence = tuple(
        item.model_copy(update={"precedence": 600})
        if item.field_path is SnapshotField.CANONICAL_TITLE
        else item
        for item in state.field_evidence
    )
    state = replace(
        state,
        field_evidence=title_evidence,
        content_sha256=canonical_content_sha256(state.snapshot, title_evidence),
    )

    conflict = plan_version(
        state,
        command(
            role=OpportunityDocumentRole.PRIMARY_NOTICE,
            facts=OpportunityPatch(
                canonical_title="Lower precedence title",
                locations=("Must not partly apply",),
            ),
        ),
    )

    assert conflict == VersionConflict(reason_codes=("LOWER_PRIORITY_CONFLICT",))


def test_same_value_is_a_semantic_noop() -> None:
    result = plan_version(
        current_state(),
        command(
            role=OpportunityDocumentRole.CORRECTION,
            facts=OpportunityPatch(canonical_title="Synthetic youth opportunity"),
        ),
    )

    assert result is None


def test_same_precedence_newer_evidence_wins() -> None:
    state = current_state()
    title_evidence = tuple(
        item.model_copy(update={"precedence": 600})
        if item.field_path is SnapshotField.CANONICAL_TITLE
        else item
        for item in state.field_evidence
    )
    state = replace(
        state,
        field_evidence=title_evidence,
        content_sha256=canonical_content_sha256(state.snapshot, title_evidence),
    )

    result = plan_version(
        state,
        command(
            role=OpportunityDocumentRole.CORRECTION,
            facts=OpportunityPatch(canonical_title="Newer corrected title"),
        ),
    )

    assert isinstance(result, VersionPlan)
    assert result.changes[0].after == "Newer corrected title"


def test_same_precedence_same_time_conflict_is_all_or_nothing() -> None:
    state = current_state()
    title_evidence = tuple(
        item.model_copy(update={"precedence": 600})
        if item.field_path is SnapshotField.CANONICAL_TITLE
        else item
        for item in state.field_evidence
    )
    state = replace(
        state,
        field_evidence=title_evidence,
        content_sha256=canonical_content_sha256(state.snapshot, title_evidence),
    )

    result = plan_version(
        state,
        command(
            role=OpportunityDocumentRole.CORRECTION,
            effective_at=NOW,
            facts=OpportunityPatch(
                canonical_title="Conflicting title",
                locations=("Must not partly apply",),
            ),
        ),
    )

    assert result == VersionConflict(reason_codes=("EVIDENCE_CONFLICT",))


@pytest.mark.parametrize(
    ("role", "before", "after", "field", "expected"),
    [
        (
            OpportunityDocumentRole.CANCELLATION,
            "OPEN",
            "CANCELLED",
            SnapshotField.STATUS,
            OpportunityEventType.CANCELLED,
        ),
        (
            OpportunityDocumentRole.CORRECTION,
            "CANCELLED",
            "OPEN",
            SnapshotField.STATUS,
            OpportunityEventType.REOPENED,
        ),
        (
            OpportunityDocumentRole.DEADLINE_EXTENSION,
            "2026-09-10",
            "2026-09-20",
            SnapshotField.APPLICATION_WINDOW_CLOSES_ON,
            OpportunityEventType.DEADLINE_CHANGED,
        ),
        (
            OpportunityDocumentRole.ATTACHMENT,
            [],
            ["https://example.gov/a.pdf"],
            SnapshotField.ATTACHMENT_URLS,
            OpportunityEventType.ATTACHMENT_REPLACED,
        ),
        (
            OpportunityDocumentRole.CORRECTION,
            "old",
            "new",
            SnapshotField.CANONICAL_TITLE,
            OpportunityEventType.CORRECTED,
        ),
        (
            OpportunityDocumentRole.PRIMARY_NOTICE,
            "old",
            "new",
            SnapshotField.CANONICAL_TITLE,
            OpportunityEventType.UPDATED,
        ),
    ],
)
def test_event_classification_priority(
    role: OpportunityDocumentRole,
    before: JsonValue,
    after: JsonValue,
    field: SnapshotField,
    expected: OpportunityEventType,
) -> None:
    changes = (
        OpportunityFieldChangeSchema(
            field_path=field,
            before=before,
            after=after,
            evidence_ref_id=EVIDENCE_REF_ID,
        ),
    )

    assert classify_event_type(2, role, changes) is expected


def test_first_version_builds_full_snapshot_and_created_event() -> None:
    result = plan_version(
        None,
        command(
            role=OpportunityDocumentRole.PRIMARY_NOTICE,
            effective_at=NOW,
            facts=OpportunityPatch(
                canonical_title="Synthetic youth opportunity",
                type=OpportunityTypeV02.YOUTH_DEVELOPMENT_PROGRAM,
                issuer_name="Synthetic Example Authority",
                status=OpportunityStatus.OPEN,
            ),
        ),
    )

    assert isinstance(result, VersionPlan)
    assert result.version == 1
    assert result.event_type is OpportunityEventType.CREATED
    assert result.snapshot.application_window.closes_on is None
    assert [change.field_path for change in result.changes] == [
        SnapshotField.CANONICAL_TITLE,
        SnapshotField.TYPE,
        SnapshotField.ISSUER_NAME,
        SnapshotField.STATUS,
    ]


def test_canonical_content_hash_is_sorted_normalized_and_literal() -> None:
    snapshot = current_snapshot(
        canonical_title="Cafe\u0301 opportunity",
        attachment_urls=(
            "https://example.gov/z.pdf",
            "https://example.gov/a.pdf",
        ),
        locations=("Z", "A"),
    )
    field_evidence = (
        evidence(SnapshotField.STATUS),
        evidence(SnapshotField.CANONICAL_TITLE),
    )

    first = canonical_content_sha256(snapshot, field_evidence)
    second = canonical_content_sha256(
        OpportunitySnapshotSchema.model_validate(
            snapshot.model_dump(mode="python")
            | {
                "canonical_title": "Café opportunity",
                "attachment_urls": tuple(reversed(snapshot.attachment_urls)),
                "locations": tuple(reversed(snapshot.locations)),
            }
        ),
        tuple(reversed(field_evidence)),
    )

    assert first == second
    assert first == "dec75fca05e9888b0a05902258fa0c8466d8873bf065cc4ae2ba82ffec20c6fc"
