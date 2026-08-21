from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, ValidationError, model_validator

from deepaha.contracts.common import EntityId, Instant, NonEmptyString, Sha256
from deepaha.contracts.phase1 import ContractModel
from deepaha.contracts.phase4 import EligibilityStatus, ProfileSnapshotSchemaV04
from deepaha.rules.major import (
    ApprovedMajorMapping,
    MajorAssetError,
    MajorCatalog,
    load_approved_major_mapping,
    load_major_catalog,
)

MANIFEST_FILENAME = "phase4-fixtures.manifest.json"
EXPECTED_COVERAGE_TAGS = frozenset(
    {
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
)


class FixtureValidationError(ValueError):
    pass


class FixtureManifestEntry(ContractModel):
    filename: NonEmptyString
    sha256: Sha256
    byte_length: int = Field(ge=1)
    record_count: int = Field(ge=1)
    license: Literal["CC0-1.0"]
    synthetic_only: Literal[True]

    @model_validator(mode="after")
    def require_plain_filename(self) -> Self:
        if Path(self.filename).name != self.filename:
            raise ValueError("manifest filenames must not contain directories")
        return self


class FixtureManifest(ContractModel):
    manifest_version: Literal["1.0.0"]
    generator_version: Literal["phase4-fixture-generator-v1"]
    scenario_clock: Instant
    license: Literal["CC0-1.0"]
    synthetic_only: Literal[True]
    files: tuple[FixtureManifestEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_filenames(self) -> Self:
        filenames = [entry.filename for entry in self.files]
        if len(filenames) != len(set(filenames)):
            raise ValueError("manifest filenames must be unique")
        if MANIFEST_FILENAME in filenames:
            raise ValueError("manifest must not contain a self-referential hash")
        return self


class GoldenCaseFixture(ContractModel):
    case_id: NonEmptyString
    coverage_tags: tuple[NonEmptyString, ...] = Field(min_length=1)
    profile_snapshot_id: EntityId
    expected_status: EligibilityStatus
    protected_from_unexpected_ineligible: bool

    @model_validator(mode="after")
    def require_protection_for_non_negative_case(self) -> Self:
        expected_protection = self.expected_status is not EligibilityStatus.INELIGIBLE
        if self.protected_from_unexpected_ineligible != expected_protection:
            raise ValueError("protection flag must match expected eligibility status")
        if len(self.coverage_tags) != len(set(self.coverage_tags)):
            raise ValueError("coverage_tags must be unique")
        return self


class ProfileFixture(ContractModel):
    synthetic_only: Literal[True]
    mother_profile_id: EntityId | None
    variation_axis: NonEmptyString
    snapshot: ProfileSnapshotSchemaV04

    @property
    def profile_id(self) -> UUID:
        return self.snapshot.profile_id


class _GoldenDataset(ContractModel):
    dataset_id: NonEmptyString
    dataset_version: NonEmptyString
    scenario_clock: Instant
    synthetic_only: Literal[True]
    license: Literal["CC0-1.0"]
    cases: tuple[GoldenCaseFixture, ...] = Field(min_length=1)


class _ProfileDataset(ContractModel):
    dataset_version: NonEmptyString
    scenario_clock: Instant
    synthetic_only: Literal[True]
    license: Literal["CC0-1.0"]
    profiles: tuple[ProfileFixture, ...] = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class FixtureBundle:
    manifest: FixtureManifest
    manifest_sha256: str
    dataset_id: str
    dataset_version: str
    scenario_clock: datetime
    golden_cases: tuple[GoldenCaseFixture, ...]
    mother_profiles: tuple[ProfileFixture, ...]
    synthetic_profiles: tuple[ProfileFixture, ...]
    major_catalog: MajorCatalog
    major_mapping: ApprovedMajorMapping


def verify_fixture_manifest(directory: Path) -> None:
    manifest = _read_manifest(directory)
    actual_json = {
        path.name for path in directory.glob("*.json") if path.name != MANIFEST_FILENAME
    }
    declared_json = {entry.filename for entry in manifest.files}
    undeclared = sorted(actual_json - declared_json)
    missing = sorted(declared_json - actual_json)
    if undeclared:
        raise FixtureValidationError(f"undeclared JSON fixture files: {undeclared}")
    if missing:
        raise FixtureValidationError(f"missing fixture files: {missing}")
    for entry in manifest.files:
        content = (directory / entry.filename).read_bytes()
        if len(content) != entry.byte_length:
            raise FixtureValidationError(
                f"byte length/SHA-256 manifest mismatch for {entry.filename}"
            )
        if sha256(content).hexdigest() != entry.sha256:
            raise FixtureValidationError(f"SHA-256 mismatch for {entry.filename}")


def load_fixture_bundle(directory: Path) -> FixtureBundle:
    verify_fixture_manifest(directory)
    manifest = _read_manifest(directory)
    payloads = {
        entry.filename: _read_verified_json(directory / entry.filename)
        for entry in manifest.files
    }
    try:
        golden = _GoldenDataset.model_validate(payloads["phase4-golden-cases.json"])
        mothers = _ProfileDataset.model_validate(
            payloads["phase4-mother-profiles.json"]
        )
        synthetic = _ProfileDataset.model_validate(
            payloads["phase4-synthetic-profiles.json"]
        )
        catalog = load_major_catalog(directory / "phase4-major-catalog.json")
        mapping = load_approved_major_mapping(
            directory / "phase4-major-mapping.json", catalog
        )
    except (KeyError, ValidationError, MajorAssetError) as error:
        raise FixtureValidationError(f"invalid Phase 4 fixture payload: {error}") from error

    _verify_record_counts(manifest, payloads)
    _verify_profiles(mothers.profiles, synthetic.profiles)
    _verify_golden_cases(golden.cases, mothers.profiles, synthetic.profiles)
    scenario_clocks = {
        manifest.scenario_clock,
        golden.scenario_clock,
        mothers.scenario_clock,
        synthetic.scenario_clock,
    }
    if len(scenario_clocks) != 1:
        raise FixtureValidationError("fixture scenario clocks must match")
    manifest_bytes = (directory / MANIFEST_FILENAME).read_bytes()
    return FixtureBundle(
        manifest=manifest,
        manifest_sha256=sha256(manifest_bytes).hexdigest(),
        dataset_id=golden.dataset_id,
        dataset_version=golden.dataset_version,
        scenario_clock=golden.scenario_clock,
        golden_cases=golden.cases,
        mother_profiles=mothers.profiles,
        synthetic_profiles=synthetic.profiles,
        major_catalog=catalog,
        major_mapping=mapping,
    )


def _read_manifest(directory: Path) -> FixtureManifest:
    try:
        return FixtureManifest.model_validate_json(
            (directory / MANIFEST_FILENAME).read_bytes()
        )
    except (OSError, ValidationError) as error:
        raise FixtureValidationError(f"invalid fixture manifest: {error}") from error


def _read_verified_json(path: Path) -> object:
    try:
        return json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise FixtureValidationError(f"invalid verified JSON {path.name}: {error}") from error


def _verify_record_counts(
    manifest: FixtureManifest,
    payloads: dict[str, object],
) -> None:
    fields = {
        "phase4-major-catalog.json": "entries",
        "phase4-major-mapping.json": "entries",
        "phase4-golden-cases.json": "cases",
        "phase4-mother-profiles.json": "profiles",
        "phase4-synthetic-profiles.json": "profiles",
    }
    for entry in manifest.files:
        payload = payloads.get(entry.filename)
        if not isinstance(payload, dict):
            raise FixtureValidationError(f"{entry.filename} must contain a JSON object")
        field = fields.get(entry.filename)
        if field is None:
            raise FixtureValidationError(f"unsupported fixture file: {entry.filename}")
        records = payload.get(field)
        if not isinstance(records, list) or len(records) != entry.record_count:
            raise FixtureValidationError(f"record count mismatch for {entry.filename}")


def _verify_profiles(
    mothers: tuple[ProfileFixture, ...],
    synthetic: tuple[ProfileFixture, ...],
) -> None:
    if len(mothers) != 20 or len(synthetic) != 100:
        raise FixtureValidationError("Phase 4 fixtures require exactly 20/100 profiles")
    mother_by_id: dict[UUID, ProfileFixture] = {}
    all_snapshot_ids: set[UUID] = set()
    profile_versions: set[tuple[UUID, int]] = set()
    for profile in (*mothers, *synthetic):
        if not profile.snapshot.synthetic:
            raise FixtureValidationError("all fixture profiles must be synthetic")
        snapshot_id = profile.snapshot.profile_snapshot_id
        if snapshot_id in all_snapshot_ids:
            raise FixtureValidationError("duplicate profile snapshot ID")
        all_snapshot_ids.add(snapshot_id)
        version_key = (profile.profile_id, profile.snapshot.version)
        if version_key in profile_versions:
            raise FixtureValidationError("profile version collision")
        profile_versions.add(version_key)
    for mother in mothers:
        if mother.mother_profile_id is not None or mother.variation_axis != "baseline":
            raise FixtureValidationError("mother profile must be a baseline")
        if mother.profile_id in mother_by_id:
            raise FixtureValidationError("duplicate mother profile ID")
        mother_by_id[mother.profile_id] = mother
    for derived in synthetic:
        mother_id = derived.mother_profile_id
        if mother_id is None or mother_id not in mother_by_id:
            raise FixtureValidationError("derived profile without an existing mother")
        if derived.profile_id != mother_id:
            raise FixtureValidationError("derived profile must retain its mother profile ID")
        mother_attributes = mother_by_id[mother_id].snapshot.attributes.model_dump(mode="json")
        derived_attributes = derived.snapshot.attributes.model_dump(mode="json")
        changed_fields = {
            field
            for field, mother_value in mother_attributes.items()
            if derived_attributes[field] != mother_value
        }
        if changed_fields != {derived.variation_axis}:
            raise FixtureValidationError("derived profile must change exactly its variation_axis")


def _verify_golden_cases(
    cases: tuple[GoldenCaseFixture, ...],
    mothers: tuple[ProfileFixture, ...],
    synthetic: tuple[ProfileFixture, ...],
) -> None:
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise FixtureValidationError("duplicate Golden case ID")
    coverage_tags = {tag for case in cases for tag in case.coverage_tags}
    if coverage_tags != EXPECTED_COVERAGE_TAGS:
        raise FixtureValidationError("Golden coverage tags do not match Phase 4 scope")
    profile_snapshot_ids = {
        profile.snapshot.profile_snapshot_id for profile in (*mothers, *synthetic)
    }
    if any(case.profile_snapshot_id not in profile_snapshot_ids for case in cases):
        raise FixtureValidationError("Golden case references an unknown profile snapshot")


__all__ = [
    "FixtureBundle",
    "FixtureManifest",
    "FixtureManifestEntry",
    "FixtureValidationError",
    "GoldenCaseFixture",
    "ProfileFixture",
    "load_fixture_bundle",
    "verify_fixture_manifest",
]
