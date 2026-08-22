import json

import pytest

import deepaha.notifications.cli as cli
from deepaha.notifications.worker import ReminderWorkerRunSummary


def test_run_once_emits_only_count_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    summary = ReminderWorkerRunSummary(
        inspected=1,
        promoted=1,
        claimed=1,
        delivered=1,
        suppressed=0,
        retried=0,
        failed=0,
        waiting_governance=0,
    )
    monkeypatch.setattr(cli, "_run_once", lambda limit: summary)

    assert cli.main(["run-once", "--limit", "50"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "claimed": 1,
        "delivered": 1,
        "failed": 0,
        "inspected": 1,
        "promoted": 1,
        "retried": 0,
        "suppressed": 0,
        "waiting_governance": 0,
    }


@pytest.mark.parametrize("limit", ["0", "101"])
def test_cli_rejects_out_of_range_limit(limit: str) -> None:
    assert cli.main(["run-once", "--limit", limit]) == 2
