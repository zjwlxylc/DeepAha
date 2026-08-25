import pytest

from deepaha.p9b.qualification import (
    QualificationBenchmarkError,
    QualificationGoldPair,
    evaluate_qualification_pairs,
    qualification_from_fact_state,
)


def pair(**updates: object) -> QualificationGoldPair:
    values: dict[str, object] = {
        "pair_id": "pair-1",
        "gold_provenance": "INDEPENDENT_HUMAN_GOVERNED_GOLD",
        "expected_status": "ELIGIBLE",
        "predicted_status": "ELIGIBLE",
        "predicted_reason_code": None,
        "deterministic_conflict_rule": False,
        "official_evidence_reference": None,
    }
    values.update(updates)
    return QualificationGoldPair(**values)  # type: ignore[arg-type]


def test_zero_real_pairs_is_not_observed_without_invented_rate() -> None:
    report = evaluate_qualification_pairs(())

    assert report.support == 0
    assert report.status == "NOT_OBSERVED"
    assert report.false_negative_rate.denominator == 0
    assert report.false_negative_rate.value is None


def test_unknown_fact_maps_to_uncertain_needs_more_info_not_fifth_status() -> None:
    assert qualification_from_fact_state("UNKNOWN") == ("UNCERTAIN", "NEEDS_MORE_INFO")


def test_ineligible_requires_deterministic_conflict_and_official_evidence() -> None:
    invalid = evaluate_qualification_pairs((pair(predicted_status="INELIGIBLE"),))
    valid = evaluate_qualification_pairs(
        (
            pair(
                expected_status="INELIGIBLE",
                predicted_status="INELIGIBLE",
                deterministic_conflict_rule=True,
                official_evidence_reference="evidence-ref:official-1",
            ),
        )
    )

    assert invalid.ineligible_guard_violations == 1
    assert invalid.status == "INVALID"
    assert valid.ineligible_guard_violations == 0


def test_false_negative_denominator_contains_only_gold_positive_pairs() -> None:
    report = evaluate_qualification_pairs(
        (
            pair(pair_id="positive", predicted_status="INELIGIBLE"),
            pair(
                pair_id="negative",
                expected_status="INELIGIBLE",
                predicted_status="INELIGIBLE",
                deterministic_conflict_rule=True,
                official_evidence_reference="evidence-ref:official-2",
            ),
        )
    )

    assert report.false_negative_rate.numerator == 1
    assert report.false_negative_rate.denominator == 1
    assert report.false_negative_rate.value == 1.0


def test_synthetic_or_fifth_state_cannot_enter_qualification_benchmark() -> None:
    with pytest.raises(QualificationBenchmarkError, match="governed Gold"):
        evaluate_qualification_pairs((pair(gold_provenance="SYNTHETIC"),))
    with pytest.raises(QualificationBenchmarkError, match="four-state"):
        evaluate_qualification_pairs((pair(predicted_status="UNKNOWN"),))
    with pytest.raises(QualificationBenchmarkError, match="NEEDS_MORE_INFO"):
        evaluate_qualification_pairs(
            (pair(predicted_status="ELIGIBLE", predicted_reason_code="NEEDS_MORE_INFO"),)
        )
