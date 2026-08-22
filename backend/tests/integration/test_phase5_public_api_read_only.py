from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from deepaha.db.session import get_read_only_session
from deepaha.main import create_app
from tests.public_catalog.support import persist_phase5_fixture

pytestmark = pytest.mark.integration


def read_only_session() -> Iterator[Session]:
    generator = get_read_only_session()
    session = next(generator)
    try:
        yield session
    finally:
        generator.close()


def test_public_session_sets_postgresql_transaction_read_only() -> None:
    for session in read_only_session():
        assert session.scalar(text("SHOW transaction_read_only")) == "on"
        with pytest.raises(DBAPIError, match="read-only transaction"):
            session.execute(
                text(
                    "INSERT INTO sources ("
                    "source_id, public_id, canonical_url, authority_name, tier, jurisdiction, "
                    "active, created_at, updated_at"
                    ") VALUES ("
                    "'019d0000-0000-7000-8000-000000000099', "
                    "'src_019d0000000070008000000000000099', "
                    "'https://phase5-read-only.example.test/', 'Synthetic', "
                    "'OFFICIAL_PRIMARY', null, true, now(), now()"
                    ")"
                )
            )
            session.flush()


def test_real_public_api_reads_fixture_without_mutating_domain_rows(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        public_ids = persist_phase5_fixture(session)
        session.commit()
    with migrated_engine.connect() as connection:
        before = connection.execute(text("SELECT count(*) FROM opportunities")).scalar_one()

    with TestClient(create_app()) as client:
        list_response = client.get("/api/v1/public/opportunities?limit=2")
        detail_response = client.get(f"/api/v1/public/opportunities/{public_ids[0]}")

    with migrated_engine.connect() as connection:
        after = connection.execute(text("SELECT count(*) FROM opportunities")).scalar_one()
    assert list_response.status_code == 200
    assert len(list_response.json()["items"]) == 2
    assert detail_response.status_code == 200
    assert detail_response.json()["public_id"] == public_ids[0]
    assert after == before == 3
