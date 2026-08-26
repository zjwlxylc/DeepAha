from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from secrets import token_urlsafe

from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from deepaha.core.settings import Settings
from deepaha.feedback.models import FeedbackEventModel
from deepaha.notifications.models import NotificationOutboxModel, TestInboxEntryModel
from deepaha.notifications.worker import ReminderWorker
from deepaha.opportunities.models import Opportunity
from deepaha.personal.auth import token_digest
from deepaha.personal.models import PersonalAuthSessionModel, PersonalUserModel
from deepaha.review.auth import ReviewerRole
from deepaha.review.models import ReviewerAccountModel
from deepaha.sources.models import Source
from tests.feedback.seed_phase7_browser import (
    _persist_synthetic_profile,
    _run_synthetic_matches,
)
from tests.feedback.support import load_phase7_feedback_fixture
from tests.notifications.support import (
    govern_phase8_fixture_version,
    load_phase8_deadline_fixture,
    prepare_phase8_prechange,
    resolve_phase8_change,
)
from tests.personal.support import persist_phase6_fixture
from tests.review.support import persist_reviewer


@dataclass(frozen=True, slots=True)
class LocalManualIdentity:
    personal_session: str
    reviewer_session: str
    reminder_session: str
    personal_public_id: str
    reminder_public_id: str


def assert_local_manual_database_url(database_url: str) -> None:
    target = make_url(database_url)
    if target.host != "127.0.0.1" or target.port != 55439 or target.database != "deepaha":
        raise ValueError(
            "local manual seed requires exact disposable database 127.0.0.1:55439/deepaha"
        )


def write_identity_file(path: Path, identity: LocalManualIdentity) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        asdict(identity),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(f"{payload}\n")


def _assert_empty_scope(session: Session) -> None:
    counts = {
        "personal_users": session.scalar(select(func.count()).select_from(PersonalUserModel)),
        "reviewers": session.scalar(select(func.count()).select_from(ReviewerAccountModel)),
        "sources": session.scalar(select(func.count()).select_from(Source)),
        "opportunities": session.scalar(select(func.count()).select_from(Opportunity)),
        "feedback_events": session.scalar(select(func.count()).select_from(FeedbackEventModel)),
        "outbox": session.scalar(select(func.count()).select_from(NotificationOutboxModel)),
    }
    if any(counts.values()):
        raise RuntimeError("local manual seed requires an empty synthetic fixture scope")


def seed_local_manual(database_url: str) -> LocalManualIdentity:
    assert_local_manual_database_url(database_url)
    load_phase7_feedback_fixture()
    phase8_fixture, _manifest = load_phase8_deadline_fixture()
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with Session(engine) as session:
            _assert_empty_scope(session)
            personal = persist_phase6_fixture(session)
            _persist_synthetic_profile(session, personal)
            reviewer_session = token_urlsafe(32)
            persist_reviewer(
                session,
                index=10,
                token=reviewer_session,
                roles=tuple(ReviewerRole),
            )
            session.commit()

        factory = sessionmaker(bind=engine, expire_on_commit=False)
        personal_public_id = _run_synthetic_matches(factory, personal)
        reminder = resolve_phase8_change(factory, prepare_phase8_prechange(factory))
        govern_phase8_fixture_version(factory, reminder)
        summary = ReminderWorker(
            session_factory=factory,
            clock=lambda: phase8_fixture.scenario_clock,
        ).run_once()
        if summary.delivered != 1:
            raise RuntimeError("local manual seed did not deliver the fixed TEST_INBOX reminder")

        reminder_session = token_urlsafe(32)
        with factory() as session:
            inbox_targets = session.scalars(select(TestInboxEntryModel.target)).all()
            if inbox_targets != ["TEST_INBOX"]:
                raise RuntimeError("local manual seed produced a non-TEST_INBOX delivery")
            session.execute(
                delete(PersonalAuthSessionModel).where(
                    PersonalAuthSessionModel.user_id == reminder.user_id
                )
            )
            session.add(
                PersonalAuthSessionModel(
                    token_sha256=token_digest(reminder_session),
                    user_id=reminder.user_id,
                    expires_at=datetime(2099, 1, 1, tzinfo=UTC),
                    revoked_at=None,
                    created_at=phase8_fixture.scenario_clock,
                )
            )
            session.commit()

        return LocalManualIdentity(
            personal_session=personal.token_a,
            reviewer_session=reviewer_session,
            reminder_session=reminder_session,
            personal_public_id=personal_public_id,
            reminder_public_id=phase8_fixture.opportunity.public_id,
        )
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--identity-file", type=Path, required=True)
    args = parser.parse_args()
    database_url = Settings().database_url
    if database_url is None:
        raise ValueError("DEEPAHA_DATABASE_URL is required")
    identity = seed_local_manual(database_url)
    write_identity_file(args.identity_file, identity)
    print("SYNTHETIC_LOCAL_MANUAL_TEST_ONLY")
    print("real participants=0")
    print("human track=NOT_STARTED")
    print("Release Qualification=NOT_STARTED")
    print("release decision=HOLD_MISSING_HUMAN_EVIDENCE")
    print("delivery target=TEST_INBOX")


if __name__ == "__main__":
    main()
