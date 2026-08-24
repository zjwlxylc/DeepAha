from datetime import UTC, datetime, timedelta

from deepaha.contracts.phase9b import GoldFieldState, PredictionFieldState
from deepaha.p9b.benchmark import (
    GoldBenchmarkFact,
    PredictedBenchmarkFact,
    UnitSegmentationCase,
    evaluate_benchmark,
)

CUTOFF = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


def test_benchmark_reports_explicit_denominators_and_unknown_semantics() -> None:
    gold = [
        GoldBenchmarkFact(
            "u1", "deadline", GoldFieldState.KNOWN_SUPPORTED, "2026-09-01", True, False, "g1"
        ),
        GoldBenchmarkFact("u1", "age_max", GoldFieldState.KNOWN_SUPPORTED, 35, True, False, "g1"),
        GoldBenchmarkFact(
            "u1", "category", GoldFieldState.KNOWN_SUPPORTED, "PUBLIC", False, False, "g1"
        ),
        GoldBenchmarkFact("u1", "residency", GoldFieldState.AMBIGUOUS, None, True, False, "g1"),
        GoldBenchmarkFact(
            "u1", "certificate", GoldFieldState.KNOWN_NOT_APPLICABLE, None, True, False, "g1"
        ),
    ]
    predictions = [
        PredictedBenchmarkFact(
            "u1", "deadline", PredictionFieldState.VALUE, "2026-09-01", True, CUTOFF
        ),
        PredictedBenchmarkFact("u1", "residency", PredictionFieldState.UNKNOWN, None, False, None),
        PredictedBenchmarkFact(
            "u1", "certificate", PredictionFieldState.VALUE, "CET6", False, CUTOFF
        ),
        PredictedBenchmarkFact(
            "u1", "category", PredictionFieldState.VALUE, "PUBLIC", True, CUTOFF + timedelta(days=1)
        ),
    ]

    report = evaluate_benchmark(gold, predictions, evaluation_as_of=CUTOFF)

    assert report.metrics["strict_fact_precision"].fraction == (1, 3)
    assert report.metrics["strict_fact_recall"].fraction == (1, 3)
    assert report.metrics["critical_silent_omission_rate"].fraction == (1, 2)
    assert report.metrics["unsupported_assertion_rate"].fraction == (2, 3)
    assert report.metrics["evidence_support_precision"].fraction == (1, 3)
    assert report.metrics["correct_abstention_rate"].fraction == (1, 1)
    assert report.metrics["unnecessary_abstention_rate"].fraction == (0, 3)
    assert report.metrics["overclaim_on_ambiguous_rate"].fraction == (0, 1)
    assert report.metrics["future_evidence_violation_rate"].fraction == (1, 3)
    assert report.silent_omissions == (("u1", "age_max"),)


def test_precedence_and_unit_segmentation_have_separate_support() -> None:
    gold = [
        GoldBenchmarkFact(
            "u1", "deadline", GoldFieldState.KNOWN_SUPPORTED, "new", True, True, "g1"
        ),
        GoldBenchmarkFact(
            "u2", "deadline", GoldFieldState.KNOWN_SUPPORTED, "new", True, True, "g2"
        ),
    ]
    predictions = [
        PredictedBenchmarkFact("u1", "deadline", PredictionFieldState.VALUE, "new", True, CUTOFF),
        PredictedBenchmarkFact("u2", "deadline", PredictionFieldState.VALUE, "old", True, CUTOFF),
    ]
    segmentation = UnitSegmentationCase(
        expected_unit_ids=frozenset({"u1", "u2"}),
        predicted_unit_ids=frozenset({"u1", "u3"}),
        singleton_expected=False,
    )

    report = evaluate_benchmark(
        gold,
        predictions,
        evaluation_as_of=CUTOFF,
        segmentation_cases=[segmentation],
    )

    assert report.metrics["precedence_accuracy"].fraction == (1, 2)
    assert report.metrics["unit_identity_precision"].fraction == (1, 2)
    assert report.metrics["unit_identity_recall"].fraction == (1, 2)
    assert report.metrics["unit_identity_f1"].value == 0.5
    assert report.metrics["opportunity_unit_count_accuracy"].fraction == (1, 1)


def test_zero_support_is_not_observed_not_a_pass() -> None:
    report = evaluate_benchmark([], [], evaluation_as_of=CUTOFF)

    assert all(metric.status == "NOT_OBSERVED" for metric in report.metrics.values())
    assert all(metric.value is None for metric in report.metrics.values())


def test_report_includes_required_slices_and_atomic_group_bootstrap() -> None:
    gold = [
        GoldBenchmarkFact(
            "u1",
            "deadline",
            GoldFieldState.KNOWN_SUPPORTED,
            "new",
            True,
            False,
            "atomic-1",
            field_type="DATE",
            opportunity_category="PUBLIC_SERVICE",
            complexity="C3",
            source_template_group="gov-table-v1",
        )
    ]
    predictions = [
        PredictedBenchmarkFact("u1", "deadline", PredictionFieldState.VALUE, "new", True, CUTOFF)
    ]

    report = evaluate_benchmark(gold, predictions, evaluation_as_of=CUTOFF)

    assert "opportunity_unit:u1" in report.slice_metrics
    assert "field_type:DATE" in report.slice_metrics
    assert "opportunity_category:PUBLIC_SERVICE" in report.slice_metrics
    assert "complexity:C3" in report.slice_metrics
    assert "source_template_group:gov-table-v1" in report.slice_metrics
    assert "high_impact_only:ALL" in report.slice_metrics
    assert report.atomic_group_macro["strict_fact_precision"].support_count == 1
    assert report.atomic_group_macro["strict_fact_precision"].ci95_low == 1.0
