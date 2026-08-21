from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID

GENERATOR_VERSION = "phase4-fixture-generator-v1"
SCENARIO_CLOCK = "2026-08-22T00:00:00Z"
MOTHER_COUNT = 20
DERIVED_PER_MOTHER = 5
LICENSE = "CC0-1.0"
OUTPUT_DIRECTORY = Path(__file__).resolve().parent

JsonObject = dict[str, Any]


def _stable_uuid(label: str) -> str:
    raw = bytearray(sha256(label.encode("utf-8")).digest()[:16])
    raw[6] = (raw[6] & 0x0F) | 0x70
    raw[8] = (raw[8] & 0x3F) | 0x80
    return str(UUID(bytes=bytes(raw)))


def _profile_attributes(index: int) -> JsonObject:
    majors = ("080901", "080902", "030101", "120401")
    education_levels = ("BACHELOR", "MASTER", "DOCTORATE")
    student_statuses = ("GRADUATING", "RECENT_GRADUATE", "EMPLOYED")
    regions = ("SYN-ZJ-A", "SYN-ZJ-B", "SYN-CN-C")
    return {
        "education_level": education_levels[index % len(education_levels)],
        "major_name": f"Synthetic major family {index % len(majors) + 1}",
        "major_code": majors[index % len(majors)],
        "graduation_year": 2026 + index % 3,
        "student_status": student_statuses[index % len(student_statuses)],
        "birth_date": f"{1998 + index % 5:04d}-{index % 12 + 1:02d}-15",
        "hukou_region": regions[index % len(regions)],
        "residence_region": regions[(index + 1) % len(regions)],
        "target_regions": sorted({regions[index % len(regions)], "SYN-NATIONAL"}),
        "certificates": [f"SYN-CERT-{index % 4 + 1}"],
    }


def _snapshot(
    *,
    profile_id: str,
    version: int,
    attributes: JsonObject,
    label: str,
) -> JsonObject:
    return {
        "profile_snapshot_id": _stable_uuid(f"phase4-profile-snapshot:{label}"),
        "profile_id": profile_id,
        "version": version,
        "synthetic": True,
        "persona_family_id": _stable_uuid(f"phase4-persona-family:{profile_id}"),
        "attributes": attributes,
        "scenario_clock": "2026-08-22",
        "profile_schema_version": "0.4.0",
        "created_at": SCENARIO_CLOCK,
        "created_by": "phase4-fixture-generator",
        "reviewed_by": "phase4-fixture-governance",
        "change_note": label,
    }


def _build_profiles() -> tuple[list[JsonObject], list[JsonObject]]:
    mothers: list[JsonObject] = []
    derived: list[JsonObject] = []
    for index in range(MOTHER_COUNT):
        profile_id = _stable_uuid(f"phase4-mother-profile:{index:02d}")
        base_attributes = _profile_attributes(index)
        mothers.append(
            {
                "synthetic_only": True,
                "mother_profile_id": None,
                "variation_axis": "baseline",
                "snapshot": _snapshot(
                    profile_id=profile_id,
                    version=1,
                    attributes=base_attributes,
                    label=f"Synthetic mother profile {index:02d}",
                ),
            }
        )
        variations: tuple[tuple[str, str, object], ...] = (
            (
                "birth_date",
                "birth_date",
                "2027-01-01" if index == 11 else f"{1997 + index % 5:04d}-08-22",
            ),
            ("major_code", "major_code", None if index == 1 else "080903"),
            ("education_level", "education_level", "ASSOCIATE"),
            ("hukou_region", "hukou_region", "SYN-OUTSIDE"),
            ("certificates", "certificates", []),
        )
        for variation_index, (axis, field, value) in enumerate(variations, start=2):
            attributes = deepcopy(base_attributes)
            attributes[field] = value
            derived.append(
                {
                    "synthetic_only": True,
                    "mother_profile_id": profile_id,
                    "variation_axis": axis,
                    "snapshot": _snapshot(
                        profile_id=profile_id,
                        version=variation_index,
                        attributes=attributes,
                        label=(
                            f"Synthetic profile {index:02d} variation "
                            f"{variation_index - 1}: {axis}"
                        ),
                    ),
                }
            )
    return mothers, derived


def _golden_rule(
    code: str,
    operator: str,
    field: str,
    value_type: str,
    value: object,
    *,
    evidence_conflict: bool = False,
) -> JsonObject:
    evidence: list[JsonObject] = [
        {
            "authority": "ORIGINAL_OFFICIAL_NOTICE",
            "relation": "SUPPORTS",
        }
    ]
    if evidence_conflict:
        evidence.append(
            {
                "authority": "ORIGINAL_OFFICIAL_NOTICE",
                "relation": "CONTRADICTS",
            }
        )
    return {
        "code": code,
        "operator": operator,
        "field": field,
        "value_type": value_type,
        "value": value,
        "evidence": evidence,
    }


def _build_golden_cases(
    mothers: list[JsonObject],
    synthetic_profiles: list[JsonObject],
) -> list[JsonObject]:
    specifications: tuple[tuple[str, str, JsonObject, JsonObject, bool], ...] = (
        (
            "age-boundary",
            "ELIGIBLE",
            synthetic_profiles[0],
            _golden_rule(
                "birth-date-boundary",
                "GTE",
                "birth_date",
                "DATE",
                "1997-08-22",
            ),
            False,
        ),
        (
            "missing-field",
            "UNCERTAIN",
            synthetic_profiles[6],
            _golden_rule("major-required", "IN", "major_code", "STRING", ["080901"]),
            False,
        ),
        (
            "evidence-conflict",
            "UNCERTAIN",
            mothers[2],
            _golden_rule(
                "education-evidence-conflict",
                "EXISTS",
                "education_level",
                "STRING",
                None,
                evidence_conflict=True,
            ),
            False,
        ),
        (
            "major-exact",
            "ELIGIBLE",
            mothers[0],
            _golden_rule("major-exact", "IN", "major_code", "STRING", ["080901"]),
            False,
        ),
        (
            "major-catalog",
            "ELIGIBLE",
            mothers[4],
            _golden_rule("major-catalog", "IN", "major_code", "STRING", ["0809"]),
            False,
        ),
        (
            "major-approved-mapping",
            "LIKELY_ELIGIBLE",
            synthetic_profiles[26],
            _golden_rule(
                "major-approved-mapping",
                "IN",
                "major_code",
                "STRING",
                ["080902"],
            ),
            False,
        ),
        (
            "major-semantic-candidate",
            "UNCERTAIN",
            mothers[6],
            _golden_rule(
                "major-semantic-candidate",
                "IN",
                "major_code",
                "STRING",
                ["080902"],
            ),
            True,
        ),
        (
            "education",
            "INELIGIBLE",
            mothers[0],
            _golden_rule("education-master", "GTE", "education_level", "STRING", "MASTER"),
            False,
        ),
        (
            "graduation-status",
            "ELIGIBLE",
            mothers[0],
            _golden_rule(
                "graduation-status",
                "EQ",
                "student_status",
                "STRING",
                "GRADUATING",
            ),
            False,
        ),
        (
            "hukou-region",
            "INELIGIBLE",
            mothers[0],
            _golden_rule("hukou-region", "EQ", "hukou_region", "STRING", "SYN-ZJ-B"),
            False,
        ),
        (
            "certificate",
            "INELIGIBLE",
            mothers[0],
            _golden_rule(
                "certificate-required",
                "CONTAINS_ALL",
                "certificates",
                "STRING_SET",
                ["SYN-CERT-9"],
            ),
            False,
        ),
        (
            "false-negative-protection",
            "UNCERTAIN",
            synthetic_profiles[55],
            _golden_rule(
                "future-birth-date-protection",
                "LTE",
                "birth_date",
                "DATE",
                "2005-01-01",
            ),
            False,
        ),
    )
    cases: list[JsonObject] = []
    for index, (tag, expected_status, profile, rule, semantic) in enumerate(specifications):
        snapshot = profile["snapshot"]
        if not isinstance(snapshot, dict):  # pragma: no cover - generator invariant
            raise TypeError("snapshot must be an object")
        cases.append(
            {
                "case_id": f"phase4-golden-{index + 1:02d}-{tag}",
                "coverage_tags": [tag],
                "profile_snapshot_id": snapshot["profile_snapshot_id"],
                "expected_status": expected_status,
                "protected_from_unexpected_ineligible": expected_status != "INELIGIBLE",
                "semantic_major_candidate": semantic,
                "rule": rule,
            }
        )
    return cases


def _write_json(filename: str, payload: JsonObject) -> None:
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    (OUTPUT_DIRECTORY / filename).write_text(
        content,
        encoding="utf-8",
        newline="\n",
    )


def _record_count(filename: str, payload: JsonObject) -> int:
    field = {
        "phase4-major-catalog.json": "entries",
        "phase4-major-mapping.json": "entries",
        "phase4-golden-cases.json": "cases",
        "phase4-mother-profiles.json": "profiles",
        "phase4-synthetic-profiles.json": "profiles",
    }[filename]
    records = payload[field]
    if not isinstance(records, list):  # pragma: no cover - generator invariant
        raise TypeError(f"{filename} {field} must be a list")
    return len(records)


def generate() -> None:
    mothers, synthetic_profiles = _build_profiles()
    generated: dict[str, JsonObject] = {
        "phase4-golden-cases.json": {
            "dataset_id": "phase4-synthetic-golden-dataset",
            "dataset_version": "phase4-synthetic-golden-v1",
            "scenario_clock": SCENARIO_CLOCK,
            "synthetic_only": True,
            "license": LICENSE,
            "cases": _build_golden_cases(mothers, synthetic_profiles),
        },
        "phase4-mother-profiles.json": {
            "dataset_version": "phase4-synthetic-mother-profiles-v1",
            "scenario_clock": SCENARIO_CLOCK,
            "synthetic_only": True,
            "license": LICENSE,
            "profiles": mothers,
        },
        "phase4-synthetic-profiles.json": {
            "dataset_version": "phase4-synthetic-derived-profiles-v1",
            "scenario_clock": SCENARIO_CLOCK,
            "synthetic_only": True,
            "license": LICENSE,
            "profiles": synthetic_profiles,
        },
    }
    for filename, payload in generated.items():
        _write_json(filename, payload)

    payloads = dict(generated)
    for filename in ("phase4-major-catalog.json", "phase4-major-mapping.json"):
        payloads[filename] = json.loads(
            (OUTPUT_DIRECTORY / filename).read_text(encoding="utf-8")
        )

    files: list[JsonObject] = []
    for filename in sorted(payloads):
        content = (OUTPUT_DIRECTORY / filename).read_bytes()
        files.append(
            {
                "filename": filename,
                "sha256": sha256(content).hexdigest(),
                "byte_length": len(content),
                "record_count": _record_count(filename, payloads[filename]),
                "license": LICENSE,
                "synthetic_only": True,
            }
        )
    _write_json(
        "phase4-fixtures.manifest.json",
        {
            "manifest_version": "1.0.0",
            "generator_version": GENERATOR_VERSION,
            "scenario_clock": SCENARIO_CLOCK,
            "license": LICENSE,
            "synthetic_only": True,
            "files": files,
        },
    )


if __name__ == "__main__":
    generate()
