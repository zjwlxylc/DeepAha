from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from secrets import token_urlsafe
from uuid import UUID

from sqlalchemy import create_engine, delete
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from deepaha.core.settings import Settings
from deepaha.review.auth import (
    OPPORTUNITY_FACT_VALIDATION_PURPOSE,
    ReviewerRole,
    reviewer_token_digest,
)
from deepaha.review.models import ReviewerAccountModel, ReviewerAuthSessionModel
from deepaha.sources.registry import import_registry, load_registry_manifest

LOCAL_REVIEWER_ID = UUID("019d0000-0000-7000-8000-000000000990")
LOCAL_REVIEWER_LABEL = "LOCAL_HUMAN_TEST_OWNER"


@dataclass(frozen=True, slots=True)
class LocalManualIdentity:
    reviewer_session: str


def assert_local_manual_database_url(database_url: str) -> None:
    target = make_url(database_url)
    if target.host != "127.0.0.1" or target.port != 55439 or target.database != "deepaha":
        raise ValueError(
            "local manual bootstrap requires exact persistent database 127.0.0.1:55439/deepaha"
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


def bootstrap_local_human_test(
    database_url: str,
    *,
    registry_path: Path,
    now: datetime | None = None,
) -> LocalManualIdentity:
    assert_local_manual_database_url(database_url)
    current_time = now or datetime.now(UTC)
    reviewer_session = token_urlsafe(32)
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with Session(engine) as session:
            import_registry(session, load_registry_manifest(registry_path))
            import_registry(
                session,
                load_registry_manifest(
                    Path(__file__).resolve().parents[3] / "config/sources/direct-wma-local.json"
                ),
            )
            reviewer = session.get(ReviewerAccountModel, LOCAL_REVIEWER_ID)
            expected_roles = [
                ReviewerRole.LOCAL_TEST_OPERATOR.value,
                ReviewerRole.VALIDATION_REVIEWER.value,
            ]
            expected_purposes = [OPPORTUNITY_FACT_VALIDATION_PURPOSE]
            if reviewer is None:
                reviewer = ReviewerAccountModel(
                    reviewer_id=LOCAL_REVIEWER_ID,
                    active=True,
                    synthetic=False,
                    principal_label=LOCAL_REVIEWER_LABEL,
                    roles=expected_roles,
                    allowed_purposes=expected_purposes,
                    created_at=current_time,
                )
                session.add(reviewer)
                session.flush()
            elif (
                not reviewer.active
                or reviewer.synthetic
                or reviewer.principal_label != LOCAL_REVIEWER_LABEL
                or reviewer.roles != expected_roles
                or reviewer.allowed_purposes != expected_purposes
            ):
                raise RuntimeError("LOCAL_HUMAN_TEST_REVIEWER_CONFLICT")

            session.execute(
                delete(ReviewerAuthSessionModel).where(
                    ReviewerAuthSessionModel.reviewer_id == LOCAL_REVIEWER_ID
                )
            )
            session.add(
                ReviewerAuthSessionModel(
                    token_sha256=reviewer_token_digest(reviewer_session),
                    reviewer_id=LOCAL_REVIEWER_ID,
                    expires_at=datetime(2099, 1, 1, tzinfo=UTC),
                    revoked_at=None,
                    created_at=current_time,
                )
            )
            session.commit()
        return LocalManualIdentity(reviewer_session=reviewer_session)
    finally:
        engine.dispose()


def seed_local_manual(database_url: str, *, registry_path: Path) -> LocalManualIdentity:
    return bootstrap_local_human_test(database_url, registry_path=registry_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--identity-file", type=Path, required=True)
    parser.add_argument(
        "--registry-path",
        type=Path,
        default=Path(__file__).resolve().parents[3]
        / "config"
        / "sources"
        / "phase2-official-endpoints.json",
    )
    args = parser.parse_args()
    database_url = Settings().database_url
    if database_url is None:
        raise ValueError("DEEPAHA_DATABASE_URL is required")
    identity = bootstrap_local_human_test(
        database_url,
        registry_path=args.registry_path,
    )
    write_identity_file(args.identity_file, identity)
    print("LOCAL_HUMAN_TEST_BOOTSTRAP_READY")
    print("synthetic opportunity count=0")
    print("real participants=0")
    print("Release Qualification=NOT_STARTED")
    print("external calls=0")


if __name__ == "__main__":
    main()
