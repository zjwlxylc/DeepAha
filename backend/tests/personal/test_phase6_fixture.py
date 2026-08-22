import pytest

from tests.personal.seed_phase6_browser import assert_phase6_browser_database_url
from tests.personal.support import load_phase6_fixture


def test_phase6_fixture_is_non_personal_synthetic_evidence() -> None:
    fixture = load_phase6_fixture()

    assert fixture.synthetic is True
    assert fixture.contains_personal_data is False
    assert fixture.business_truth is False
    assert fixture.release_qualification_eligible is False
    assert len(fixture.users) == 2


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
