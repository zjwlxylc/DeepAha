from deepaha.p9b.benchmark_cli import report_payload, run_payload


def test_executable_payload_preserves_support_and_not_observed() -> None:
    report = run_payload(
        {
            "evaluation_as_of": "2026-08-24T12:00:00Z",
            "gold_facts": [],
            "predictions": [],
            "segmentation_cases": [],
        }
    )

    rendered = report_payload(report)
    metric = rendered["metrics"]["strict_fact_precision"]  # type: ignore[index]
    assert metric["numerator"] == 0
    assert metric["denominator"] == 0
    assert metric["status"] == "NOT_OBSERVED"
