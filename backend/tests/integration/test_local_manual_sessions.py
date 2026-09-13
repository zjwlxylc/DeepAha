from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from deepaha.core.settings import Settings
from deepaha.review.auth import (
    ReviewerAuthenticationError,
    resolve_reviewer_principal,
    reviewer_token_digest,
)
from deepaha.review.models import ReviewerAuthSessionModel
from tests.manual import seed_local_manual

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("revoke_first", [False, True])
def test_bootstrap_preserves_existing_session_authentication_state(
    database_url: str,
    migrated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    revoke_first: bool,
) -> None:
    # Only redirect the bootstrap's local-database guard to the isolated test DB.
    # Never run the integration fixtures against the persistent manual database.
    def test_database_only(value: str) -> None:
        assert value == database_url

    monkeypatch.setattr(seed_local_manual, "assert_local_manual_database_url", test_database_only)
    registry = Path(__file__).resolve().parents[3] / "config/sources/phase2-official-endpoints.json"
    first = seed_local_manual.bootstrap_local_human_test(database_url, registry_path=registry)
    if revoke_first:
        with Session(migrated_engine) as session:
            existing = session.get(
                ReviewerAuthSessionModel, reviewer_token_digest(first.reviewer_session)
            )
            assert existing is not None
            existing.revoked_at = datetime.now(UTC)
            session.commit()
    second = seed_local_manual.bootstrap_local_human_test(database_url, registry_path=registry)
    assert first.reviewer_session != second.reviewer_session
    with Session(migrated_engine) as session:
        for identity in (first, second):
            if identity is first and revoke_first:
                with pytest.raises(ReviewerAuthenticationError):
                    resolve_reviewer_principal(
                        "Bearer " + identity.reviewer_session,
                        session,
                        Settings(environment="test", reviewer_auth_mode="fixture"),
                        now=datetime.now(UTC),
                    )
                continue
            principal = resolve_reviewer_principal(
                "Bearer " + identity.reviewer_session,
                session,
                Settings(environment="test", reviewer_auth_mode="fixture"),
                now=datetime.now(UTC),
            )
            assert principal.reviewer_id == seed_local_manual.LOCAL_REVIEWER_ID
