from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import deepaha.db.models  # noqa: F401  # Register ORM FK targets in the standalone worker.
from deepaha.acquisition.contracts import FetchStrategy, SourceRecipe
from deepaha.acquisition.evaluations import EvaluationService
from deepaha.acquisition.fetchers import OfficialAlternativeFetcher, StaticHttpFetcher
from deepaha.acquisition.health_evidence import AcquisitionEvidenceService
from deepaha.acquisition.models import AcquisitionRun
from deepaha.acquisition.orchestrator import (
    AcquisitionOrchestrator,
    AcquisitionRunSummary,
    DatabaseEndpointPolicyLoader,
    RunTerminalCode,
)
from deepaha.acquisition.pipeline import advance_valid_artifact
from deepaha.acquisition.recipes import load_recipe_manifest
from deepaha.artifacts.local_file import LocalFileObjectStore
from deepaha.core.settings import Settings
from deepaha.db.session import get_engine, session_factory
from deepaha.documents.html import P9BHtmlDocumentParser
from deepaha.documents.pdf import PypdfDocumentParser
from deepaha.documents.service import DocumentService
from deepaha.documents.spreadsheet import OpenpyxlSpreadsheetParser
from deepaha.local_human_test.bootstrap import (
    AcquisitionExecution,
    HumanTestAcquisitionService,
)
from deepaha.local_human_test.contracts import ItemStatus, ProviderConfigSnapshot, RunMode
from deepaha.local_human_test.extraction import P9BExtractionCoordinator
from deepaha.local_human_test.models import LocalHumanTestItem, LocalHumanTestRun
from deepaha.local_human_test.provider_config import (
    LocalProviderConfigStore,
    ProviderConfigError,
    ResolvedProviderConfig,
    WindowsDirectoryHardener,
    WindowsDpapiProtector,
)
from deepaha.local_human_test.runs import HumanTestRunService
from deepaha.local_human_test.worker import (
    HumanTestExtractionProcessor,
    HumanTestWorker,
    RoutedHumanTestItem,
    RoutedHumanTestItemProcessor,
)
from deepaha.p9b.gateway import GatewayExecutor
from deepaha.p9b.openai_compatible import OpenAICompatibleProviderAdapter
from deepaha.sources.collector import (
    CollectionRunner,
    SocketHostResolver,
    SystemClock,
    SystemSleeper,
)
from deepaha.sources.registry import load_registry_manifest
from deepaha.sources.transport import HttpxTransport

LOGGER = logging.getLogger(__name__)
RESPONSE_BUCKET = "deepaha-local-human-test"


class _PersistedAcquisitionRunner:
    def __init__(
        self,
        *,
        orchestrator: AcquisitionOrchestrator,
        session_factory: sessionmaker[Session],
    ) -> None:
        self._orchestrator = orchestrator
        self._session_factory = session_factory

    def run(self, recipe_id: UUID) -> AcquisitionExecution:
        summary = self._orchestrator.run(recipe_id)
        with self._session_factory() as session:
            run = session.scalar(
                select(AcquisitionRun)
                .where(
                    AcquisitionRun.recipe_id == summary.recipe_id,
                    AcquisitionRun.source_id == summary.source_id,
                    AcquisitionRun.endpoint_id == summary.endpoint_id,
                    AcquisitionRun.recipe_version == summary.recipe_version,
                )
                .order_by(
                    AcquisitionRun.completed_at.desc(),
                    AcquisitionRun.acquisition_run_id.desc(),
                )
                .limit(1)
            )
            if run is None:
                raise RuntimeError("ACQUISITION_RUN_EVIDENCE_MISSING")
            evaluation_ids = _evaluation_ids(run.strategy_attempts)
        return AcquisitionExecution(
            summary=summary,
            acquisition_evaluation_ids=evaluation_ids,
        )


class _ReplayAcquisitionRunner:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        recipes: dict[UUID, SourceRecipe],
    ) -> None:
        self._session_factory = session_factory
        self._recipes = recipes

    def run(self, recipe_id: UUID) -> AcquisitionExecution:
        recipe = self._recipes.get(recipe_id)
        if recipe is None:
            raise LookupError("ACTIVE_RECIPE_NOT_FOUND")
        with self._session_factory() as session:
            run = session.scalar(
                select(AcquisitionRun)
                .where(
                    AcquisitionRun.recipe_id == recipe_id,
                    AcquisitionRun.terminal_code == RunTerminalCode.COMPLETE.value,
                    AcquisitionRun.parsed_count > 0,
                )
                .order_by(
                    AcquisitionRun.completed_at.desc(),
                    AcquisitionRun.acquisition_run_id.desc(),
                )
                .limit(1)
            )
            if run is None:
                return AcquisitionExecution(
                    summary=_empty_replay_summary(recipe),
                    acquisition_evaluation_ids=(),
                )
            return AcquisitionExecution(
                summary=AcquisitionRunSummary(
                    recipe_id=run.recipe_id,
                    recipe_version=run.recipe_version,
                    source_id=run.source_id,
                    endpoint_id=run.endpoint_id,
                    terminal_code=RunTerminalCode(run.terminal_code),
                    request_count=0,
                    valid_count=run.validated_count,
                    parsed_count=run.parsed_count,
                    discovered_count=run.discovered_count,
                    attachment_count=run.attachment_count,
                    evidence_count=run.evidence_count,
                    attempts=(),
                ),
                acquisition_evaluation_ids=_evaluation_ids(run.strategy_attempts),
            )


class _FailedConfigurationExtraction:
    def __init__(
        self,
        *,
        service: HumanTestRunService,
        item_id: UUID,
        error_code: str,
    ) -> None:
        self._service = service
        self._item_id = item_id
        self._error_code = error_code

    def extract(self, item_id: UUID) -> object:
        if item_id != self._item_id:
            raise RuntimeError("LOCAL_HUMAN_TEST_ITEM_CHANGED")
        return self._service.transition_item(
            item_id,
            expected=ItemStatus.EXTRACTING,
            target=ItemStatus.FAILED_CONFIG,
            error_code=self._error_code,
        )


def _evaluation_ids(attempts: list[dict[str, object]]) -> tuple[UUID, ...]:
    values: list[UUID] = []
    for attempt in attempts:
        value = attempt.get("acquisition_evaluation_id")
        if value is not None:
            values.append(UUID(str(value)))
    return tuple(values)


def _empty_replay_summary(recipe: SourceRecipe) -> AcquisitionRunSummary:
    return AcquisitionRunSummary(
        recipe_id=recipe.recipe_id,
        recipe_version=recipe.recipe_version,
        source_id=recipe.source_id,
        endpoint_id=recipe.endpoint_id,
        terminal_code=RunTerminalCode.FETCH_FAILED,
        request_count=0,
        valid_count=0,
        parsed_count=0,
        discovered_count=0,
        attachment_count=0,
        evidence_count=0,
        attempts=(),
    )


def _provider_matches_snapshot(
    resolved: ResolvedProviderConfig,
    snapshot: ProviderConfigSnapshot,
) -> bool:
    return (
        resolved.provider == snapshot.provider
        and str(resolved.base_url).rstrip("/") == str(snapshot.base_url).rstrip("/")
        and resolved.protocol == snapshot.protocol
        and resolved.model_id == snapshot.model_id
        and resolved.model_snapshot == snapshot.model_snapshot
        and resolved.provider_region == snapshot.provider_region
        and resolved.zero_retention == snapshot.zero_retention
        and resolved.training_use == snapshot.training_use
        and resolved.supports_idempotency == snapshot.supports_idempotency
    )


def _validate_settings(settings: Settings) -> Path:
    if (
        settings.environment != "development"
        or not settings.local_human_test_enabled
        or settings.local_human_test_root is None
        or settings.local_human_test_bind_host not in {"127.0.0.1", "localhost", "::1"}
        or settings.database_url is None
    ):
        raise RuntimeError("LOCAL_HUMAN_TEST_RUNTIME_DISABLED")
    return Path(settings.local_human_test_root).resolve()


def build_human_test_worker(settings: Settings | None = None) -> HumanTestWorker:
    resolved_settings = settings or Settings()
    runtime_root = _validate_settings(resolved_settings)
    project_root = Path(__file__).resolve().parents[4]
    engine = get_engine(resolved_settings)
    factory = session_factory(engine)
    recipes = load_recipe_manifest(
        project_root / "config" / "acquisition" / "recipes.v1.json"
    ).recipes
    registry = load_registry_manifest(
        project_root / "config" / "sources" / "phase2-official-endpoints.json"
    )
    object_store = LocalFileObjectStore(
        root=runtime_root / "objects",
        bucket=RESPONSE_BUCKET,
    )
    object_store.ensure_bucket()
    run_service = HumanTestRunService(
        session_factory=factory,
        lease_seconds=resolved_settings.local_human_test_lease_seconds,
    )

    def live_runner_factory(
        reserve_request: Callable[[], object],
    ) -> _PersistedAcquisitionRunner:
        collection_runner = CollectionRunner(
            session_factory=factory,
            object_store=object_store,
            transport=HttpxTransport(),
            resolver=SocketHostResolver(),
            clock=SystemClock(),
            sleeper=SystemSleeper(),
        )
        fetchers = {
            FetchStrategy.STATIC_HTTP: StaticHttpFetcher(
                session_factory=factory,
                collection_runner=collection_runner,
            ),
            FetchStrategy.OFFICIAL_ALTERNATIVE: OfficialAlternativeFetcher(
                session_factory=factory,
                collection_runner=collection_runner,
            ),
        }
        document_service = DocumentService(
            session_factory=factory,
            object_store=object_store,
            parsers=(P9BHtmlDocumentParser(), PypdfDocumentParser(), OpenpyxlSpreadsheetParser()),
        )

        def advance(evaluation_id: UUID) -> object:
            return advance_valid_artifact(
                session_factory=factory,
                document_service=document_service,
                acquisition_evaluation_id=evaluation_id,
            )

        orchestrator = AcquisitionOrchestrator(
            recipes=recipes,
            policy_loader=DatabaseEndpointPolicyLoader(factory),
            fetchers=fetchers,
            object_store=object_store,
            evaluation_recorder=EvaluationService(factory),
            advance_valid_artifact=advance,
            run_recorder=AcquisitionEvidenceService(factory),
            clock=SystemClock().now,
            reserve_request=reserve_request,
        )
        return _PersistedAcquisitionRunner(
            orchestrator=orchestrator,
            session_factory=factory,
        )

    def replay_runner_factory(
        _reserve_request: Callable[[], object],
    ) -> _ReplayAcquisitionRunner:
        return _ReplayAcquisitionRunner(
            session_factory=factory,
            recipes={recipe.recipe_id: recipe for recipe in recipes},
        )

    acquisition = HumanTestAcquisitionService(
        session_factory=factory,
        run_service=run_service,
        recipes=recipes,
        registry=registry,
        live_runner_factory=live_runner_factory,
        replay_runner_factory=replay_runner_factory,
    )
    provider_store = LocalProviderConfigStore(
        root=runtime_root,
        protector=WindowsDpapiProtector(),
        hardener=WindowsDirectoryHardener(),
    )

    def load_item(item_id: UUID) -> RoutedHumanTestItem:
        with factory() as session:
            row = session.execute(
                select(LocalHumanTestItem.status, LocalHumanTestRun.mode)
                .join(LocalHumanTestRun, LocalHumanTestItem.run_id == LocalHumanTestRun.run_id)
                .where(LocalHumanTestItem.item_id == item_id)
            ).one_or_none()
            if row is None:
                raise LookupError("LOCAL_HUMAN_TEST_ITEM_NOT_FOUND")
            return RoutedHumanTestItem(
                status=ItemStatus(row.status),
                mode=RunMode(row.mode),
            )

    def extraction_factory(item_id: UUID) -> HumanTestExtractionProcessor:
        with factory() as session:
            snapshot_value = session.scalar(
                select(LocalHumanTestRun.provider_config_snapshot)
                .join(
                    LocalHumanTestItem,
                    LocalHumanTestItem.run_id == LocalHumanTestRun.run_id,
                )
                .where(LocalHumanTestItem.item_id == item_id)
            )
        if snapshot_value is None:
            return _FailedConfigurationExtraction(
                service=run_service,
                item_id=item_id,
                error_code="PROVIDER_CONFIG_SNAPSHOT_MISSING",
            )
        snapshot = ProviderConfigSnapshot.model_validate(snapshot_value)
        try:
            provider = provider_store.load_for_invocation()
        except ProviderConfigError:
            return _FailedConfigurationExtraction(
                service=run_service,
                item_id=item_id,
                error_code="PROVIDER_CONFIG_UNAVAILABLE",
            )
        if not _provider_matches_snapshot(provider, snapshot):
            return _FailedConfigurationExtraction(
                service=run_service,
                item_id=item_id,
                error_code="PROVIDER_CONFIG_CHANGED_AFTER_RUN",
            )
        adapter = OpenAICompatibleProviderAdapter(
            config=provider,
            object_store=object_store,
        )
        return P9BExtractionCoordinator(
            session_factory=factory,
            gateway=GatewayExecutor(session_factory=factory, adapter=adapter),
            object_store=object_store,
            response_bucket=RESPONSE_BUCKET,
            run_service=run_service,
            worker_id=resolved_settings.local_human_test_worker_id,
        )

    processor = RoutedHumanTestItemProcessor(
        item_loader=load_item,
        acquisition=acquisition,
        extraction_factory=extraction_factory,
        worker_id=resolved_settings.local_human_test_worker_id,
    )
    return HumanTestWorker(
        service=run_service,
        processor=processor,
        worker_id=resolved_settings.local_human_test_worker_id,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DeepAha local human-test worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=0.5)
    arguments = parser.parse_args(argv)
    if not 0.1 <= arguments.poll_seconds <= 10:
        parser.error("--poll-seconds must be between 0.1 and 10")
    logging.basicConfig(level=logging.INFO)
    worker = build_human_test_worker()
    if arguments.once:
        worker.run_once()
        return 0
    try:
        while True:
            if not worker.run_once():
                time.sleep(cast(float, arguments.poll_seconds))
    except KeyboardInterrupt:
        LOGGER.info("local human-test worker stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_human_test_worker", "main"]
