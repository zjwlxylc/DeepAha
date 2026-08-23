from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid7

import pytest

from deepaha.acquisition.contracts import (
    AcquisitionEvaluationSchema,
    FetchRequest,
    FetchResult,
    FetchStrategy,
    SourceRecipe,
)
from deepaha.acquisition.evaluations import RecordEvaluationCommand
from deepaha.acquisition.orchestrator import (
    AcquisitionOrchestrator,
    EndpointPolicy,
    RunTerminalCode,
)
from deepaha.acquisition.recipes import load_recipe_manifest

FIXTURE = Path(__file__).parents[1] / "fixtures" / "acquisition" / "recipes-valid.json"
NOW = datetime(2026, 8, 23, 10, 0, tzinfo=UTC)
LIST_BODY = b'<main>official notice<a class="notice" href="/detail/1">one</a></main>'
DETAIL_BODY = b'<main>official notice detail<a class="notice" href="/detail/1">self</a></main>'


def recipe(**changes: object) -> SourceRecipe:
    payload = load_recipe_manifest(FIXTURE).recipes[0].model_dump(mode="json")
    payload.update(changes)
    return SourceRecipe.model_validate(payload)


def policy() -> EndpointPolicy:
    item = load_recipe_manifest(FIXTURE).recipes[0]
    return EndpointPolicy(
        source_id=item.source_id,
        endpoint_id=item.endpoint_id,
        url="https://notices.example.gov/list/",
        allowed_hosts=("notices.example.gov",),
        expected_media_types=("text/html",),
        browser_policy="FALLBACK",
        minimum_interval_seconds=1,
        timeout_seconds=20,
        policy_version="2026-08-23.1",
    )


class FakeFetcher:
    def __init__(self, responses: list[bytes | str]) -> None:
        self.responses = responses
        self.requests: list[FetchRequest] = []
        self.artifacts: dict[UUID, UUID] = {}

    def fetch(self, request: FetchRequest) -> FetchResult:
        self.requests.append(request)
        scripted = self.responses.pop(0)
        if isinstance(scripted, str):
            return FetchResult.model_validate(
                {
                    "request_id": request.request_id,
                    "source_id": request.source_id,
                    "endpoint_id": request.endpoint_id,
                    "requested_url": request.requested_url,
                    "final_url": None,
                    "redirect_chain": [],
                    "strategy": request.strategy,
                    "fetched_at": NOW,
                    "outcome": "FAILED",
                    "http_status": None,
                    "media_type": None,
                    "safe_headers": {},
                    "body": None,
                    "body_object_key": None,
                    "content_sha256": None,
                    "byte_size": None,
                    "fetcher_name": "fake",
                    "fetcher_version": "1.0.0",
                    "error_code": scripted,
                    "contract_version": "1.0.0",
                }
            )
        observation_id = uuid7()
        artifact_id = uuid7()
        self.artifacts[observation_id] = artifact_id
        return FetchResult.model_validate(
            {
                "request_id": request.request_id,
                "source_id": request.source_id,
                "endpoint_id": request.endpoint_id,
                "observation_id": observation_id,
                "artifact_id": artifact_id,
                "requested_url": request.requested_url,
                "final_url": request.requested_url,
                "redirect_chain": [request.requested_url],
                "strategy": request.strategy,
                "fetched_at": NOW,
                "outcome": "SUCCEEDED",
                "http_status": 200,
                "media_type": "text/html",
                "safe_headers": {},
                "body": scripted,
                "body_object_key": None,
                "content_sha256": sha256(scripted).hexdigest(),
                "byte_size": len(scripted),
                "fetcher_name": "fake",
                "fetcher_version": "1.0.0",
                "error_code": None,
                "contract_version": "1.0.0",
            }
        )


class FakeEvaluationRecorder:
    def __init__(self, fetchers: list[FakeFetcher]) -> None:
        self._fetchers = fetchers
        self.commands: list[RecordEvaluationCommand] = []

    def record(self, command: RecordEvaluationCommand) -> AcquisitionEvaluationSchema:
        self.commands.append(command)
        artifact_id = next(
            fetcher.artifacts[command.observation_id]
            for fetcher in self._fetchers
            if command.observation_id in fetcher.artifacts
        )
        return AcquisitionEvaluationSchema.model_validate(
            {
                "acquisition_evaluation_id": uuid7(),
                "observation_id": command.observation_id,
                "source_id": policy().source_id,
                "endpoint_id": policy().endpoint_id,
                "artifact_id": artifact_id,
                "strategy_used": command.strategy_used,
                "validation_status": command.validation_result.status,
                "challenge_type": command.validation_result.challenge_type,
                "redirect_chain": command.redirect_chain,
                "discovered_count": command.validation_result.discovered_count,
                "manual_intervention": command.manual_intervention,
                "diagnostic_codes": command.validation_result.diagnostic_codes,
                "validator_name": command.validation_result.validator_name,
                "validator_version": command.validation_result.validator_version,
                "metrics_schema_version": command.validation_result.metrics_schema_version,
                "validation_metrics": command.validation_result.metrics,
                "evaluated_at": command.evaluated_at,
                "contract_version": "1.0.0",
            }
        )


class FakeAdvancer:
    def __init__(self) -> None:
        self.calls: list[UUID] = []

    def __call__(self, evaluation_id: UUID) -> None:
        self.calls.append(evaluation_id)


class UnusedObjectStore:
    def get_bytes(self, *, key: str) -> bytes:
        raise AssertionError(f"unexpected object read: {key}")


class AdvancingClock:
    def __init__(self, step: timedelta = timedelta()) -> None:
        self.value = NOW
        self.step = step

    def __call__(self) -> datetime:
        current = self.value
        self.value += self.step
        return current


def orchestrator(
    *,
    configured_recipe: SourceRecipe,
    fetchers: dict[FetchStrategy, FakeFetcher],
    clock: Callable[[], datetime] | None = None,
) -> tuple[AcquisitionOrchestrator, FakeEvaluationRecorder, FakeAdvancer]:
    recorder = FakeEvaluationRecorder(list(fetchers.values()))
    advancer = FakeAdvancer()
    value = AcquisitionOrchestrator(
        recipes=(configured_recipe,),
        policy_loader=lambda _: policy(),
        fetchers=fetchers,
        object_store=UnusedObjectStore(),
        evaluation_recorder=recorder,
        advance_valid_artifact=advancer,
        clock=clock or (lambda: NOW),
        sleeper=lambda _: None,
    )
    return value, recorder, advancer


def fallback_recipe(*, maximum_requests: int = 25) -> SourceRecipe:
    return recipe(
        fetch_plan=[
            {"strategy": "STATIC_HTTP", "fallback_on": ["CONTENT_CHALLENGE"]},
            {"strategy": "BROWSER", "fallback_on": []},
        ],
        maximum_requests=maximum_requests,
    )


def test_valid_root_and_discovered_detail_are_parsed_once() -> None:
    static = FakeFetcher([LIST_BODY, DETAIL_BODY])
    value, recorder, advancer = orchestrator(
        configured_recipe=recipe(),
        fetchers={FetchStrategy.STATIC_HTTP: static},
    )

    summary = value.run(recipe().recipe_id)

    assert summary.terminal_code is RunTerminalCode.COMPLETE
    assert summary.request_count == 2
    assert summary.valid_count == 2
    assert summary.parsed_count == 2
    assert summary.discovered_count == 1
    assert len(recorder.commands) == len(advancer.calls) == 2
    assert [str(item.requested_url) for item in static.requests] == [
        "https://notices.example.gov/list/",
        "https://notices.example.gov/detail/1",
    ]


def test_detail_page_can_discover_a_bounded_attachment_without_recursive_details() -> None:
    detail = (
        b'<main>official notice detail<a class="notice" href="/detail/2">other</a>'
        b'<a class="attachment" href="/files/roles.xlsx">roles</a></main>'
    )
    attachment = b'<main>official notice attachment<a class="notice" href="/detail/3">x</a></main>'
    static = FakeFetcher([LIST_BODY, detail, attachment])
    value, _, _ = orchestrator(
        configured_recipe=recipe(),
        fetchers={FetchStrategy.STATIC_HTTP: static},
    )

    summary = value.run(recipe().recipe_id)

    assert summary.terminal_code is RunTerminalCode.COMPLETE
    assert summary.request_count == 3
    assert summary.attachment_count == 1
    assert [str(item.requested_url) for item in static.requests] == [
        "https://notices.example.gov/list/",
        "https://notices.example.gov/detail/1",
        "https://notices.example.gov/files/roles.xlsx",
    ]


def test_declared_content_challenge_falls_back_deterministically() -> None:
    static = FakeFetcher(
        [
            b"<main>document.cookie challenge</main>",
            b"<main>document.cookie challenge</main>",
        ]
    )
    browser = FakeFetcher([LIST_BODY, DETAIL_BODY])
    configured = fallback_recipe()
    value, recorder, _ = orchestrator(
        configured_recipe=configured,
        fetchers={FetchStrategy.STATIC_HTTP: static, FetchStrategy.BROWSER: browser},
    )

    summary = value.run(configured.recipe_id)

    assert [attempt.strategy for attempt in summary.attempts[:2]] == [
        FetchStrategy.STATIC_HTTP,
        FetchStrategy.BROWSER,
    ]
    assert [item.validation_result.status for item in recorder.commands[:2]] == [
        "CONTENT_CHALLENGE",
        "VALID",
    ]


@pytest.mark.parametrize(
    ("body", "terminal"),
    [
        (b"<main>captcha</main>", RunTerminalCode.CAPTCHA_REQUIRED),
        (b'<main><input type="password"></main>', RunTerminalCode.AUTH_REQUIRED),
        (b"<main>access denied</main>", RunTerminalCode.ACCESS_DENIED),
    ],
)
def test_captcha_auth_and_access_control_stop_without_fallback(
    body: bytes, terminal: RunTerminalCode
) -> None:
    static = FakeFetcher([body])
    browser = FakeFetcher([LIST_BODY])
    configured = fallback_recipe()
    value, _, advancer = orchestrator(
        configured_recipe=configured,
        fetchers={FetchStrategy.STATIC_HTTP: static, FetchStrategy.BROWSER: browser},
    )

    summary = value.run(configured.recipe_id)

    assert summary.terminal_code is terminal
    assert summary.request_count == 1
    assert browser.requests == []
    assert advancer.calls == []


def test_exhausted_plan_and_transport_failure_are_explicit() -> None:
    unexpected = b"<main>wrong page</main>"
    configured = recipe(
        fetch_plan=[
            {"strategy": "STATIC_HTTP", "fallback_on": ["UNEXPECTED_CONTENT"]},
            {"strategy": "BROWSER", "fallback_on": []},
        ]
    )
    static = FakeFetcher([unexpected])
    browser = FakeFetcher([unexpected])
    value, _, _ = orchestrator(
        configured_recipe=configured,
        fetchers={FetchStrategy.STATIC_HTTP: static, FetchStrategy.BROWSER: browser},
    )
    assert value.run(configured.recipe_id).terminal_code is RunTerminalCode.PLAN_EXHAUSTED

    failed = FakeFetcher(["NETWORK_TIMEOUT"])
    value, _, _ = orchestrator(
        configured_recipe=recipe(),
        fetchers={FetchStrategy.STATIC_HTTP: failed},
    )
    assert value.run(recipe().recipe_id).terminal_code is RunTerminalCode.FETCH_FAILED


def test_total_request_and_elapsed_budgets_stop_before_another_fetch() -> None:
    static = FakeFetcher([LIST_BODY])
    configured = recipe(maximum_requests=1)
    value, _, _ = orchestrator(
        configured_recipe=configured,
        fetchers={FetchStrategy.STATIC_HTTP: static},
    )
    summary = value.run(configured.recipe_id)
    assert summary.terminal_code is RunTerminalCode.REQUEST_BUDGET_EXHAUSTED
    assert summary.request_count == 1

    slow = FakeFetcher([LIST_BODY])
    configured = recipe(maximum_elapsed_seconds=1)
    value, _, _ = orchestrator(
        configured_recipe=configured,
        fetchers={FetchStrategy.STATIC_HTTP: slow},
        clock=AdvancingClock(timedelta(seconds=2)),
    )
    summary = value.run(configured.recipe_id)
    assert summary.terminal_code is RunTerminalCode.ELAPSED_BUDGET_EXHAUSTED
    assert summary.request_count == 0


def test_off_policy_dynamic_url_is_recorded_invalid_and_never_fetched() -> None:
    body = b'<main>official notice<a class="notice" href="https://evil.example/x">x</a></main>'
    static = FakeFetcher([body])
    value, recorder, advancer = orchestrator(
        configured_recipe=recipe(),
        fetchers={FetchStrategy.STATIC_HTTP: static},
    )

    summary = value.run(recipe().recipe_id)

    assert summary.terminal_code is RunTerminalCode.PLAN_EXHAUSTED
    assert recorder.commands[0].validation_result.diagnostic_codes == (
        "DISCOVERED_URL_NOT_ALLOWED",
    )
    assert summary.request_count == 1
    assert advancer.calls == []


def test_repeated_equivalent_runs_produce_the_same_safe_summary() -> None:
    summaries = []
    for _ in range(2):
        configured = recipe()
        value, _, _ = orchestrator(
            configured_recipe=configured,
            fetchers={FetchStrategy.STATIC_HTTP: FakeFetcher([LIST_BODY, DETAIL_BODY])},
        )
        summaries.append(value.run(configured.recipe_id))

    assert summaries[0] == summaries[1]
    assert "body" not in summaries[0].model_dump_json().lower()
    assert "header" not in summaries[0].model_dump_json().lower()
