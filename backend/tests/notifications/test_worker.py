from dataclasses import asdict

import pytest

from deepaha.notifications.worker import ReminderWorkerRunSummary, validate_worker_limit


def test_worker_summary_is_counts_only() -> None:
    summary = ReminderWorkerRunSummary(
        inspected=1,
        promoted=2,
        claimed=3,
        delivered=4,
        suppressed=5,
        retried=6,
        failed=7,
        waiting_governance=8,
    )

    assert asdict(summary) == {
        "inspected": 1,
        "promoted": 2,
        "claimed": 3,
        "delivered": 4,
        "suppressed": 5,
        "retried": 6,
        "failed": 7,
        "waiting_governance": 8,
    }


@pytest.mark.parametrize("value", [0, 101, -1])
def test_worker_limit_is_bounded(value: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 100"):
        validate_worker_limit(value)


def test_worker_limit_accepts_configured_batch_bounds() -> None:
    assert validate_worker_limit(None, default=50) == 50
    assert validate_worker_limit(1) == 1
    assert validate_worker_limit(100) == 100
