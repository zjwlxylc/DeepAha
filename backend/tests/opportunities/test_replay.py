from datetime import UTC, datetime
from uuid import UUID

import pytest

from deepaha.contracts.phase3 import (
    OpportunityEventSchemaV03,
    OpportunityEventType,
    OpportunityFieldChangeSchema,
    OpportunityReviewStatus,
    OpportunityVersionSchemaV03,
)
from deepaha.opportunities.versioning import (
    ReplayError,
    VersionPlan,
    plan_version,
    replay_opportunity_state,
)

from .test_versioning import current_state, deadline_extension

NOW = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)
EVENT_ONE_ID = UUID("019b0000-0000-7000-8000-000000000040")
EVENT_TWO_ID = UUID("019b0000-0000-7000-8000-000000000041")


def schemas_from_plan(
    plan: VersionPlan,
    *,
    event_id: UUID,
) -> tuple[OpportunityVersionSchemaV03, OpportunityEventSchemaV03]:
    version = OpportunityVersionSchemaV03(
        opportunity_id=plan.opportunity_id,
        version=plan.version,
        effective_from=plan.effective_from,
        source_document_id=plan.source_document_id,
        source_evidence_ref_id=plan.source_evidence_ref_id,
        snapshot=plan.snapshot,
        field_evidence=plan.field_evidence,
        changes=plan.changes,
        content_sha256=plan.content_sha256,
        review_status=OpportunityReviewStatus.NOT_REQUIRED,
        created_at=plan.effective_from,
    )
    event = OpportunityEventSchemaV03(
        event_id=event_id,
        opportunity_id=plan.opportunity_id,
        from_version=None if plan.version == 1 else plan.version - 1,
        to_version=plan.version,
        event_type=plan.event_type,
        changed_fields=tuple(change.field_path for change in plan.changes),
        changes=plan.changes,
        source_document_id=plan.source_document_id,
        source_evidence_ref_id=plan.source_evidence_ref_id,
        detected_at=plan.effective_from,
    )
    return version, event


def valid_history() -> tuple[
    list[OpportunityVersionSchemaV03],
    list[OpportunityEventSchemaV03],
]:
    initial = current_state()
    initial_plan = VersionPlan(
        opportunity_id=initial.opportunity_id,
        version=1,
        effective_from=NOW,
        source_document_id=UUID("019b0000-0000-7000-8000-000000000010"),
        source_evidence_ref_id=UUID("019b0000-0000-7000-8000-000000000011"),
        snapshot=initial.snapshot,
        field_evidence=initial.field_evidence,
        changes=tuple(
            OpportunityFieldChangeSchema(
                field_path=item.field_path,
                before=None,
                after=initial.snapshot_value(item.field_path),
                evidence_ref_id=item.evidence_ref_id,
            )
            for item in initial.field_evidence
        ),
        content_sha256=initial.content_sha256,
        event_type=OpportunityEventType.CREATED,
    )
    next_plan = plan_version(initial, deadline_extension())
    assert isinstance(next_plan, VersionPlan)
    version_one, event_one = schemas_from_plan(initial_plan, event_id=EVENT_ONE_ID)
    version_two, event_two = schemas_from_plan(next_plan, event_id=EVENT_TWO_ID)
    return [version_one, version_two], [event_one, event_two]


def test_valid_history_replays_deterministically_from_any_input_order() -> None:
    versions, events = valid_history()

    forward = replay_opportunity_state(versions, events)
    reverse = replay_opportunity_state(list(reversed(versions)), list(reversed(events)))

    assert forward == reverse
    assert forward.version == 2
    assert forward.snapshot.application_window.closes_on is not None
    assert forward.snapshot.application_window.closes_on.isoformat() == "2026-09-20"


def test_replay_rejects_a_changed_before_value() -> None:
    versions, events = valid_history()
    original = events[1].changes[0]
    wrong = original.model_copy(update={"before": "2026-09-09"})
    events[1] = events[1].model_copy(update={"changes": (wrong,)})

    with pytest.raises(ReplayError, match="before"):
        replay_opportunity_state(versions, events)


def test_replay_rejects_missing_version() -> None:
    versions, events = valid_history()

    with pytest.raises(ReplayError, match="continuous"):
        replay_opportunity_state([versions[1]], events)


def test_replay_rejects_duplicate_event_for_version() -> None:
    versions, events = valid_history()
    duplicate = events[1].model_copy(update={"event_id": EVENT_ONE_ID})

    with pytest.raises(ReplayError, match="exactly one event"):
        replay_opportunity_state(versions, [*events, duplicate])


def test_replay_rejects_hash_drift() -> None:
    versions, events = valid_history()
    versions[1] = versions[1].model_copy(update={"content_sha256": "f" * 64})

    with pytest.raises(ReplayError, match="hash"):
        replay_opportunity_state(versions, events)


def test_replay_rejects_event_and_version_change_drift() -> None:
    versions, events = valid_history()
    change = events[1].changes[0]
    altered = change.model_copy(update={"after": "2026-09-21"})
    events[1] = events[1].model_copy(
        update={
            "changes": (altered,),
            "changed_fields": (altered.field_path,),
        }
    )

    with pytest.raises(ReplayError, match="version changes"):
        replay_opportunity_state(versions, events)
