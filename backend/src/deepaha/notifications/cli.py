import argparse
import json
from dataclasses import asdict

from deepaha.core.settings import Settings
from deepaha.db.session import get_engine, session_factory
from deepaha.notifications.worker import (
    ReminderWorker,
    ReminderWorkerRunSummary,
    validate_worker_limit,
)


def _bounded_limit(value: str) -> int:
    try:
        return validate_worker_limit(int(value))
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeepAha Phase 8 reminder worker")
    commands = parser.add_subparsers(dest="command", required=True)
    run_once = commands.add_parser("run-once")
    run_once.add_argument("--limit", type=_bounded_limit, default=50)
    return parser


def _run_once(limit: int) -> ReminderWorkerRunSummary:
    settings = Settings()
    engine = get_engine(settings)
    try:
        worker = ReminderWorker(
            session_factory=session_factory(engine),
            batch_size=settings.notification_worker_batch_size,
            lease_seconds=settings.notification_lease_seconds,
        )
        return worker.run_once(limit=limit)
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = _build_parser().parse_args(argv)
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else 1
    if arguments.command != "run-once":
        return 2
    try:
        summary = _run_once(arguments.limit)
    except Exception:
        print(json.dumps({"error_code": "REMINDER_WORKER_FAILED"}, separators=(",", ":")))
        return 1
    print(json.dumps(asdict(summary), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
