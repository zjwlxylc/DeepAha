import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

from deepaha.investigations.group_bindings import preview_group_source, register_group_source
from tests.integration.test_group_source_binding import _registered
from tests.integration.test_investigation_store import StoreHarness, harness

pytestmark = pytest.mark.integration
__all__ = ["harness"]


def test_group_source_migration_round_trip_and_model_match(migrated_engine: Engine) -> None:
    config = Config("alembic.ini")
    command.downgrade(config, "20260910_0045")
    command.upgrade(config, "head")
    command.check(config)


def test_group_source_history_refuses_downgrade(harness: StoreHarness) -> None:
    task, _ = _registered(harness)
    preview = preview_group_source(harness.store, task, "unit", harness.principal)
    register_group_source(harness.store, task, "unit", preview["source_hash"], harness.principal)
    with pytest.raises(RuntimeError, match="GROUP_SOURCE_HISTORY_DOWNGRADE_REFUSED"):
        command.downgrade(Config("alembic.ini"), "20260910_0045")
