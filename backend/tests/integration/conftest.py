from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.orm import Session

from deepaha.core.settings import Settings

BACKEND_ROOT = Path(__file__).parents[2]


@pytest.fixture(scope="session")
def database_url() -> str:
    value = Settings().database_url
    if value is None:
        pytest.fail("DEEPAHA_DATABASE_URL is required for integration tests")
    return value


@pytest.fixture(scope="session")
def migrated_engine(database_url: str) -> Iterator[Engine]:
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")
    engine = create_engine(database_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def connection(migrated_engine: Engine) -> Iterator[Connection]:
    with migrated_engine.connect() as value:
        yield value


@pytest.fixture
def session(migrated_engine: Engine) -> Iterator[Session]:
    with migrated_engine.connect() as connection:
        transaction = connection.begin()
        value = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield value
        finally:
            value.close()
            if transaction.is_active:
                transaction.rollback()
