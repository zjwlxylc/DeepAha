import json
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from deepaha.contracts import (
    DeadlineChangeReminderIntentSchemaV07 as ExportedDeadlineChangeReminderIntentSchemaV07,
)
from deepaha.contracts.export import (
    PHASE8_SCHEMAS,
    render_phase1_schemas,
    render_phase2_schemas,
    render_phase3_schemas,
    render_phase4_schemas,
    render_phase6_schemas,
    render_phase7_schemas,
    render_phase8_schemas,
    write_phase8_schemas,
)
from deepaha.contracts.phase8 import (
    DeadlineChangeReminderIntentSchemaV07,
    NotificationDeliveryAttemptSchemaV07,
    ReminderPreferenceSnapshotSchemaV07,
)
from deepaha.contracts.phase8 import (
    TestInboxEntrySchemaV07 as InboxEntrySchemaV07,
)

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
REPOSITORY_ROOT = Path(__file__).parents[3]
V07_EXAMPLE_PATH = REPOSITORY_ROOT / "contracts" / "examples" / "v0.7.0" / "phase-8-example.json"


def entity(serial: int) -> UUID:
    return UUID(f"019b0000-0000-7000-8000-{serial:012d}")


def preference_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "preference_snapshot_id": entity(701),
        "preference_id": entity(702),
        "user_id": entity(703),
        "version": 1,
        "predecessor_snapshot_id": None,
        "reminder_kind": "DEADLINE_CHANGED",
        "enabled": True,
        "cadence": "AS_SOON_AS_GOVERNED",
        "target": "TEST_INBOX",
        "actor_user_id": entity(703),
        "preference_policy_version": "phase8-deadline-reminder-v1",
        "contract_version": "0.7.0",
        "created_at": NOW,
    }
    values.update(changes)
    return values


def intent_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "reminder_id": entity(704),
        "user_id": entity(703),
        "opportunity_id": entity(705),
        "event_id": entity(706),
        "from_version": 1,
        "to_version": 2,
        "old_closes_on": date(2026, 9, 20),
        "new_closes_on": date(2026, 9, 10),
        "direction": "ADVANCED",
        "previous_evidence_ref_id": entity(707),
        "current_evidence_ref_id": entity(708),
        "action_snapshot_id": entity(709),
        "preference_snapshot_id": entity(701),
        "user_state_snapshot_id": entity(710),
        "consent_version": "phase6-consent-v1",
        "detected_at": NOW,
        "created_at": NOW,
        "reminder_kind": "DEADLINE_CHANGED",
        "cadence": "AS_SOON_AS_GOVERNED",
        "target": "TEST_INBOX",
        "contract_version": "0.7.0",
    }
    values.update(changes)
    return values


def attempt_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "delivery_attempt_id": entity(711),
        "reminder_id": entity(704),
        "attempt_number": 1,
        "lease_token": entity(712),
        "adapter": "POSTGRES_TEST_INBOX",
        "outcome": "SUCCEEDED",
        "error_code": None,
        "started_at": NOW,
        "completed_at": NOW,
        "contract_version": "0.7.0",
    }
    values.update(changes)
    return values


def inbox_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "inbox_entry_id": entity(713),
        "reminder_id": entity(704),
        "user_id": entity(703),
        "opportunity_id": entity(705),
        "opportunity_public_id": "opp_00000000000000000000000000000705",
        "opportunity_title": "合成浙江青年项目",
        "event_id": entity(706),
        "from_version": 1,
        "to_version": 2,
        "old_closes_on": date(2026, 9, 20),
        "new_closes_on": date(2026, 9, 10),
        "direction": "ADVANCED",
        "previous_evidence_ref_id": entity(707),
        "current_evidence_ref_id": entity(708),
        "previous_official_url": "https://example.gov.cn/notices/phase8-v1",
        "current_official_url": "https://example.gov.cn/notices/phase8-v2",
        "personal_detail_path": "/me/opportunities/opp_00000000000000000000000000000705",
        "detected_at": NOW,
        "delivered_at": NOW,
        "target": "TEST_INBOX",
        "contract_version": "0.7.0",
    }
    values.update(changes)
    return values


def test_preference_is_frozen_and_rejects_unapproved_delivery_options() -> None:
    preference = ReminderPreferenceSnapshotSchemaV07.model_validate(preference_values())

    assert preference.enabled is True
    with pytest.raises(ValidationError, match="frozen"):
        preference.enabled = False
    with pytest.raises(ValidationError):
        ReminderPreferenceSnapshotSchemaV07.model_validate(
            preference_values(target="WECHAT_MINI_PROGRAM")
        )
    with pytest.raises(ValidationError):
        ReminderPreferenceSnapshotSchemaV07.model_validate(
            preference_values(cadence="DAILY_DIGEST")
        )
    with pytest.raises(ValidationError):
        ReminderPreferenceSnapshotSchemaV07.model_validate(
            preference_values(predecessor_snapshot_id=entity(799), version=1)
        )


@pytest.mark.parametrize(
    ("old_closes_on", "new_closes_on", "direction"),
    [
        (date(2026, 9, 20), date(2026, 9, 10), "ADVANCED"),
        (date(2026, 9, 20), date(2026, 9, 30), "EXTENDED"),
    ],
)
def test_intent_accepts_only_consistent_consecutive_deadline_changes(
    old_closes_on: date,
    new_closes_on: date,
    direction: str,
) -> None:
    intent = DeadlineChangeReminderIntentSchemaV07.model_validate(
        intent_values(
            old_closes_on=old_closes_on,
            new_closes_on=new_closes_on,
            direction=direction,
        )
    )

    assert intent.direction.value == direction
    assert intent.user_state_snapshot_id == entity(710)


@pytest.mark.parametrize(
    "changes",
    [
        {"old_closes_on": None},
        {"new_closes_on": None},
        {"new_closes_on": date(2026, 9, 20)},
        {"new_closes_on": date(2026, 9, 30), "direction": "ADVANCED"},
        {"to_version": 3},
        {"target": "EMAIL"},
    ],
)
def test_intent_rejects_ambiguous_or_inconsistent_change(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        DeadlineChangeReminderIntentSchemaV07.model_validate(intent_values(**changes))


def test_delivery_attempt_requires_bounded_failure_code_and_ordered_time() -> None:
    NotificationDeliveryAttemptSchemaV07.model_validate(attempt_values())
    NotificationDeliveryAttemptSchemaV07.model_validate(
        attempt_values(outcome="TRANSIENT_FAILURE", error_code="TEST_ADAPTER_TIMEOUT")
    )

    with pytest.raises(ValidationError):
        NotificationDeliveryAttemptSchemaV07.model_validate(
            attempt_values(outcome="PERMANENT_FAILURE", error_code=None)
        )
    with pytest.raises(ValidationError):
        NotificationDeliveryAttemptSchemaV07.model_validate(
            attempt_values(outcome="SUCCEEDED", error_code="UNEXPECTED")
        )
    with pytest.raises(ValidationError):
        NotificationDeliveryAttemptSchemaV07.model_validate(
            attempt_values(completed_at=datetime(2026, 8, 22, 11, 59, tzinfo=UTC))
        )


def test_test_inbox_has_no_behavior_tracking_fields() -> None:
    entry = InboxEntrySchemaV07.model_validate(inbox_values())

    assert entry.target.value == "TEST_INBOX"
    assert {
        "opened_at",
        "read_at",
        "clicked_at",
        "complaint_at",
        "retention_rate",
    }.isdisjoint(InboxEntrySchemaV07.model_fields)
    with pytest.raises(ValidationError):
        InboxEntrySchemaV07.model_validate(inbox_values(opened_at=NOW))


def committed_schema_bytes(version: str) -> dict[str, bytes]:
    directory = REPOSITORY_ROOT / "contracts" / "schemas" / version
    return {path.name: path.read_bytes() for path in directory.glob("*.schema.json")}


def test_phase8_export_preserves_prior_schema_bytes_and_writes_complete_v07(
    tmp_path: Path,
) -> None:
    assert render_phase1_schemas() == committed_schema_bytes("v0.1.0")
    assert render_phase2_schemas() == committed_schema_bytes("v0.2.0")
    assert render_phase3_schemas() == committed_schema_bytes("v0.3.0")
    assert render_phase4_schemas() == committed_schema_bytes("v0.4.0")
    assert render_phase6_schemas() == committed_schema_bytes("v0.5.0")
    assert render_phase7_schemas() == committed_schema_bytes("v0.6.0")

    rendered = render_phase8_schemas()
    assert set(rendered) == set(PHASE8_SCHEMAS)
    assert rendered == committed_schema_bytes("v0.7.0")
    assert len(rendered) == 4
    written = write_phase8_schemas(tmp_path)
    assert {name: path.read_bytes() for name, path in written.items()} == rendered


def test_phase8_contract_is_available_from_public_contract_package() -> None:
    assert ExportedDeadlineChangeReminderIntentSchemaV07 is DeadlineChangeReminderIntentSchemaV07


def test_phase8_example_is_synthetic_and_engineering_only() -> None:
    example = json.loads(V07_EXAMPLE_PATH.read_text(encoding="utf-8"))

    assert example["synthetic"] is True
    assert example["contains_personal_data"] is False
    assert example["business_truth"] is False
    assert example["release_qualification_eligible"] is False
    assert example["evidence_class"] == "SYNTHETIC_REMINDER_DELIVERY_ONLY"
    assert example["real_participants"] == 0
    assert example["human_track"] == "NOT_STARTED"
    assert example["release_decision"] == "HOLD_MISSING_HUMAN_EVIDENCE"
    ReminderPreferenceSnapshotSchemaV07.model_validate(example["preference"])
    DeadlineChangeReminderIntentSchemaV07.model_validate(example["intent"])
    NotificationDeliveryAttemptSchemaV07.model_validate(example["delivery_attempt"])
    InboxEntrySchemaV07.model_validate(example["test_inbox_entry"])
