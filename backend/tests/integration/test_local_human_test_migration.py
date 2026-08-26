import re
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.engine import URL, make_url

from deepaha.db.models import Base

pytestmark = pytest.mark.integration

EXPECTED_TABLES = {
    "local_human_test_runs",
    "local_human_test_items",
    "local_human_test_review_decisions",
}


def _temporary_database(database_url: str) -> tuple[str, Engine, URL, str]:
    database_name = f"deepaha_local_human_test_{uuid4().hex}"
    assert re.fullmatch(r"deepaha_local_human_test_[0-9a-f]{32}", database_name)
    url = make_url(database_url)
    maintenance_engine = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
    )
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


def _constraint_sql(engine: Engine, table_name: str) -> str:
    with engine.connect() as connection:
        constraints = inspect(connection).get_check_constraints(table_name)
    return " ".join(str(item["sqltext"]) for item in constraints)


def test_0030_0031_round_trip_and_legacy_idempotency_repair(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name, maintenance, temporary_url, rendered = _temporary_database(database_url)
    engine = None
    try:
        monkeypatch.setenv("DEEPAHA_DATABASE_URL", rendered)
        config = Config("alembic.ini")
        command.upgrade(config, "20260825_0029")
        engine = create_engine(temporary_url)

        command.upgrade(config, "20260826_0030")
        with engine.connect() as connection:
            inspector = inspect(connection)
            assert set(inspector.get_table_names()) >= EXPECTED_TABLES
            assert connection.exec_driver_sql(
                "select version_num from alembic_version"
            ).scalar_one() == "20260826_0030"
            item_columns = {
                item["name"]
                for item in inspector.get_columns("local_human_test_items")
            }
            run_columns = {
                item["name"]
                for item in inspector.get_columns("local_human_test_runs")
            }
            assert {"idempotency_key", "request_hash"} <= run_columns
            assert {
                "document_id",
                "opportunity_id",
                "source_bundle_revision_id",
                "extraction_run_id",
                "model_call_id",
                "verified_fact_set_id",
            } <= item_columns

        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE local_human_test_runs DROP CONSTRAINT "
                "uq_local_human_test_runs_creator_idempotency"
            )
            connection.exec_driver_sql(
                "ALTER TABLE local_human_test_runs DROP COLUMN idempotency_key, "
                "DROP COLUMN request_hash"
            )
        command.upgrade(config, "20260826_0031")
        with engine.connect() as connection:
            inspector = inspect(connection)
            run_columns = {
                item["name"]
                for item in inspector.get_columns("local_human_test_runs")
            }
            constraint_names = {
                item["name"]
                for item in inspector.get_unique_constraints("local_human_test_runs")
            }
            assert {"idempotency_key", "request_hash"} <= run_columns
            assert "uq_local_human_test_runs_creator_idempotency" in constraint_names
            assert connection.exec_driver_sql(
                "select version_num from alembic_version"
            ).scalar_one() == "20260826_0031"

        assert "LOCAL_HUMAN_REVIEWED" in _constraint_sql(engine, "public_catalog_entries")
        assert "LOCAL_TEST_OPERATOR" in _constraint_sql(engine, "reviewer_accounts")
        assert "OPPORTUNITY_FACT_VALIDATION" in _constraint_sql(
            engine, "reviewer_accounts"
        )

        command.downgrade(config, "20260825_0029")
        with engine.connect() as connection:
            assert set(inspect(connection).get_table_names()).isdisjoint(EXPECTED_TABLES)
        assert "LOCAL_HUMAN_REVIEWED" not in _constraint_sql(engine, "public_catalog_entries")
        assert "LOCAL_TEST_OPERATOR" not in _constraint_sql(engine, "reviewer_accounts")

        command.upgrade(config, "20260826_0031")
        with engine.connect() as connection:
            assert set(inspect(connection).get_table_names()) >= EXPECTED_TABLES
            context = MigrationContext.configure(connection)
            assert compare_metadata(context, Base.metadata) == []
    finally:
        if engine is not None:
            engine.dispose()
        _drop_database(name, maintenance)
