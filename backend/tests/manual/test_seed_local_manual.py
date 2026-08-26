from pathlib import Path

import pytest

from tests.manual.seed_local_manual import (
    LocalManualIdentity,
    assert_local_manual_database_url,
    write_identity_file,
)


@pytest.mark.parametrize(
    "database_url",
    (
        "postgresql+psycopg://deepaha:secret@localhost:55439/deepaha",
        "postgresql+psycopg://deepaha:secret@127.0.0.1:55438/deepaha",
        "postgresql+psycopg://deepaha:secret@127.0.0.1:55439/production",
    ),
)
def test_seed_rejects_every_database_outside_exact_disposable_target(
    database_url: str,
) -> None:
    with pytest.raises(ValueError, match="127.0.0.1:55439/deepaha"):
        assert_local_manual_database_url(database_url)


def test_identity_file_contains_only_required_synthetic_browser_sessions(tmp_path: Path) -> None:
    target = tmp_path / "identity.json"
    identity = LocalManualIdentity(
        reviewer_session="reviewer-secret",
    )

    write_identity_file(target, identity)

    assert target.read_text("utf-8") == '{"reviewer_session":"reviewer-secret"}\n'
