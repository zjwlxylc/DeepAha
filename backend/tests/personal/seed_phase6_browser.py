from __future__ import annotations

from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from deepaha.core.settings import Settings
from deepaha.opportunities.models import Opportunity
from deepaha.personal.models import PersonalUserModel
from deepaha.public_catalog.models import PublicCatalogEntry
from tests.personal.support import Phase6FixtureIdentity, persist_phase6_fixture


def assert_phase6_browser_database_url(database_url: str) -> None:
    url = make_url(database_url)
    if url.host != "127.0.0.1" or url.port != 55436 or url.database != "deepaha":
        raise ValueError("browser seed requires exact disposable database 127.0.0.1:55436/deepaha")


def seed_phase6_browser(database_url: str) -> Phase6FixtureIdentity:
    assert_phase6_browser_database_url(database_url)
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with Session(engine) as session:
            counts = (
                session.scalar(select(func.count()).select_from(PersonalUserModel)),
                session.scalar(select(func.count()).select_from(PublicCatalogEntry)),
                session.scalar(select(func.count()).select_from(Opportunity)),
            )
            if any(counts):
                raise RuntimeError(
                    "browser seed requires an empty Phase 6 personal/public database"
                )
            identity = persist_phase6_fixture(session)
            session.commit()
            return identity
    finally:
        engine.dispose()


def main() -> None:
    database_url = Settings().database_url
    if database_url is None:
        raise ValueError("DEEPAHA_DATABASE_URL is required")
    identity = seed_phase6_browser(database_url)
    print(
        "SYNTHETIC_FIXTURE_ONLY "
        f"users=2 opportunities={len(identity.public_ids)} "
        f"session_cookie_a={identity.token_a}"
    )
    for public_id in identity.public_ids:
        print(public_id)


if __name__ == "__main__":
    main()
