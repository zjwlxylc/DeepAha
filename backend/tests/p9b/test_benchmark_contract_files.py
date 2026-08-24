import json
from pathlib import Path

ROOT = Path(__file__).parents[3]


def test_split_contract_freezes_exact_counts_and_no_promotion() -> None:
    contract = json.loads(
        (ROOT / "config/p9b/benchmark-split-contract.v1.json").read_text(encoding="utf-8")
    )

    assert {
        name: values["exact_entry_count"] for name, values in contract["partitions"].items()
    } == {
        "CALIBRATION": 30,
        "DEVELOPMENT": 70,
        "VALIDATION": 30,
        "LOCKED_ACCEPTANCE": 200,
    }
    assert contract["promotion"] == "PROHIBITED"
    assert contract["locked_blind"]["adjudicator_visibility_before_both_submit"] == "DENIED"


def test_metric_contract_never_turns_zero_support_into_a_pass() -> None:
    contract = json.loads(
        (ROOT / "config/p9b/benchmark-metric-contract.v1.json").read_text(encoding="utf-8")
    )

    assert contract["zero_support_status"] == "NOT_OBSERVED"
    assert contract["confidence_intervals"]["binary_proportion"] == "wilson_95"
    assert (
        contract["metrics"]["critical_silent_omission_rate"]["denominator"]
        == "all high-impact KNOWN_SUPPORTED Gold facts"
    )
