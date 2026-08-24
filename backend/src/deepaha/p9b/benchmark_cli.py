import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from deepaha.contracts.phase9b import GoldFieldState, PredictionFieldState
from deepaha.p9b.benchmark import (
    BenchmarkReport,
    GoldBenchmarkFact,
    PredictedBenchmarkFact,
    UnitSegmentationCase,
    evaluate_benchmark,
)


def _instant(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def run_payload(payload: dict[str, Any]) -> BenchmarkReport:
    gold = [
        GoldBenchmarkFact(
            target_identity=item["target_identity"],
            field_name=item["field_name"],
            state=GoldFieldState(item["state"]),
            normalized_value=item.get("normalized_value"),
            high_impact=item["high_impact"],
            precedence_sensitive=item["precedence_sensitive"],
            atomic_group_id=item["atomic_group_id"],
            field_type=item.get("field_type", "UNSPECIFIED"),
            opportunity_category=item.get("opportunity_category", "UNSPECIFIED"),
            complexity=item.get("complexity", "UNSPECIFIED"),
            source_template_group=item.get("source_template_group", "UNSPECIFIED"),
        )
        for item in payload.get("gold_facts", [])
    ]
    predictions = [
        PredictedBenchmarkFact(
            target_identity=item["target_identity"],
            field_name=item["field_name"],
            state=PredictionFieldState(item["state"]),
            normalized_value=item.get("normalized_value"),
            evidence_supported=item.get("evidence_supported", False),
            evidence_published_at=(
                _instant(item["evidence_published_at"])
                if item.get("evidence_published_at") is not None
                else None
            ),
        )
        for item in payload.get("predictions", [])
    ]
    segmentation = [
        UnitSegmentationCase(
            expected_unit_ids=frozenset(item["expected_unit_ids"]),
            predicted_unit_ids=frozenset(item["predicted_unit_ids"]),
            singleton_expected=item["singleton_expected"],
        )
        for item in payload.get("segmentation_cases", [])
    ]
    return evaluate_benchmark(
        gold,
        predictions,
        evaluation_as_of=_instant(payload["evaluation_as_of"]),
        segmentation_cases=segmentation,
    )


def report_payload(report: BenchmarkReport) -> dict[str, object]:
    return {
        "metrics": {name: asdict(metric) for name, metric in report.metrics.items()},
        "silent_omissions": [list(value) for value in report.silent_omissions],
        "slice_metrics": {
            slice_name: {name: asdict(metric) for name, metric in metrics.items()}
            for slice_name, metrics in report.slice_metrics.items()
        },
        "atomic_group_macro": {
            name: asdict(metric) for name, metric in report.atomic_group_macro.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the deterministic P9-B benchmark contract")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    payload = json.loads(arguments.input.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("benchmark input root must be an object")
    rendered = json.dumps(report_payload(run_payload(payload)), indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        print(rendered, end="")
    else:
        arguments.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()


__all__ = ["report_payload", "run_payload"]
