from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from time import sleep
from typing import Protocol
from uuid import UUID, uuid7

from pydantic import Field, HttpUrl
from sqlalchemy.orm import Session, sessionmaker

from deepaha.acquisition.contracts import (
    AcquisitionContract,
    AcquisitionEvaluationSchema,
    FetchRequest,
    FetchResult,
    FetchStrategy,
    SourceRecipe,
    ValidationResult,
    ValidationStatus,
)
from deepaha.acquisition.discovery import (
    DiscoveredLink,
    DiscoveredLinkKind,
    DiscoveryError,
    discover_links,
)
from deepaha.acquisition.evaluations import RecordEvaluationCommand
from deepaha.acquisition.health_evidence import RecordRunCommand
from deepaha.acquisition.recipes import recipe_allows_url
from deepaha.acquisition.validation import ContentValidator
from deepaha.sources.models import Source, SourceEndpoint


class RunTerminalCode(StrEnum):
    COMPLETE = "COMPLETE"
    PLAN_EXHAUSTED = "PLAN_EXHAUSTED"
    FETCH_FAILED = "FETCH_FAILED"
    CONTENT_CHALLENGE = "CONTENT_CHALLENGE"
    CAPTCHA_REQUIRED = "CAPTCHA_REQUIRED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    ACCESS_DENIED = "ACCESS_DENIED"
    REQUEST_BUDGET_EXHAUSTED = "REQUEST_BUDGET_EXHAUSTED"
    ELAPSED_BUDGET_EXHAUSTED = "ELAPSED_BUDGET_EXHAUSTED"


class AcquisitionRunAttempt(AcquisitionContract):
    requested_url: HttpUrl
    strategy: FetchStrategy
    validation_status: ValidationStatus | None
    error_code: str | None


class AcquisitionRunSummary(AcquisitionContract):
    recipe_id: UUID
    recipe_version: str
    source_id: UUID
    endpoint_id: UUID
    terminal_code: RunTerminalCode
    request_count: int = Field(ge=0)
    valid_count: int = Field(ge=0)
    parsed_count: int = Field(ge=0)
    discovered_count: int = Field(ge=0)
    attachment_count: int = Field(ge=0)
    evidence_count: int = Field(ge=0)
    attempts: tuple[AcquisitionRunAttempt, ...]


@dataclass(frozen=True, slots=True)
class EndpointPolicy:
    source_id: UUID
    endpoint_id: UUID
    url: str
    allowed_hosts: tuple[str, ...]
    expected_media_types: tuple[str, ...]
    browser_policy: str
    minimum_interval_seconds: int
    timeout_seconds: int
    policy_version: str


class Fetcher(Protocol):
    def fetch(self, request: FetchRequest) -> FetchResult: ...


class EvaluationRecorder(Protocol):
    def record(self, command: RecordEvaluationCommand) -> AcquisitionEvaluationSchema: ...


class RunRecorder(Protocol):
    def record_run(self, command: RecordRunCommand) -> object: ...


class ObjectReader(Protocol):
    def get_bytes(self, *, key: str) -> bytes: ...


@dataclass(frozen=True, slots=True)
class _PendingUrl:
    url: str
    kind: DiscoveredLinkKind | None


@dataclass(frozen=True, slots=True)
class _UrlResult:
    terminal_code: RunTerminalCode | None
    discovered: tuple[DiscoveredLink, ...]
    valid: bool
    parsed: bool
    evidence_count: int


class DatabaseEndpointPolicyLoader:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def __call__(self, recipe: SourceRecipe) -> EndpointPolicy:
        with self._session_factory() as session:
            source = session.get(Source, recipe.source_id)
            endpoint = session.get(SourceEndpoint, recipe.endpoint_id)
            if source is None or endpoint is None:
                raise LookupError("Recipe source or endpoint not found")
            consistent = (
                recipe.active
                and source.active
                and endpoint.active
                and endpoint.source_id == source.source_id == recipe.source_id
                and endpoint.policy_version == recipe.endpoint_policy_version
                and tuple(endpoint.allowed_hosts) == recipe.allowed_hosts
                and tuple(endpoint.expected_media_types) == recipe.expected_media_types
                and recipe_allows_url(recipe, endpoint.url)
                and (
                    recipe.usage_role != "PRIMARY_EVIDENCE"
                    or source.tier == "OFFICIAL_PRIMARY"
                )
                and (
                    all(step.strategy is not FetchStrategy.BROWSER for step in recipe.fetch_plan)
                    or endpoint.browser_policy == "FALLBACK"
                )
            )
            if not consistent:
                raise RuntimeError("RECIPE_POLICY_MISMATCH")
            return EndpointPolicy(
                source_id=source.source_id,
                endpoint_id=endpoint.endpoint_id,
                url=endpoint.url,
                allowed_hosts=tuple(endpoint.allowed_hosts),
                expected_media_types=tuple(endpoint.expected_media_types),
                browser_policy=endpoint.browser_policy,
                minimum_interval_seconds=endpoint.minimum_interval_seconds,
                timeout_seconds=endpoint.timeout_seconds,
                policy_version=endpoint.policy_version,
            )


class AcquisitionOrchestrator:
    def __init__(
        self,
        *,
        recipes: tuple[SourceRecipe, ...],
        policy_loader: Callable[[SourceRecipe], EndpointPolicy],
        fetchers: Mapping[FetchStrategy, Fetcher],
        object_store: ObjectReader,
        evaluation_recorder: EvaluationRecorder,
        advance_valid_artifact: Callable[[UUID], object | None],
        run_recorder: RunRecorder | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleeper: Callable[[float], None] = sleep,
        validator: ContentValidator | None = None,
    ) -> None:
        self._recipes = recipes
        self._policy_loader = policy_loader
        self._fetchers = fetchers
        self._object_store = object_store
        self._evaluation_recorder = evaluation_recorder
        self._advance_valid_artifact = advance_valid_artifact
        self._run_recorder = run_recorder
        self._clock = clock
        self._sleeper = sleeper
        self._validator = validator or ContentValidator()

    def run(self, recipe_id: UUID) -> AcquisitionRunSummary:
        recipe = self._find_recipe(recipe_id)
        policy = self._policy_loader(recipe)
        queue = deque([_PendingUrl(policy.url, None)])
        seen = {policy.url}
        started_at = self._clock()
        attempts: list[AcquisitionRunAttempt] = []
        request_count = 0
        valid_count = 0
        parsed_count = 0
        discovered_count = 0
        attachment_count = 0
        evidence_count = 0
        terminal_code = RunTerminalCode.COMPLETE
        last_request_at: datetime | None = None

        while queue:
            if request_count >= recipe.maximum_requests:
                terminal_code = RunTerminalCode.REQUEST_BUDGET_EXHAUSTED
                break
            if (self._clock() - started_at).total_seconds() >= recipe.maximum_elapsed_seconds:
                terminal_code = RunTerminalCode.ELAPSED_BUDGET_EXHAUSTED
                break
            pending = queue.popleft()
            result, used, last_request_at = self._run_url(
                recipe=recipe,
                policy=policy,
                pending=pending,
                remaining_requests=recipe.maximum_requests - request_count,
                attempts=attempts,
                started_at=started_at,
                last_request_at=last_request_at,
            )
            request_count += used
            if result.valid:
                valid_count += 1
            if result.parsed:
                parsed_count += 1
            evidence_count += result.evidence_count
            discovered_count += len(result.discovered)
            attachment_count += sum(
                link.kind is DiscoveredLinkKind.ATTACHMENT for link in result.discovered
            )
            if result.terminal_code is not None:
                terminal_code = result.terminal_code
                break
            for link in result.discovered:
                url = str(link.url)
                if url not in seen:
                    seen.add(url)
                    queue.append(_PendingUrl(url, link.kind))

        summary = AcquisitionRunSummary(
            recipe_id=recipe.recipe_id,
            recipe_version=recipe.recipe_version,
            source_id=recipe.source_id,
            endpoint_id=recipe.endpoint_id,
            terminal_code=terminal_code,
            request_count=request_count,
            valid_count=valid_count,
            parsed_count=parsed_count,
            discovered_count=discovered_count,
            attachment_count=attachment_count,
            evidence_count=evidence_count,
            attempts=tuple(attempts),
        )
        if self._run_recorder is not None:
            self._record_run(
                summary=summary,
                policy=policy,
                started_at=started_at,
                completed_at=self._clock(),
            )
        return summary

    def _run_url(
        self,
        *,
        recipe: SourceRecipe,
        policy: EndpointPolicy,
        pending: _PendingUrl,
        remaining_requests: int,
        attempts: list[AcquisitionRunAttempt],
        started_at: datetime,
        last_request_at: datetime | None,
    ) -> tuple[_UrlResult, int, datetime | None]:
        used = 0
        for index, step in enumerate(recipe.fetch_plan):
            if used >= remaining_requests:
                return (
                    _UrlResult(
                        RunTerminalCode.REQUEST_BUDGET_EXHAUSTED, (), False, False, 0
                    ),
                    used,
                    last_request_at,
                )
            if (self._clock() - started_at).total_seconds() >= recipe.maximum_elapsed_seconds:
                return (
                    _UrlResult(
                        RunTerminalCode.ELAPSED_BUDGET_EXHAUSTED, (), False, False, 0
                    ),
                    used,
                    last_request_at,
                )
            fetcher = self._fetchers.get(step.strategy)
            if fetcher is None:
                raise LookupError(f"Fetcher not registered: {step.strategy}")
            last_request_at = self._wait_for_policy_interval(policy, last_request_at)
            if (self._clock() - started_at).total_seconds() >= recipe.maximum_elapsed_seconds:
                return (
                    _UrlResult(
                        RunTerminalCode.ELAPSED_BUDGET_EXHAUSTED, (), False, False, 0
                    ),
                    used,
                    last_request_at,
                )
            request = FetchRequest.model_validate(
                {
                    "request_id": uuid7(),
                    "source_id": policy.source_id,
                    "endpoint_id": policy.endpoint_id,
                    "requested_url": pending.url,
                    "strategy": step.strategy,
                    "allowed_hosts": policy.allowed_hosts,
                    "expected_media_types": policy.expected_media_types,
                    "timeout_seconds": policy.timeout_seconds,
                    "max_attempts": 1,
                    "max_bytes": recipe.expectations.maximum_bytes,
                    "policy_version": policy.policy_version,
                    "contract_version": "1.0.0",
                }
            )
            fetched = fetcher.fetch(request)
            used += 1
            if fetched.outcome == "FAILED":
                attempts.append(
                    AcquisitionRunAttempt.model_validate(
                        {
                            "requested_url": pending.url,
                            "strategy": step.strategy,
                            "validation_status": None,
                            "error_code": fetched.error_code,
                        }
                    )
                )
                return (
                    _UrlResult(RunTerminalCode.FETCH_FAILED, (), False, False, 0),
                    used,
                    last_request_at,
                )

            body, integrity_error = self._load_body(fetched)
            validation, discovered = self._validate(
                fetched=fetched,
                body=body,
                integrity_error=integrity_error,
                recipe=recipe,
                policy=policy,
                pending=pending,
            )
            attempts.append(
                AcquisitionRunAttempt.model_validate(
                    {
                        "requested_url": pending.url,
                        "strategy": step.strategy,
                        "validation_status": validation.status,
                        "error_code": (
                            validation.diagnostic_codes[0]
                            if validation.diagnostic_codes
                            else None
                        ),
                    }
                )
            )
            evaluation = self._record_evaluation(fetched, validation)
            hard_stop = _hard_stop(validation.status)
            if hard_stop is not None:
                return _UrlResult(hard_stop, (), False, False, 0), used, last_request_at
            if validation.status is ValidationStatus.VALID:
                advanced = self._advance_valid_artifact(evaluation.acquisition_evaluation_id)
                parsed = (
                    advanced is None
                    or getattr(advanced, "outcome", "SUCCEEDED") == "SUCCEEDED"
                )
                evidence_count = len(getattr(advanced, "evidence_ref_ids", ()))
                return (
                    _UrlResult(None, discovered, True, parsed, evidence_count),
                    used,
                    last_request_at,
                )
            has_next = index + 1 < len(recipe.fetch_plan)
            if validation.status in step.fallback_on and has_next:
                continue
            if validation.status is ValidationStatus.CONTENT_CHALLENGE:
                return (
                    _UrlResult(RunTerminalCode.CONTENT_CHALLENGE, (), False, False, 0),
                    used,
                    last_request_at,
                )
            return (
                _UrlResult(RunTerminalCode.PLAN_EXHAUSTED, (), False, False, 0),
                used,
                last_request_at,
            )
        return (
            _UrlResult(RunTerminalCode.PLAN_EXHAUSTED, (), False, False, 0),
            used,
            last_request_at,
        )

    def _wait_for_policy_interval(
        self,
        policy: EndpointPolicy,
        last_request_at: datetime | None,
    ) -> datetime:
        now = self._clock()
        if last_request_at is not None:
            elapsed = (now - last_request_at).total_seconds()
            remaining = policy.minimum_interval_seconds - elapsed
            if remaining > 0:
                self._sleeper(remaining)
        return self._clock()

    def _validate(
        self,
        *,
        fetched: FetchResult,
        body: bytes | None,
        integrity_error: str | None,
        recipe: SourceRecipe,
        policy: EndpointPolicy,
        pending: _PendingUrl,
    ) -> tuple[ValidationResult, tuple[DiscoveredLink, ...]]:
        if integrity_error is not None or body is None:
            return _validation_error(integrity_error or "BODY_UNAVAILABLE"), ()
        inline = _inline_result(fetched, body)
        discovery_enabled = pending.kind is not DiscoveredLinkKind.ATTACHMENT
        expectations = recipe.expectations
        if pending.kind is not None:
            expectations = expectations.model_copy(update={"minimum_discovered_count": None})
        preliminary = self._validator.evaluate(inline, expectations)
        if not discovery_enabled or preliminary.status not in {
            ValidationStatus.VALID,
            ValidationStatus.ZERO_DISCOVERY_SUSPECT,
        }:
            return preliminary, ()
        try:
            discovered = discover_links(
                content=body,
                media_type=fetched.media_type or "",
                base_url=str(fetched.final_url or fetched.requested_url),
                allowed_hosts=policy.allowed_hosts,
                recipe=recipe,
            )
            if pending.kind is DiscoveredLinkKind.DETAIL:
                discovered = tuple(
                    link
                    for link in discovered
                    if link.kind is DiscoveredLinkKind.ATTACHMENT
                )
        except DiscoveryError as error:
            status = (
                ValidationStatus.SELECTOR_DRIFT
                if error.code == "SELECTOR_DRIFT"
                else ValidationStatus.UNEXPECTED_CONTENT
            )
            return _validation_error(error.code, status=status), ()
        return self._validator.evaluate(
            inline,
            expectations,
            discovered_count=len(discovered),
        ), discovered

    def _record_evaluation(
        self, fetched: FetchResult, validation: ValidationResult
    ) -> AcquisitionEvaluationSchema:
        if fetched.observation_id is None or fetched.artifact_id is None:
            raise RuntimeError("Successful FetchResult must reference persisted common evidence")
        redirect_chain = fetched.redirect_chain or (
            fetched.requested_url,
            fetched.final_url or fetched.requested_url,
        )
        return self._evaluation_recorder.record(
            RecordEvaluationCommand(
                observation_id=fetched.observation_id,
                strategy_used=fetched.strategy,
                redirect_chain=tuple(str(url) for url in redirect_chain),
                manual_intervention=fetched.strategy is FetchStrategy.MANUAL,
                validation_result=validation,
                evaluated_at=self._clock(),
            )
        )

    def _load_body(self, fetched: FetchResult) -> tuple[bytes | None, str | None]:
        if fetched.body is not None:
            return fetched.body, None
        if fetched.body_object_key is None:
            return None, "BODY_UNAVAILABLE"
        body = self._object_store.get_bytes(key=fetched.body_object_key)
        if fetched.content_sha256 != sha256(body).hexdigest() or fetched.byte_size != len(body):
            return None, "OBJECT_INTEGRITY_MISMATCH"
        return body, None

    def _find_recipe(self, recipe_id: UUID) -> SourceRecipe:
        matches = [recipe for recipe in self._recipes if recipe.recipe_id == recipe_id]
        if len(matches) != 1 or not matches[0].active:
            raise LookupError(f"Active Recipe not found: {recipe_id}")
        return matches[0]

    def _record_run(
        self,
        *,
        summary: AcquisitionRunSummary,
        policy: EndpointPolicy,
        started_at: datetime,
        completed_at: datetime,
    ) -> None:
        if self._run_recorder is None:
            return
        self._run_recorder.record_run(
            RecordRunCommand.model_validate(
                {
                    "acquisition_run_id": uuid7(),
                    "recipe_id": summary.recipe_id,
                    "source_id": summary.source_id,
                    "endpoint_id": summary.endpoint_id,
                    "endpoint_policy_version": policy.policy_version,
                    "recipe_version": summary.recipe_version,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "terminal_code": summary.terminal_code.value,
                    "request_count": summary.request_count,
                    "strategy_attempts": [
                        {
                            "strategy": attempt.strategy,
                            "validation_status": attempt.validation_status,
                            "error_code": attempt.error_code,
                        }
                        for attempt in summary.attempts
                    ],
                    "discovered_count": summary.discovered_count,
                    "validated_count": summary.valid_count,
                    "parsed_count": summary.parsed_count,
                    "attachment_count": summary.attachment_count,
                    "evidence_count": summary.evidence_count,
                    "zero_discovery_flag": any(
                        attempt.validation_status is ValidationStatus.ZERO_DISCOVERY_SUSPECT
                        for attempt in summary.attempts
                    ),
                    "selector_drift_flag": any(
                        attempt.validation_status is ValidationStatus.SELECTOR_DRIFT
                        for attempt in summary.attempts
                    ),
                    "manual_intervention": any(
                        attempt.strategy is FetchStrategy.MANUAL for attempt in summary.attempts
                    ),
                    "stable_stop_reason": (
                        None
                        if summary.terminal_code is RunTerminalCode.COMPLETE
                        else summary.terminal_code.value
                    ),
                    "contract_version": "1.0.0",
                }
            )
        )


def _inline_result(fetched: FetchResult, body: bytes) -> FetchResult:
    values = fetched.model_dump(mode="python")
    values["body"] = body
    values["body_object_key"] = None
    return FetchResult.model_validate(values)


def _validation_error(
    code: str,
    *,
    status: ValidationStatus = ValidationStatus.UNEXPECTED_CONTENT,
) -> ValidationResult:
    return ValidationResult(
        status=status,
        challenge_type=None,
        discovered_count=None,
        diagnostic_codes=(code,),
        metrics={},
        validator_name="deepaha-content-validator",
        validator_version="1.0.0",
        metrics_schema_version="1.0.0",
        contract_version="1.0.0",
    )


def _hard_stop(status: ValidationStatus) -> RunTerminalCode | None:
    return {
        ValidationStatus.CAPTCHA_REQUIRED: RunTerminalCode.CAPTCHA_REQUIRED,
        ValidationStatus.AUTH_REQUIRED: RunTerminalCode.AUTH_REQUIRED,
        ValidationStatus.ACCESS_DENIED: RunTerminalCode.ACCESS_DENIED,
    }.get(status)


__all__ = [
    "AcquisitionOrchestrator",
    "AcquisitionRunAttempt",
    "AcquisitionRunSummary",
    "DatabaseEndpointPolicyLoader",
    "EndpointPolicy",
    "RunTerminalCode",
]
