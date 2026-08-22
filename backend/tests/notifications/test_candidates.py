from datetime import UTC, date, datetime
from uuid import UUID

import pytest

from deepaha.notifications.candidates import recognize_deadline_change
from deepaha.opportunities.models import OpportunityEvent

EVENT_ID = UUID("019b0000-0000-7000-8000-000000000821")
OPPORTUNITY_ID = UUID("019b0000-0000-7000-8000-000000000822")
DOCUMENT_ID = UUID("019b0000-0000-7000-8000-000000000823")
EVIDENCE_ID = UUID("019b0000-0000-7000-8000-000000000824")
NOW = datetime(2026, 8, 22, 13, 0, tzinfo=UTC)


def event_values(
    before: object,
    after: object,
    *,
    event_type: str = "DEADLINE_CHANGED",
    from_version: int | None = 1,
    to_version: int = 2,
    changed_fields: list[str] | None = None,
    changes: list[dict[str, object]] | None = None,
) -> OpportunityEvent:
    default_change = {
        "field_path": "application_window.closes_on",
        "before": before,
        "after": after,
        "evidence_ref_id": str(EVIDENCE_ID),
    }
    return OpportunityEvent(
        event_id=EVENT_ID,
        opportunity_id=OPPORTUNITY_ID,
        from_version=from_version,
        to_version=to_version,
        event_type=event_type,
        changed_fields=(
            ["application_window.closes_on"] if changed_fields is None else changed_fields
        ),
        changes=[default_change] if changes is None else changes,
        source_document_id=DOCUMENT_ID,
        source_evidence_ref_id=EVIDENCE_ID,
        detected_at=NOW,
    )


@pytest.mark.parametrize(
    ("before", "after", "direction"),
    [
        (date(2026, 9, 20), date(2026, 9, 10), "ADVANCED"),
        (date(2026, 9, 20), date(2026, 9, 30), "EXTENDED"),
    ],
)
def test_recognizes_one_exact_deadline_change(
    before: date,
    after: date,
    direction: str,
) -> None:
    recognition = recognize_deadline_change(event_values(before.isoformat(), after.isoformat()))

    assert recognition is not None
    assert recognition.old_closes_on == before
    assert recognition.new_closes_on == after
    assert recognition.direction.value == direction


@pytest.mark.parametrize(
    "event_type",
    [
        "UPDATED",
        "CORRECTED",
        "CANCELLED",
        "REOPENED",
        "ATTACHMENT_REPLACED",
        "CREATED",
    ],
)
def test_rejects_non_deadline_event_types(event_type: str) -> None:
    assert (
        recognize_deadline_change(event_values("2026-09-20", "2026-09-10", event_type=event_type))
        is None
    )


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("2026-09-20", "2026-09-20"),
        (None, "2026-09-10"),
        ("2026-09-20", None),
        ("2026-09-20T00:00:00Z", "2026-09-10"),
        ("not-a-date", "2026-09-10"),
    ],
)
def test_rejects_missing_equal_or_non_iso_dates(before: object, after: object) -> None:
    assert recognize_deadline_change(event_values(before, after)) is None


def test_rejects_two_changed_fields_or_mismatched_changes() -> None:
    second: dict[str, object] = {
        "field_path": "status",
        "before": "OPEN",
        "after": "CANCELLED",
        "evidence_ref_id": str(EVIDENCE_ID),
    }
    deadline = event_values("2026-09-20", "2026-09-10").changes[0]

    assert (
        recognize_deadline_change(
            event_values(
                "2026-09-20",
                "2026-09-10",
                changed_fields=["application_window.closes_on", "status"],
                changes=[deadline, second],
            )
        )
        is None
    )
    assert (
        recognize_deadline_change(
            event_values(
                "2026-09-20",
                "2026-09-10",
                changes=[second],
            )
        )
        is None
    )


def test_rejects_non_consecutive_versions_and_identity_actions() -> None:
    assert (
        recognize_deadline_change(
            event_values("2026-09-20", "2026-09-10", from_version=1, to_version=3)
        )
        is None
    )
    assert recognize_deadline_change(object()) is None
