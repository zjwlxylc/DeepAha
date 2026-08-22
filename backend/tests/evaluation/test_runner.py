from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest

from deepaha.contracts.phase4 import EligibilityStatus
from deepaha.evaluation.fixtures import GoldenCaseFixture, load_fixture_bundle
from deepaha.evaluation.runner import (
    CaseEvaluation,
    UnexpectedIneligibleError,
    run_synthetic_evaluation,
)

FIXTURE_DIRECTORY = Path(__file__).parents[1] / "fixtures" / "evaluation"


def _uuid7_from_label(label: str) -> UUID:
    raw = bytearray(sha256(label.encode("utf-8")).digest()[:16])
    raw[6] = (raw[6] & 0x0F) | 0x70
    raw[8] = (raw[8] & 0x3F) | 0x80
    return UUID(bytes=bytes(raw))


def _expected_evaluator(case: GoldenCaseFixture) -> CaseEvaluation:
    return CaseEvaluation(
        actual_status=case.expected_status,
        match_snapshot_id=_uuid7_from_label(case.case_id),
        input_sha256=sha256(case.case_id.encode("utf-8")).hexdigest(),
        reason_codes=("SYNTHETIC_EXPECTED_RESULT",),
        replay_matched=True,
    )


def test_runner_sorts_cases_and_computes_integer_safety_counts() -> None:
    bundle = load_fixture_bundle(FIXTURE_DIRECTORY)
    reversed_bundle = replace(bundle, golden_cases=tuple(reversed(bundle.golden_cases)))

    report = run_synthetic_evaluation(reversed_bundle, _expected_evaluator)
    metrics = report.metrics

    assert tuple(result.case_id for result in report.case_results) == tuple(
        sorted(case.case_id for case in bundle.golden_cases)
    )
    assert metrics.case_count == len(bundle.golden_cases)
    assert metrics.expected_ineligible_count == 3
    assert metrics.actual_ineligible_count == 3
    assert metrics.unexpected_ineligible_count == 0
    assert metrics.unexpected_ineligible_case_ids == ()
    assert metrics.passed_case_count == len(bundle.golden_cases)


def test_report_is_deterministic_and_explicitly_synthetic_only() -> None:
    bundle = load_fixture_bundle(FIXTURE_DIRECTORY)
    first = run_synthetic_evaluation(bundle, _expected_evaluator)
    second = run_synthetic_evaluation(bundle, _expected_evaluator)

    assert first.report_sha256 == second.report_sha256
    assert first.evidence_label == "SYNTHETIC_EVALUATION_ONLY"
    assert first.dataset_version == "phase4-synthetic-golden-v1"
    assert first.component_versions.contract == "0.4.0"
    assert first.component_versions.compiler == "phase4-rule-compiler-v1"
    assert first.component_versions.engine == "phase4-eligibility-engine-v1"
    assert first.component_versions.major_catalog == bundle.major_catalog.version
    assert first.component_versions.major_mapping == bundle.major_mapping.version
    serialized = json.dumps(first.to_payload(), sort_keys=True)
    for forbidden in (
        "production_accuracy",
        "retention",
        "willingness_to_pay",
        "0.5%",
    ):
        assert forbidden not in serialized


def test_runner_stops_on_a_protected_unexpected_ineligible() -> None:
    bundle = load_fixture_bundle(FIXTURE_DIRECTORY)
    protected = next(
        case for case in bundle.golden_cases if case.protected_from_unexpected_ineligible
    )

    def unsafe_evaluator(case: GoldenCaseFixture) -> CaseEvaluation:
        evaluation = _expected_evaluator(case)
        if case.case_id != protected.case_id:
            return evaluation
        return replace(evaluation, actual_status=EligibilityStatus.INELIGIBLE)

    with pytest.raises(UnexpectedIneligibleError, match=protected.case_id):
        run_synthetic_evaluation(bundle, unsafe_evaluator)


def test_replay_mismatch_is_an_integer_count_and_reason() -> None:
    bundle = load_fixture_bundle(FIXTURE_DIRECTORY)
    first_case = min(bundle.golden_cases, key=lambda case: case.case_id)

    def mismatch_evaluator(case: GoldenCaseFixture) -> CaseEvaluation:
        evaluation = _expected_evaluator(case)
        if case.case_id == first_case.case_id:
            return replace(evaluation, replay_matched=False)
        return evaluation

    report = run_synthetic_evaluation(bundle, mismatch_evaluator)

    assert report.metrics.replay_mismatch_count == 1
    assert "REPLAY_MISMATCH" in report.case_results[0].reason_codes
