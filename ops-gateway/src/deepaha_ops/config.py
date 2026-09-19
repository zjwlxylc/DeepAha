from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ALL_SCOPES = frozenset(
    {
        "read",
        "deploy",
        "backup",
        "rollback",
        "restart",
        "user_admin",
    }
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DEEPAHA_OPS_", extra="ignore")

    environment: str = "production"
    host: str = "127.0.0.1"
    port: int = 8765
    mutations_enabled: bool = False
    adapter_path: Path = Path("/usr/local/sbin/deepaha-ops-adapter")
    adapter_use_sudo: bool = True
    state_dir: Path = Path("/var/lib/deepaha-ops")
    audit_log: Path = Path("/var/log/deepaha-ops/audit.jsonl")
    command_timeout_seconds: int = Field(default=1800, ge=10, le=7200)
    max_output_bytes: int = Field(default=131_072, ge=4096, le=1_048_576)
    max_log_lines: int = Field(default=500, ge=20, le=2000)
    trusted_hosts: list[str] = Field(\n        default_factory=lambda: ["ops.deepaha.com", "localhost", "127.0.0.1"]\n    )
    token_hashes_json: str = "{}"

    @field_validator("trusted_hosts", mode="before")
    @classmethod
    def parse_hosts(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    def token_scopes(self) -> dict[str, frozenset[str]]:
        try:
            raw = json.loads(self.token_hashes_json)
        except json.JSONDecodeError as exc:
            raise ValueError("DEEPAHA_OPS_TOKEN_HASHES_JSON must be valid JSON") from exc
        if not isinstance(raw, dict):
            raise ValueError("DEEPAHA_OPS_TOKEN_HASHES_JSON must be a JSON object")
        parsed: dict[str, frozenset[str]] = {}
        for digest, scopes in raw.items():
            if (
                not isinstance(digest, str)
                or len(digest) != 64
                or any(char not in "0123456789abcdefABCDEF" for char in digest)
            ):
                raise ValueError("token hashes must be 64-character SHA-256 hex digests")
            if not isinstance(scopes, list) or not all(isinstance(scope, str) for scope in scopes):
                raise ValueError("token scope values must be arrays of strings")
            unknown = set(scopes) - ALL_SCOPES
            if unknown:
                raise ValueError(f"unknown scopes: {sorted(unknown)}")
            parsed[digest.lower()] = frozenset(scopes)
        return parsed


@lru_cache
def get_settings() -> Settings:
    return Settings()
