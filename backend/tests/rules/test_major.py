import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from deepaha.rules.major import (
    ApprovedMajorMapping,
    MajorAssetError,
    MajorCatalog,
    MajorMatchKind,
    load_approved_major_mapping,
    load_major_catalog,
    match_major,
)

FIXTURE_DIRECTORY = Path(__file__).parents[1] / "fixtures" / "evaluation"
CATALOG_PATH = FIXTURE_DIRECTORY / "phase4-major-catalog.json"
MAPPING_PATH = FIXTURE_DIRECTORY / "phase4-major-mapping.json"


@pytest.fixture(scope="module")
def assets() -> tuple[MajorCatalog, ApprovedMajorMapping]:
    catalog = load_major_catalog(CATALOG_PATH)
    mapping = load_approved_major_mapping(MAPPING_PATH, catalog)
    return catalog, mapping


@pytest.mark.parametrize(
    ("profile_code", "accepted_codes", "semantic_candidate", "kind", "official"),
    [
        ("080902", ("080902",), False, MajorMatchKind.EXACT, True),
        ("080902", ("0809",), False, MajorMatchKind.CATALOG, True),
        ("080903", ("080902",), False, MajorMatchKind.APPROVED_MAPPING, False),
        ("030101", ("0809",), True, MajorMatchKind.SEMANTIC_CANDIDATE, False),
        ("030101", ("0809",), False, MajorMatchKind.NO_MATCH, True),
        (None, ("0809",), False, MajorMatchKind.MISSING, False),
        ("999999", ("0809",), False, MajorMatchKind.UNKNOWN_CODE, False),
        ("080902", ("0809", "0809"), False, MajorMatchKind.CONFLICT, False),
    ],
)
def test_major_match_resolution_order(
    assets: tuple[MajorCatalog, ApprovedMajorMapping],
    profile_code: str | None,
    accepted_codes: tuple[str, ...],
    semantic_candidate: bool,
    kind: MajorMatchKind,
    official: bool,
) -> None:
    catalog, mapping = assets
    result = match_major(
        profile_code,
        accepted_codes,
        catalog,
        mapping,
        semantic_candidate=semantic_candidate,
    )
    assert result.kind is kind
    assert result.official_conclusion is official
    if kind is MajorMatchKind.APPROVED_MAPPING:
        assert result.evidence_authority == "HUMAN_APPROVED_MAPPING"
        assert result.matched_code == "080902"
    if kind is MajorMatchKind.SEMANTIC_CANDIDATE:
        assert result.deterministic is False
        assert result.evidence_authority == "LLM_SEMANTIC_INFERENCE"


def test_catalog_and_mapping_metadata_are_fixed_and_synthetic(
    assets: tuple[MajorCatalog, ApprovedMajorMapping],
) -> None:
    catalog, mapping = assets
    assert catalog.version == "phase4-synthetic-major-catalog-v1"
    assert mapping.version == "phase4-synthetic-major-mapping-v1"
    assert mapping.catalog_version == catalog.version
    assert catalog.synthetic_only is True
    assert mapping.synthetic_only is True
    assert catalog.license == mapping.license == "CC0-1.0"
    assert mapping.approved_by == "phase4-fixture-governance"


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda value: value["entries"].append(value["entries"][0]),
            "duplicate",
        ),
        (
            lambda value: value["entries"][1].update({"parent_codes": ["missing"]}),
            "parent",
        ),
        (
            lambda value: value["entries"][0].update({"parent_codes": ["0809"]}),
            "cycle",
        ),
    ],
)
def test_catalog_loader_rejects_invalid_graph(
    tmp_path: Path,
    mutator: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    value = json.loads(CATALOG_PATH.read_text("utf-8"))
    mutator(value)
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(value), "utf-8")
    with pytest.raises(MajorAssetError, match=message):
        load_major_catalog(path)


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda value: value.update({"catalog_version": "other-catalog"}),
            "catalog version",
        ),
        (
            lambda value: value["entries"][0].update({"approved": False}),
            "approved",
        ),
        (
            lambda value: value["entries"].append(
                {"source_code": "080902", "target_code": "080903", "approved": True}
            ),
            "cycle",
        ),
    ],
)
def test_mapping_loader_rejects_invalid_governance_or_graph(
    assets: tuple[MajorCatalog, ApprovedMajorMapping],
    tmp_path: Path,
    mutator: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    catalog, _ = assets
    value = json.loads(MAPPING_PATH.read_text("utf-8"))
    mutator(value)
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps(value), "utf-8")
    with pytest.raises(MajorAssetError, match=message):
        load_approved_major_mapping(path, catalog)


def test_match_rejects_runtime_asset_version_mismatch(
    assets: tuple[MajorCatalog, ApprovedMajorMapping],
) -> None:
    catalog, mapping = assets
    mismatched = mapping.__class__(
        version=mapping.version,
        catalog_version="other-catalog",
        synthetic_only=mapping.synthetic_only,
        license=mapping.license,
        approved_by=mapping.approved_by,
        approved_at=mapping.approved_at,
        targets_by_source=mapping.targets_by_source,
    )
    with pytest.raises(MajorAssetError, match="catalog version"):
        match_major("080902", ("0809",), catalog, mismatched)
