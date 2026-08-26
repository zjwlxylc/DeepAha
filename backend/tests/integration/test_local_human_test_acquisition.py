import os
import re
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4, uuid7

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from deepaha.acquisition.contracts import (
    ChallengeType,
    SourceRecipe,
    ValidationStatus,
)
from deepaha.acquisition.models import AcquisitionEvaluation
from deepaha.acquisition.orchestrator import AcquisitionRunSummary, RunTerminalCode
from deepaha.acquisition.recipes import load_recipe_manifest
from deepaha.artifacts.models import RawArtifact
from deepaha.documents.models import Document, EvidenceRef
from deepaha.local_human_test.bootstrap import (
    AcquisitionExecution,
    BootstrapReviewRequired,
    HumanTestAcquisitionService,
    ProvisionalOpportunityService,
    ProvisionalTarget,
)
from deepaha.local_human_test.contracts import (
    CreateRunCommand,
    ItemStatus,
    ProviderConfigSnapshot,
    RunMode,
)
from deepaha.local_human_test.models import LocalHumanTestItem, LocalHumanTestRun
from deepaha.local_human_test.runs import HumanTestRunService
from deepaha.opportunities.models import Opportunity, OpportunityVersion
from deepaha.p9b.models import ModelCall
from deepaha.review.models import ReviewerAccountModel
from deepaha.sources.models import CaptureObservation
from deepaha.sources.registry import import_registry, load_registry_manifest

pytestmark = pytest.mark.integration
ROOT = Path(__file__).parents[3]
RECIPES_PATH = ROOT / "config" / "acquisition" / "recipes.v1.json"
REGISTRY_PATH = ROOT / "config" / "sources" / "phase2-official-endpoints.json"
NOW = datetime(2026, 8, 26, 11, 0, tzinfo=UTC)


def _temporary_database(database_url: str) -> tuple[str, Engine, URL, str]:
    database_name = f"deepaha_human_acquisition_{uuid4().hex}"
    assert re.fullmatch(r"deepaha_human_acquisition_[0-9a-f]{32}", database_name)
    url = make_url(database_url)
    maintenance_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with maintenance_engine.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
    temporary_url = url.set(database=database_name)
    return (
        database_name,
        maintenance_engine,
        temporary_url,
        temporary_url.render_as_string(hide_password=False),
    )


@pytest.fixture(scope="module")
def human_acquisition_engine(database_url: str) -> Iterator[Engine]:
    name, maintenance, temporary_url, rendered = _temporary_database(database_url)
    previous = os.environ.get("DEEPAHA_DATABASE_URL")
    engine: Engine | None = None
    try:
        os.environ["DEEPAHA_DATABASE_URL"] = rendered
        command.upgrade(Config("alembic.ini"), "head")
        engine = create_engine(temporary_url)
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        if previous is None:
            os.environ.pop("DEEPAHA_DATABASE_URL", None)
        else:
            os.environ["DEEPAHA_DATABASE_URL"] = previous
        with maintenance.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        maintenance.dispose()


@pytest.fixture(autouse=True)
def clean_human_acquisition_rows(human_acquisition_engine: Engine) -> Iterator[None]:
    yield
    with human_acquisition_engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE TABLE reviewer_accounts, sources, opportunities RESTART IDENTITY CASCADE"
            )
        )


def _active_recipe(*, role: str = "PRIMARY_EVIDENCE") -> SourceRecipe:
    return next(
        recipe
        for recipe in load_recipe_manifest(RECIPES_PATH).recipes
        if recipe.active and recipe.usage_role == role
    )


def _seed_document(
    engine: Engine,
    *,
    title: str | None = "2026 年青年发展计划公告",
    validation_status: ValidationStatus = ValidationStatus.VALID,
    role: str = "PRIMARY_EVIDENCE",
) -> tuple[UUID, UUID, UUID]:
    recipe = _active_recipe(role=role)
    artifact_id = uuid7()
    observation_id = uuid7()
    document_id = uuid7()
    evidence_ref_id = uuid7()
    evaluation_id = uuid7()
    content_sha256 = sha256(str(artifact_id).encode()).hexdigest()
    with Session(engine) as session:
        import_registry(session, load_registry_manifest(REGISTRY_PATH))
        from deepaha.sources.models import SourceEndpoint

        endpoint = session.get(SourceEndpoint, recipe.endpoint_id)
        assert endpoint is not None
        session.add(
            RawArtifact(
                artifact_id=artifact_id,
                source_id=recipe.source_id,
                requested_url=endpoint.url,
                resolved_url=endpoint.url,
                retrieved_at=NOW,
                http_status=200,
                media_type="text/html",
                content_sha256=content_sha256,
                storage_bucket="deepaha-local-test",
                object_key=f"raw/sha256/{content_sha256[:2]}/{content_sha256}",
                byte_size=1024,
                collector_version="local-test-1",
                metadata_schema_version="0.2.0",
            )
        )
        session.flush()
        session.add(
            CaptureObservation(
                observation_id=observation_id,
                collection_run_id=uuid7(),
                attempt_number=1,
                endpoint_id=recipe.endpoint_id,
                source_id=recipe.source_id,
                requested_url=endpoint.url,
                resolved_url=endpoint.url,
                started_at=NOW,
                completed_at=NOW,
                outcome="SUCCEEDED",
                http_status=200,
                response_etag=None,
                response_last_modified=None,
                artifact_id=artifact_id,
                error_code=None,
                collector_name="local-test",
                collector_version="1.0.0",
                policy_version=recipe.endpoint_policy_version,
            )
        )
        session.flush()
        session.add(
            AcquisitionEvaluation(
                acquisition_evaluation_id=evaluation_id,
                observation_id=observation_id,
                endpoint_id=recipe.endpoint_id,
                source_id=recipe.source_id,
                artifact_id=artifact_id,
                strategy_used=recipe.fetch_plan[0].strategy.value,
                validation_status=validation_status.value,
                challenge_type=(
                    ChallengeType.ACCESS_CONTROL.value
                    if validation_status is ValidationStatus.ACCESS_DENIED
                    else None
                ),
                redirect_chain=[endpoint.url],
                discovered_count=0,
                manual_intervention=False,
                diagnostic_codes=[],
                validator_name="deepaha-content-validator",
                validator_version="1.0.0",
                metrics_schema_version="1.0.0",
                validation_metrics={},
                evaluated_at=NOW,
                contract_version="1.0.0",
            )
        )
        session.add(
            Document(
                document_id=document_id,
                artifact_id=artifact_id,
                title=title,
                published_at=NOW,
                language="zh-CN",
                extracted_text_uri="local://derived/document.txt",
                parser_name="html_lxml",
                parser_version="0.2.0",
                parse_contract_version="0.2.0",
                document_parse_key="b" * 64,
                parse_confidence=Decimal("1.0"),
                created_at=NOW,
            )
        )
        session.flush()
        session.add(
            EvidenceRef(
                evidence_ref_id=evidence_ref_id,
                document_id=document_id,
                artifact_id=artifact_id,
                locator_kind="full_document",
                locator_value="*",
                locator_schema_version="0.1.0",
                locator_payload=None,
                quote_sha256=None,
            )
        )
        session.commit()
    return document_id, recipe.recipe_id, evaluation_id


def _service(engine: Engine) -> ProvisionalOpportunityService:
    return ProvisionalOpportunityService(
        session_factory=sessionmaker(bind=engine, expire_on_commit=False),
        recipes=load_recipe_manifest(RECIPES_PATH).recipes,
        clock=lambda: NOW,
    )


def test_bootstrap_uses_only_deterministic_governed_fields(
    human_acquisition_engine: Engine,
) -> None:
    document_id, recipe_id, _ = _seed_document(human_acquisition_engine)

    result = _service(human_acquisition_engine).create(
        document_id=document_id,
        recipe_id=recipe_id,
    )

    assert isinstance(result, ProvisionalTarget)
    assert result.opportunity.publication_status == "INTERNAL"
    assert result.opportunity.status == "UNKNOWN"
    assert result.opportunity.type == "STATE_OWNED_ENTERPRISE_JOB"
    assert result.opportunity.issuer_name == "中国中车集团有限公司"
    assert result.version.review_status == "PENDING"
    assert result.version.version == 1
    with Session(human_acquisition_engine) as session:
        assert session.scalar(select(func.count()).select_from(ModelCall)) == 0


@pytest.mark.parametrize(
    ("title", "validation_status", "role", "reason"),
    [
        (None, ValidationStatus.VALID, "PRIMARY_EVIDENCE", "DOCUMENT_TITLE_MISSING"),
        (
            "青年计划",
            ValidationStatus.ACCESS_DENIED,
            "PRIMARY_EVIDENCE",
            "ACQUISITION_NOT_VALID",
        ),
        (
            "青年计划",
            ValidationStatus.VALID,
            "OFFICIAL_DISCOVERY",
            "RECIPE_NOT_PRIMARY_EVIDENCE",
        ),
    ],
)
def test_invalid_bootstrap_inputs_require_review_and_create_no_opportunity(
    human_acquisition_engine: Engine,
    title: str | None,
    validation_status: ValidationStatus,
    role: str,
    reason: str,
) -> None:
    document_id, recipe_id, _ = _seed_document(
        human_acquisition_engine,
        title=title,
        validation_status=validation_status,
        role=role,
    )

    result = _service(human_acquisition_engine).create(
        document_id=document_id,
        recipe_id=recipe_id,
    )

    assert isinstance(result, BootstrapReviewRequired)
    assert reason in result.reason_codes
    with Session(human_acquisition_engine) as session:
        assert session.scalar(select(func.count()).select_from(Opportunity)) == 0
        assert session.scalar(select(func.count()).select_from(OpportunityVersion)) == 0
        assert session.scalar(select(func.count()).select_from(ModelCall)) == 0


def _run_command(reviewer_id: UUID, recipe_id: UUID, mode: RunMode) -> CreateRunCommand:
    provider = ProviderConfigSnapshot.model_validate(
        {
            "provider": "deepseek",
            "base_url": "https://provider.invalid",
            "protocol": "openai_chat_completions",
            "model_id": "deepseek-chat",
            "model_snapshot": "manual-2026-08-26",
        }
    )
    return CreateRunCommand(
        mode=mode,
        recipe_ids=(str(recipe_id),),
        provider=provider,
        reviewer_id=reviewer_id,
    )


def _execution(recipe: SourceRecipe, evaluation_id: UUID) -> AcquisitionExecution:
    return AcquisitionExecution(
        summary=AcquisitionRunSummary(
            recipe_id=recipe.recipe_id,
            recipe_version=recipe.recipe_version,
            source_id=recipe.source_id,
            endpoint_id=recipe.endpoint_id,
            terminal_code=RunTerminalCode.COMPLETE,
            request_count=1,
            valid_count=1,
            parsed_count=1,
            discovered_count=0,
            attachment_count=0,
            evidence_count=1,
            attempts=(),
        ),
        acquisition_evaluation_ids=(evaluation_id,),
    )


def test_acquisition_coordinates_replay_without_fetch_and_live_with_budget_first(
    human_acquisition_engine: Engine,
) -> None:
    document_id, recipe_id, evaluation_id = _seed_document(human_acquisition_engine)
    recipes = load_recipe_manifest(RECIPES_PATH).recipes
    recipe = next(value for value in recipes if value.recipe_id == recipe_id)
    factory = sessionmaker(bind=human_acquisition_engine, expire_on_commit=False)
    reviewer_id = uuid7()
    with factory.begin() as session:
        session.add(
            ReviewerAccountModel(
                reviewer_id=reviewer_id,
                active=True,
                synthetic=False,
                principal_label=f"acquisition-operator-{reviewer_id}",
                roles=["LOCAL_TEST_OPERATOR"],
                allowed_purposes=["OPPORTUNITY_FACT_VALIDATION"],
                created_at=NOW,
            )
        )
    execution = _execution(recipe, evaluation_id)
    callbacks: list[Callable[[], object]] = []

    class Runner:
        def __init__(self, callback: Callable[[], object], *, invoke_callback: bool) -> None:
            self._callback = callback
            self._invoke_callback = invoke_callback

        def run(self, requested_recipe_id: UUID) -> AcquisitionExecution:
            assert requested_recipe_id == recipe_id
            if self._invoke_callback:
                self._callback()
            return execution

    def runner_factory(*, invoke_callback: bool) -> Callable[[Callable[[], object]], Runner]:
        def build(callback: Callable[[], object]) -> Runner:
            callbacks.append(callback)
            return Runner(callback, invoke_callback=invoke_callback)

        return build

    for mode, expected_requests in (
        (RunMode.OFFICIAL_REPLAY, 0),
        (RunMode.LIVE_OFFICIAL, 1),
    ):
        run_service = HumanTestRunService(session_factory=factory, now_factory=lambda: NOW)
        run = run_service.create(
            _run_command(reviewer_id, recipe_id, mode),
            idempotency_key=f"acquisition-{mode.value}",
        )
        claim = run_service.claim_next(f"worker-{mode.value}", now=NOW)
        assert claim is not None
        service = HumanTestAcquisitionService(
            session_factory=factory,
            run_service=run_service,
            recipes=recipes,
            registry=load_registry_manifest(REGISTRY_PATH),
            live_runner_factory=runner_factory(invoke_callback=True),
            replay_runner_factory=runner_factory(invoke_callback=False),
        )

        acquired = service.acquire(
            claim.item_id,
            mode,
            worker_id=f"worker-{mode.value}",
        )

        assert acquired is not None
        assert acquired.document_id == document_id
        with factory() as session:
            persisted_run = session.get(LocalHumanTestRun, run.run_id)
            persisted_item = session.get(LocalHumanTestItem, claim.item_id)
            assert persisted_run is not None
            assert persisted_item is not None
            assert persisted_run.official_request_count == expected_requests
            assert persisted_item.status == ItemStatus.BOOTSTRAP_REVIEW
            assert persisted_item.document_id == document_id

    assert len(callbacks) == 2
