import re
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.integration


def test_health_migration_round_trip(database_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    database_name = f"deepaha_acquisition_health_{uuid4().hex}"
    assert re.fullmatch(r"deepaha_acquisition_health_[0-9a-f]{32}", database_name)
    url = make_url(database_url)
    maintenance_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    temporary_engine = None
    try:
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
        temporary_url = url.set(database=database_name)
        monkeypatch.setenv(
            "DEEPAHA_DATABASE_URL", temporary_url.render_as_string(hide_password=False)
        )
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        temporary_engine = create_engine(temporary_url)
        with temporary_engine.connect() as connection:
            tables = inspect(connection).get_table_names()
            assert "acquisition_runs" in tables
            assert "source_integration_evidence" in tables

        command.downgrade(config, "20260823_0009")
        with temporary_engine.connect() as connection:
            tables = inspect(connection).get_table_names()
            assert "acquisition_runs" not in tables
            assert "source_integration_evidence" not in tables

        command.upgrade(config, "head")
    finally:
        if temporary_engine is not None:
            temporary_engine.dispose()
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
        maintenance_engine.dispose()


def test_health_migration_downgrade_refuses_run_evidence(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_name = f"deepaha_acquisition_health_{uuid4().hex}"
    url = make_url(database_url)
    maintenance_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    temporary_engine = None
    try:
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
        temporary_url = url.set(database=database_name)
        monkeypatch.setenv(
            "DEEPAHA_DATABASE_URL", temporary_url.render_as_string(hide_password=False)
        )
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        temporary_engine = create_engine(temporary_url)
        with temporary_engine.begin() as connection:
            connection.exec_driver_sql(
                "insert into sources (source_id, public_id, canonical_url, authority_name, tier, "
                "jurisdiction, active, created_at, updated_at) values "
                "('019c0000-0000-7000-8000-000000000701', "
                "'src_00000000000000000000000000000701', "
                "'https://health.example.gov/', 'Synthetic', 'OFFICIAL_PRIMARY', null, true, "
                "now(), now())"
            )
            connection.exec_driver_sql(
                "insert into source_endpoints (endpoint_id, source_id, url, allowed_hosts, "
                "expected_media_types, browser_policy, minimum_interval_seconds, timeout_seconds, "
                "max_attempts, robots_url, robots_decision, robots_checked_at, content_use_basis, "
                "license_name, license_url, attribution, fixture_storage_allowed, usage_note, "
                "policy_version, active, verified_at, created_at, updated_at) values "
                "('019c0000-0000-7000-8000-000000000702', "
                "'019c0000-0000-7000-8000-000000000701', 'https://health.example.gov/list', "
                "'[\"health.example.gov\"]'::jsonb, '[\"text/html\"]'::jsonb, 'NEVER', 1, "
                "30, 1, null, 'NOT_APPLICABLE', now(), 'LINK_ONLY', null, null, 'Synthetic', "
                "false, 'test', 'v1', true, now(), now(), now())"
            )
            connection.exec_driver_sql(
                "insert into acquisition_runs (acquisition_run_id, recipe_id, source_id, "
                "endpoint_id, endpoint_policy_version, recipe_version, started_at, completed_at, "
                "terminal_code, request_count, strategy_attempts, discovered_count, "
                "validated_count, parsed_count, attachment_count, evidence_count, "
                "zero_discovery_flag, selector_drift_flag, manual_intervention, "
                "stable_stop_reason, contract_version) values "
                "('019c0000-0000-7000-8000-000000000703', "
                "'019c0000-0000-7000-8000-000000000704', "
                "'019c0000-0000-7000-8000-000000000701', "
                "'019c0000-0000-7000-8000-000000000702', 'v1', 'r1', now(), now(), "
                '\'COMPLETE\', 1, \'[{"strategy":"STATIC_HTTP",'
                '"validation_status":"VALID","error_code":null}]\'::jsonb, 1, 1, 1, '
                "0, 1, false, false, false, null, '1.0.0')"
            )

        with pytest.raises(RuntimeError, match="cannot downgrade acquisition health"):
            command.downgrade(config, "20260823_0009")
    finally:
        if temporary_engine is not None:
            temporary_engine.dispose()
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
        maintenance_engine.dispose()
