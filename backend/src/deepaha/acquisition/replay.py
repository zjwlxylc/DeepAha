import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol, Self
from uuid import UUID

from pydantic import Field, HttpUrl, field_validator, model_validator

from deepaha.acquisition.contracts import (
    AcquisitionContract,
    FetchResult,
    FetchStrategy,
    SourceRecipe,
    ValidationResult,
    ValidationStatus,
)
from deepaha.acquisition.discovery import DiscoveryError, discover_links
from deepaha.acquisition.recipes import recipe_allows_url
from deepaha.acquisition.validation import (
    METRICS_SCHEMA_VERSION,
    VALIDATOR_NAME,
    VALIDATOR_VERSION,
    ContentValidator,
)
from deepaha.contracts.common import (
    EntityId,
    HttpStatus,
    Instant,
    NonEmptyString,
    Sha256,
)
from deepaha.documents.parser import DocumentParser, ExpectedParseError
from deepaha.sources.transport import MAX_RESPONSE_BYTES


class ReplayStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class ControlledObjectReader(Protocol):
    def get_bytes(self, *, key: str) -> bytes: ...


class ReplayExpectedOutcome(AcquisitionContract):
    validation_status: ValidationStatus
    diagnostic_codes: tuple[str, ...] = Field(max_length=32)
    discovered_urls: tuple[HttpUrl, ...] = Field(max_length=150)
    parse_outcome: Literal["NOT_ATTEMPTED", "SUCCEEDED", "NEEDS_REVIEW", "FAILED"]
    parse_error_code: NonEmptyString | None
    normalized_text_sha256: Sha256 | None
    evidence_locator_count: int = Field(ge=0, le=100_000)

    @model_validator(mode="after")
    def require_parse_shape(self) -> Self:
        if self.validation_status is not ValidationStatus.VALID and (
            self.parse_outcome != "NOT_ATTEMPTED"
            or self.parse_error_code is not None
            or self.normalized_text_sha256 is not None
            or self.evidence_locator_count != 0
        ):
            raise ValueError("non-VALID replay must not claim a parse outcome")
        if self.parse_outcome in {"SUCCEEDED", "NEEDS_REVIEW"} and (
            self.normalized_text_sha256 is None or self.evidence_locator_count == 0
        ):
            raise ValueError("successful replay parse requires text hash and locators")
        if self.parse_outcome == "FAILED" and self.parse_error_code is None:
            raise ValueError("failed replay parse requires parse_error_code")
        if self.parse_outcome == "NOT_ATTEMPTED" and (
            self.parse_error_code is not None
            or self.normalized_text_sha256 is not None
            or self.evidence_locator_count != 0
        ):
            raise ValueError("NOT_ATTEMPTED forbids parse output")
        return self


class ReplayCorpusEntry(AcquisitionContract):
    entry_id: EntityId
    source_id: EntityId
    endpoint_id: EntityId
    artifact_id: EntityId
    recipe_id: EntityId
    endpoint_policy_version: NonEmptyString
    recipe_version: NonEmptyString
    original_url: HttpUrl
    final_url: HttpUrl
    fetched_at: Instant
    http_status: HttpStatus
    media_type: NonEmptyString
    content_sha256: Sha256
    byte_size: int = Field(gt=0, le=MAX_RESPONSE_BYTES)
    object_key: NonEmptyString
    strategy: FetchStrategy
    fetcher_name: NonEmptyString
    fetcher_version: NonEmptyString
    validator_name: NonEmptyString
    validator_version: NonEmptyString
    parser_name: NonEmptyString
    parser_version: NonEmptyString
    expected: ReplayExpectedOutcome
    contract_version: Literal["1.0.0"]

    @field_validator("object_key")
    @classmethod
    def require_relative_object_key(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            "\\" in value
            or path.is_absolute()
            or ".." in path.parts
            or "." in path.parts
            or not path.parts
        ):
            raise ValueError("object_key must be a relative controlled object key")
        return value


class ReplayCorpusManifest(AcquisitionContract):
    schema_version: Literal["1.0.0"]
    corpus_name: NonEmptyString
    entries: tuple[ReplayCorpusEntry, ...] = Field(max_length=100)

    @model_validator(mode="after")
    def reject_duplicate_identities(self) -> Self:
        entry_ids = {entry.entry_id for entry in self.entries}
        artifact_ids = {entry.artifact_id for entry in self.entries}
        if len(entry_ids) != len(self.entries) or len(artifact_ids) != len(self.entries):
            raise ValueError("duplicate replay entry or artifact identity")
        return self


@dataclass(frozen=True, slots=True)
class ReplayBinding:
    source_id: UUID
    endpoint_id: UUID
    artifact_id: UUID


@dataclass(frozen=True, slots=True)
class ReplayResult:
    status: ReplayStatus
    error_code: str | None
    validation_status: ValidationStatus | None
    diagnostic_codes: tuple[str, ...]
    discovered_urls: tuple[str, ...]
    parse_outcome: str | None
    parse_error_code: str | None
    normalized_text_sha256: str | None
    evidence_locator_count: int
    result_sha256: str | None


class ControlledDirectoryStore:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def get_bytes(self, *, key: str) -> bytes:
        path = PurePosixPath(key)
        if (
            "\\" in key
            or path.is_absolute()
            or ".." in path.parts
            or "." in path.parts
            or not path.parts
        ):
            raise ValueError("key must be a relative controlled object key")
        resolved = self._root.joinpath(*path.parts).resolve()
        if not resolved.is_relative_to(self._root):
            raise ValueError("key must be a relative controlled object key")
        return resolved.read_bytes()


def load_replay_manifest(path: Path) -> ReplayCorpusManifest:
    content = path.read_bytes()
    if content.startswith(b"\xef\xbb\xbf"):
        raise ValueError("Replay manifest must not contain a UTF-8 BOM")
    payload: object = json.loads(content.decode("utf-8", errors="strict"))
    return ReplayCorpusManifest.model_validate(payload)


class ReplayRunner:
    def __init__(
        self,
        *,
        object_store: ControlledObjectReader,
        validator: ContentValidator,
        parsers: Sequence[DocumentParser],
        fetcher_versions: Mapping[str, str],
    ) -> None:
        self._object_store = object_store
        self._validator = validator
        self._parsers = tuple(parsers)
        self._fetcher_versions = dict(fetcher_versions)

    def run(
        self,
        *,
        entry: ReplayCorpusEntry,
        recipe: SourceRecipe,
        binding: ReplayBinding,
    ) -> ReplayResult:
        preflight_error = self._preflight_error(entry, recipe, binding)
        if preflight_error is not None:
            return _empty_result(ReplayStatus.FAILED, preflight_error)
        try:
            body = self._object_store.get_bytes(key=entry.object_key)
        except FileNotFoundError, KeyError:
            return _empty_result(ReplayStatus.BLOCKED, "REPLAY_OBJECT_MISSING")
        if len(body) != entry.byte_size:
            return _empty_result(ReplayStatus.FAILED, "REPLAY_OBJECT_SIZE_MISMATCH")
        if sha256(body).hexdigest() != entry.content_sha256:
            return _empty_result(ReplayStatus.FAILED, "REPLAY_OBJECT_HASH_MISMATCH")

        fetched = FetchResult.model_validate(
            {
                "request_id": entry.entry_id,
                "source_id": entry.source_id,
                "endpoint_id": entry.endpoint_id,
                "requested_url": entry.original_url,
                "final_url": entry.final_url,
                "redirect_chain": (entry.original_url, entry.final_url)
                if entry.original_url != entry.final_url
                else (entry.original_url,),
                "strategy": entry.strategy,
                "fetched_at": entry.fetched_at,
                "outcome": "SUCCEEDED",
                "http_status": entry.http_status,
                "media_type": entry.media_type,
                "safe_headers": {},
                "body": body,
                "body_object_key": None,
                "content_sha256": entry.content_sha256,
                "byte_size": entry.byte_size,
                "fetcher_name": entry.fetcher_name,
                "fetcher_version": entry.fetcher_version,
                "error_code": None,
                "contract_version": "1.0.0",
            }
        )
        validation, discovered_urls = self._evaluate_and_discover(fetched, recipe)
        parse_outcome, parse_error, text_hash, locator_count = self._parse(entry, body, validation)
        result_hash = _result_hash(
            entry=entry,
            validation=validation,
            discovered_urls=discovered_urls,
            parse_outcome=parse_outcome,
            parse_error=parse_error,
            text_hash=text_hash,
            locator_count=locator_count,
        )
        matches = (
            validation.status is entry.expected.validation_status
            and validation.diagnostic_codes == entry.expected.diagnostic_codes
            and discovered_urls == tuple(str(url) for url in entry.expected.discovered_urls)
            and parse_outcome == entry.expected.parse_outcome
            and parse_error == entry.expected.parse_error_code
            and text_hash == entry.expected.normalized_text_sha256
            and locator_count == entry.expected.evidence_locator_count
        )
        return ReplayResult(
            status=ReplayStatus.PASSED if matches else ReplayStatus.FAILED,
            error_code=None if matches else "REPLAY_EXPECTATION_MISMATCH",
            validation_status=validation.status,
            diagnostic_codes=validation.diagnostic_codes,
            discovered_urls=discovered_urls,
            parse_outcome=parse_outcome,
            parse_error_code=parse_error,
            normalized_text_sha256=text_hash,
            evidence_locator_count=locator_count,
            result_sha256=result_hash,
        )

    def _preflight_error(
        self,
        entry: ReplayCorpusEntry,
        recipe: SourceRecipe,
        binding: ReplayBinding,
    ) -> str | None:
        if binding != ReplayBinding(entry.source_id, entry.endpoint_id, entry.artifact_id):
            return "REPLAY_BINDING_MISMATCH"
        if (
            recipe.recipe_id != entry.recipe_id
            or recipe.source_id != entry.source_id
            or recipe.endpoint_id != entry.endpoint_id
            or recipe.endpoint_policy_version != entry.endpoint_policy_version
            or recipe.recipe_version != entry.recipe_version
            or entry.strategy not in {step.strategy for step in recipe.fetch_plan}
            or not recipe_allows_url(recipe, str(entry.original_url))
            or not recipe_allows_url(recipe, str(entry.final_url))
        ):
            return "REPLAY_RECIPE_BINDING_MISMATCH"
        if self._fetcher_versions.get(entry.fetcher_name) != entry.fetcher_version:
            return "REPLAY_FETCHER_VERSION_MISMATCH"
        if entry.validator_name != VALIDATOR_NAME or entry.validator_version != VALIDATOR_VERSION:
            return "REPLAY_VALIDATOR_VERSION_MISMATCH"
        parser = self._select_parser(entry)
        if parser is None or parser.version != entry.parser_version:
            return "REPLAY_PARSER_VERSION_MISMATCH"
        return None

    def _select_parser(self, entry: ReplayCorpusEntry) -> DocumentParser | None:
        matches = [
            parser
            for parser in self._parsers
            if parser.name == entry.parser_name and parser.supports(entry.media_type)
        ]
        return matches[0] if len(matches) == 1 else None

    def _evaluate_and_discover(
        self, fetched: FetchResult, recipe: SourceRecipe
    ) -> tuple[ValidationResult, tuple[str, ...]]:
        preliminary = self._validator.evaluate(fetched, recipe.expectations)
        if preliminary.status not in {
            ValidationStatus.VALID,
            ValidationStatus.ZERO_DISCOVERY_SUSPECT,
        }:
            return preliminary, ()
        try:
            links = discover_links(
                content=fetched.body or b"",
                media_type=fetched.media_type or "",
                base_url=str(fetched.final_url or fetched.requested_url),
                allowed_hosts=recipe.allowed_hosts,
                recipe=recipe,
            )
        except DiscoveryError as error:
            status = (
                ValidationStatus.SELECTOR_DRIFT
                if error.code == "SELECTOR_DRIFT"
                else ValidationStatus.UNEXPECTED_CONTENT
            )
            return (
                ValidationResult(
                    status=status,
                    challenge_type=None,
                    discovered_count=0,
                    diagnostic_codes=(error.code,),
                    metrics={"byte_size": fetched.byte_size or 0, "discovered_count": 0},
                    validator_name=VALIDATOR_NAME,
                    validator_version=VALIDATOR_VERSION,
                    metrics_schema_version=METRICS_SCHEMA_VERSION,
                    contract_version="1.0.0",
                ),
                (),
            )
        urls = tuple(str(link.url) for link in links)
        return self._validator.evaluate(
            fetched,
            recipe.expectations,
            discovered_count=len(urls),
        ), urls

    def _parse(
        self,
        entry: ReplayCorpusEntry,
        body: bytes,
        validation: ValidationResult,
    ) -> tuple[str, str | None, str | None, int]:
        if validation.status is not ValidationStatus.VALID:
            return "NOT_ATTEMPTED", None, None, 0
        parser = self._select_parser(entry)
        if parser is None:
            return "FAILED", "PARSER_NOT_AVAILABLE", None, 0
        try:
            parsed = parser.parse(body, artifact_sha256=entry.content_sha256)
        except ExpectedParseError as error:
            return "FAILED", error.code, None, 0
        outcome = "NEEDS_REVIEW" if parsed.needs_review_reasons else "SUCCEEDED"
        parse_error = "|".join(parsed.needs_review_reasons) or None
        return (
            outcome,
            parse_error,
            sha256(parsed.normalized_text.encode("utf-8")).hexdigest(),
            len(parsed.locators),
        )


def _empty_result(status: ReplayStatus, error_code: str) -> ReplayResult:
    return ReplayResult(status, error_code, None, (), (), None, None, None, 0, None)


def _result_hash(
    *,
    entry: ReplayCorpusEntry,
    validation: ValidationResult,
    discovered_urls: tuple[str, ...],
    parse_outcome: str,
    parse_error: str | None,
    text_hash: str | None,
    locator_count: int,
) -> str:
    payload = {
        "entry_id": str(entry.entry_id),
        "validation_status": validation.status,
        "diagnostic_codes": validation.diagnostic_codes,
        "discovered_urls": discovered_urls,
        "parse_outcome": parse_outcome,
        "parse_error_code": parse_error,
        "normalized_text_sha256": text_hash,
        "evidence_locator_count": locator_count,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


__all__ = [
    "ControlledDirectoryStore",
    "ReplayBinding",
    "ReplayCorpusEntry",
    "ReplayCorpusManifest",
    "ReplayExpectedOutcome",
    "ReplayResult",
    "ReplayRunner",
    "ReplayStatus",
    "load_replay_manifest",
]
