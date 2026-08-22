from dataclasses import asdict
from uuid import UUID

import pytest

import tests.notifications.seed_phase8_browser as browser_seed
from tests.notifications.support import (
    FIXTURE_MARKER,
    Phase8EngineeringReport,
    load_phase8_deadline_fixture,
    validate_phase8_deadline_fixture_bytes,
)


def test_phase8_fixture_is_fixed_synthetic_delivery_evidence_only() -> None:
    fixture, manifest = load_phase8_deadline_fixture()

    assert fixture.marker == manifest.marker == FIXTURE_MARKER
    assert fixture.synthetic is True
    assert fixture.release_qualification_eligible is False
    assert manifest.human_participant_count == 0
    assert manifest.human_track == "NOT_STARTED"
    assert manifest.release_qualification == "NOT_STARTED"
    assert manifest.release_decision == "HOLD_MISSING_HUMAN_EVIDENCE"
    assert fixture.evidence_boundary.real_participants == 0


def test_manifest_declares_exact_versions_evidence_audiences_and_counts() -> None:
    fixture, manifest = load_phase8_deadline_fixture()

    assert manifest.scenario_clock == fixture.scenario_clock
    assert manifest.opportunity_public_id == fixture.opportunity.public_id
    assert (manifest.from_version, manifest.to_version) == (6, 7)
    assert manifest.previous_evidence_ref_id == fixture.opportunity.previous_evidence_ref_id
    assert manifest.current_evidence_ref_id == fixture.opportunity.current_evidence_ref_id
    assert manifest.audience_expected_reminders == {
        item.role: item.expected_reminder_count for item in fixture.audiences
    }
    assert sum(manifest.audience_expected_reminders.values()) == 1
    assert (
        len([value for value in manifest.audience_expected_reminders.values() if value == 0]) == 4
    )
    assert manifest.expected_engineering_counts == fixture.expected_engineering_counts


def test_engineering_report_is_counts_only_and_never_human_metrics() -> None:
    fixture, _manifest = load_phase8_deadline_fixture()
    report = Phase8EngineeringReport(**fixture.expected_engineering_counts)

    assert asdict(report) == fixture.expected_engineering_counts
    serialized = str(asdict(report)).lower()
    for forbidden in ("open_rate", "complaint", "retention", "human_action"):
        assert forbidden not in serialized


def test_fixture_hash_mismatch_fails_closed() -> None:
    fixture, manifest = load_phase8_deadline_fixture()

    with pytest.raises(ValueError, match="hash does not match"):
        validate_phase8_deadline_fixture_bytes(
            fixture.model_dump_json().encode(),
            manifest.model_dump_json().encode(),
        )


def test_nonqualifying_fixture_cases_never_claim_engineering_candidates() -> None:
    fixture, _manifest = load_phase8_deadline_fixture()

    assert fixture.qualifying_event.expected_candidate_count == 1
    assert {item.case: item.expected_candidate_count for item in fixture.non_qualifying_events} == {
        "multi_field_update": 0,
        "cancellation": 0,
    }


def test_browser_seeder_prints_only_synthetic_token_and_expected_route(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    identity = browser_seed.Phase8BrowserIdentity(
        user_id=UUID("019b0000-0000-7000-8000-000000000831"),
        bearer_token="fixed-synthetic-token",
        route="/me/reminders",
        opportunity_public_id="opp_63be197cc6ef3632650c5f69b5938f0b",
    )
    monkeypatch.setenv(
        "DEEPAHA_DATABASE_URL",
        "postgresql+psycopg://deepaha:fixture@127.0.0.1:55438/deepaha",
    )
    monkeypatch.setattr(browser_seed, "seed_phase8_browser", lambda _database_url: identity)

    browser_seed.main()

    output = capsys.readouterr().out
    assert FIXTURE_MARKER in output
    assert "real participants=0" in output
    assert "Release Qualification=NOT_STARTED" in output
    assert "bearer_token=fixed-synthetic-token" in output
    assert "web_route=/me/reminders" in output
