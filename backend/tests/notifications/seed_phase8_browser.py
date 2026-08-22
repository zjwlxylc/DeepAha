from dataclasses import dataclass
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.core.settings import Settings
from deepaha.notifications.models import NotificationOutboxModel
from deepaha.notifications.worker import ReminderWorker
from deepaha.opportunities.models import Opportunity
from deepaha.personal.models import PersonalUserModel
from deepaha.sources.models import Source
from tests.notifications.support import (
    FIXTURE_MARKER,
    PHASE8_WEB_ROUTE,
    govern_phase8_fixture_version,
    load_phase8_deadline_fixture,
    prepare_phase8_prechange,
    resolve_phase8_change,
)


@dataclass(frozen=True, slots=True)
class Phase8BrowserIdentity:
    user_id: UUID
    bearer_token: str
    route: str
    opportunity_public_id: str


def assert_phase8_browser_database_url(database_url: str) -> None:
    target = urlparse(database_url)
    if target.hostname != "127.0.0.1" or target.port != 55438 or target.path != "/deepaha":
        raise ValueError("browser seed requires exact disposable database 127.0.0.1:55438/deepaha")


def seed_phase8_browser(database_url: str) -> Phase8BrowserIdentity:
    assert_phase8_browser_database_url(database_url)
    fixture, _manifest = load_phase8_deadline_fixture()
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            counts = {
                "sources": session.scalar(select(func.count()).select_from(Source)),
                "opportunities": session.scalar(select(func.count()).select_from(Opportunity)),
                "users": session.scalar(select(func.count()).select_from(PersonalUserModel)),
                "outbox": session.scalar(select(func.count()).select_from(NotificationOutboxModel)),
            }
            if any(counts.values()):
                raise RuntimeError("browser seed requires an empty Phase 8 fixture scope")
        factory = sessionmaker(engine, expire_on_commit=False)
        context = resolve_phase8_change(factory, prepare_phase8_prechange(factory))
        govern_phase8_fixture_version(factory, context)
        summary = ReminderWorker(
            session_factory=factory,
            clock=lambda: fixture.scenario_clock,
        ).run_once()
        if summary.delivered != 1:
            raise RuntimeError("browser seed did not deliver the fixed Phase 8 reminder")
        return Phase8BrowserIdentity(
            user_id=context.user_id,
            bearer_token=context.bearer_token,
            route=PHASE8_WEB_ROUTE,
            opportunity_public_id=fixture.opportunity.public_id,
        )
    finally:
        engine.dispose()


def main() -> None:
    database_url = Settings().database_url
    if database_url is None:
        raise ValueError("DEEPAHA_DATABASE_URL is required")
    identity = seed_phase8_browser(database_url)
    print(FIXTURE_MARKER)
    print("real participants=0")
    print("human track=NOT_STARTED")
    print("Release Qualification=NOT_STARTED")
    print("release decision=HOLD_MISSING_HUMAN_EVIDENCE")
    print(f"bearer_token={identity.bearer_token}")
    print(f"web_route={identity.route}")


if __name__ == "__main__":
    main()
