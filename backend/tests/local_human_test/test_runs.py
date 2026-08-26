from datetime import UTC, datetime
from uuid import UUID

import pytest

from deepaha.local_human_test.contracts import (
    CreateRunCommand,
    ExternalCallBudget,
    ItemStatus,
    ProviderConfigSnapshot,
    RunMode,
    RunStatus,
)
from deepaha.local_human_test.runs import (
    BudgetExhausted,
    ItemTransitionError,
    assert_item_transition,
    create_run_request_hash,
    derive_terminal_run_status,
    reserve_budget_count,
)

REVIEWER_ID = UUID("019d0000-0000-7000-8000-000000000001")
NOW = datetime(2026, 8, 26, 10, 0, tzinfo=UTC)


def _command(*, model_id: str = "deepseek-chat") -> CreateRunCommand:
    provider = ProviderConfigSnapshot.model_validate(
        {
            "provider": "deepseek",
            "base_url": "https://provider.invalid",
            "protocol": "openai_chat_completions",
            "model_id": model_id,
            "model_snapshot": "manual-2026-08-26",
        }
    )
    return CreateRunCommand(
        mode=RunMode.OFFICIAL_REPLAY,
        recipe_ids=("zj-policy", "central-service"),
        provider=provider,
        budget=ExternalCallBudget(),
        reviewer_id=REVIEWER_ID,
    )


def test_create_run_request_hash_is_canonical_and_semantic() -> None:
    first = _command()
    equivalent = CreateRunCommand.model_validate(first.model_dump(mode="json"))

    assert create_run_request_hash(first) == create_run_request_hash(equivalent)
    assert create_run_request_hash(first) != create_run_request_hash(
        _command(model_id="deepseek-reasoner")
    )
    assert len(create_run_request_hash(first)) == 64


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ItemStatus.CREATED, ItemStatus.ACQUIRING),
        (ItemStatus.ACQUIRING, ItemStatus.BOOTSTRAP_REVIEW),
        (ItemStatus.ACQUIRING, ItemStatus.EXTRACTING),
        (ItemStatus.BOOTSTRAP_REVIEW, ItemStatus.EXTRACTING),
        (ItemStatus.EXTRACTING, ItemStatus.FACT_REVIEW),
        (ItemStatus.FACT_REVIEW, ItemStatus.RULE_REVIEW),
        (ItemStatus.RULE_REVIEW, ItemStatus.READY_TO_PUBLISH),
        (ItemStatus.READY_TO_PUBLISH, ItemStatus.COMPLETED),
        (ItemStatus.EXTRACTING, ItemStatus.UNKNOWN_OUTCOME),
    ],
)
def test_allowed_item_transitions(current: ItemStatus, target: ItemStatus) -> None:
    assert_item_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ItemStatus.CREATED, ItemStatus.FACT_REVIEW),
        (ItemStatus.ACQUIRING, ItemStatus.COMPLETED),
        (ItemStatus.FACT_REVIEW, ItemStatus.READY_TO_PUBLISH),
        (ItemStatus.UNKNOWN_OUTCOME, ItemStatus.EXTRACTING),
        (ItemStatus.COMPLETED, ItemStatus.CANCELLED),
    ],
)
def test_forbidden_item_transition_is_rejected(
    current: ItemStatus,
    target: ItemStatus,
) -> None:
    with pytest.raises(ItemTransitionError):
        assert_item_transition(current, target)


def test_cancellation_is_allowed_only_before_terminal_state() -> None:
    assert_item_transition(ItemStatus.FACT_REVIEW, ItemStatus.CANCELLED)
    with pytest.raises(ItemTransitionError):
        assert_item_transition(ItemStatus.FAILED, ItemStatus.CANCELLED)


def test_budget_reservation_consumes_exact_limit_then_fails_closed() -> None:
    count = 0
    for _ in range(9):
        count = reserve_budget_count(count, limit=9, kind="official_request")
    assert count == 9
    with pytest.raises(BudgetExhausted, match="OFFICIAL_REQUEST_BUDGET_EXHAUSTED"):
        reserve_budget_count(count, limit=9, kind="official_request")

    count = 0
    for _ in range(8):
        count = reserve_budget_count(count, limit=8, kind="llm_call")
    assert count == 8
    with pytest.raises(BudgetExhausted, match="LLM_CALL_BUDGET_EXHAUSTED"):
        reserve_budget_count(count, limit=8, kind="llm_call")


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ((ItemStatus.COMPLETED,), RunStatus.COMPLETED),
        ((ItemStatus.CANCELLED, ItemStatus.CANCELLED), RunStatus.CANCELLED),
        ((ItemStatus.COMPLETED, ItemStatus.FAILED), RunStatus.PARTIAL),
        ((ItemStatus.PARTIAL_BUDGET_EXHAUSTED,), RunStatus.PARTIAL),
        ((ItemStatus.FAILED, ItemStatus.MODEL_OUTPUT_INVALID), RunStatus.FAILED),
    ],
)
def test_terminal_run_status_is_derived_from_all_items(
    statuses: tuple[ItemStatus, ...],
    expected: RunStatus,
) -> None:
    assert derive_terminal_run_status(statuses) is expected


def test_unknown_outcome_is_a_manual_hold_not_a_terminal_run_state() -> None:
    with pytest.raises(ItemTransitionError, match="RUN_HAS_NONTERMINAL_ITEMS"):
        derive_terminal_run_status((ItemStatus.UNKNOWN_OUTCOME,))
