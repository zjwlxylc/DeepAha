from dataclasses import dataclass
from math import sqrt

ELIGIBILITY_STATES = frozenset({"ELIGIBLE", "LIKELY_ELIGIBLE", "UNCERTAIN", "INELIGIBLE"})


class QualificationBenchmarkError(ValueError):
    pass


def qualification_from_fact_state(fact_state: str) -> tuple[str, str | None]:
    if fact_state == "UNKNOWN":
        return "UNCERTAIN", "NEEDS_MORE_INFO"
    raise QualificationBenchmarkError("only UNKNOWN fact abstention has a direct safe mapping")


@dataclass(frozen=True)
class QualificationGoldPair:
    pair_id: str
    gold_provenance: str
    expected_status: str
    predicted_status: str
    predicted_reason_code: str | None
    deterministic_conflict_rule: bool
    official_evidence_reference: str | None


@dataclass(frozen=True)
class QualificationMetric:
    numerator: int
    denominator: int
    value: float | None
    interval_low: float | None
    interval_high: float | None
    observation_state: str


@dataclass(frozen=True)
class QualificationBenchmarkReport:
    support: int
    false_negative_rate: QualificationMetric
    ineligible_guard_violations: int
    status: str


def _wilson(numerator: int, denominator: int) -> tuple[float, float]:
    z = 1.959963984540054
    value = numerator / denominator
    scale = 1 + z * z / denominator
    center = (value + z * z / (2 * denominator)) / scale
    margin = z * sqrt(value * (1 - value) / denominator + z * z / (4 * denominator**2))
    return max(0.0, center - margin / scale), min(1.0, center + margin / scale)


def evaluate_qualification_pairs(
    pairs: tuple[QualificationGoldPair, ...],
) -> QualificationBenchmarkReport:
    if not pairs:
        metric = QualificationMetric(0, 0, None, None, None, "NOT_OBSERVED")
        return QualificationBenchmarkReport(0, metric, 0, "NOT_OBSERVED")
    for pair in pairs:
        if pair.gold_provenance != "INDEPENDENT_HUMAN_GOVERNED_GOLD":
            raise QualificationBenchmarkError("qualification benchmark requires governed Gold")
        if pair.expected_status not in ELIGIBILITY_STATES or (
            pair.predicted_status not in ELIGIBILITY_STATES
        ):
            raise QualificationBenchmarkError("eligibility is exactly four-state")
        if pair.predicted_reason_code == "NEEDS_MORE_INFO" and (
            pair.predicted_status != "UNCERTAIN"
        ):
            raise QualificationBenchmarkError("NEEDS_MORE_INFO is only an UNCERTAIN reason")
    guard_violations = sum(
        pair.predicted_status == "INELIGIBLE"
        and not (pair.deterministic_conflict_rule and pair.official_evidence_reference)
        for pair in pairs
    )
    positive_pairs = tuple(
        pair for pair in pairs if pair.expected_status in {"ELIGIBLE", "LIKELY_ELIGIBLE"}
    )
    false_negatives = sum(
        pair.expected_status in {"ELIGIBLE", "LIKELY_ELIGIBLE"}
        and pair.predicted_status == "INELIGIBLE"
        for pair in pairs
    )
    if not positive_pairs:
        metric = QualificationMetric(0, 0, None, None, None, "NOT_OBSERVED")
        return QualificationBenchmarkReport(
            len(pairs),
            metric,
            guard_violations,
            "INVALID" if guard_violations else "OBSERVED",
        )
    low, high = _wilson(false_negatives, len(positive_pairs))
    metric = QualificationMetric(
        false_negatives,
        len(positive_pairs),
        false_negatives / len(positive_pairs),
        low,
        high,
        "OBSERVED",
    )
    return QualificationBenchmarkReport(
        len(pairs),
        metric,
        guard_violations,
        "INVALID" if guard_violations else "OBSERVED",
    )


__all__ = [
    "ELIGIBILITY_STATES",
    "QualificationBenchmarkError",
    "QualificationBenchmarkReport",
    "QualificationGoldPair",
    "evaluate_qualification_pairs",
    "qualification_from_fact_state",
]
