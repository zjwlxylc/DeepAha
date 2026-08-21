import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Self

from pydantic import Field, ValidationError, model_validator

from deepaha.contracts.common import Instant, NonEmptyString
from deepaha.contracts.phase1 import ContractModel
from deepaha.contracts.phase4 import RuleEvidenceAuthority


class MajorAssetError(ValueError):
    pass


class MajorMatchKind(StrEnum):
    EXACT = "EXACT"
    CATALOG = "CATALOG"
    APPROVED_MAPPING = "APPROVED_MAPPING"
    SEMANTIC_CANDIDATE = "SEMANTIC_CANDIDATE"
    NO_MATCH = "NO_MATCH"
    MISSING = "MISSING"
    UNKNOWN_CODE = "UNKNOWN_CODE"
    CONFLICT = "CONFLICT"


class _CatalogEntryAsset(ContractModel):
    code: NonEmptyString
    name: NonEmptyString
    parent_codes: tuple[NonEmptyString, ...]

    @model_validator(mode="after")
    def require_unique_parents(self) -> Self:
        if len(self.parent_codes) != len(set(self.parent_codes)):
            raise ValueError("parent_codes must be unique")
        return self


class _CatalogAsset(ContractModel):
    version: NonEmptyString
    synthetic_only: bool
    license: NonEmptyString
    entries: tuple[_CatalogEntryAsset, ...] = Field(min_length=1)


class _MappingEntryAsset(ContractModel):
    source_code: NonEmptyString
    target_code: NonEmptyString
    approved: bool


class _MappingAsset(ContractModel):
    version: NonEmptyString
    catalog_version: NonEmptyString
    synthetic_only: bool
    license: NonEmptyString
    approved_by: NonEmptyString
    approved_at: Instant
    entries: tuple[_MappingEntryAsset, ...] = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class MajorCatalogEntry:
    code: str
    name: str
    parent_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MajorCatalog:
    version: str
    synthetic_only: bool
    license: str
    entries: Mapping[str, MajorCatalogEntry]

    def ancestry_path(self, code: str, ancestor: str) -> tuple[str, ...] | None:
        if code not in self.entries or ancestor not in self.entries:
            return None
        visiting: set[str] = set()

        def walk(current: str) -> tuple[str, ...] | None:
            if current == ancestor:
                return (current,)
            if current in visiting:
                return None
            visiting.add(current)
            for parent in self.entries[current].parent_codes:
                path = walk(parent)
                if path is not None:
                    visiting.remove(current)
                    return (current, *path)
            visiting.remove(current)
            return None

        return walk(code)


@dataclass(frozen=True, slots=True)
class ApprovedMajorMapping:
    version: str
    catalog_version: str
    synthetic_only: bool
    license: str
    approved_by: str
    approved_at: datetime
    targets_by_source: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class MajorMatchResult:
    kind: MajorMatchKind
    deterministic: bool
    official_conclusion: bool
    matched_code: str | None
    catalog_path: tuple[str, ...]
    evidence_authority: str | None
    reason_code: str


def load_major_catalog(path: Path) -> MajorCatalog:
    try:
        asset = _CatalogAsset.model_validate(json.loads(path.read_text("utf-8")))
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        raise MajorAssetError(f"invalid major catalog: {error}") from error
    if not asset.synthetic_only:
        raise MajorAssetError("Phase 4 major catalog must be synthetic_only")
    entries: dict[str, MajorCatalogEntry] = {}
    for item in asset.entries:
        if item.code in entries:
            raise MajorAssetError(f"duplicate major code: {item.code}")
        entries[item.code] = MajorCatalogEntry(item.code, item.name, item.parent_codes)
    for entry in entries.values():
        for parent_code in entry.parent_codes:
            if parent_code not in entries:
                raise MajorAssetError(
                    f"parent code {parent_code} for {entry.code} is not in catalog"
                )
    _reject_catalog_cycles(entries)
    return MajorCatalog(
        version=asset.version,
        synthetic_only=asset.synthetic_only,
        license=asset.license,
        entries=MappingProxyType(entries),
    )


def load_approved_major_mapping(
    path: Path,
    catalog: MajorCatalog,
) -> ApprovedMajorMapping:
    try:
        asset = _MappingAsset.model_validate(json.loads(path.read_text("utf-8")))
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        raise MajorAssetError(f"invalid major mapping: {error}") from error
    if asset.catalog_version != catalog.version:
        raise MajorAssetError("major mapping catalog version does not match catalog")
    if not asset.synthetic_only:
        raise MajorAssetError("Phase 4 major mapping must be synthetic_only")
    pairs: set[tuple[str, str]] = set()
    targets_by_source: dict[str, list[str]] = {}
    for item in asset.entries:
        if not item.approved:
            raise MajorAssetError("every mapping row must be approved")
        pair = (item.source_code, item.target_code)
        if pair in pairs:
            raise MajorAssetError(f"duplicate approved mapping: {pair}")
        if item.source_code not in catalog.entries or item.target_code not in catalog.entries:
            raise MajorAssetError("approved mapping codes must exist in the catalog")
        pairs.add(pair)
        targets_by_source.setdefault(item.source_code, []).append(item.target_code)
    normalized = {
        source_code: tuple(sorted(target_codes))
        for source_code, target_codes in targets_by_source.items()
    }
    _reject_mapping_cycles(normalized)
    return ApprovedMajorMapping(
        version=asset.version,
        catalog_version=asset.catalog_version,
        synthetic_only=asset.synthetic_only,
        license=asset.license,
        approved_by=asset.approved_by,
        approved_at=asset.approved_at,
        targets_by_source=MappingProxyType(normalized),
    )


def match_major(
    profile_code: str | None,
    accepted_codes: tuple[str, ...],
    catalog: MajorCatalog,
    mapping: ApprovedMajorMapping,
    *,
    semantic_candidate: bool = False,
) -> MajorMatchResult:
    if mapping.catalog_version != catalog.version:
        raise MajorAssetError("major mapping catalog version does not match catalog")
    if not accepted_codes or len(accepted_codes) != len(set(accepted_codes)):
        return _result(MajorMatchKind.CONFLICT, "MAJOR_RULE_CODE_CONFLICT")
    if any(code not in catalog.entries for code in accepted_codes):
        return _result(MajorMatchKind.CONFLICT, "MAJOR_RULE_UNKNOWN_CATALOG_CODE")
    if profile_code is None or not profile_code.strip():
        return _result(MajorMatchKind.MISSING, "MAJOR_CODE_MISSING")
    if profile_code not in catalog.entries:
        return _result(MajorMatchKind.UNKNOWN_CODE, "MAJOR_CODE_UNKNOWN")
    if profile_code in accepted_codes:
        return _result(
            MajorMatchKind.EXACT,
            "MAJOR_EXACT_MATCH",
            deterministic=True,
            official=True,
            matched_code=profile_code,
            path=(profile_code,),
            authority=RuleEvidenceAuthority.ORIGINAL_OFFICIAL_NOTICE.value,
        )
    for accepted_code in sorted(accepted_codes):
        path = catalog.ancestry_path(profile_code, accepted_code)
        if path is not None:
            return _result(
                MajorMatchKind.CATALOG,
                "MAJOR_CATALOG_MATCH",
                deterministic=True,
                official=True,
                matched_code=accepted_code,
                path=path,
                authority=RuleEvidenceAuthority.FORMAL_OFFICIAL_ATTACHMENT.value,
            )
    for target_code in mapping.targets_by_source.get(profile_code, ()):
        for accepted_code in sorted(accepted_codes):
            path = catalog.ancestry_path(target_code, accepted_code)
            if path is not None:
                return _result(
                    MajorMatchKind.APPROVED_MAPPING,
                    "MAJOR_APPROVED_MAPPING_MATCH",
                    deterministic=True,
                    official=False,
                    matched_code=target_code,
                    path=path,
                    authority=RuleEvidenceAuthority.HUMAN_APPROVED_MAPPING.value,
                )
    if semantic_candidate:
        return _result(
            MajorMatchKind.SEMANTIC_CANDIDATE,
            "MAJOR_SEMANTIC_CANDIDATE_ONLY",
            authority=RuleEvidenceAuthority.LLM_SEMANTIC_INFERENCE.value,
        )
    return _result(
        MajorMatchKind.NO_MATCH,
        "MAJOR_DETERMINISTIC_NO_MATCH",
        deterministic=True,
        official=True,
        authority=RuleEvidenceAuthority.ORIGINAL_OFFICIAL_NOTICE.value,
    )


def _result(
    kind: MajorMatchKind,
    reason_code: str,
    *,
    deterministic: bool = False,
    official: bool = False,
    matched_code: str | None = None,
    path: tuple[str, ...] = (),
    authority: str | None = None,
) -> MajorMatchResult:
    return MajorMatchResult(
        kind=kind,
        deterministic=deterministic,
        official_conclusion=official,
        matched_code=matched_code,
        catalog_path=path,
        evidence_authority=authority,
        reason_code=reason_code,
    )


def _reject_catalog_cycles(entries: Mapping[str, MajorCatalogEntry]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(code: str) -> None:
        if code in visiting:
            raise MajorAssetError(f"major catalog cycle reaches {code}")
        if code in visited:
            return
        visiting.add(code)
        for parent_code in entries[code].parent_codes:
            visit(parent_code)
        visiting.remove(code)
        visited.add(code)

    for code in sorted(entries):
        visit(code)


def _reject_mapping_cycles(targets_by_source: Mapping[str, tuple[str, ...]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(code: str) -> None:
        if code in visiting:
            raise MajorAssetError(f"approved mapping cycle reaches {code}")
        if code in visited:
            return
        visiting.add(code)
        for target_code in targets_by_source.get(code, ()):
            visit(target_code)
        visiting.remove(code)
        visited.add(code)

    for code in sorted(targets_by_source):
        visit(code)


__all__ = [
    "ApprovedMajorMapping",
    "MajorAssetError",
    "MajorCatalog",
    "MajorCatalogEntry",
    "MajorMatchKind",
    "MajorMatchResult",
    "load_approved_major_mapping",
    "load_major_catalog",
    "match_major",
]
