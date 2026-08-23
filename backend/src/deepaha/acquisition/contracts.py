from enum import StrEnum
from hashlib import sha256
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import (
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)

from deepaha.contracts.common import EntityId, HttpStatus, Instant, NonEmptyString, Sha256
from deepaha.contracts.phase1 import ContractModel
from deepaha.contracts.phase2 import CaptureOutcome
from deepaha.sources.transport import MAX_RESPONSE_BYTES

ContractVersion = Literal["1.0.0"]
DiagnosticCode = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{0,127}$")]
MetricValue = bool | int | str


class AcquisitionContract(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FetchStrategy(StrEnum):
    STRUCTURED = "STRUCTURED"
    STATIC_HTTP = "STATIC_HTTP"
    BROWSER = "BROWSER"
    OFFICIAL_ALTERNATIVE = "OFFICIAL_ALTERNATIVE"
    MANUAL = "MANUAL"


class ValidationStatus(StrEnum):
    VALID = "VALID"
    CONTENT_CHALLENGE = "CONTENT_CHALLENGE"
    CAPTCHA_REQUIRED = "CAPTCHA_REQUIRED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    ACCESS_DENIED = "ACCESS_DENIED"
    UNEXPECTED_CONTENT = "UNEXPECTED_CONTENT"
    ZERO_DISCOVERY_SUSPECT = "ZERO_DISCOVERY_SUSPECT"
    SELECTOR_DRIFT = "SELECTOR_DRIFT"


class ChallengeType(StrEnum):
    JAVASCRIPT_COOKIE = "JAVASCRIPT_COOKIE"
    CAPTCHA = "CAPTCHA"
    AUTHENTICATION = "AUTHENTICATION"
    ACCESS_CONTROL = "ACCESS_CONTROL"


class SourceUsageRole(StrEnum):
    PRIMARY_EVIDENCE = "PRIMARY_EVIDENCE"
    OFFICIAL_DISCOVERY = "OFFICIAL_DISCOVERY"
    TRUSTED_LEAD = "TRUSTED_LEAD"
    GENERAL_LEAD = "GENERAL_LEAD"


class DiscoveryKind(StrEnum):
    NONE = "NONE"
    HTML_LINKS = "HTML_LINKS"
    JSON_ITEMS = "JSON_ITEMS"
    XML_ITEMS = "XML_ITEMS"


class ExpectedChangeFrequency(StrEnum):
    HOURLY = "HOURLY"
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    IRREGULAR = "IRREGULAR"


def _normalize_unique(values: object, *, label: str) -> object:
    if not isinstance(values, (list, tuple)):
        return values
    normalized = tuple(
        value.strip().lower().rstrip(".") if isinstance(value, str) else value for value in values
    )
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{label} contains duplicates after normalization")
    return normalized


def _require_public_url_shape(value: HttpUrl, *, label: str) -> None:
    parsed = urlsplit(str(value))
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{label} must not contain credentials")


def _require_bounded_safe_metrics(
    value: dict[str, MetricValue], *, label: str
) -> dict[str, MetricValue]:
    forbidden_fragments = (
        "auth",
        "body",
        "content",
        "cookie",
        "password",
        "raw",
        "secret",
        "token",
    )
    for key, item in value.items():
        lowered = key.lower()
        if any(fragment in lowered for fragment in forbidden_fragments):
            raise ValueError(f"{label} contains a forbidden diagnostic key")
        if isinstance(item, str) and len(item) > 128:
            raise ValueError(f"{label} string value is too long")
    return value


def _required_challenge(status: ValidationStatus) -> ChallengeType | None:
    return {
        ValidationStatus.CONTENT_CHALLENGE: ChallengeType.JAVASCRIPT_COOKIE,
        ValidationStatus.CAPTCHA_REQUIRED: ChallengeType.CAPTCHA,
        ValidationStatus.AUTH_REQUIRED: ChallengeType.AUTHENTICATION,
        ValidationStatus.ACCESS_DENIED: ChallengeType.ACCESS_CONTROL,
    }.get(status)


class FetchRequest(AcquisitionContract):
    request_id: EntityId
    source_id: EntityId
    endpoint_id: EntityId
    requested_url: HttpUrl
    strategy: FetchStrategy
    allowed_hosts: tuple[NonEmptyString, ...] = Field(min_length=1, max_length=16)
    expected_media_types: tuple[NonEmptyString, ...] = Field(min_length=1, max_length=16)
    timeout_seconds: int = Field(ge=1, le=120)
    max_attempts: int = Field(ge=1, le=3)
    max_bytes: int = Field(gt=0, le=MAX_RESPONSE_BYTES)
    policy_version: NonEmptyString
    contract_version: ContractVersion

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def normalize_hosts(cls, value: object) -> object:
        return _normalize_unique(value, label="allowed_hosts")

    @field_validator("expected_media_types", mode="before")
    @classmethod
    def normalize_media_types(cls, value: object) -> object:
        return _normalize_unique(value, label="expected_media_types")

    @model_validator(mode="after")
    def require_url_policy(self) -> Self:
        _require_public_url_shape(self.requested_url, label="requested_url")
        host = (urlsplit(str(self.requested_url)).hostname or "").lower().rstrip(".")
        if host not in self.allowed_hosts:
            raise ValueError("requested_url host must be present in allowed_hosts")
        return self


class FetchResult(AcquisitionContract):
    request_id: EntityId
    source_id: EntityId
    endpoint_id: EntityId
    observation_id: EntityId | None = None
    artifact_id: EntityId | None = None
    requested_url: HttpUrl
    final_url: HttpUrl | None
    redirect_chain: tuple[HttpUrl, ...] = Field(max_length=11)
    strategy: FetchStrategy
    fetched_at: Instant
    outcome: CaptureOutcome
    http_status: HttpStatus | None
    media_type: NonEmptyString | None
    safe_headers: dict[NonEmptyString, NonEmptyString] = Field(max_length=16)
    body: bytes | None
    body_object_key: NonEmptyString | None
    content_sha256: Sha256 | None
    byte_size: int | None = Field(default=None, ge=0, le=MAX_RESPONSE_BYTES)
    fetcher_name: NonEmptyString
    fetcher_version: NonEmptyString
    error_code: DiagnosticCode | None
    contract_version: ContractVersion

    @field_validator("safe_headers")
    @classmethod
    def require_safe_headers(cls, value: dict[str, str]) -> dict[str, str]:
        allowed = {"cache-control", "content-length", "content-type", "etag", "last-modified"}
        normalized = {key.strip().lower(): item.strip() for key, item in value.items()}
        if set(normalized) - allowed:
            raise ValueError("safe_headers contains a non-permitted header")
        if any(len(item) > 512 for item in normalized.values()):
            raise ValueError("safe_headers value is too long")
        return normalized

    @model_validator(mode="after")
    def require_result_consistency(self) -> Self:
        _require_public_url_shape(self.requested_url, label="requested_url")
        if self.final_url is not None:
            _require_public_url_shape(self.final_url, label="final_url")
        if self.redirect_chain:
            if self.redirect_chain[0] != self.requested_url:
                raise ValueError("redirect_chain must begin with requested_url")
            if self.final_url is None or self.redirect_chain[-1] != self.final_url:
                raise ValueError("redirect_chain must end with final_url")

        if self.outcome is CaptureOutcome.FAILED:
            if (
                any(
                    value is not None
                    for value in (
                        self.body,
                        self.body_object_key,
                        self.artifact_id,
                        self.content_sha256,
                        self.byte_size,
                    )
                )
                or self.error_code is None
            ):
                raise ValueError("FAILED requires error_code and forbids body metadata")
            return self

        if self.error_code is not None:
            raise ValueError("successful FetchResult forbids error_code")
        if (self.body is None) == (self.body_object_key is None):
            raise ValueError("successful FetchResult requires exactly one body location")
        if self.body_object_key is not None and (
            self.observation_id is None or self.artifact_id is None
        ):
            raise ValueError("persisted FetchResult requires observation_id and artifact_id")
        if self.artifact_id is not None and self.observation_id is None:
            raise ValueError("artifact_id requires observation_id")
        if self.content_sha256 is None or self.byte_size is None or self.final_url is None:
            raise ValueError("successful FetchResult requires content metadata and final_url")
        if self.body is not None:
            if sha256(self.body).hexdigest() != self.content_sha256:
                raise ValueError("content_sha256 does not match body")
            if len(self.body) != self.byte_size:
                raise ValueError("byte_size does not match body")
        if self.outcome is CaptureOutcome.NOT_MODIFIED and self.http_status != 304:
            raise ValueError("NOT_MODIFIED requires HTTP 304")
        return self


class ContentExpectations(AcquisitionContract):
    minimum_bytes: int = Field(ge=0, le=MAX_RESPONSE_BYTES)
    maximum_bytes: int = Field(gt=0, le=MAX_RESPONSE_BYTES)
    required_markers: tuple[NonEmptyString, ...] = Field(max_length=32)
    forbidden_markers: tuple[NonEmptyString, ...] = Field(max_length=32)
    required_selectors: tuple[NonEmptyString, ...] = Field(max_length=32)
    minimum_discovered_count: int | None = Field(default=None, ge=0, le=10_000)
    structured_kind: Literal["JSON", "XML"] | None
    contract_version: ContractVersion

    @field_validator("required_markers", "forbidden_markers", "required_selectors", mode="before")
    @classmethod
    def normalize_expectation_lists(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            return value
        normalized = tuple(item.strip() if isinstance(item, str) else item for item in value)
        if len(normalized) != len(set(normalized)):
            raise ValueError("expectation list contains duplicates")
        return normalized

    @model_validator(mode="after")
    def require_ordered_byte_limits(self) -> Self:
        if self.maximum_bytes < self.minimum_bytes:
            raise ValueError("maximum_bytes must not be less than minimum_bytes")
        return self


class ValidationResult(AcquisitionContract):
    status: ValidationStatus
    challenge_type: ChallengeType | None
    discovered_count: int | None = Field(default=None, ge=0, le=10_000)
    diagnostic_codes: tuple[DiagnosticCode, ...] = Field(max_length=32)
    metrics: dict[NonEmptyString, MetricValue] = Field(max_length=32)
    validator_name: NonEmptyString
    validator_version: NonEmptyString
    metrics_schema_version: NonEmptyString
    contract_version: ContractVersion

    @field_validator("metrics")
    @classmethod
    def require_bounded_safe_metrics(cls, value: dict[str, MetricValue]) -> dict[str, MetricValue]:
        return _require_bounded_safe_metrics(value, label="metrics")

    @model_validator(mode="after")
    def require_challenge_consistency(self) -> Self:
        required_challenge = _required_challenge(self.status)
        if required_challenge is None and self.challenge_type is not None:
            raise ValueError("challenge_type is only valid for a challenge status")
        if required_challenge is not None and self.challenge_type is not required_challenge:
            raise ValueError("challenge_type must match validation status")
        return self


class AcquisitionEvaluationSchema(AcquisitionContract):
    acquisition_evaluation_id: EntityId
    observation_id: EntityId
    source_id: EntityId
    endpoint_id: EntityId
    artifact_id: EntityId
    strategy_used: FetchStrategy
    validation_status: ValidationStatus
    challenge_type: ChallengeType | None
    redirect_chain: tuple[HttpUrl, ...] = Field(min_length=1, max_length=11)
    discovered_count: int | None = Field(default=None, ge=0, le=10_000)
    manual_intervention: bool
    diagnostic_codes: tuple[DiagnosticCode, ...] = Field(max_length=32)
    validator_name: NonEmptyString
    validator_version: NonEmptyString
    metrics_schema_version: NonEmptyString
    validation_metrics: dict[NonEmptyString, MetricValue] = Field(max_length=32)
    evaluated_at: Instant
    contract_version: ContractVersion

    @field_validator("validation_metrics")
    @classmethod
    def require_bounded_safe_validation_metrics(
        cls, value: dict[str, MetricValue]
    ) -> dict[str, MetricValue]:
        return _require_bounded_safe_metrics(value, label="validation_metrics")

    @model_validator(mode="after")
    def require_evaluation_consistency(self) -> Self:
        required_challenge = _required_challenge(self.validation_status)
        if required_challenge is None and self.challenge_type is not None:
            raise ValueError("challenge_type is only valid for a challenge status")
        if required_challenge is not None and self.challenge_type is not required_challenge:
            raise ValueError("challenge_type must match validation status")
        if (self.strategy_used is FetchStrategy.MANUAL) is not self.manual_intervention:
            raise ValueError("manual_intervention must match MANUAL strategy")
        for index, url in enumerate(self.redirect_chain):
            _require_public_url_shape(url, label=f"redirect_chain[{index}]")
        return self


class FetchPlanStep(AcquisitionContract):
    strategy: FetchStrategy
    fallback_on: tuple[ValidationStatus, ...] = Field(max_length=8)

    @field_validator("fallback_on")
    @classmethod
    def require_safe_fallback_statuses(
        cls, value: tuple[ValidationStatus, ...]
    ) -> tuple[ValidationStatus, ...]:
        if len(value) != len(set(value)):
            raise ValueError("fallback_on contains duplicates")
        allowed = {
            ValidationStatus.CONTENT_CHALLENGE,
            ValidationStatus.UNEXPECTED_CONTENT,
            ValidationStatus.ZERO_DISCOVERY_SUSPECT,
            ValidationStatus.SELECTOR_DRIFT,
        }
        if set(value) - allowed:
            raise ValueError("fallback_on contains a non-permitted status")
        return value


class HealthThresholds(AcquisitionContract):
    expected_change_frequency: ExpectedChangeFrequency
    zero_discovery_grace_runs: int = Field(ge=0, le=10)
    consecutive_failure_limit: int = Field(ge=1, le=20)
    selector_drift_grace_runs: int = Field(ge=0, le=10)


class DiscoverySpec(AcquisitionContract):
    kind: DiscoveryKind
    item_selector: NonEmptyString | None
    detail_link_selector: NonEmptyString | None
    attachment_link_selector: NonEmptyString | None
    pagination_link_selector: NonEmptyString | None
    structured_items_path: tuple[NonEmptyString, ...] = Field(max_length=16)
    structured_detail_url_field: NonEmptyString | None = None
    structured_attachment_url_field: NonEmptyString | None = None
    detail_limit: int = Field(ge=0, le=100)
    attachment_limit: int = Field(ge=0, le=50)
    pagination_limit: int = Field(ge=0, le=10)

    @model_validator(mode="after")
    def require_discovery_shape(self) -> Self:
        selectors = (
            self.item_selector,
            self.detail_link_selector,
            self.attachment_link_selector,
            self.pagination_link_selector,
        )
        structured_fields = (
            self.structured_detail_url_field,
            self.structured_attachment_url_field,
        )
        if self.kind is DiscoveryKind.NONE:
            if (
                any(value is not None for value in selectors)
                or any(value is not None for value in structured_fields)
                or self.structured_items_path
                or any((self.detail_limit, self.attachment_limit, self.pagination_limit))
            ):
                raise ValueError("NONE discovery forbids selectors, paths and nonzero limits")
            return self
        if self.kind is DiscoveryKind.HTML_LINKS:
            if self.item_selector is None or self.detail_link_selector is None:
                raise ValueError("HTML_LINKS requires item and detail selectors")
            if self.structured_items_path:
                raise ValueError("HTML_LINKS forbids structured_items_path")
            if any(value is not None for value in structured_fields):
                raise ValueError("HTML_LINKS forbids structured URL fields")
        elif not self.structured_items_path or self.structured_detail_url_field is None:
            raise ValueError("structured discovery requires an item path and detail URL field")
        elif any(value is not None for value in selectors):
            raise ValueError("structured discovery forbids HTML selectors")
        return self


class SourceRecipe(AcquisitionContract):
    recipe_id: EntityId
    source_id: EntityId
    endpoint_id: EntityId
    endpoint_policy_version: NonEmptyString
    recipe_version: NonEmptyString
    usage_role: SourceUsageRole
    allowed_hosts: tuple[NonEmptyString, ...] = Field(min_length=1, max_length=16)
    expected_media_types: tuple[NonEmptyString, ...] = Field(min_length=1, max_length=16)
    allowed_url_patterns: tuple[NonEmptyString, ...] = Field(min_length=1, max_length=16)
    fetch_plan: tuple[FetchPlanStep, ...] = Field(min_length=1, max_length=5)
    expectations: ContentExpectations
    discovery: DiscoverySpec
    maximum_requests: int = Field(ge=1, le=25)
    maximum_elapsed_seconds: int = Field(ge=1, le=300)
    health: HealthThresholds
    active: bool
    verified_at: Instant
    contract_version: ContractVersion

    @field_validator("allowed_hosts", "expected_media_types", mode="before")
    @classmethod
    def normalize_policy_lists(cls, value: object, info: ValidationInfo) -> object:
        return _normalize_unique(value, label=info.field_name or "policy list")

    @field_validator("allowed_url_patterns")
    @classmethod
    def require_path_patterns(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("allowed_url_patterns contains duplicates")
        if any(not item.startswith("/") or "://" in item for item in value):
            raise ValueError("allowed_url_patterns must contain path-only glob patterns")
        return value

    @model_validator(mode="after")
    def require_bounded_coherent_plan(self) -> Self:
        strategies = tuple(step.strategy for step in self.fetch_plan)
        if len(strategies) != len(set(strategies)):
            raise ValueError("fetch_plan contains duplicate strategies")
        if self.maximum_requests < len(self.fetch_plan):
            raise ValueError("maximum_requests cannot be less than fetch_plan length")
        if self.discovery.kind is DiscoveryKind.JSON_ITEMS and (
            self.expectations.structured_kind != "JSON"
        ):
            raise ValueError("JSON_ITEMS requires JSON content expectations")
        if self.discovery.kind is DiscoveryKind.XML_ITEMS and (
            self.expectations.structured_kind != "XML"
        ):
            raise ValueError("XML_ITEMS requires XML content expectations")
        if self.discovery.kind is DiscoveryKind.HTML_LINKS and (
            self.expectations.structured_kind is not None
        ):
            raise ValueError("HTML_LINKS forbids structured content expectations")
        normalized_media_types = {
            value.partition(";")[0].strip().lower() for value in self.expected_media_types
        }
        if self.expectations.structured_kind == "JSON" and not any(
            value == "application/json" or value.endswith("+json")
            for value in normalized_media_types
        ):
            raise ValueError("JSON expectations require a matching expected media type")
        if self.expectations.structured_kind == "XML" and not any(
            value in {"application/xml", "text/xml"} or value.endswith("+xml")
            for value in normalized_media_types
        ):
            raise ValueError("XML expectations require a matching expected media type")
        if self.discovery.kind is DiscoveryKind.HTML_LINKS and not (
            normalized_media_types & {"application/xhtml+xml", "text/html"}
        ):
            raise ValueError("HTML discovery requires a matching expected media type")
        return self


class SourceRecipeManifest(AcquisitionContract):
    schema_version: ContractVersion
    recipes: tuple[SourceRecipe, ...]

    @model_validator(mode="after")
    def reject_duplicate_recipes(self) -> Self:
        recipe_ids: set[object] = set()
        endpoint_versions: set[tuple[object, object, str]] = set()
        for recipe in self.recipes:
            endpoint_version = (
                recipe.source_id,
                recipe.endpoint_id,
                recipe.recipe_version,
            )
            if recipe.recipe_id in recipe_ids or endpoint_version in endpoint_versions:
                raise ValueError("duplicate Recipe identity or endpoint version")
            recipe_ids.add(recipe.recipe_id)
            endpoint_versions.add(endpoint_version)
        return self


__all__ = [
    "AcquisitionEvaluationSchema",
    "AcquisitionContract",
    "ChallengeType",
    "ContentExpectations",
    "DiscoveryKind",
    "DiscoverySpec",
    "ExpectedChangeFrequency",
    "FetchPlanStep",
    "FetchRequest",
    "FetchResult",
    "FetchStrategy",
    "HealthThresholds",
    "SourceUsageRole",
    "SourceRecipe",
    "SourceRecipeManifest",
    "ValidationResult",
    "ValidationStatus",
]
