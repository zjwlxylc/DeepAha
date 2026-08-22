from datetime import date
from uuid import UUID

import pytest
from pydantic import ValidationError

from deepaha.personal.schemas import MaterialPlanItemWrite, MaterialPlanWrite, SavedWrite


def test_action_inputs_reject_client_user_identity_and_bound_materials() -> None:
    with pytest.raises(ValidationError):
        SavedWrite.model_validate({"saved": True, "user_id": str(UUID(int=0))})
    with pytest.raises(ValidationError):
        MaterialPlanItemWrite.model_validate(
            {
                "material_item_id": "019b0000-0000-7000-8000-000000000701",
                "label": "x" * 81,
                "completed": False,
                "due_on": date(2026, 9, 1),
            }
        )
    with pytest.raises(ValidationError):
        MaterialPlanWrite.model_validate(
            {
                "items": [
                    {
                        "material_item_id": f"019b0000-0000-7000-8000-{index:012d}",
                        "label": f"材料 {index}",
                        "completed": False,
                        "due_on": None,
                    }
                    for index in range(1, 22)
                ]
            }
        )


def test_material_input_normalizes_label_and_has_no_phase7_or_phase8_shape() -> None:
    command = MaterialPlanWrite.model_validate(
        {
            "items": [
                {
                    "material_item_id": "019b0000-0000-7000-8000-000000000701",
                    "label": "  合成报名表  ",
                    "completed": False,
                    "due_on": None,
                }
            ]
        }
    )

    assert command.items[0].label == "合成报名表"
    serialized = command.model_dump_json().lower()
    for forbidden in ("feedback", "review", "reminder", "notification"):
        assert forbidden not in serialized
