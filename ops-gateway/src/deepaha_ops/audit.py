from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

_AUTH_BEARER_PATTERN = re.compile(r"(?i)(authorization\s*[:=]\s*bearer)\s+[^\s,;]+")
_SECRET_PATTERN = re.compile(r"(?i)(api[_-]?key|password|secret|token)\s*[:=]\s*([^\s,;]+)")


def redact_text(value: str) -> str:
    value = _AUTH_BEARER_PATTERN.sub(
        lambda match: f"{match.group(1)} [REDACTED]",
        value,
    )
    return _SECRET_PATTERN.sub(
        lambda match: f"{match.group(1)}=[REDACTED]",
        value,
    )


@dataclass(frozen=True, slots=True)
class AuditEvent:
    timestamp: str
    event: str
    request_id: str
    principal: str
    details: dict[str, Any]


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()
        self._previous_hash = "0" * 64
        self._load_tail_hash()

    def _load_tail_hash(self) -> None:
        if not self.path.exists():
            if self._previous_hash != "0" * 64:
                raise ValueError("AUDIT_CHAIN_REMOVED")
            return
        previous = "0" * 64
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                digest = record.pop("hash")
                if record.pop("previous_hash") != previous:
                    raise ValueError("AUDIT_CHAIN_CORRUPTED")
                canonical = json.dumps(
                    record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                )
                if hashlib.sha256((previous + canonical).encode()).hexdigest() != digest:
                    raise ValueError("AUDIT_CHAIN_CORRUPTED")
                previous = digest
        if previous == "0" * 64 and self._previous_hash != previous:
            raise ValueError("AUDIT_CHAIN_TRUNCATED")
        self._previous_hash = previous

    def append(self, event: AuditEvent) -> str:
        with self._lock:
            self._load_tail_hash()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = asdict(event)
            payload["details"] = self._redact(payload["details"])
            canonical = json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            digest = hashlib.sha256((self._previous_hash + canonical).encode("utf-8")).hexdigest()
            record = {
                **payload,
                "previous_hash": self._previous_hash,
                "hash": digest,
            }
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        record,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
                handle.flush()
                os.fsync(handle.fileno())
            self._previous_hash = digest
            return digest

    def _redact(self, value: Any) -> Any:
        if isinstance(value, str):
            return redact_text(value)
        if isinstance(value, dict):
            return {
                key: (
                    "[REDACTED]"
                    if key.lower() in {"token", "authorization", "password", "secret"}
                    else self._redact(item)
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        return value


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
