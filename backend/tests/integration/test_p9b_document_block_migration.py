import re
from datetime import UTC, datetime
from uuid import uuid4, uuid7

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from deepaha.artifacts.s3 import S3ObjectStore
from deepaha.artifacts.service import ImportRawArtifactCommand, import_raw_artifact
from deepaha.core.settings import Settings
from deepaha.documents.html import P9BHtmlDocumentParser
from deepaha.documents.service import DocumentService, ParseDocumentCommand
from deepaha.sources.models import Source

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 24, 14, 30, tzinfo=UTC)
CONTENT = b"<html><body><main><p>Migration block</p></main></body></html>"


class FixedClock:
    def now(self) -> datetime:
        return NOW


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


def test_document_block_migration_empty_round_trip(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    name, maintenance, temporary_url, rendered = _temporary_database(
        database_url, "deepaha_p9b_blocks_empty"
    )
    engine = None
    try:
        monkeypatch.setenv("DEEPAHA_DATABASE_URL", rendered)
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        engine = create_engine(temporary_url)
        with engine.connect() as connection:
            assert "document_blocks" in inspect(connection).get_table_names()

        command.downgrade(config, "20260824_0011")
        with engine.connect() as connection:
            assert "document_blocks" not in inspect(connection).get_table_names()

        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert "document_blocks" in inspect(connection).get_table_names()
    finally:
        if engine is not None:
            engine.dispose()
        _drop_database(name, maintenance)


def test_document_block_migration_refuses_populated_history(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    name, maintenance, temporary_url, rendered = _temporary_database(
        database_url, "deepaha_p9b_blocks_history"
    )
    engine = None
    try:
        monkeypatch.setenv("DEEPAHA_DATABASE_URL", rendered)
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        engine = create_engine(temporary_url)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        object_store = S3ObjectStore(Settings())
        object_store.ensure_bucket()
        artifact_id = _seed_artifact(factory, object_store)
        result = DocumentService(
            session_factory=factory,
            object_store=object_store,
            parsers=[P9BHtmlDocumentParser()],
            clock=FixedClock(),
        ).parse(ParseDocumentCommand(artifact_id=artifact_id))
        assert result.document_block_ids

        with pytest.raises(RuntimeError, match="cannot downgrade P9-B DocumentBlock"):
            command.downgrade(config, "20260824_0011")

        with engine.connect() as connection:
            assert connection.exec_driver_sql("select count(*) from document_blocks").scalar_one()
    finally:
        if engine is not None:
            engine.dispose()
        _drop_database(name, maintenance)


def _seed_artifact(factory: sessionmaker[Session], object_store: S3ObjectStore):  # type: ignore[no-untyped-def]
    source_id = uuid7()
    with factory.begin() as session:
        session.add(
            Source(
                source_id=source_id,
                public_id=f"src_{source_id.hex}",
                canonical_url=f"https://p9b-migration-{source_id.hex}.example.gov/",
                authority_name="Synthetic migration authority",
                tier="OFFICIAL_PRIMARY",
                jurisdiction=None,
                active=True,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.flush()
        result = import_raw_artifact(
            session=session,
            object_store=object_store,
            command=ImportRawArtifactCommand(
                source_id=source_id,
                requested_url="https://p9b-migration.example.gov/notice",
                resolved_url="https://p9b-migration.example.gov/notice",
                retrieved_at=NOW,
                http_status=200,
                media_type="text/html",
                content=CONTENT,
                collector_version="test/0.8.0",
                metadata_schema_version="0.2.0",
            ),
        )
        return result.artifact.artifact_id
