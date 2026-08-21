import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from deepaha.artifacts.s3 import S3ObjectStore
from deepaha.core.settings import Settings
from deepaha.db.session import get_engine, session_factory
from deepaha.sources.collector import (
    CollectionRunner,
    CollectionRunResult,
    SocketHostResolver,
    SystemClock,
    SystemSleeper,
)
from deepaha.sources.health import get_source_health
from deepaha.sources.registry import import_registry, load_registry_manifest
from deepaha.sources.transport import HttpxTransport


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        arguments = parser.parse_args(argv)
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else 1

    settings = Settings()
    if arguments.command in {"collect", "collect-manifest"} and not (
        settings.allow_live_source_check
    ):
        _emit({"error_code": "LIVE_SOURCE_CHECK_NOT_ALLOWED"})
        return 2

    try:
        if arguments.command == "import-registry":
            result = _command_import_registry(arguments.path)
        elif arguments.command == "collect":
            result = _command_collect(arguments.endpoint_id)
        elif arguments.command == "collect-manifest":
            result = _command_collect_manifest(arguments.path)
        elif arguments.command == "health":
            result = _command_health(arguments.endpoint_id, arguments.as_of)
        else:
            _emit({"error_code": "COMMAND_NOT_SUPPORTED"})
            return 2
    except Exception:
        _emit({"error_code": "COMMAND_FAILED"})
        return 1

    _emit(result)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeepAha Phase 2 source operations")
    commands = parser.add_subparsers(dest="command", required=True)

    import_parser = commands.add_parser("import-registry")
    import_parser.add_argument("--path", type=Path, required=True)

    collect_parser = commands.add_parser("collect")
    collect_parser.add_argument("--endpoint-id", type=UUID, required=True)

    collect_manifest_parser = commands.add_parser("collect-manifest")
    collect_manifest_parser.add_argument("--path", type=Path, required=True)

    health_parser = commands.add_parser("health")
    health_parser.add_argument("--endpoint-id", type=UUID, required=True)
    health_parser.add_argument("--as-of")
    return parser


def _command_import_registry(path: Path) -> dict[str, object]:
    settings = Settings()
    factory = session_factory(get_engine(settings))
    manifest = load_registry_manifest(path)
    with factory.begin() as session:
        result = import_registry(session, manifest)
    return {
        "schema_version": manifest.schema_version,
        "created_sources": result.created_sources,
        "created_endpoints": result.created_endpoints,
    }


def _command_collect(endpoint_id: UUID) -> dict[str, object]:
    result = _build_collection_runner().collect(endpoint_id)
    return {"endpoint_id": str(endpoint_id), **_collection_result(result)}


def _command_collect_manifest(path: Path) -> dict[str, object]:
    settings = Settings()
    factory = session_factory(get_engine(settings))
    manifest = load_registry_manifest(path)
    with factory.begin() as session:
        imported = import_registry(session, manifest)

    runner = _build_collection_runner(settings=settings)
    results = []
    for entry in manifest.sources:
        for endpoint in entry.endpoints:
            if endpoint.active:
                results.append(
                    {
                        "endpoint_id": str(endpoint.endpoint_id),
                        **_collection_result(runner.collect(endpoint.endpoint_id)),
                    }
                )
    return {
        "schema_version": manifest.schema_version,
        "created_sources": imported.created_sources,
        "created_endpoints": imported.created_endpoints,
        "results": results,
    }


def _command_health(endpoint_id: UUID, as_of: str | None) -> dict[str, object]:
    settings = Settings()
    factory = session_factory(get_engine(settings))
    resolved_as_of = _parse_as_of(as_of) if as_of is not None else datetime.now(UTC)
    with factory() as session:
        summary = get_source_health(session, endpoint_id, resolved_as_of)
    return {
        "endpoint_id": str(summary.endpoint_id),
        "source_id": str(summary.source_id),
        "as_of": summary.as_of,
        "last_attempt_at": summary.last_attempt_at,
        "last_success_at": summary.last_success_at,
        "consecutive_failures": summary.consecutive_failures,
        "attempts_24h": summary.attempts_24h,
        "successes_24h": summary.successes_24h,
        "not_modified_24h": summary.not_modified_24h,
        "failures_24h": summary.failures_24h,
        "latest_artifact_id": str(summary.latest_artifact_id)
        if summary.latest_artifact_id is not None
        else None,
        "latest_content_sha256": summary.latest_content_sha256,
        "latest_object_key": summary.latest_object_key,
        "parse_successes": summary.parse_successes,
        "parse_needs_review": summary.parse_needs_review,
        "parse_failures": summary.parse_failures,
    }


def _build_collection_runner(*, settings: Settings | None = None) -> CollectionRunner:
    resolved = settings or Settings()
    store = S3ObjectStore(resolved)
    store.ensure_bucket()
    return CollectionRunner(
        session_factory=session_factory(get_engine(resolved)),
        object_store=store,
        transport=HttpxTransport(),
        resolver=SocketHostResolver(),
        clock=SystemClock(),
        sleeper=SystemSleeper(),
    )


def _collection_result(result: CollectionRunResult) -> dict[str, object]:
    return {
        "collection_run_id": str(result.collection_run_id),
        "attempts": [
            {
                "attempt_number": attempt.attempt_number,
                "outcome": attempt.outcome,
                "http_status": attempt.http_status,
                "artifact_id": str(attempt.artifact_id)
                if attempt.artifact_id is not None
                else None,
                "error_code": attempt.error_code,
                "started_at": attempt.started_at,
                "completed_at": attempt.completed_at,
            }
            for attempt in result.attempts
        ],
        "final_error_code": result.final_error_code,
    }


def _parse_as_of(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--as-of must include timezone information")
    return parsed.astimezone(UTC)


def _json_ready(value: object) -> object:
    if isinstance(value, (UUID, datetime)):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _emit(value: dict[str, object]) -> None:
    print(json.dumps(_json_ready(value), ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    raise SystemExit(main())
