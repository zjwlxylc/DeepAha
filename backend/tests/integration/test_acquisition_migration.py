import re
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.integration


def test_acquisition_migration_round_trip(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_name = f"deepaha_acquisition_migration_{uuid4().hex}"
    assert re.fullmatch(r"deepaha_acquisition_migration_[0-9a-f]{32}", database_name)
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
            assert "acquisition_evaluations" in inspect(connection).get_table_names()

        command.downgrade(config, "20260822_0008")
        with temporary_engine.connect() as connection:
            assert "acquisition_evaluations" not in inspect(connection).get_table_names()

        command.upgrade(config, "head")
        with temporary_engine.connect() as connection:
            assert "acquisition_evaluations" in inspect(connection).get_table_names()
    finally:
        if temporary_engine is not None:
            temporary_engine.dispose()
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
        maintenance_engine.dispose()


def test_acquisition_downgrade_refuses_semantic_evidence(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_name = f"deepaha_acquisition_migration_{uuid4().hex}"
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
                "insert into sources "
                "(source_id, public_id, canonical_url, authority_name, tier, jurisdiction, "
                "active, created_at, updated_at) values "
                "('019c0000-0000-7000-8000-000000000101', "
                "'src_00000000000000000000000000000101', "
                "'https://migration.example.gov/', 'Synthetic migration authority', "
                "'OFFICIAL_PRIMARY', null, true, now(), now())"
            )
            connection.exec_driver_sql(
                "insert into source_endpoints "
                "(endpoint_id, source_id, url, allowed_hosts, expected_media_types, "
                "browser_policy, minimum_interval_seconds, timeout_seconds, max_attempts, "
                "robots_url, robots_decision, robots_checked_at, content_use_basis, "
                "license_name, license_url, attribution, fixture_storage_allowed, usage_note, "
                "policy_version, active, verified_at, created_at, updated_at) values "
                "('019c0000-0000-7000-8000-000000000102', "
                "'019c0000-0000-7000-8000-000000000101', "
                "'https://migration.example.gov/list/', '[\"migration.example.gov\"]'::jsonb, "
                "'[\"text/html\"]'::jsonb, 'NEVER', 21600, 30, 1, "
                "'https://migration.example.gov/robots.txt', 'ALLOWED', now(), 'LINK_ONLY', "
                "null, null, 'Synthetic migration authority', false, 'Migration test only', "
                "'2026-08-23.1', true, now(), now(), now())"
            )
            content_sha256 = "a" * 64
            connection.exec_driver_sql(
                "insert into raw_artifacts "
                "(artifact_id, source_id, requested_url, resolved_url, retrieved_at, http_status, "
                "media_type, content_sha256, storage_bucket, object_key, byte_size, "
                "collector_version, metadata_schema_version) values "
                "('019c0000-0000-7000-8000-000000000103', "
                "'019c0000-0000-7000-8000-000000000101', "
                "'https://migration.example.gov/list/', "
                "'https://migration.example.gov/list/', now(), 200, 'text/html', "
                f"'{content_sha256}', 'deepaha-raw', "
                f"'raw/sha256/aa/{content_sha256}', 1, '1.0.0', '0.1.0')"
            )
            connection.exec_driver_sql(
                "insert into capture_observations "
                "(observation_id, collection_run_id, attempt_number, endpoint_id, source_id, "
                "requested_url, resolved_url, started_at, completed_at, outcome, http_status, "
                "response_etag, response_last_modified, artifact_id, error_code, collector_name, "
                "collector_version, policy_version) values "
                "('019c0000-0000-7000-8000-000000000104', "
                "'019c0000-0000-7000-8000-000000000105', 1, "
                "'019c0000-0000-7000-8000-000000000102', "
                "'019c0000-0000-7000-8000-000000000101', "
                "'https://migration.example.gov/list/', "
                "'https://migration.example.gov/list/', now(), now(), 'SUCCEEDED', 200, "
                "null, null, '019c0000-0000-7000-8000-000000000103', null, "
                "'synthetic', '1.0.0', '2026-08-23.1')"
            )
            connection.exec_driver_sql(
                "insert into acquisition_evaluations "
                "(acquisition_evaluation_id, observation_id, endpoint_id, source_id, artifact_id, "
                "strategy_used, validation_status, challenge_type, redirect_chain, "
                "discovered_count, manual_intervention, diagnostic_codes, validator_name, "
                "validator_version, metrics_schema_version, validation_metrics, evaluated_at, "
                "contract_version) values "
                "('019c0000-0000-7000-8000-000000000106', "
                "'019c0000-0000-7000-8000-000000000104', "
                "'019c0000-0000-7000-8000-000000000102', "
                "'019c0000-0000-7000-8000-000000000101', "
                "'019c0000-0000-7000-8000-000000000103', 'STATIC_HTTP', 'VALID', null, "
                "'[\"https://migration.example.gov/list/\"]'::jsonb, 1, false, '[]'::jsonb, "
                "'deepaha-content-validator', '1.0.0', '1.0.0', "
                "'{\"byte_size\": 1}'::jsonb, now(), '1.0.0')"
            )

        with pytest.raises(RuntimeError, match="cannot downgrade source acquisition"):
            command.downgrade(config, "20260822_0008")

        with temporary_engine.connect() as connection:
            count = connection.exec_driver_sql(
                "select count(*) from acquisition_evaluations"
            ).scalar_one()
            assert count == 1
    finally:
        if temporary_engine is not None:
            temporary_engine.dispose()
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
        maintenance_engine.dispose()
