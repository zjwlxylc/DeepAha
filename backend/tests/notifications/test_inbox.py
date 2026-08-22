from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from deepaha.notifications.inbox import _owner_inbox_statement
from deepaha.notifications.schemas import ReminderInboxPage

USER_ID = UUID("019b0000-0000-7000-8000-000000000501")


def test_owner_query_is_bounded_ordered_and_filters_in_sql() -> None:
    statement = _owner_inbox_statement(USER_ID, limit=50)
    compiled = statement.compile(dialect=postgresql.dialect())  # type: ignore[no-untyped-call]
    sql = str(compiled)

    assert "test_inbox_entries.user_id =" in sql
    assert USER_ID in compiled.params.values()
    assert "ORDER BY test_inbox_entries.delivered_at DESC" in sql
    assert "test_inbox_entries.inbox_entry_id DESC" in sql
    assert 50 in compiled.params.values()


@pytest.mark.parametrize("limit", [0, 51])
def test_owner_query_rejects_unbounded_limits(limit: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 50"):
        _owner_inbox_statement(USER_ID, limit=limit)


def test_inbox_page_contains_no_tracking_or_private_profile_fields() -> None:
    page = ReminderInboxPage.model_validate(
        {
            "items": [
                {
                    "inbox_entry_id": "019b0000-0000-7000-8000-000000000821",
                    "reminder_id": "019b0000-0000-7000-8000-000000000822",
                    "user_id": str(USER_ID),
                    "opportunity_id": "019b0000-0000-7000-8000-000000000823",
                    "opportunity_public_id": "opp_019b0000000070008000000000000823",
                    "opportunity_title": "合成机会",
                    "event_id": "019b0000-0000-7000-8000-000000000824",
                    "from_version": 1,
                    "to_version": 2,
                    "old_closes_on": date(2026, 9, 20),
                    "new_closes_on": date(2026, 9, 30),
                    "direction": "EXTENDED",
                    "previous_evidence_ref_id": "019b0000-0000-7000-8000-000000000825",
                    "current_evidence_ref_id": "019b0000-0000-7000-8000-000000000826",
                    "previous_official_url": "https://official.example.test/v1",
                    "current_official_url": "https://official.example.test/v2",
                    "personal_detail_path": (
                        "/me/opportunities/opp_019b0000000070008000000000000823"
                    ),
                    "detected_at": datetime(2026, 8, 21, tzinfo=UTC),
                    "delivered_at": datetime(2026, 8, 22, tzinfo=UTC),
                    "target": "TEST_INBOX",
                    "contract_version": "0.7.0",
                }
            ],
            "count": 1,
        }
    )

    payload = page.model_dump(mode="json")
    serialized = str(payload).lower()
    for forbidden in ("profile", "consent", "opened", "read", "click", "tracking"):
        assert forbidden not in serialized

    with pytest.raises(ValidationError):
        ReminderInboxPage.model_validate({**payload, "unread_count": 1})
    with pytest.raises(ValidationError, match="count must match"):
        ReminderInboxPage.model_validate({"items": payload["items"], "count": 0})
