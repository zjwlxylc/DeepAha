import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from pydantic import ValidationError

from deepaha.contracts import UserStateSnapshotSchemaV05 as ExportedUserStateSnapshotSchemaV05
from deepaha.contracts.export import (
    PHASE6_SCHEMAS,
    render_phase1_schemas,
    render_phase2_schemas,
    render_phase3_schemas,
    render_phase4_schemas,
    render_phase6_schemas,
    write_phase6_schemas,
)
from deepaha.contracts.phase6 import (
    PersonalActionEventSchemaV05,
    PersonalActionSnapshotSchemaV05,
    PersonalRankingItemSchemaV05,
    PersonalRankingSnapshotSchemaV05,
    UserStateSnapshotSchemaV05,
)

NOW = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)
USER_STATE_SNAPSHOT_ID = UUID("019b0000-0000-7000-8000-000000000201")
USER_STATE_ID = UUID("019b0000-0000-7000-8000-000000000202")
PROFILE_SNAPSHOT_ID = UUID("019b0000-0000-7000-8000-000000000203")
RANKING_SNAPSHOT_ID = UUID("019b0000-0000-7000-8000-000000000204")
ACTION_ID = UUID("019b0000-0000-7000-8000-000000000205")
ACTION_SNAPSHOT_ID = UUID("019b0000-0000-7000-8000-000000000206")
ACTION_EVENT_ID = UUID("019b0000-0000-7000-8000-000000000207")
MATERIAL_ITEM_ID = UUID("019b0000-0000-7000-8000-000000000208")
REPOSITORY_ROOT = Path(__file__).parents[3]
V05_EXAMPLE_PATH = REPOSITORY_ROOT / "contracts" / "examples" / "v0.5.0" / "phase-6-example.json"


def user_state_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "user_state_snapshot_id": USER_STATE_SNAPSHOT_ID,
        "user_state_id": USER_STATE_ID,
        "version": 1,
        "qualification_profile_snapshot_id": PROFILE_SNAPSHOT_ID,
        "qualification_profile_version": 1,
        "life_stage": "GRADUATING",
        "goal_types": ["PUBLIC_SERVICE_EMPLOYMENT"],
        "attributes": {
            "education_level": "BACHELOR",
            "major_name": "合成软件工程",
            "major_code": "080902",
            "graduation_year": 2026,
            "student_status": "GRADUATING",
            "birth_date": None,
            "hukou_region": None,
            "residence_region": "合成杭州市",
            "target_regions": None,
            "certificates": None,
        },
        "preference_regions": ["合成杭州市"],
        "preference_types": ["PUBLIC_INSTITUTION_JOB"],
        "skipped_fields": ["birth_date", "hukou_region", "target_regions", "certificates"],
        "personalization_enabled": True,
        "consent_version": "phase6-consent-v1",
        "allowed_purposes": ["ACTION_TRACKING", "ELIGIBILITY", "PERSONAL_RANKING"],
        "scenario_clock": date(2026, 8, 22),
        "input_sha256": "1" * 64,
        "created_at": NOW,
    }
    values.update(changes)
    return values


def test_user_state_preserves_unknown_set_and_rejects_skipped_provided_conflict() -> None:
    state = UserStateSnapshotSchemaV05.model_validate(user_state_values())

    assert state.attributes.target_regions is None
    assert state.attributes.certificates is None

    attributes = cast(dict[str, object], user_state_values()["attributes"])
    conflicting_attributes = dict(attributes)
    conflicting_attributes["target_regions"] = ["合成宁波市"]
    with pytest.raises(ValidationError, match="skipped fields must be absent"):
        UserStateSnapshotSchemaV05.model_validate(
            user_state_values(attributes=conflicting_attributes)
        )


def ranking_item_values(index: int, **changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "ordinal": index,
        "opportunity_id": UUID(f"019b0000-0000-7000-8000-{300 + index:012d}"),
        "opportunity_version": 1,
        "match_snapshot_id": UUID(f"019b0000-0000-7000-8000-{400 + index:012d}"),
        "eligibility_status": "ELIGIBLE",
        "reason_codes": ["ELIGIBILITY_ELIGIBLE", "EARLIER_DEADLINE"],
        "deadline": date(2026, 9, 10 + index),
    }
    values.update(changes)
    return values


def ranking_values(item_count: int = 1, **changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "ranking_snapshot_id": RANKING_SNAPSHOT_ID,
        "user_state_snapshot_id": USER_STATE_SNAPSHOT_ID,
        "qualification_profile_snapshot_id": PROFILE_SNAPSHOT_ID,
        "qualification_profile_version": 1,
        "scenario_clock": date(2026, 8, 22),
        "window_end": date(2026, 11, 20),
        "ranker_version": "phase6-deterministic-ranker-v1",
        "input_sha256": "2" * 64,
        "items": [ranking_item_values(index) for index in range(1, item_count + 1)],
        "omitted_rule_set_count": 0,
        "created_at": NOW,
    }
    values.update(changes)
    return values


def test_ranking_has_no_score_and_rejects_more_than_three_or_ineligible_items() -> None:
    assert "score" not in PersonalRankingItemSchemaV05.model_fields
    assert "confidence" not in PersonalRankingItemSchemaV05.model_fields

    with pytest.raises(ValidationError):
        PersonalRankingSnapshotSchemaV05.model_validate(ranking_values(item_count=4))

    with pytest.raises(ValidationError, match="INELIGIBLE"):
        PersonalRankingSnapshotSchemaV05.model_validate(
            ranking_values(
                items=[
                    ranking_item_values(
                        1,
                        eligibility_status="INELIGIBLE",
                        reason_codes=["ELIGIBILITY_INELIGIBLE"],
                    )
                ]
            )
        )


def action_snapshot_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "action_snapshot_id": ACTION_SNAPSHOT_ID,
        "action_id": ACTION_ID,
        "version": 1,
        "opportunity_id": UUID("019b0000-0000-7000-8000-000000000301"),
        "opportunity_version": 1,
        "saved": True,
        "state": "PREPARING",
        "material_items": [
            {
                "material_item_id": MATERIAL_ITEM_ID,
                "label": "合成报名表",
                "completed": False,
                "due_on": "2026-09-01",
            }
        ],
        "last_event_id": ACTION_EVENT_ID,
        "input_sha256": "3" * 64,
        "created_at": NOW,
    }
    values.update(changes)
    return values


def action_event_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "event_id": ACTION_EVENT_ID,
        "action_id": ACTION_ID,
        "action_snapshot_id": ACTION_SNAPSHOT_ID,
        "event_type": "MATERIAL_PLAN_CHANGED",
        "payload_sha256": "4" * 64,
        "occurred_at": NOW,
    }
    values.update(changes)
    return values


def test_action_contract_rejects_duplicate_materials_and_phase7_phase8_fields() -> None:
    snapshot = PersonalActionSnapshotSchemaV05.model_validate(action_snapshot_values())
    assert snapshot.state.value == "PREPARING"

    duplicate = action_snapshot_values()["material_items"] * 2  # type: ignore[operator]
    with pytest.raises(ValidationError, match="material item IDs must be unique"):
        PersonalActionSnapshotSchemaV05.model_validate(
            action_snapshot_values(material_items=duplicate)
        )

    with pytest.raises(ValidationError, match="feedback"):
        PersonalActionSnapshotSchemaV05.model_validate(
            action_snapshot_values(feedback="not allowed")
        )
    with pytest.raises(ValidationError, match="reminder_at"):
        PersonalActionEventSchemaV05.model_validate(
            action_event_values(reminder_at="2026-09-01T09:00:00Z")
        )


def committed_schema_bytes(version: str) -> dict[str, bytes]:
    directory = REPOSITORY_ROOT / "contracts" / "schemas" / version
    return {path.name: path.read_bytes() for path in directory.glob("*.schema.json")}


def test_phase6_export_preserves_prior_schema_bytes_and_writes_complete_v05(tmp_path: Path) -> None:
    assert render_phase1_schemas() == committed_schema_bytes("v0.1.0")
    assert render_phase2_schemas() == committed_schema_bytes("v0.2.0")
    assert render_phase3_schemas() == committed_schema_bytes("v0.3.0")
    assert render_phase4_schemas() == committed_schema_bytes("v0.4.0")

    rendered = render_phase6_schemas()
    assert set(rendered) == set(PHASE6_SCHEMAS)
    assert rendered == committed_schema_bytes("v0.5.0")
    assert {
        "user-state-snapshot.schema.json",
        "personal-ranking-snapshot.schema.json",
        "personal-action-snapshot.schema.json",
        "personal-action-event.schema.json",
    }.issubset(rendered)

    written = write_phase6_schemas(tmp_path)
    assert {name: path.read_bytes() for name, path in written.items()} == rendered


def test_phase6_contract_is_available_from_the_public_contract_package() -> None:
    assert ExportedUserStateSnapshotSchemaV05 is UserStateSnapshotSchemaV05


def test_phase6_example_is_synthetic_non_personal_and_schema_valid() -> None:
    example = json.loads(V05_EXAMPLE_PATH.read_text(encoding="utf-8"))

    assert example["synthetic"] is True
    assert example["business_truth"] is False
    assert example["release_qualification_eligible"] is False
    assert example["contains_personal_data"] is False
    UserStateSnapshotSchemaV05.model_validate(example["user_state_snapshot"])
    PersonalRankingSnapshotSchemaV05.model_validate(example["personal_ranking_snapshot"])
    PersonalActionSnapshotSchemaV05.model_validate(example["personal_action_snapshot"])
    PersonalActionEventSchemaV05.model_validate(example["personal_action_event"])
