import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from deepaha.p9b.identity import OpportunityUnitService, UnitSeed

from .test_p9b_b0_persistence import NOW, frozen_bundle, seed_graph

pytestmark = pytest.mark.integration


def test_group_migration_round_trip_and_model_match(migrated_engine: Engine) -> None:
    config = Config("alembic.ini")
    command.downgrade(config, "20260909_0044")
    command.upgrade(config, "head")
    command.check(config)
    with migrated_engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == ScriptDirectory.from_config(config).get_current_head()
        )


def test_group_history_refuses_downgrade(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        graph = seed_graph(session)
        bundle = frozen_bundle(session, graph)
        unit = OpportunityUnitService(session).create_unit(
            opportunity_id=graph.opportunity_id,
            opportunity_version=1,
            source_bundle_revision_id=bundle.source_bundle_revision_id,
            seed=UnitSeed("group:01", "GROUP", "Group", "a" * 64),
            effective_from=NOW,
        )
        group_id = unit.opportunity_unit_id
        session.commit()
    with pytest.raises(RuntimeError, match="GROUP_IDENTITY_HISTORY_DOWNGRADE_REFUSED"):
        command.downgrade(Config("alembic.ini"), "20260909_0044")
    with migrated_engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
        )
        assert (
            connection.scalar(
                text("SELECT unit_kind FROM opportunity_units WHERE opportunity_unit_id=:id"),
                {"id": group_id},
            )
            == "GROUP"
        )
