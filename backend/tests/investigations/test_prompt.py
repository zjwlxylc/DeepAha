import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from deepaha.investigations.contracts import CreateInvestigation, InvestigationError
from deepaha.investigations.prompt import prepare_input, task_root


def command() -> CreateInvestigation:
    return CreateInvestigation(
        source_id=UUID(int=2),
        endpoint_id=UUID(int=3),
        notice_url="https://example.gov/notice",
        brief="Read only this synthetic notice.",
        wall_time_seconds=600,
    )


def test_preloaded_contract_uses_real_remaining_deadline_and_existing_schema_paths() -> None:
    task_id = UUID(int=1)
    prepared = datetime(2026, 9, 7, tzinfo=UTC)
    files, prompt = prepare_input(
        task_id,
        command(),
        ["example.gov"],
        prepared_at=prepared,
        deadline_at=prepared + timedelta(seconds=150),
    )
    root = task_root(task_id)
    task = json.loads(files[f"{root}/task.json"])
    budget = task["execution_budget"]
    assert budget["remaining_seconds_at_preparation"] == 150
    assert budget["advisory_collection_reserve_seconds"] == 30
    assert datetime.fromisoformat(budget["requested_delivery_by"]) == prepared + timedelta(
        seconds=120
    )
    assert task["resource_limits"]["max_artifacts"] == 50
    for name in ("opportunities.schema.json", "evidence.schema.json"):
        assert f"{root}/schemas/{name}" in files
        assert f"{root}/schemas/{name}" in prompt
    assert (
        b"skills/deepaha-opportunity-investigator/schemas"
        not in files[f"{root}/investigator-sop.md"]
    )


def test_sop_requires_file_name_to_match_the_artifact_path_basename() -> None:
    """Guard the contract handed to the agent.

    A real run (task 01a08fc1-ce83-7473-afc3-4c3ad6931ff6) ended in
    ARTIFACT_PATH_INVALID because the agent stored ``artifacts/jihua.xlsx`` but
    declared ``file_name`` as the original Chinese filename. The receiver is
    correct to reject that; the SOP simply never stated the rule.
    """
    task_id = UUID(int=1)
    prepared = datetime(2026, 9, 7, tzinfo=UTC)
    files, _prompt = prepare_input(
        task_id,
        command(),
        ["example.gov"],
        prepared_at=prepared,
        deadline_at=prepared + timedelta(seconds=150),
    )
    sop = files[f"{task_root(task_id)}/investigator-sop.md"].decode("utf-8")
    assert "`file_name` 必须与 `local_path` 末段逐字相同" in sop
    assert "不要用 ASCII 转写名保存文件" in sop


def test_expired_task_does_not_receive_a_fresh_full_investigation_budget() -> None:
    now = datetime(2026, 9, 7, tzinfo=UTC)
    with pytest.raises(InvestigationError, match="INVALID_INVESTIGATION_BUDGET"):
        prepare_input(UUID(int=1), command(), ["example.gov"], prepared_at=now, deadline_at=now)
