from uuid import UUID

import pytest
from pydantic import ValidationError

from deepaha.notifications.preferences import reminder_preference_input_sha256
from deepaha.notifications.schemas import ReminderPreferenceWrite

USER_A_ID = UUID("019b0000-0000-7000-8000-000000000501")
USER_B_ID = UUID("019b0000-0000-7000-8000-000000000502")


def test_preference_hash_is_bound_to_server_owner_and_enabled_value() -> None:
    first = reminder_preference_input_sha256(USER_A_ID, True)

    assert first == reminder_preference_input_sha256(USER_A_ID, True)
    assert first != reminder_preference_input_sha256(USER_A_ID, False)
    assert first != reminder_preference_input_sha256(USER_B_ID, True)


def test_preference_write_accepts_only_the_independent_enabled_switch() -> None:
    assert ReminderPreferenceWrite(enabled=True).model_dump() == {"enabled": True}

    for extra in (
        {"user_id": str(USER_A_ID)},
        {"cadence": "DAILY"},
        {"target": "WECHAT_MINI_PROGRAM"},
    ):
        with pytest.raises(ValidationError):
            ReminderPreferenceWrite.model_validate({"enabled": True, **extra})
