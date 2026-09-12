"""Local WMA credentials, separate from model-provider configuration.

Each save creates an immutable encrypted revision. Connection checks belong to
that revision, so a late check can never validate replacement credentials.
"""

import asyncio
import base64
import importlib.util
import json
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid7

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from deepaha.investigations.contracts import InvestigationError
from deepaha.investigations.wma import DirectWmaClient, DirectWmaError, WmaBinding
from deepaha.local_human_test.provider_config import DirectoryHardener, SecretProtector


class SaveWmaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    api_key: SecretStr
    agent_id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
    source_app: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")

    @field_validator("api_key")
    @classmethod
    def valid_key(cls, value: SecretStr) -> SecretStr:
        key = value.get_secret_value()
        if not 1 <= len(key) <= 4096 or any(c.isspace() or not c.isprintable() for c in key):
            raise ValueError("invalid key")
        return value


class LocalWmaConfigStore:
    def __init__(self, root: Path, protector: SecretProtector, hardener: DirectoryHardener) -> None:
        self.root = root / "wma"
        self.protector, self.hardener = protector, hardener

    def _write(self, path: Path, payload: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.hardener.harden(self.root)
        temporary = self.root / f"{uuid7()}.tmp"
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except Exception:
            raise InvestigationError("WMA_CONFIG_WRITE_FAILED") from None

    def _read(self, revision: str | None = None) -> dict[str, Any]:
        try:
            if revision is None:
                current = json.loads((self.root / "current.json").read_text(encoding="utf-8"))
                revision = current["revision"]
            revision = str(UUID(revision))
            row = json.loads((self.root / f"{revision}.json").read_text(encoding="utf-8"))
            if not isinstance(row, dict) or row.get("revision") != revision:
                raise ValueError("invalid revision")
            return row
        except Exception:
            raise InvestigationError("WMA_CONFIG_UNREADABLE") from None

    def save(self, command: SaveWmaConfig, operator_id: UUID) -> dict[str, Any]:
        revision = str(uuid7())
        try:
            encrypted = self.protector.protect(command.api_key.get_secret_value().encode())
            self._write(
                self.root / f"{revision}.json",
                {
                    "revision": revision,
                    "agent_id": command.agent_id,
                    "source_app": command.source_app,
                    "protected_api_key": base64.b64encode(encrypted).decode(),
                    "saved_by": str(operator_id),
                    "saved_at": datetime.now(UTC).isoformat(),
                },
            )
            self._write(self.root / "current.json", {"revision": revision})
        except Exception:
            raise InvestigationError("WMA_CONFIG_WRITE_FAILED") from None
        return self.status()

    def load(self, revision: str | None = None) -> tuple[str, WmaBinding]:
        row = self._read(revision)
        try:
            secret = self.protector.unprotect(
                base64.b64decode(row["protected_api_key"], validate=True)
            )
            binding = WmaBinding(
                SecretStr(secret.decode()), row["agent_id"], row["source_app"], "1.0"
            )
        except Exception:
            raise InvestigationError("WMA_CONFIG_DECRYPT_FAILED") from None
        return row["revision"], binding

    def record_check(
        self, revision: str, release: dict[str, object] | None, error: str | None
    ) -> None:
        revision = str(UUID(revision))
        self._write(
            self.root / f"{revision}.check.json",
            {
                "checked_at": datetime.now(UTC).isoformat(),
                "release": release,
                "error_code": error,
            },
        )

    def status(self) -> dict[str, Any]:
        if not (self.root / "current.json").exists():
            return {
                "state": "NOT_CONFIGURED",
                "sdk_available": importlib.util.find_spec("cloud_agent_sdk") is not None,
            }
        row = self._read()
        result = {
            key: row[key] for key in ("revision", "agent_id", "source_app", "saved_at", "saved_by")
        }
        result.update(
            state="SAVED", sdk_available=importlib.util.find_spec("cloud_agent_sdk") is not None
        )
        check_path = self.root / f"{row['revision']}.check.json"
        if check_path.exists():
            try:
                check = json.loads(check_path.read_text(encoding="utf-8"))
                stale = datetime.fromisoformat(check["checked_at"]) < datetime.now(UTC) - timedelta(
                    minutes=15
                )
                result.update(check)
                result["state"] = (
                    "CHECK_EXPIRED"
                    if stale
                    else "CHECK_FAILED"
                    if check["error_code"]
                    else "CONNECTION_VERIFIED"
                )
            except Exception:
                result["state"] = "CHECK_FAILED"
                result["error_code"] = "WMA_CHECK_UNREADABLE"
        return result


class ReleaseClient(Protocol):
    async def inspect_release(self) -> dict[str, object]: ...
    async def aclose(self) -> None: ...


async def inspect_configuration(
    store: LocalWmaConfigStore,
    client_factory: Callable[[WmaBinding], ReleaseClient] = DirectWmaClient,
) -> dict[str, Any]:
    revision, binding = store.load()
    client = None
    release, code = None, None
    try:
        client = client_factory(binding)
        async with asyncio.timeout(60):
            release = await client.inspect_release()
    except DirectWmaError as error:
        code = error.code
    except Exception:
        code = "WMA_CONNECTION_CHECK_FAILED"
    finally:
        if client is not None:
            try:
                async with asyncio.timeout(5):
                    await client.aclose()
            except Exception:
                pass
    store.record_check(revision, release, code)
    return store.status()
