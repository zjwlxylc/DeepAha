from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from deepaha.evaluation.fixtures import (
    FixtureValidationError,
    load_fixture_bundle,
    verify_fixture_manifest,
)

FIXTURE_DIRECTORY = Path(__file__).parents[1] / "fixtures" / "evaluation"
EXPECTED_COVERAGE_TAGS = {
    "age-boundary",
    "certificate",
    "education",
    "evidence-conflict",
    "false-negative-protection",
    "graduation-status",
    "hukou-region",
    "major-approved-mapping",
    "major-catalog",
    "major-exact",
    "major-semantic-candidate",
    "missing-field",
}


def test_loads_fixed_synthetic_bundle() -> None:
    bundle = load_fixture_bundle(FIXTURE_DIRECTORY)

    assert len(bundle.mother_profiles) == 20
    assert len(bundle.synthetic_profiles) == 100
    assert {profile.mother_profile_id for profile in bundle.synthetic_profiles} == {
        profile.profile_id for profile in bundle.mother_profiles
    }
    assert all(
        profile.synthetic_only for profile in bundle.mother_profiles + bundle.synthetic_profiles
    )
    assert {tag for case in bundle.golden_cases for tag in case.coverage_tags} == (
        EXPECTED_COVERAGE_TAGS
    )
    assert bundle.scenario_clock.isoformat() == "2026-08-22T00:00:00+00:00"


def test_manifest_declares_every_phase4_evaluation_json() -> None:
    bundle = load_fixture_bundle(FIXTURE_DIRECTORY)
    declared = {entry.filename for entry in bundle.manifest.files}

    assert declared == {
        "phase4-golden-cases.json",
        "phase4-major-catalog.json",
        "phase4-major-mapping.json",
        "phase4-mother-profiles.json",
        "phase4-synthetic-profiles.json",
    }
    assert bundle.manifest.license == "CC0-1.0"
    assert bundle.manifest.synthetic_only is True
    assert bundle.manifest.generator_version == "phase4-fixture-generator-v1"


def test_golden_cases_contain_executable_boundary_inputs() -> None:
    bundle = load_fixture_bundle(FIXTURE_DIRECTORY)
    cases = {case.coverage_tags[0]: case for case in bundle.golden_cases}
    profiles = {
        profile.snapshot.profile_snapshot_id: profile
        for profile in bundle.mother_profiles + bundle.synthetic_profiles
    }

    age_case = cases["age-boundary"]
    assert age_case.rule.field.value == "birth_date"
    assert age_case.rule.value == "1997-08-22"
    assert profiles[age_case.profile_snapshot_id].snapshot.attributes.birth_date == date(
        1997, 8, 22
    )

    missing_case = cases["missing-field"]
    assert missing_case.rule.field.value == "major_code"
    assert profiles[missing_case.profile_snapshot_id].snapshot.attributes.major_code is None

    mapping_case = cases["major-approved-mapping"]
    assert mapping_case.rule.value == ["080902"]
    assert profiles[mapping_case.profile_snapshot_id].snapshot.attributes.major_code == "080903"

    semantic_case = cases["major-semantic-candidate"]
    assert semantic_case.semantic_major_candidate is True
    assert profiles[semantic_case.profile_snapshot_id].snapshot.attributes.major_code == "030101"

    protection_case = cases["false-negative-protection"]
    assert profiles[protection_case.profile_snapshot_id].snapshot.attributes.birth_date == date(
        2027, 1, 1
    )


def test_manifest_verification_happens_before_json_parsing(tmp_path: Path) -> None:
    copied = tmp_path / "evaluation"
    shutil.copytree(FIXTURE_DIRECTORY, copied)
    golden_path = copied / "phase4-golden-cases.json"
    golden_path.write_bytes(golden_path.read_bytes() + b"not-json")

    with pytest.raises(FixtureValidationError, match="SHA-256"):
        load_fixture_bundle(copied)


def test_rejects_an_undeclared_json_file(tmp_path: Path) -> None:
    copied = tmp_path / "evaluation"
    shutil.copytree(FIXTURE_DIRECTORY, copied)
    (copied / "undeclared.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(FixtureValidationError, match="undeclared JSON"):
        verify_fixture_manifest(copied)


def test_rejects_duplicate_profile_version_after_valid_manifest(tmp_path: Path) -> None:
    copied = tmp_path / "evaluation"
    shutil.copytree(FIXTURE_DIRECTORY, copied)
    synthetic_path = copied / "phase4-synthetic-profiles.json"
    payload = json.loads(synthetic_path.read_text(encoding="utf-8"))
    payload["profiles"][1]["snapshot"]["profile_id"] = payload["profiles"][0]["snapshot"][
        "profile_id"
    ]
    payload["profiles"][1]["snapshot"]["version"] = payload["profiles"][0]["snapshot"]["version"]
    synthetic_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _rewrite_manifest_hash(copied, synthetic_path)

    with pytest.raises(FixtureValidationError, match="profile version collision"):
        load_fixture_bundle(copied)


def _rewrite_manifest_hash(directory: Path, changed_path: Path) -> None:
    from hashlib import sha256

    manifest_path = directory / "phase4-fixtures.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    content = changed_path.read_bytes()
    for entry in manifest["files"]:
        if entry["filename"] == changed_path.name:
            entry["sha256"] = sha256(content).hexdigest()
            entry["byte_length"] = len(content)
            break
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
