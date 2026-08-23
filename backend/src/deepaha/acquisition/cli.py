import argparse
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import UUID

from deepaha.acquisition.contracts import FetchStrategy, SourceRecipe
from deepaha.acquisition.evaluations import EvaluationService
from deepaha.acquisition.fetchers import StaticHttpFetcher
from deepaha.acquisition.health_evidence import AcquisitionEvidenceService
from deepaha.acquisition.orchestrator import (
    AcquisitionOrchestrator,
    AcquisitionRunSummary,
    DatabaseEndpointPolicyLoader,
    EndpointPolicy,
    RunTerminalCode,
)
from deepaha.acquisition.pipeline import advance_valid_artifact
from deepaha.acquisition.recipes import load_recipe_manifest
from deepaha.artifacts.s3 import S3ObjectStore
from deepaha.core.settings import Settings
from deepaha.db.session import get_engine, session_factory
from deepaha.documents.html import LxmlHtmlParser
from deepaha.documents.pdf import PypdfDocumentParser
from deepaha.documents.service import DocumentService
from deepaha.documents.spreadsheet import OpenpyxlSpreadsheetParser
from deepaha.sources.collector import (
    CollectionRunner,
    SocketHostResolver,
    SystemClock,
    SystemSleeper,
)
from deepaha.sources.transport import HttpxTransport

Qualifier = Callable[[UUID, UUID, Path, int, int], "QualificationOutcome"]


@dataclass(frozen=True, slots=True)
class QualificationOutcome:
    summary: AcquisitionRunSummary
    unsafe_diagnostics: Mapping[str, object] | None = None


def main(argv: list[str] | None = None, *, qualifier: Qualifier | None = None) -> int:
    parser = _build_parser()
    try:
        arguments = parser.parse_args(argv)
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else 2

    if arguments.command != "qualify":
        _emit({"error_code": "COMMAND_NOT_SUPPORTED"})
        return 2
    if not _valid_budget(arguments.maximum_requests, arguments.minimum_interval_seconds):
        _emit({"error_code": "QUALIFICATION_BUDGET_INVALID"})
        return 2
    if not arguments.live or not Settings().allow_live_source_check:
        _emit({"error_code": "LIVE_QUALIFICATION_NOT_ALLOWED"})
        return 2

    selected = qualifier or _run_live_qualification
    try:
        outcome = selected(
            arguments.recipe_id,
            arguments.endpoint_id,
            arguments.recipe_path,
            arguments.maximum_requests,
            arguments.minimum_interval_seconds,
        )
    except Exception:
        _emit({"error_code": "QUALIFICATION_FAILED"})
        return 1

    _emit(_safe_summary(outcome.summary))
    return 0 if outcome.summary.terminal_code is RunTerminalCode.COMPLETE else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeepAha bounded source qualification")
    commands = parser.add_subparsers(dest="command", required=True)
    qualify = commands.add_parser("qualify")
    qualify.add_argument("--recipe-id", type=UUID, required=True)
    qualify.add_argument("--endpoint-id", type=UUID, required=True)
    qualify.add_argument("--recipe-path", type=Path, required=True)
    qualify.add_argument("--maximum-requests", type=int, required=True)
    qualify.add_argument("--minimum-interval-seconds", type=int, required=True)
    qualify.add_argument("--live", action="store_true")
    return parser


def _valid_budget(maximum_requests: int, minimum_interval_seconds: int) -> bool:
    return 1 <= maximum_requests <= 25 and 1 <= minimum_interval_seconds <= 86_400


def _run_live_qualification(
    recipe_id: UUID,
    endpoint_id: UUID,
    recipe_path: Path,
    maximum_requests: int,
    minimum_interval_seconds: int,
) -> QualificationOutcome:
    settings = Settings()
    factory = session_factory(get_engine(settings))
    manifest = load_recipe_manifest(recipe_path)
    recipe = _select_recipe(manifest.recipes, recipe_id, endpoint_id, maximum_requests)
    base_policy_loader = DatabaseEndpointPolicyLoader(factory)

    def policy_loader(selected: SourceRecipe) -> EndpointPolicy:
        policy = base_policy_loader(selected)
        return replace(
            policy,
            minimum_interval_seconds=max(
                policy.minimum_interval_seconds,
                minimum_interval_seconds,
            ),
        )

    store = S3ObjectStore(settings)
    store.ensure_bucket()
    collection_runner = CollectionRunner(
        session_factory=factory,
        object_store=store,
        transport=HttpxTransport(),
        resolver=SocketHostResolver(),
        clock=SystemClock(),
        sleeper=SystemSleeper(),
    )
    fetchers = {
        FetchStrategy.STATIC_HTTP: StaticHttpFetcher(
            session_factory=factory,
            collection_runner=collection_runner,
        )
    }
    missing = {step.strategy for step in recipe.fetch_plan} - set(fetchers)
    if missing:
        raise RuntimeError("Recipe requires an unavailable qualification strategy")
    document_service = DocumentService(
        session_factory=factory,
        object_store=store,
        parsers=(LxmlHtmlParser(), PypdfDocumentParser(), OpenpyxlSpreadsheetParser()),
    )

    def advance(evaluation_id: UUID) -> object:
        return advance_valid_artifact(
            session_factory=factory,
            document_service=document_service,
            acquisition_evaluation_id=evaluation_id,
        )

    clock = SystemClock()
    orchestrator = AcquisitionOrchestrator(
        recipes=(recipe,),
        policy_loader=policy_loader,
        fetchers=fetchers,
        object_store=store,
        evaluation_recorder=EvaluationService(factory),
        advance_valid_artifact=advance,
        run_recorder=AcquisitionEvidenceService(factory),
        clock=clock.now,
    )
    return QualificationOutcome(summary=orchestrator.run(recipe.recipe_id))


def _select_recipe(
    recipes: tuple[SourceRecipe, ...],
    recipe_id: UUID,
    endpoint_id: UUID,
    maximum_requests: int,
) -> SourceRecipe:
    matches = [
        recipe
        for recipe in recipes
        if recipe.recipe_id == recipe_id and recipe.endpoint_id == endpoint_id and recipe.active
    ]
    if len(matches) != 1:
        raise LookupError("Active Recipe and endpoint binding not found")
    values = matches[0].model_dump(mode="python")
    values["maximum_requests"] = min(matches[0].maximum_requests, maximum_requests)
    return SourceRecipe.model_validate(values)


def _safe_summary(summary: AcquisitionRunSummary) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "recipe_id": str(summary.recipe_id),
        "recipe_version": summary.recipe_version,
        "source_id": str(summary.source_id),
        "endpoint_id": str(summary.endpoint_id),
        "terminal_code": summary.terminal_code.value,
        "request_count": summary.request_count,
        "valid_count": summary.valid_count,
        "parsed_count": summary.parsed_count,
        "discovered_count": summary.discovered_count,
        "attachment_count": summary.attachment_count,
        "evidence_count": summary.evidence_count,
        "attempts": [
            {
                "requested_url": str(attempt.requested_url),
                "strategy": attempt.strategy.value,
                "validation_status": (
                    attempt.validation_status.value
                    if attempt.validation_status is not None
                    else None
                ),
                "error_code": attempt.error_code,
            }
            for attempt in summary.attempts
        ],
    }


def _emit(value: dict[str, object]) -> None:
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["QualificationOutcome", "main"]
