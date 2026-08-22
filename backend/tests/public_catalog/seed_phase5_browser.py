from __future__ import annotations

from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from deepaha.core.settings import Settings
from deepaha.public_catalog.models import PublicCatalogEntry
from tests.public_catalog.support import persist_phase5_fixture


def assert_phase5_browser_database_url(database_url: str) -> None:
    url = make_url(database_url)
    if url.host != "127.0.0.1" or url.port != 55435 or url.database != "deepaha":
        raise ValueError("browser seed requires exact disposable database 127.0.0.1:55435/deepaha")


def seed_phase5_browser(database_url: str) -> tuple[str, ...]:
    assert_phase5_browser_database_url(database_url)
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with Session(engine) as session:
            existing = session.scalar(select(func.count()).select_from(PublicCatalogEntry))
            if existing:
                raise RuntimeError("browser seed requires an empty Phase 5 public catalog")
            public_ids = persist_phase5_fixture(session)
            session.commit()
            return public_ids
    finally:
        engine.dispose()


def main() -> None:
    database_url = Settings().database_url
    if database_url is None:
        raise ValueError("DEEPAHA_DATABASE_URL is required")
    public_ids = seed_phase5_browser(database_url)
    print(f"SYNTHETIC_FIXTURE_ONLY inserted={len(public_ids)}")
    for public_id in public_ids:
        print(public_id)


if __name__ == "__main__":
    main()
