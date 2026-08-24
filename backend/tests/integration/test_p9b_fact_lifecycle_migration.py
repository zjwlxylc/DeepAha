import re
from datetime import UTC, datetime
from uuid import uuid4, uuid7

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import URL, make_url

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 24, 17, 0, tzinfo=UTC)


def _temporary_database(database_url: str, prefix: str) -> tuple[str, Engine, URL, str]:
    database_name = f"{prefix}_{uuid4().hex}"
    assert re.fullmatch(r"[a-z0-9_]+_[0-9a-f]{32}", database_name)
    url = make_url(database_url)
    maintenance_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with maintenance_engine.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
    temporary_url = url.set(database=database_name)
    return (
        database_name,
        maintenance_engine,
        temporary_url,
        temporary_url.render_as_string(hide_password=False),
    )


def _drop_database(database_name: str, maintenance_engine: Engine) -> None:
    with maintenance_engine.connect() as connection:
        connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
    maintenance_engine.dispose()


def test_fact_lifecycle_migration_empty_round_trip(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    name, maintenance, temporary_url, rendered = _temporary_database(
        database_url, "deepaha_p9b_facts_empty"
    )
    engine = None
    try:
        monkeypatch.setenv("DEEPAHA_DATABASE_URL", rendered)
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        engine = create_engine(temporary_url)
        with engine.connect() as connection:
            assert "versioned_verified_fact_sets" in inspect(connection).get_table_names()

        command.downgrade(config, "20260824_0012")
        with engine.connect() as connection:
            assert "versioned_verified_fact_sets" not in inspect(connection).get_table_names()

        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert "unit_rule_sets" in inspect(connection).get_table_names()
    finally:
        if engine is not None:
            engine.dispose()
        _drop_database(name, maintenance)


def test_fact_lifecycle_migration_refuses_populated_history(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    name, maintenance, temporary_url, rendered = _temporary_database(
        database_url, "deepaha_p9b_facts_history"
    )
    engine = None
    try:
        monkeypatch.setenv("DEEPAHA_DATABASE_URL", rendered)
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        engine = create_engine(temporary_url)
        with engine.begin() as connection:
            connection.execute(text("alter table extraction_runs disable trigger all"))
            connection.execute(
                text(
                    "insert into extraction_runs (extraction_run_id, "
                    "source_bundle_revision_id, target_scope, opportunity_id, "
                    "opportunity_version, opportunity_unit_id, opportunity_unit_version_id, "
                    "unit_segmentation_version, task_spec_version, extractor_kind, "
                    "component_version, producer_identity, producer_response_id, "
                    "ordered_input_block_ids, input_block_set_hash, evidence_binding_hash, "
                    "started_at, completed_at, status) values (:run_id, :revision_id, "
                    "'OPPORTUNITY', :opportunity_id, 1, null, null, null, 'test/0.8.0', "
                    "'DETERMINISTIC', 'test/0.8.0', 'component:migration-history', null, "
                    "cast(:blocks as jsonb), :hash, :hash, :now, :now, 'SUCCEEDED')"
                ),
                {
                    "run_id": uuid7(),
                    "revision_id": uuid7(),
                    "opportunity_id": uuid7(),
                    "blocks": f'["{uuid7()}"]',
                    "hash": "a" * 64,
                    "now": NOW,
                },
            )
            connection.execute(text("alter table extraction_runs enable trigger all"))

        with pytest.raises(RuntimeError, match="cannot downgrade P9-B fact lifecycle"):
            command.downgrade(config, "20260824_0012")
    finally:
        if engine is not None:
            engine.dispose()
        _drop_database(name, maintenance)
