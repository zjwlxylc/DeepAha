import ipaddress
import json
from hashlib import sha256
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from deepaha.contracts.phase2 import OpportunityTypeV02

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


class InvestigationPositionBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    entity_id: str = Field(min_length=1, max_length=256)
    opportunity_unit_id: UUID
    opportunity_unit_version_id: UUID


class BindInvestigation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    delivery_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    opportunity_id: UUID
    opportunity_version: int = Field(ge=1)
    positions: tuple[InvestigationPositionBinding, ...] = Field(default=(), max_length=2000)
    previous_binding_id: UUID | None = None
    reason: str = Field(min_length=1, max_length=2000)


class RegisterInvestigationPosition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    entity_id: str = Field(min_length=1, max_length=256)
    unit_key: str = Field(min_length=1, max_length=256)
    label: str = Field(min_length=1, max_length=500)


class RegisterInvestigationIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    delivery_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_title: str = Field(min_length=1, max_length=500)
    type: OpportunityTypeV02
    issuer_name: str = Field(min_length=1, max_length=500)
    positions: tuple[RegisterInvestigationPosition, ...] = Field(default=(), max_length=2000)
    reason: str = Field(min_length=1, max_length=2000)


class RegisterInvestigationPositions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    delivery_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    previous_binding_id: UUID
    positions: tuple[RegisterInvestigationPosition, ...] = Field(min_length=1, max_length=2000)
    reason: str = Field(min_length=1, max_length=2000)


class PrepareInvestigationFacts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    delivery_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    binding_id: UUID
    check_id: UUID


class DecideInvestigationFact(PrepareInvestigationFacts):
    preparation_id: UUID
    candidate_id: UUID
    decision: Literal["APPROVE", "REJECT", "UNKNOWN", "NEEDS_ADJUDICATION"]
    evidence_support: Literal["SUPPORTED", "UNSUPPORTED", "UNKNOWN"]
    precedence_check: Literal["PASSED", "FAILED", "UNKNOWN"]
    reason: str = Field(min_length=1, max_length=2000)


class PromoteInvestigationFacts(PrepareInvestigationFacts):
    preparation_id: UUID
    entity_id: str = Field(min_length=1, max_length=256)
    supersedes_id: UUID | None = None
    reason: str = Field(min_length=1, max_length=2000)


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
