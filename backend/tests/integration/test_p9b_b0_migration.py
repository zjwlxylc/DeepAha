import re
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL, Engine, make_url

from deepaha.p9b.hashing import document_parse_key

pytestmark = pytest.mark.integration

P9B_B0_TABLES = {
    "opportunity_units",
    "opportunity_unit_versions",
    "opportunity_unit_aliases",
    "opportunity_unit_lineage_events",
    "opportunity_unit_lineage_members",
    "opportunity_unit_lineage_evidence",
    "source_bundles",
    "source_bundle_revisions",
    "source_bundle_members",
    "source_bundle_member_relations",
    "dataset_manifests",
    "dataset_manifest_entries",
}
LEGACY_PARSE_CONTRACT = "phase2-locator-contract-v0.2.0"


def temporary_database(database_url: str, prefix: str) -> tuple[str, Engine, URL, str]:
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


def drop_temporary_database(database_name: str, maintenance_engine: Engine) -> None:
    with maintenance_engine.connect() as connection:
        connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
    maintenance_engine.dispose()


def test_p9b_b0_migration_round_trips_through_p9a(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_name, maintenance_engine, temporary_url, rendered_url = temporary_database(
        database_url, "deepaha_p9b_b0_migration"
    )
    temporary_engine = None
    try:
        monkeypatch.setenv("DEEPAHA_DATABASE_URL", rendered_url)
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        temporary_engine = create_engine(temporary_url)
        with temporary_engine.connect() as connection:
            inspector = inspect(connection)
            assert set(inspector.get_table_names()) >= P9B_B0_TABLES
            document_columns = {column["name"] for column in inspector.get_columns("documents")}
            assert {"parse_contract_version", "document_parse_key"} <= document_columns

        command.downgrade(config, "20260823_0010")
        with temporary_engine.connect() as connection:
            inspector = inspect(connection)
            assert set(inspector.get_table_names()).isdisjoint(P9B_B0_TABLES)
            document_columns = {column["name"] for column in inspector.get_columns("documents")}
            assert {"parse_contract_version", "document_parse_key"}.isdisjoint(document_columns)

        command.upgrade(config, "head")
        with temporary_engine.connect() as connection:
            assert set(inspect(connection).get_table_names()) >= P9B_B0_TABLES
    finally:
        if temporary_engine is not None:
            temporary_engine.dispose()
        drop_temporary_database(database_name, maintenance_engine)


def test_p9b_b0_migration_preserves_document_id_and_backfills_legacy_parse_identity(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_name, maintenance_engine, temporary_url, rendered_url = temporary_database(
        database_url, "deepaha_p9b_parse_identity"
    )
    temporary_engine = None
    try:
        monkeypatch.setenv("DEEPAHA_DATABASE_URL", rendered_url)
        config = Config("alembic.ini")
        command.upgrade(config, "20260823_0010")
        temporary_engine = create_engine(temporary_url)
        source_id = UUID("019c0000-0000-7000-8000-000000001001")
        artifact_id = UUID("019c0000-0000-7000-8000-000000001002")
        document_id = UUID("019c0000-0000-7000-8000-000000001003")
        attempt_id = UUID("019c0000-0000-7000-8000-000000001004")
        digest = "a" * 64
        with temporary_engine.begin() as connection:
            connection.exec_driver_sql(
                "insert into sources (source_id, public_id, canonical_url, authority_name, tier, "
                "jurisdiction, active, created_at, updated_at) values "
                f"('{source_id}', 'src_{source_id.hex}', 'https://migration.example.gov', "
                "'Migration authority', 'OFFICIAL_PRIMARY', null, true, now(), now())"
            )
            connection.exec_driver_sql(
                "insert into raw_artifacts (artifact_id, source_id, requested_url, resolved_url, "
                "retrieved_at, http_status, media_type, content_sha256, storage_bucket, "
                "object_key, "
                "byte_size, collector_version, metadata_schema_version) values "
                f"('{artifact_id}', '{source_id}', 'https://migration.example.gov/a', "
                f"'https://migration.example.gov/a', now(), 200, 'text/html', '{digest}', "
                f"'deepaha-raw', 'raw/sha256/aa/{digest}', 1, '1.0.0', '0.2.0')"
            )
            connection.exec_driver_sql(
                "insert into documents (document_id, artifact_id, title, published_at, language, "
                "extracted_text_uri, parser_name, parser_version, parse_confidence, created_at) "
                f"values ('{document_id}', '{artifact_id}', 'Legacy', null, 'zh-CN', null, "
                "'html_lxml', '0.2.0', null, now())"
            )
            connection.exec_driver_sql(
                "insert into parse_attempts (parse_attempt_id, artifact_id, parser_name, "
                "parser_version, started_at, completed_at, outcome, document_id, error_code, "
                f"input_media_type) values ('{attempt_id}', '{artifact_id}', 'html_lxml', "
                f"'0.2.0', now(), now(), 'SUCCEEDED', '{document_id}', null, 'text/html')"
            )

        command.upgrade(config, "head")
        expected_key = document_parse_key(
            artifact_id=artifact_id,
            artifact_sha256=digest,
            parser_name="html_lxml",
            parser_version="0.2.0",
            parse_contract_version=LEGACY_PARSE_CONTRACT,
        )
        with temporary_engine.connect() as connection:
            document = connection.exec_driver_sql(
                "select document_id, parse_contract_version, document_parse_key from documents"
            ).one()
            attempt = connection.exec_driver_sql(
                "select parse_contract_version, document_parse_key from parse_attempts"
            ).one()
            assert document == (document_id, LEGACY_PARSE_CONTRACT, expected_key)
            assert attempt == (LEGACY_PARSE_CONTRACT, expected_key)
    finally:
        if temporary_engine is not None:
            temporary_engine.dispose()
        drop_temporary_database(database_name, maintenance_engine)


def test_p9b_b0_downgrade_refuses_identity_or_provenance_history(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_name, maintenance_engine, temporary_url, rendered_url = temporary_database(
        database_url, "deepaha_p9b_b0_refusal"
    )
    temporary_engine = None
    try:
        monkeypatch.setenv("DEEPAHA_DATABASE_URL", rendered_url)
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        temporary_engine = create_engine(temporary_url)
        opportunity_id = UUID("019c0000-0000-7000-8000-000000001101")
        bundle_id = UUID("019c0000-0000-7000-8000-000000001102")
        with temporary_engine.begin() as connection:
            connection.exec_driver_sql(
                "insert into opportunities (opportunity_id, public_id, type, canonical_title, "
                "issuer_name, jurisdiction, current_version, status, publication_status, "
                f"created_at, updated_at) values ('{opportunity_id}', 'opp_{opportunity_id.hex}', "
                "'PUBLIC_INSTITUTION_JOB', 'Migration opportunity', 'Migration authority', null, "
                "null, 'DRAFT', 'INTERNAL', now(), now())"
            )
            connection.exec_driver_sql(
                "insert into source_bundles (source_bundle_id, opportunity_id, created_at, "
                f"retired_at) values ('{bundle_id}', '{opportunity_id}', now(), null)"
            )

        with pytest.raises(RuntimeError, match="cannot downgrade P9-B0"):
            command.downgrade(config, "20260823_0010")

        with temporary_engine.connect() as connection:
            bundle_count = connection.exec_driver_sql(
                "select count(*) from source_bundles"
            ).scalar_one()
            assert bundle_count == 1
    finally:
        if temporary_engine is not None:
            temporary_engine.dispose()
        drop_temporary_database(database_name, maintenance_engine)
