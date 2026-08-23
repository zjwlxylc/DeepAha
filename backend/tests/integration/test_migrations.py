import re
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Connection, create_engine, inspect
from sqlalchemy.engine import make_url

from deepaha.db.models import Base

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).parents[2]
PHASE1_TABLES = {"sources", "raw_artifacts", "documents", "opportunities", "evidence_refs"}
PHASE2_TABLES = {"source_endpoints", "capture_observations", "parse_attempts"}


def test_database_is_postgresql_18(connection: Connection) -> None:
    version_num = int(connection.exec_driver_sql("show server_version_num").scalar_one())

    assert 180000 <= version_num < 190000


def test_migration_matches_orm_metadata(connection: Connection) -> None:
    context = MigrationContext.configure(connection)

    assert compare_metadata(context, Base.metadata) == []


def test_phase2_migration_round_trips_through_phase1_in_an_isolated_database(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_name = f"deepaha_migration_{uuid4().hex}"
    assert re.fullmatch(r"deepaha_migration_[0-9a-f]{32}", database_name)

    url = make_url(database_url)
    maintenance_url = url.set(database="postgres")
    temporary_url = url.set(database=database_name)
    maintenance_engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    temporary_engine = None
    try:
        with maintenance_engine.connect() as maintenance_connection:
            maintenance_connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')

        monkeypatch.setenv(
            "DEEPAHA_DATABASE_URL",
            temporary_url.render_as_string(hide_password=False),
        )
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        command.upgrade(config, "20260821_0001")
        temporary_engine = create_engine(temporary_url)
        with temporary_engine.connect() as temporary_connection:
            assert set(inspect(temporary_connection).get_table_names()) >= PHASE1_TABLES
            assert set(inspect(temporary_connection).get_table_names()).isdisjoint(PHASE2_TABLES)

        command.upgrade(config, "20260821_0002")
        with temporary_engine.connect() as temporary_connection:
            assert set(inspect(temporary_connection).get_table_names()) >= (
                PHASE1_TABLES | PHASE2_TABLES
            )

        command.downgrade(config, "20260821_0001")
        with temporary_engine.connect() as temporary_connection:
            inspector = inspect(temporary_connection)
            assert set(inspector.get_table_names()) >= PHASE1_TABLES
            assert set(inspector.get_table_names()).isdisjoint(PHASE2_TABLES)
            assert {column["name"] for column in inspector.get_columns("evidence_refs")} == {
                "evidence_ref_id",
                "document_id",
                "artifact_id",
                "locator_kind",
                "locator_value",
                "quote_sha256",
            }

        command.upgrade(config, "20260821_0002")
        with temporary_engine.connect() as temporary_connection:
            assert set(inspect(temporary_connection).get_table_names()) >= (
                PHASE1_TABLES | PHASE2_TABLES
            )
    finally:
        if temporary_engine is not None:
            temporary_engine.dispose()
        with maintenance_engine.connect() as maintenance_connection:
            maintenance_connection.exec_driver_sql(
                f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'
            )
        maintenance_engine.dispose()


def test_phase2_downgrade_refuses_v02_opportunity_data(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_name = f"deepaha_migration_{uuid4().hex}"
    assert re.fullmatch(r"deepaha_migration_[0-9a-f]{32}", database_name)

    url = make_url(database_url)
    maintenance_url = url.set(database="postgres")
    temporary_url = url.set(database=database_name)
    maintenance_engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    temporary_engine = None
    try:
        with maintenance_engine.connect() as maintenance_connection:
            maintenance_connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')

        monkeypatch.setenv(
            "DEEPAHA_DATABASE_URL",
            temporary_url.render_as_string(hide_password=False),
        )
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        command.upgrade(config, "20260821_0002")
        temporary_engine = create_engine(temporary_url)
        with temporary_engine.begin() as temporary_connection:
            temporary_connection.exec_driver_sql(
                "insert into opportunities "
                "(opportunity_id, public_id, type, canonical_title, issuer_name, "
                "jurisdiction, current_version, status, publication_status, "
                "created_at, updated_at) values "
                "(uuidv7(), 'opp_11111111111111111111111111111111', 'SCHOLARSHIP', "
                "'Synthetic scholarship', 'Synthetic authority', null, null, "
                "'UNKNOWN', 'INTERNAL', now(), now())"
            )

        with pytest.raises(RuntimeError, match="cannot downgrade Phase 2.*opportunity"):
            command.downgrade(config, "20260821_0001")
    finally:
        if temporary_engine is not None:
            temporary_engine.dispose()
        with maintenance_engine.connect() as maintenance_connection:
            maintenance_connection.exec_driver_sql(
                f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'
            )
        maintenance_engine.dispose()
