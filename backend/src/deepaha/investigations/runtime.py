"""Local investigation process. Startup never starts a remote investigation."""

import asyncio
import json
import os
from contextlib import suppress
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID, uuid7

from sqlalchemy import Engine, text

import deepaha.db.models  # noqa: F401
from deepaha.artifacts.local_file import LocalFileObjectStore
from deepaha.core.settings import Settings
from deepaha.db.session import get_engine, session_factory
from deepaha.investigations.dispatch import DISPATCH_INTERVAL_SECONDS, dispatch_candidate
from deepaha.investigations.local_config import LocalWmaConfigStore
from deepaha.investigations.store import InvestigationStore
from deepaha.investigations.wma import DirectWmaClient
from deepaha.local_human_test.provider_config import (
    WindowsDirectoryHardener,
    WindowsDpapiProtector,
)

CODEBASE_ID = sha256(str(Path(__file__).resolve().parents[3]).casefold().encode()).hexdigest()


def heartbeat(root: Path, database_url: str, now: datetime) -> None:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "investigation-worker.json"
    temporary = root / f"worker-{uuid7()}.tmp"
    temporary.write_text(
        json.dumps(
            {
                "database": sha256(database_url.encode()).hexdigest(),
                "codebase": CODEBASE_ID,
                "updated_at": now.isoformat(),
                "version": "direct-wma-runtime/1",
            }
        ),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def worker_status(root: Path, database_url: str, now: datetime) -> dict[str, Any]:
    try:
        row = json.loads((root / "investigation-worker.json").read_text(encoding="utf-8"))
        age = (now - datetime.fromisoformat(row["updated_at"])).total_seconds()
        if (
            row["database"] == sha256(database_url.encode()).hexdigest()
            and row.get("codebase") == CODEBASE_ID
            and 0 <= age <= 30
        ):
            return {"state": "RUNNING", "updated_at": row["updated_at"]}
    except OSError, ValueError, KeyError, TypeError:
        pass
    return {"state": "OFFLINE", "updated_at": None}


async def serve(settings: Settings) -> None:
    if (
        settings.environment != "development"
        or not settings.local_human_test_enabled
        or settings.local_human_test_root is None
        or settings.database_url is None
        or settings.local_human_test_bind_host not in ("127.0.0.1", "localhost", "::1")
    ):
        raise RuntimeError("LOCAL_INVESTIGATION_RUNTIME_NOT_ENABLED")
    engine = get_engine(settings)
    try:
        # Two independent coroutines: dispatch may await for minutes without ever
        # delaying a heartbeat.
        await asyncio.gather(
            _heartbeat_loop(settings, engine),
            _dispatch_loop(settings, engine),
        )
    finally:
        engine.dispose()


async def _heartbeat_loop(settings: Settings, engine: Engine) -> None:
    root = settings.local_human_test_root
    database_url = settings.database_url
    assert root is not None and database_url is not None
    while True:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            heartbeat(root, database_url, datetime.now(UTC))
        except Exception:
            # Failed DB checks do not refresh liveness, or leak dependency messages.
            print("INVESTIGATION_RUNTIME_HEALTH_FAILED", flush=True)
        await asyncio.sleep(5)


async def _dispatch_loop(settings: Settings, engine: Engine) -> None:
    root = settings.local_human_test_root
    assert root is not None
    store = InvestigationStore(
        session_factory(engine),
        LocalFileObjectStore(
            root=root / "investigation-objects",
            bucket="deepaha-investigations",
        ),
    )
    config = LocalWmaConfigStore(root, WindowsDpapiProtector(), WindowsDirectoryHardener())
    attempted: set[tuple[UUID, str]] = set()
    while True:
        try:
            candidates = [
                candidate
                for candidate in store.list_dispatchable(store.clock())
                if isinstance(candidate.get("dispatch_intent"), dict)
                and candidate["dispatch_intent"].get("configuration_revision")
            ]

            def key(candidate: dict[str, Any]) -> tuple[UUID, str]:
                return candidate["task_id"], str(candidate["dispatch_intent"].get("intent_id"))

            attempted &= {key(candidate) for candidate in candidates}
            pending = [candidate for candidate in candidates if key(candidate) not in attempted]
            if pending:
                candidate = pending[0]
                attempted.add(key(candidate))
                await dispatch_candidate(store, config, DirectWmaClient, candidate)
        except Exception:
            print("INVESTIGATION_DISPATCH_CYCLE_FAILED", flush=True)
        await asyncio.sleep(DISPATCH_INTERVAL_SECONDS)


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        asyncio.run(serve(Settings()))
