import ipaddress
import json
from hashlib import sha256
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024
MAX_FILES = 50
RESULT_NAMES = ("opportunities.json", "evidence.json", "report.md")


class InvestigationError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class CreateInvestigation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_id: UUID
    endpoint_id: UUID
    notice_url: str = Field(min_length=1, max_length=2048)
    brief: str = Field(min_length=1, max_length=12000)
    expected_artifact_urls: tuple[str, ...] = Field(default=(), max_length=50)
    expected_entity_keys: tuple[str, ...] = Field(default=(), max_length=2000)
    calibration: bool = False
    wall_time_seconds: int = Field(default=600, ge=60, le=1800)


class ReviewInvestigation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    decision: Literal["APPROVE", "REJECT"]
    delivery_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=2000)


class PrepareInvestigationDocuments(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    delivery_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


def digest(value: object) -> str:
    return sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def allowed_url(value: str, hosts: list[str]) -> bool:
    try:
        url = urlsplit(value)
        host = url.hostname or ""
        if (
            value != value.strip()
            or any(ord(c) < 33 for c in value)
            or "\\" in value
            or url.scheme != "https"
            or url.username
            or url.password
            or url.fragment
            or url.port not in (None, 443)
            or host not in hosts
            or host in {"localhost", "localhost.localdomain"}
            or host.endswith((".localhost", ".local", ".internal"))
        ):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return bool(host and "." in host)
    except ValueError:
        return False
