from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from deepaha.acquisition.contracts import SourceRecipe
from deepaha.acquisition.evaluations import EvaluationService
from deepaha.acquisition.health_evidence import AcquisitionEvidenceService
from deepaha.acquisition.models import AcquisitionEvaluation, AcquisitionRun
from deepaha.acquisition.orchestrator import (
    AcquisitionOrchestrator,
    DatabaseEndpointPolicyLoader,
    RunTerminalCode,
)
from deepaha.acquisition.pipeline import advance_valid_artifact
from deepaha.artifacts.models import RawArtifact
from deepaha.artifacts.s3 import S3ObjectStore
from deepaha.core.settings import Settings
from deepaha.documents.html import LxmlHtmlParser
from deepaha.documents.models import Document
from deepaha.documents.service import DocumentService
from deepaha.sources.collector import CollectionRunner
from deepaha.sources.models import CaptureObservation, SourceEndpoint
from deepaha.sources.transport import HttpResponse
from tests.integration.test_collection_service import (
    FakeSleeper,
    PublicResolver,
    ScriptedTransport,
    create_endpoint,
)

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 23, 10, 0, tzinfo=UTC)
VALID_BODY = (
    b"<html><head><title>Official</title></head><body><main>"
    b'<p>official notice</p><a class="notice" href="/detail/1">one</a>'
    b'<a class="notice" href="/detail/1#duplicate">duplicate</a>'
    b"</main></body></html>"
)


@pytest.fixture(scope="module")
def object_store() -> S3ObjectStore:
    value = S3ObjectStore(Settings())
    value.ensure_bucket()
    return value


@pytest.fixture
def factory(migrated_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=migrated_engine, expire_on_commit=False)


class SharedClock:
    def __init__(self) -> None:
        self.value = NOW

    def now(self) -> datetime:
        return self.value

    def __call__(self) -> datetime:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += timedelta(seconds=seconds)


def http_response(url: str, body: bytes) -> HttpResponse:
    return HttpResponse(
        status_code=200,
        url=url,
        media_type="text/html; charset=utf-8",
        etag=None,
        last_modified=None,
        location=None,
        body=body,
    )


def configured_recipe(endpoint: SourceEndpoint) -> SourceRecipe:
    return SourceRecipe.model_validate(
        {
            "recipe_id": "019c0000-0000-7000-8000-000000000401",
            "source_id": endpoint.source_id,
            "endpoint_id": endpoint.endpoint_id,
            "endpoint_policy_version": endpoint.policy_version,
            "recipe_version": "2026-08-23.integration.1",
            "usage_role": "PRIMARY_EVIDENCE",
            "allowed_hosts": endpoint.allowed_hosts,
            "expected_media_types": endpoint.expected_media_types,
            "allowed_url_patterns": ["/list", "/detail/*"],
            "fetch_plan": [{"strategy": "STATIC_HTTP", "fallback_on": []}],
            "expectations": {
                "minimum_bytes": 20,
                "maximum_bytes": 1_000_000,
                "required_markers": ["official notice"],
                "forbidden_markers": [],
                "required_selectors": ["main", "a.notice"],
                "minimum_discovered_count": 1,
                "structured_kind": None,
                "contract_version": "1.0.0",
            },
            "discovery": {
                "kind": "HTML_LINKS",
                "item_selector": "main",
                "detail_link_selector": "a.notice",
                "attachment_link_selector": None,
                "pagination_link_selector": None,
                "structured_items_path": [],
                "detail_limit": 10,
                "attachment_limit": 0,
                "pagination_limit": 0,
            },
            "maximum_requests": 5,
            "maximum_elapsed_seconds": 30,
            "health": {
                "expected_change_frequency": "DAILY",
                "zero_discovery_grace_runs": 1,
                "consecutive_failure_limit": 3,
                "selector_drift_grace_runs": 0,
            },
            "active": True,
            "verified_at": NOW,
            "contract_version": "1.0.0",
        }
    )


def build_orchestrator(
    *,
    factory: sessionmaker[Session],
    object_store: S3ObjectStore,
    recipe: SourceRecipe,
    transport: ScriptedTransport,
    clock: SharedClock,
) -> AcquisitionOrchestrator:
    from deepaha.acquisition.fetchers import StaticHttpFetcher

    runner = CollectionRunner(
        session_factory=factory,
        object_store=object_store,
        transport=transport,
        resolver=PublicResolver(),
        clock=clock,
        sleeper=FakeSleeper(),
    )
    fetcher = StaticHttpFetcher(session_factory=factory, collection_runner=runner)
    document_service = DocumentService(
        session_factory=factory,
        object_store=object_store,
        parsers=(LxmlHtmlParser(),),
        clock=clock,
    )

    def advance(evaluation_id: UUID) -> object:
        return advance_valid_artifact(
            session_factory=factory,
            document_service=document_service,
            acquisition_evaluation_id=evaluation_id,
        )

    return AcquisitionOrchestrator(
        recipes=(recipe,),
        policy_loader=DatabaseEndpointPolicyLoader(factory),
        fetchers={recipe.fetch_plan[0].strategy: fetcher},
        object_store=object_store,
        evaluation_recorder=EvaluationService(factory),
        run_recorder=AcquisitionEvidenceService(factory),
        advance_valid_artifact=advance,
        clock=clock,
        sleeper=clock.sleep,
    )


def prepare_endpoint(factory: sessionmaker[Session]) -> SourceEndpoint:
    endpoint = create_endpoint(factory)
    with factory.begin() as session:
        session.execute(
            update(SourceEndpoint)
            .where(SourceEndpoint.endpoint_id == endpoint.endpoint_id)
            .values(minimum_interval_seconds=1)
        )
    endpoint.minimum_interval_seconds = 1
    return endpoint


def test_orchestrator_persists_common_evidence_deduplicates_and_parses_valid_only(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint = prepare_endpoint(factory)
    recipe = configured_recipe(endpoint)
    transport = ScriptedTransport(
        [
            http_response("https://official.example/list", VALID_BODY),
            http_response("https://official.example/detail/1", VALID_BODY),
        ]
    )
    summary = build_orchestrator(
        factory=factory,
        object_store=object_store,
        recipe=recipe,
        transport=transport,
        clock=SharedClock(),
    ).run(recipe.recipe_id)

    assert summary.terminal_code is RunTerminalCode.COMPLETE
    assert summary.request_count == summary.valid_count == summary.parsed_count == 2
    assert summary.discovered_count == 1
    assert [request.url for request in transport.requests] == [
        "https://official.example/list",
        "https://official.example/detail/1",
    ]
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(CaptureObservation)) == 2
        assert session.scalar(select(func.count()).select_from(RawArtifact)) == 1
        assert session.scalar(select(func.count()).select_from(AcquisitionEvaluation)) == 2
        assert session.scalar(select(func.count()).select_from(AcquisitionRun)) == 1
        assert session.scalar(select(func.count()).select_from(Document)) == 1
        run = session.scalar(select(AcquisitionRun))
        assert run is not None
        persisted_lineage = {
            (
                item.get("capture_observation_id"),
                item.get("acquisition_evaluation_id"),
                item.get("raw_artifact_id"),
            )
            for item in run.strategy_attempts
        }
        expected_lineage = {
            (
                str(evaluation.observation_id),
                str(evaluation.acquisition_evaluation_id),
                str(evaluation.artifact_id),
            )
            for evaluation in session.scalars(select(AcquisitionEvaluation))
        }
        assert persisted_lineage == expected_lineage


def test_challenge_is_evaluated_but_cannot_create_document(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint = prepare_endpoint(factory)
    recipe = configured_recipe(endpoint)
    challenge = b"<main>captcha validation page</main>"
    summary = build_orchestrator(
        factory=factory,
        object_store=object_store,
        recipe=recipe,
        transport=ScriptedTransport([http_response("https://official.example/list", challenge)]),
        clock=SharedClock(),
    ).run(recipe.recipe_id)

    assert summary.terminal_code is RunTerminalCode.CAPTCHA_REQUIRED
    with factory() as session:
        evaluation = session.scalar(select(AcquisitionEvaluation))
        assert evaluation is not None
        assert evaluation.validation_status == "CAPTCHA_REQUIRED"
        assert session.scalar(select(func.count()).select_from(RawArtifact)) == 1
        assert session.scalar(select(func.count()).select_from(AcquisitionRun)) == 1
        assert session.scalar(select(func.count()).select_from(Document)) == 0
