import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from deepaha.investigations.contracts import digest
from deepaha.investigations.group_inheritance_contracts import GroupInheritancePreview


def sample() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(
            (Path(__file__).parents[3] / "web/tests/group-inheritance-fixture.json").read_text(
                encoding="utf-8"
            )
        ),
    )


def rehash(v: dict[str, Any]) -> None:
    g = v["dependencies"]["group_source"]
    g["registration"]["source"] = deepcopy(g["source"])
    g["registration"]["source_hash"] = digest(g["source"])
    p = g["rule_preview"]
    f = p["result"]["fact_review"]
    f["result"]["group_source"] = deepcopy(g["registration"])
    f["result_hash"] = digest(f["result"])
    p["result_hash"] = digest(p["result"])
    review = g["rule_review"]
    review["result"]["preview"] = deepcopy(p)
    review["result_hash"] = digest(review["result"])
    for history in g["applicability_histories"].values():
        for receipt in history:
            receipt["context"]["group_source_hash"] = g["registration"]["source_hash"]
            receipt["context"]["source_rule_preparation_hash"] = review["result_hash"]
            receipt["context"]["source_review_hash"] = digest(review)
            receipt["context_hash"] = digest(receipt["context"])
            receipt["request"]["context_hash"] = receipt["context_hash"]
            receipt["request_hash"] = digest(receipt["request"])
    for row in v["snapshot"]["group_conditions"]:
        if row["source_rule"] and row["applicability"]:
            row["applicability"] = deepcopy(
                g["applicability_histories"][row["source_rule"]["rule_candidate_id"]][-1]
            )
    v["dependencies_hash"] = digest(v["dependencies"])
    v["snapshot_hash"] = digest(v["snapshot"])


def test_actual_fixture_preserves_timestamp_spelling() -> None:
    v = sample()
    assert GroupInheritancePreview.model_validate(v).model_dump(mode="json") == v


@pytest.mark.parametrize("shape", ["legacy_note", "missing_evidence", "missing_locator"])
def test_optional_original_representation_is_preserved(shape: str) -> None:
    v = sample()
    g = v["dependencies"]["group_source"]
    raw = g["source"]["source_group"]["unit_level"][1]
    row = g["rule_preview"]["result"]["fact_review"]["result"]["rows"][1]
    if shape == "legacy_note":
        raw["note"] = "Historical note retained only in the official source"
        row["original"].pop("note", None)
    elif shape == "missing_evidence":
        raw.pop("evidence", None)
        row["original"]["evidence"] = []
        row["evidence"] = []
    else:
        raw["evidence"][0].pop("locator", None)
        row["original"]["evidence"][0]["locator"] = {}
        row["evidence"][0]["reference"]["locator"] = {}
    rehash(v)
    assert GroupInheritancePreview.model_validate(v).model_dump(mode="json") == v


def test_existing_note_cannot_be_rewritten() -> None:
    v = sample()
    v["dependencies"]["group_source"]["rule_preview"]["result"]["fact_review"]["result"]["rows"][1][
        "original"
    ]["note"] = "Forged note"
    rehash(v)
    with pytest.raises(ValidationError, match="frozen original"):
        GroupInheritancePreview.model_validate(v)


@pytest.mark.parametrize("field", ["raw_value", "original_field", "evidence", "locator"])
def test_rehashed_display_cannot_disagree_with_original(field: str) -> None:
    v = sample()
    row = v["dependencies"]["group_source"]["rule_preview"]["result"]["fact_review"]["result"][
        "rows"
    ][1]
    if field == "locator":
        row["original"]["evidence"][0]["locator"] = {"selector": "forged"}
        row["evidence"][0]["reference"]["locator"] = {"selector": "forged"}
    elif field == "evidence":
        row["evidence"][0]["reference"]["quote"] = "forged quote"
    else:
        row[field] = "forged condition"
    rehash(v)
    with pytest.raises(ValidationError, match="frozen original"):
        GroupInheritancePreview.model_validate(v)


def test_frozen_denominator_cannot_be_emptied_even_without_preparation() -> None:
    v = sample()
    for base in [v["dependencies"]["base_v2"], v["snapshot"]["base_v2"]]:
        base["plan"]["manifest"]["conditions"] = [
            c for c in base["plan"]["manifest"]["conditions"] if c["scope"] != "EMPLOYER_GROUP"
        ]
        ids = {c["condition_id"] for c in base["plan"]["manifest"]["conditions"]}
        base["plan"]["dispositions"] = [
            d for d in base["plan"]["dispositions"] if d["condition_id"] in ids
        ]
        base["plan"]["manifest_sha256"] = digest(base["plan"]["manifest"])
        base["plan_hash"] = digest(base["plan"])
    g = v["dependencies"]["group_source"]
    g.update(rule_preview=None, rule_review=None, applicability_histories={})
    v["snapshot"]["group_conditions"] = []
    v["dependencies_hash"] = digest(v["dependencies"])
    v["snapshot_hash"] = digest(v["snapshot"])
    with pytest.raises(ValidationError, match="denominator"):
        GroupInheritancePreview.model_validate(v)
