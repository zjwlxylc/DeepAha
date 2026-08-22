from hashlib import sha256
from pathlib import Path

import pytest

from tests.feedback.seed_phase7_browser import assert_phase7_browser_database_url
from tests.feedback.support import (
    PHASE7_FIXTURE_PATH,
    PHASE7_MANIFEST_PATH,
    load_phase7_feedback_fixture,
    validate_phase7_feedback_fixture_bytes,
)


def test_phase7_fixture_is_fixed_cc0_synthetic_evidence_only() -> None:
    first = load_phase7_feedback_fixture()
    second = load_phase7_feedback_fixture()

    assert first == second
    assert first.synthetic is True
    assert first.contains_personal_data is False
    assert first.business_truth is False
    assert first.release_qualification_eligible is False
    assert first.license == "CC0-1.0 synthetic fixture"
    assert first.feedback.claim_kind == "EXPLANATION_UNCLEAR"
    assert first.validation.direction == "EXPLANATION_CLARITY"
    assert first.validation.component == "personal-explanation"
    assert first.validation.simulation.release_qualification_eligible is False
    assert first.validation.expected_gate_decision == "HOLD_MISSING_HUMAN_EVIDENCE"


def test_phase7_manifest_binds_exact_fixture_bytes() -> None:
    fixture_bytes = PHASE7_FIXTURE_PATH.read_bytes()
    manifest_bytes = PHASE7_MANIFEST_PATH.read_bytes()

    first = validate_phase7_feedback_fixture_bytes(fixture_bytes, manifest_bytes)
    second = validate_phase7_feedback_fixture_bytes(fixture_bytes, manifest_bytes)

    assert first == second
    assert sha256(fixture_bytes).hexdigest() in manifest_bytes.decode("utf-8")


def test_phase7_fixture_tamper_fails_before_json_parsing() -> None:
    fixture_bytes = bytearray(PHASE7_FIXTURE_PATH.read_bytes())
    fixture_bytes[-2] = ord("!")

    with pytest.raises(ValueError, match="hash does not match"):
        validate_phase7_feedback_fixture_bytes(
            bytes(fixture_bytes),
            PHASE7_MANIFEST_PATH.read_bytes(),
        )


def test_phase7_fixture_contains_no_plaintext_credentials() -> None:
    fixture_text = PHASE7_FIXTURE_PATH.read_text(encoding="utf-8").lower()

    for forbidden in ("password", "session_token", "bearer", "authorization"):
        assert forbidden not in fixture_text


@pytest.mark.parametrize(
    "candidate",
    [
        *(
            f"postgresql+psycopg://deepaha:test@127.0.0.1:{port}/deepaha"
            for port in range(55432, 55437)
        ),
        "postgresql+psycopg://deepaha:test@localhost:55437/deepaha",
        "postgresql+psycopg://deepaha:test@127.0.0.1:55437/other",
        "postgresql+psycopg://deepaha:test@example.test:55437/deepaha",
    ],
)
def test_phase7_browser_seed_rejects_every_non_exact_database(candidate: str) -> None:
    with pytest.raises(ValueError, match="127.0.0.1:55437/deepaha"):
        assert_phase7_browser_database_url(candidate)


def test_phase7_browser_seed_accepts_only_the_exact_disposable_database() -> None:
    assert_phase7_browser_database_url("postgresql+psycopg://deepaha:test@127.0.0.1:55437/deepaha")


def test_phase7_fixture_paths_stay_inside_declared_feedback_directory() -> None:
    expected = Path(__file__).parents[1] / "fixtures" / "feedback"

    assert PHASE7_FIXTURE_PATH.parent == expected
    assert PHASE7_MANIFEST_PATH.parent == expected
