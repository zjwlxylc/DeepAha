from dataclasses import dataclass
from datetime import datetime
from math import sqrt
from random import Random
from typing import Any

from deepaha.contracts.phase9b import GoldFieldState, PredictionFieldState


@dataclass(frozen=True)
class GoldBenchmarkFact:
    target_identity: str
    field_name: str
    state: GoldFieldState
    normalized_value: Any | None
    high_impact: bool
    precedence_sensitive: bool
    atomic_group_id: str
    field_type: str = "UNSPECIFIED"
    opportunity_category: str = "UNSPECIFIED"
    complexity: str = "UNSPECIFIED"
    source_template_group: str = "UNSPECIFIED"


@dataclass(frozen=True)
class PredictedBenchmarkFact:
    target_identity: str
    field_name: str
    state: PredictionFieldState
    normalized_value: Any | None
    evidence_supported: bool
    evidence_published_at: datetime | None


@dataclass(frozen=True)
class UnitSegmentationCase:
    expected_unit_ids: frozenset[str]
    predicted_unit_ids: frozenset[str]
    singleton_expected: bool


@dataclass(frozen=True)
class BenchmarkMetric:
    numerator: int
    denominator: int
    support_count: int
    value: float | None
    ci95_low: float | None
    ci95_high: float | None
    status: str

    @property
    def fraction(self) -> tuple[int, int]:
        return self.numerator, self.denominator


@dataclass(frozen=True)
class BenchmarkReport:
    metrics: dict[str, BenchmarkMetric]
    silent_omissions: tuple[tuple[str, str], ...]
    slice_metrics: dict[str, dict[str, BenchmarkMetric]]
    atomic_group_macro: dict[str, BenchmarkMetric]


def _bootstrap_mean(values: list[float]) -> tuple[float, float, float]:
    mean = sum(values) / len(values)
    if len(values) == 1:
        return mean, mean, mean
    random = Random(9_021)
    estimates = sorted(
        sum(random.choice(values) for _ in values) / len(values) for _ in range(2_000)
    )
    return mean, estimates[49], estimates[1_949]


def _metric(numerator: int, denominator: int) -> BenchmarkMetric:
    if denominator == 0:
        return BenchmarkMetric(0, 0, 0, None, None, None, "NOT_OBSERVED")
    value = numerator / denominator
    z = 1.959963984540054
    adjusted = 1 + z * z / denominator
    center = (value + z * z / (2 * denominator)) / adjusted
    margin = z * sqrt((value * (1 - value) + z * z / (4 * denominator)) / denominator) / adjusted
    return BenchmarkMetric(
        numerator,
        denominator,
        denominator,
        value,
        max(0.0, center - margin),
        min(1.0, center + margin),
        "OBSERVED",
    )


def evaluate_benchmark(
    gold_facts: list[GoldBenchmarkFact],
    predictions: list[PredictedBenchmarkFact],
    *,
    evaluation_as_of: datetime,
    segmentation_cases: list[UnitSegmentationCase] | None = None,
    _include_slices: bool = True,
) -> BenchmarkReport:
    gold = {(item.target_identity, item.field_name): item for item in gold_facts}
    predicted = {(item.target_identity, item.field_name): item for item in predictions}
    values = [item for item in predictions if item.state == PredictionFieldState.VALUE]

    def timely_supported(item: PredictedBenchmarkFact) -> bool:
        return bool(
            item.evidence_supported
            and item.evidence_published_at is not None
            and item.evidence_published_at <= evaluation_as_of
        )

    def exact(item: PredictedBenchmarkFact, expected: GoldBenchmarkFact | None) -> bool:
        return bool(
            expected is not None
            and expected.state == GoldFieldState.KNOWN_SUPPORTED
            and item.normalized_value == expected.normalized_value
            and timely_supported(item)
        )

    exact_values = sum(
        exact(item, gold.get((item.target_identity, item.field_name))) for item in values
    )
    unsupported = sum(
        not timely_supported(item)
        or gold.get((item.target_identity, item.field_name)) is None
        or gold[(item.target_identity, item.field_name)].state
        in {GoldFieldState.KNOWN_NOT_APPLICABLE, GoldFieldState.AMBIGUOUS}
        for item in values
    )
    known = [item for item in gold_facts if item.state == GoldFieldState.KNOWN_SUPPORTED]
    high_known = [item for item in known if item.high_impact]
    silent = tuple(
        (item.target_identity, item.field_name)
        for item in high_known
        if (candidate := predicted.get((item.target_identity, item.field_name))) is None
        or candidate.state == PredictionFieldState.OMITTED
    )
    ambiguous = [item for item in gold_facts if item.state == GoldFieldState.AMBIGUOUS]
    correct_abstentions = sum(
        predicted.get((item.target_identity, item.field_name)) is not None
        and predicted[(item.target_identity, item.field_name)].state == PredictionFieldState.UNKNOWN
        for item in ambiguous
    )
    unnecessary_abstentions = sum(
        predicted.get((item.target_identity, item.field_name)) is not None
        and predicted[(item.target_identity, item.field_name)].state == PredictionFieldState.UNKNOWN
        for item in known
    )
    ambiguous_overclaims = sum(
        predicted.get((item.target_identity, item.field_name)) is not None
        and predicted[(item.target_identity, item.field_name)].state == PredictionFieldState.VALUE
        for item in ambiguous
    )
    precedence = [item for item in known if item.precedence_sensitive]
    precedence_correct = sum(
        (candidate := predicted.get((item.target_identity, item.field_name))) is not None
        and exact(candidate, item)
        for item in precedence
    )
    future_evidence = sum(
        item.evidence_published_at is not None and item.evidence_published_at > evaluation_as_of
        for item in values
    )

    metrics = {
        "strict_fact_precision": _metric(exact_values, len(values)),
        "strict_fact_recall": _metric(
            sum(
                (candidate := predicted.get((item.target_identity, item.field_name))) is not None
                and exact(candidate, item)
                for item in known
            ),
            len(known),
        ),
        "critical_silent_omission_rate": _metric(len(silent), len(high_known)),
        "unsupported_assertion_rate": _metric(unsupported, len(values)),
        "evidence_support_precision": _metric(
            sum(timely_supported(item) for item in values), len(values)
        ),
        "correct_abstention_rate": _metric(correct_abstentions, len(ambiguous)),
        "unnecessary_abstention_rate": _metric(unnecessary_abstentions, len(known)),
        "overclaim_on_ambiguous_rate": _metric(ambiguous_overclaims, len(ambiguous)),
        "precedence_accuracy": _metric(precedence_correct, len(precedence)),
        "future_evidence_violation_rate": _metric(future_evidence, len(values)),
    }

    cases = segmentation_cases or []
    expected_total = sum(len(case.expected_unit_ids) for case in cases)
    predicted_total = sum(len(case.predicted_unit_ids) for case in cases)
    matched_total = sum(len(case.expected_unit_ids & case.predicted_unit_ids) for case in cases)
    precision = _metric(matched_total, predicted_total)
    recall = _metric(matched_total, expected_total)
    if precision.value is None or recall.value is None or precision.value + recall.value == 0:
        f1 = _metric(0, 0)
    else:
        f1_value = 2 * precision.value * recall.value / (precision.value + recall.value)
        f1 = BenchmarkMetric(
            matched_total,
            max(expected_total, predicted_total),
            len(cases),
            f1_value,
            None,
            None,
            "OBSERVED",
        )
    metrics.update(
        {
            "unit_identity_precision": precision,
            "unit_identity_recall": recall,
            "unit_identity_f1": f1,
            "opportunity_unit_count_accuracy": _metric(
                sum(len(case.expected_unit_ids) == len(case.predicted_unit_ids) for case in cases),
                len(cases),
            ),
            "singleton_fallback_accuracy": _metric(
                sum(
                    case.predicted_unit_ids == case.expected_unit_ids
                    for case in cases
                    if case.singleton_expected
                ),
                sum(case.singleton_expected for case in cases),
            ),
        }
    )
    if not _include_slices:
        return BenchmarkReport(
            metrics=metrics,
            silent_omissions=silent,
            slice_metrics={},
            atomic_group_macro={},
        )

    slice_groups: dict[str, list[GoldBenchmarkFact]] = {}
    for item in gold_facts:
        for dimension, value in (
            ("opportunity_unit", item.target_identity),
            ("field_type", item.field_type),
            ("opportunity_category", item.opportunity_category),
            ("complexity", item.complexity),
            ("source_template_group", item.source_template_group),
        ):
            slice_groups.setdefault(f"{dimension}:{value}", []).append(item)
        if item.high_impact:
            slice_groups.setdefault("high_impact_only:ALL", []).append(item)
    prediction_by_key = {(item.target_identity, item.field_name): item for item in predictions}
    slice_metrics: dict[str, dict[str, BenchmarkMetric]] = {}
    for slice_name, slice_gold in sorted(slice_groups.items()):
        keys = {(item.target_identity, item.field_name) for item in slice_gold}
        slice_predictions = [prediction_by_key[key] for key in keys if key in prediction_by_key]
        slice_metrics[slice_name] = evaluate_benchmark(
            slice_gold,
            slice_predictions,
            evaluation_as_of=evaluation_as_of,
            _include_slices=False,
        ).metrics

    atomic_reports: list[BenchmarkReport] = []
    for group_id in sorted({item.atomic_group_id for item in gold_facts}):
        group_gold = [item for item in gold_facts if item.atomic_group_id == group_id]
        keys = {(item.target_identity, item.field_name) for item in group_gold}
        group_predictions = [prediction_by_key[key] for key in keys if key in prediction_by_key]
        atomic_reports.append(
            evaluate_benchmark(
                group_gold,
                group_predictions,
                evaluation_as_of=evaluation_as_of,
                _include_slices=False,
            )
        )
    atomic_macro: dict[str, BenchmarkMetric] = {}
    for metric_name in metrics:
        macro_values = [
            report.metrics[metric_name].value
            for report in atomic_reports
            if report.metrics[metric_name].value is not None
        ]
        observed = [value for value in macro_values if value is not None]
        if not observed:
            atomic_macro[metric_name] = _metric(0, 0)
            continue
        mean, low, high = _bootstrap_mean(observed)
        atomic_macro[metric_name] = BenchmarkMetric(
            numerator=0,
            denominator=len(observed),
            support_count=len(observed),
            value=mean,
            ci95_low=low,
            ci95_high=high,
            status="OBSERVED",
        )
    return BenchmarkReport(
        metrics=metrics,
        silent_omissions=silent,
        slice_metrics=slice_metrics,
        atomic_group_macro=atomic_macro,
    )


__all__ = [
    "BenchmarkMetric",
    "BenchmarkReport",
    "GoldBenchmarkFact",
    "PredictedBenchmarkFact",
    "UnitSegmentationCase",
    "evaluate_benchmark",
]
