from uuid import UUID

import pytest
from pydantic import ValidationError

try:
    from deepaha.local_human_test.contracts import (
        CreateRunCommand,
        ExternalCallBudget,
        ItemStatus,
        ProviderConfigSnapshot,
        ReviewDecisionKind,
        RunMode,
        RunStatus,
    )
except ImportError:
    CreateRunCommand = None  # type: ignore[assignment,misc]
    ExternalCallBudget = None  # type: ignore[assignment,misc]
    ItemStatus = None  # type: ignore[assignment,misc]
    ProviderConfigSnapshot = None  # type: ignore[assignment,misc]
    ReviewDecisionKind = None  # type: ignore[assignment,misc]
    RunMode = None  # type: ignore[assignment,misc]
    RunStatus = None  # type: ignore[assignment,misc]


REVIEWER_ID = UUID("019b0000-0000-7000-8000-000000000701")


def test_control_contracts_expose_the_closed_state_sets() -> None:
    assert RunMode is not None
    assert RunStatus is not None
    assert ItemStatus is not None
    assert ReviewDecisionKind is not None
    assert {item.value for item in RunMode} == {"LIVE_OFFICIAL", "OFFICIAL_REPLAY"}
    assert {item.value for item in RunStatus} == {
        "CREATED",
        "RUNNING",
        "COMPLETED",
        "PARTIAL",
        "FAILED",
        "CANCELLED",
    }
    assert {item.value for item in ReviewDecisionKind} == {
        "BOOTSTRAP",
        "FACT",
        "RULE",
        "PUBLISH",
    }
    assert "UNKNOWN_OUTCOME" in {item.value for item in ItemStatus}
    assert "READY_TO_PUBLISH" in {item.value for item in ItemStatus}


def test_external_call_budget_defaults_are_hard_upper_bounds() -> None:
    assert ExternalCallBudget is not None
    budget = ExternalCallBudget()

    assert budget.model_dump() == {
        "official_request_limit": 9,
        "llm_call_limit": 8,
        "max_input_tokens": 12_000,
        "max_output_tokens": 3_000,
        "timeout_seconds": 90,
        "temperature": 0,
    }
    with pytest.raises(ValidationError):
        ExternalCallBudget(official_request_limit=10)
    with pytest.raises(ValidationError):
        ExternalCallBudget(llm_call_limit=9)
    with pytest.raises(ValidationError):
        ExternalCallBudget(max_input_tokens=12_001)
    with pytest.raises(ValidationError):
        ExternalCallBudget(max_output_tokens=3_001)
    with pytest.raises(ValidationError):
        ExternalCallBudget(timeout_seconds=91)
    with pytest.raises(ValidationError):
        ExternalCallBudget.model_validate({"temperature": 0.1})


def test_create_run_command_is_immutable_and_contains_no_secret_field() -> None:
    assert CreateRunCommand is not None
    assert ProviderConfigSnapshot is not None
    command = CreateRunCommand(
        mode=RunMode.OFFICIAL_REPLAY,
        recipe_ids=("recipe-zj", "recipe-gov"),
        provider=ProviderConfigSnapshot.model_validate(
            {
                "provider": "deepseek",
                "base_url": "https://platform.example.invalid",
                "protocol": "openai_chat_completions",
                "model_id": "deepseek-v4-flash",
                "model_snapshot": "deepseek-v4-flash@configured",
            }
        ),
        budget=ExternalCallBudget(),
        reviewer_id=REVIEWER_ID,
    )

    assert "api_key" not in command.model_dump_json()
    with pytest.raises(ValidationError):
        command.mode = RunMode.LIVE_OFFICIAL


def test_create_run_command_rejects_empty_or_duplicate_recipe_ids() -> None:
    assert CreateRunCommand is not None
    provider = ProviderConfigSnapshot.model_validate(
        {
            "provider": "deepseek",
            "base_url": "https://platform.example.invalid",
            "protocol": "openai_chat_completions",
            "model_id": "deepseek-v4-flash",
            "model_snapshot": "deepseek-v4-flash@configured",
        }
    )

    with pytest.raises(ValidationError):
        CreateRunCommand(
            mode=RunMode.LIVE_OFFICIAL,
            recipe_ids=(),
            provider=provider,
            reviewer_id=REVIEWER_ID,
        )
    with pytest.raises(ValidationError):
        CreateRunCommand(
            mode=RunMode.LIVE_OFFICIAL,
            recipe_ids=("recipe-gov", "recipe-gov"),
            provider=provider,
            reviewer_id=REVIEWER_ID,
        )
