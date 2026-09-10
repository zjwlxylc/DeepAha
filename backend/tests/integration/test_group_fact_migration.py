import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

from deepaha.investigations.group_facts import prepare_group_facts
from tests.integration.test_group_facts import ready_group
from tests.integration.test_investigation_store import StoreHarness, harness

pytestmark = pytest.mark.integration
__all__ = ["harness"]


def test_group_fact_migration_round_trip_and_model_match(migrated_engine: Engine) -> None:
    config = Config("alembic.ini")
    command.downgrade(config, "20260910_0046")
    command.upgrade(config, "head")
    command.check(config)


def test_group_fact_history_refuses_downgrade(
    harness: StoreHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    task, group_id, request = ready_group(harness, monkeypatch)
    prepare_group_facts(harness.store, task, group_id, request, harness.principal)
    with pytest.raises(RuntimeError, match="GROUP_FACT_HISTORY_DOWNGRADE_REFUSED"):
        command.downgrade(Config("alembic.ini"), "20260910_0046")
