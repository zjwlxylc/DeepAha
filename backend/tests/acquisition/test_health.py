from datetime import UTC, datetime, timedelta

import pytest

from deepaha.acquisition.contracts import (
    AcquisitionRunSchema,
    SourceIntegrationEvidenceSchema,
)
from deepaha.acquisition.health import (
    HealthState,
    InsufficientIntegrationEvidence,
    compute_integration_cost_gate,
    derive_acquisition_health,
)

NOW = datetime(2026, 8, 23, 14, 0, tzinfo=UTC)
SOURCE_ID = "019c0000-0000-7000-8000-000000000801"
ENDPOINT_ID = "019c0000-0000-7000-8000-000000000802"
RECIPE_ID = "019c0000-0000-7000-8000-000000000803"


def run(index: int, **changes: object) -> AcquisitionRunSchema:
    started = NOW + timedelta(minutes=index * 10)
    values: dict[str, object] = {
        "acquisition_run_id": f"019c0000-0000-7000-8000-{index + 804:012d}",
        "recipe_id": RECIPE_ID,
        "source_id": SOURCE_ID,
        "endpoint_id": ENDPOINT_ID,
        "endpoint_policy_version": "policy-v1",
        "recipe_version": "recipe-v1",
        "started_at": started,
        "completed_at": started + timedelta(seconds=2),
        "terminal_code": "COMPLETE",
        "request_count": 1,
        "strategy_attempts": [
            {"strategy": "STATIC_HTTP", "validation_status": "VALID", "error_code": None}
        ],
        "discovered_count": 3,
        "validated_count": 1,
        "parsed_count": 1,
        "attachment_count": 1,
        "evidence_count": 2,
        "zero_discovery_flag": False,
        "selector_drift_flag": False,
        "manual_intervention": False,
        "stable_stop_reason": None,
        "contract_version": "1.0.0",
    }
    values.update(changes)
    return AcquisitionRunSchema.model_validate(values)


def integration(index: int, **changes: object) -> SourceIntegrationEvidenceSchema:
    values: dict[str, object] = {
        "source_integration_evidence_id": f"019c0000-0000-7000-8000-{index + 900:012d}",
        "recipe_id": f"019c0000-0000-7000-8000-{index + 920:012d}",
        "source_id": f"019c0000-0000-7000-8000-{index + 940:012d}",
        "endpoint_id": f"019c0000-0000-7000-8000-{index + 960:012d}",
        "recipe_version": f"recipe-v{index}",
        "primary_fetcher": "deepaha-static-http",
        "onboarding_mode": "RECIPE_ONLY",
        "reused_existing_fetcher": True,
        "recipe_line_count": 40,
        "source_specific_production_loc": 0,
        "generic_capability_changes": 0,
        "core_schema_changed": False,
        "onboarding_minutes": 30,
        "total_request_count": 5,
        "browser_request_count": 0,
        "manual_request_count": 0,
        "run_failure_count": 0,
        "maintenance_minutes": 0,
        "recorded_at": NOW + timedelta(minutes=index),
        "contract_version": "1.0.0",
    }
    values.update(changes)
    return SourceIntegrationEvidenceSchema.model_validate(values)


def test_no_runs_is_explicit_unknown() -> None:
    health = derive_acquisition_health(
        (),
        source_id=SOURCE_ID,
        endpoint_id=ENDPOINT_ID,
        as_of=NOW,
        zero_discovery_grace_runs=1,
        selector_drift_grace_runs=0,
    )

    assert health.run_count == 0
    assert {
        health.accessibility,
        health.discovery,
        health.fetch_integrity,
        health.parseability,
        health.evidenceability,
        health.drift,
    } == {HealthState.UNKNOWN}
    assert health.last_valid_success_at is None


def test_valid_run_keeps_six_health_dimensions_distinct() -> None:
    health = derive_acquisition_health(
        (run(0),),
        source_id=SOURCE_ID,
        endpoint_id=ENDPOINT_ID,
        as_of=NOW + timedelta(hours=1),
        zero_discovery_grace_runs=1,
        selector_drift_grace_runs=0,
    )

    assert health.accessibility is HealthState.HEALTHY
    assert health.discovery is HealthState.HEALTHY
    assert health.fetch_integrity is HealthState.HEALTHY
    assert health.parseability is HealthState.HEALTHY
    assert health.evidenceability is HealthState.HEALTHY
    assert health.drift is HealthState.HEALTHY
    assert health.consecutive_semantic_failures == 0
    assert health.last_valid_success_at == run(0).completed_at


def test_http_challenge_is_blocked_access_but_preserves_fetch_integrity() -> None:
    challenge = run(
        0,
        terminal_code="CONTENT_CHALLENGE",
        strategy_attempts=[
            {
                "strategy": "STATIC_HTTP",
                "validation_status": "CONTENT_CHALLENGE",
                "error_code": "JAVASCRIPT_COOKIE_CHALLENGE",
            }
        ],
        discovered_count=0,
        validated_count=0,
        parsed_count=0,
        attachment_count=0,
        evidence_count=0,
        stable_stop_reason="CONTENT_CHALLENGE",
    )
    health = derive_acquisition_health(
        (challenge,),
        source_id=SOURCE_ID,
        endpoint_id=ENDPOINT_ID,
        as_of=NOW + timedelta(hours=1),
        zero_discovery_grace_runs=1,
        selector_drift_grace_runs=0,
    )

    assert health.accessibility is HealthState.BLOCKED
    assert health.fetch_integrity is HealthState.HEALTHY
    assert health.discovery is HealthState.UNKNOWN
    assert health.parseability is HealthState.UNKNOWN
    assert health.last_valid_success_at is None


def test_zero_discovery_and_selector_drift_use_declared_grace_runs() -> None:
    zero_attempt = [
        {
            "strategy": "STATIC_HTTP",
            "validation_status": "ZERO_DISCOVERY_SUSPECT",
            "error_code": "MINIMUM_DISCOVERY_NOT_MET",
        }
    ]
    zero_runs = tuple(
        run(
            index,
            terminal_code="PLAN_EXHAUSTED",
            strategy_attempts=zero_attempt,
            discovered_count=0,
            validated_count=0,
            parsed_count=0,
            attachment_count=0,
            evidence_count=0,
            zero_discovery_flag=True,
            stable_stop_reason="PLAN_EXHAUSTED",
        )
        for index in range(2)
    )
    health = derive_acquisition_health(
        zero_runs,
        source_id=SOURCE_ID,
        endpoint_id=ENDPOINT_ID,
        as_of=NOW + timedelta(hours=1),
        zero_discovery_grace_runs=1,
        selector_drift_grace_runs=0,
    )
    assert health.zero_discovery_runs == 2
    assert health.discovery is HealthState.DEGRADED
    assert health.drift is HealthState.DEGRADED

    selector = run(
        3,
        terminal_code="PLAN_EXHAUSTED",
        strategy_attempts=[
            {
                "strategy": "STATIC_HTTP",
                "validation_status": "SELECTOR_DRIFT",
                "error_code": "REQUIRED_SELECTOR_MISSING",
            }
        ],
        discovered_count=0,
        validated_count=0,
        parsed_count=0,
        attachment_count=0,
        evidence_count=0,
        selector_drift_flag=True,
        stable_stop_reason="PLAN_EXHAUSTED",
    )
    health = derive_acquisition_health(
        (*zero_runs, selector),
        source_id=SOURCE_ID,
        endpoint_id=ENDPOINT_ID,
        as_of=NOW + timedelta(hours=1),
        zero_discovery_grace_runs=5,
        selector_drift_grace_runs=0,
    )
    assert health.selector_drift_runs == 1
    assert health.drift is HealthState.DEGRADED


def test_last_valid_success_failures_and_browser_manual_ratios_are_deterministic() -> None:
    browser_failure = run(
        1,
        terminal_code="PLAN_EXHAUSTED",
        strategy_attempts=[
            {
                "strategy": "BROWSER",
                "validation_status": "UNEXPECTED_CONTENT",
                "error_code": "REQUIRED_MARKER_MISSING",
            }
        ],
        discovered_count=0,
        validated_count=0,
        parsed_count=0,
        attachment_count=0,
        evidence_count=0,
        stable_stop_reason="PLAN_EXHAUSTED",
    )
    manual_failure = run(
        2,
        terminal_code="PLAN_EXHAUSTED",
        strategy_attempts=[
            {
                "strategy": "MANUAL",
                "validation_status": "UNEXPECTED_CONTENT",
                "error_code": "REQUIRED_MARKER_MISSING",
            }
        ],
        discovered_count=0,
        validated_count=0,
        parsed_count=0,
        attachment_count=0,
        evidence_count=0,
        manual_intervention=True,
        stable_stop_reason="PLAN_EXHAUSTED",
    )
    health = derive_acquisition_health(
        (run(0), browser_failure, manual_failure),
        source_id=SOURCE_ID,
        endpoint_id=ENDPOINT_ID,
        as_of=NOW + timedelta(hours=1),
        zero_discovery_grace_runs=1,
        selector_drift_grace_runs=0,
    )

    assert health.consecutive_semantic_failures == 2
    assert health.last_valid_success_at == run(0).completed_at
    assert health.browser_ratio == pytest.approx(1 / 3)
    assert health.manual_ratio == pytest.approx(1 / 3)


def test_successful_run_resets_consecutive_drift_counters() -> None:
    zero_attempt = [
        {
            "strategy": "STATIC_HTTP",
            "validation_status": "ZERO_DISCOVERY_SUSPECT",
            "error_code": "MINIMUM_DISCOVERY_NOT_MET",
        }
    ]
    prior_zero = run(
        0,
        terminal_code="PLAN_EXHAUSTED",
        strategy_attempts=zero_attempt,
        discovered_count=0,
        validated_count=0,
        parsed_count=0,
        attachment_count=0,
        evidence_count=0,
        zero_discovery_flag=True,
        stable_stop_reason="PLAN_EXHAUSTED",
    )
    health = derive_acquisition_health(
        (prior_zero, run(1)),
        source_id=SOURCE_ID,
        endpoint_id=ENDPOINT_ID,
        as_of=NOW + timedelta(hours=1),
        zero_discovery_grace_runs=0,
        selector_drift_grace_runs=0,
    )

    assert health.zero_discovery_runs == 0
    assert health.drift is HealthState.HEALTHY


def test_future_run_is_rejected_by_fixed_as_of_clock() -> None:
    with pytest.raises(ValueError, match="after as_of"):
        derive_acquisition_health(
            (run(0),),
            source_id=SOURCE_ID,
            endpoint_id=ENDPOINT_ID,
            as_of=NOW - timedelta(seconds=1),
            zero_discovery_grace_runs=1,
            selector_drift_grace_runs=0,
        )


def test_integration_cost_requires_five_complete_sources() -> None:
    with pytest.raises(InsufficientIntegrationEvidence):
        compute_integration_cost_gate(tuple(integration(index) for index in range(4)))


def test_first_five_cost_gate_uses_persisted_reuse_and_recipe_thin_facts() -> None:
    evidence = (
        integration(0),
        integration(1, onboarding_mode="THIN_PLUGIN", source_specific_production_loc=12),
        integration(2),
        integration(
            3,
            onboarding_mode="GENERIC_CAPABILITY",
            generic_capability_changes=1,
            reused_existing_fetcher=False,
        ),
        integration(
            4,
            onboarding_mode="NEW_FETCHER",
            primary_fetcher="new-fetcher",
            reused_existing_fetcher=False,
        ),
    )

    gate = compute_integration_cost_gate(evidence)

    assert gate.sample_count == 5
    assert gate.existing_fetcher_reuse_count == 3
    assert gate.recipe_or_thin_count == 3
    assert gate.existing_fetcher_reuse_ratio == pytest.approx(0.6)
    assert gate.recipe_or_thin_ratio == pytest.approx(0.6)
    assert gate.status == "PASS"
