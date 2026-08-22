from pathlib import Path

import pytest

from tests.personal.seed_phase6_browser import assert_phase6_browser_database_url
from tests.personal.support import load_phase6_fixture

SUPPORT_MODULE = Path(__file__).with_name("support.py")


def test_phase6_fixture_is_non_personal_synthetic_evidence() -> None:
    fixture = load_phase6_fixture()

    assert fixture.synthetic is True
    assert fixture.contains_personal_data is False
    assert fixture.business_truth is False
    assert fixture.release_qualification_eligible is False
    assert len(fixture.users) == 2


def test_phase6_fixture_does_not_commit_plaintext_session_credentials() -> None:
    source = SUPPORT_MODULE.read_text(encoding="utf-8")

    assert "_SYNTHETIC_SESSION_TOKEN" not in source


@pytest.mark.parametrize(
    "candidate",
    [
        "postgresql+psycopg://deepaha:test@127.0.0.1:55432/deepaha",
        "postgresql+psycopg://deepaha:test@127.0.0.1:55433/deepaha",
        "postgresql+psycopg://deepaha:test@127.0.0.1:55434/deepaha",
        "postgresql+psycopg://deepaha:test@127.0.0.1:55435/deepaha",
        "postgresql+psycopg://deepaha:test@localhost:55436/deepaha",
        "postgresql+psycopg://deepaha:test@127.0.0.1:55436/other",
        "postgresql+psycopg://deepaha:test@example.test:55436/deepaha",
    ],
)
def test_phase6_browser_seed_rejects_every_non_exact_database(candidate: str) -> None:
    with pytest.raises(ValueError, match="127.0.0.1:55436/deepaha"):
        assert_phase6_browser_database_url(candidate)


def test_phase6_browser_seed_accepts_only_the_exact_disposable_database() -> None:
    assert_phase6_browser_database_url("postgresql+psycopg://deepaha:test@127.0.0.1:55436/deepaha")
