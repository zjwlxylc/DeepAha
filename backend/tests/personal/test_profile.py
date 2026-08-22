from datetime import date
from typing import cast
from uuid import UUID

import pytest
from pydantic import ValidationError

from deepaha.personal.profile import profile_input_sha256
from deepaha.personal.schemas import ProfileWrite

USER_ID = UUID("019b0000-0000-7000-8000-000000000501")


def profile_write_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "life_stage": "GRADUATING",
        "goal_types": ["PUBLIC_SERVICE_EMPLOYMENT", "POLICY_BENEFIT"],
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
        "preference_regions": ["合成宁波市", "合成杭州市"],
        "preference_types": ["YOUTH_POLICY_BENEFIT", "PUBLIC_INSTITUTION_JOB"],
        "skipped_fields": ["birth_date", "hukou_region", "target_regions", "certificates"],
        "personalization_enabled": True,
        "consent_version": "phase6-consent-v1",
        "allowed_purposes": ["PERSONAL_RANKING", "ELIGIBILITY", "ACTION_TRACKING"],
        "scenario_clock": date(2026, 8, 22),
    }
    values.update(changes)
    return values


def test_profile_write_forbids_owner_input_and_preserves_unknown_sets() -> None:
    command = ProfileWrite.model_validate(profile_write_values())

    assert command.attributes.target_regions is None
    assert command.attributes.certificates is None
    with pytest.raises(ValidationError, match="user_id"):
        ProfileWrite.model_validate(profile_write_values(user_id=str(USER_ID)))


def test_profile_hash_is_owner_bound_and_independent_of_set_input_order() -> None:
    first = ProfileWrite.model_validate(profile_write_values())
    goal_types = cast(list[str], profile_write_values()["goal_types"])
    preference_regions = cast(list[str], profile_write_values()["preference_regions"])
    reordered = ProfileWrite.model_validate(
        profile_write_values(
            goal_types=list(reversed(goal_types)),
            preference_regions=list(reversed(preference_regions)),
        )
    )

    assert profile_input_sha256(USER_ID, first) == profile_input_sha256(USER_ID, reordered)
    assert profile_input_sha256(USER_ID, first) != profile_input_sha256(
        UUID("019b0000-0000-7000-8000-000000000502"), first
    )
