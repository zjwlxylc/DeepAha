from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class Operation:
    id: str
    action: str
    status: str
    environment: str | None
    target: str | None
    idempotency_key: str | None
    requested_by: str
    request_id: str
    params: dict[str, Any]
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    exit_code: int | None = None
    output: str | None = None

    def public(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("idempotency_key", None)
        return value


class OperationStore:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._lock = Lock()
        self._initialize()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS operations (
                  id TEXT PRIMARY KEY,
                  action TEXT NOT NULL,
                  status TEXT NOT NULL,
                  environment TEXT,
                  target TEXT,
                  idempotency_key TEXT,
                  requested_by TEXT NOT NULL,
                  request_id TEXT NOT NULL,
                  params_json TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  started_at TEXT,
                  finished_at TEXT,
                  exit_code INTEGER,
                  output TEXT
                )
                """
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_operations_idempotency "
                "ON operations(idempotency_key) WHERE idempotency_key IS NOT NULL"
            )
            connection.commit()
        self.abort_incomplete()

    def abort_incomplete(self) -> None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                "UPDATE operations SET status='UNKNOWN', finished_at=?, "
                "output=COALESCE(output, 'gateway restarted; "
                "reconcile host state before any retry') "
                "WHERE status IN ('QUEUED','RUNNING')",
                (now,),
            )
            connection.commit()

    def create(
        self,
        *,
        action: str,
        environment: str | None,
        target: str | None,
        idempotency_key: str | None,
        requested_by: str,
        request_id: str,
        params: dict[str, Any],
    ) -> tuple[Operation, bool]:
        with self._lock:
            if idempotency_key:
                existing = self.by_idempotency(idempotency_key)
                if existing is not None:
                    return existing, False
            operation = Operation(
                id=uuid4().hex,
                action=action,
                status="QUEUED",
                environment=environment,
                target=target,
                idempotency_key=idempotency_key,
                requested_by=requested_by,
                request_id=request_id,
                params=params,
                created_at=datetime.now(UTC).isoformat(),
            )
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO operations ("
                    "id, action, status, environment, target, idempotency_key, "
                    "requested_by, request_id, params_json, created_at, started_at, "
                    "finished_at, exit_code, output"
                    ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        operation.id,
                        operation.action,
                        operation.status,
                        operation.environment,
                        operation.target,
                        operation.idempotency_key,
                        operation.requested_by,
                        operation.request_id,
                        json.dumps(operation.params, separators=(",", ":")),
                        operation.created_at,
                        operation.started_at,
                        operation.finished_at,
                        operation.exit_code,
                        operation.output,
                    ),
                )
                connection.commit()
            return operation, True

    def by_idempotency(self, key: str) -> Operation | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM operations WHERE idempotency_key=?",
                (key,),
            ).fetchone()
        return self._row(row) if row else None

    def get(self, operation_id: str) -> Operation | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM operations WHERE id=?",
                (operation_id,),
            ).fetchone()
        return self._row(row) if row else None

    def list_recent(self, limit: int = 20, environment: str | None = None) -> list[Operation]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM operations WHERE environment=? ORDER BY created_at DESC LIMIT ?",
                (environment, limit),
            ).fetchall()
        return [self._row(row) for row in rows]

    def mark_running(self, operation_id: str) -> None:
        self._update(
            operation_id,
            status="RUNNING",
            started_at=datetime.now(UTC).isoformat(),
        )

    def finish(self, operation_id: str, *, exit_code: int, output: str) -> None:
        self._update(
            operation_id,
            status="SUCCEEDED" if exit_code == 0 else "FAILED",
            finished_at=datetime.now(UTC).isoformat(),
            exit_code=exit_code,
            output=output,
        )

    def _update(self, operation_id: str, **fields: Any) -> None:
        if not fields:
            return
        clauses = ", ".join(f"{name}=?" for name in fields)
        values = [*fields.values(), operation_id]
        with self._connect() as connection:
            connection.execute(
                f"UPDATE operations SET {clauses} WHERE id=?",
                values,
            )
            connection.commit()

    @staticmethod
    def _row(row: sqlite3.Row) -> Operation:
        return Operation(
            id=row["id"],
            action=row["action"],
            status=row["status"],
            environment=row["environment"],
            target=row["target"],
            idempotency_key=row["idempotency_key"],
            requested_by=row["requested_by"],
            request_id=row["request_id"],
            params=json.loads(row["params_json"]),
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            exit_code=row["exit_code"],
            output=row["output"],
        )
