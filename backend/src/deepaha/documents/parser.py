import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from deepaha.contracts.phase2 import EvidenceLocatorV02

_STABLE_CODE_PATTERN = re.compile(r"[A-Z][A-Z0-9_]*")
LEGACY_PARSE_CONTRACT_VERSION = "phase2-locator-contract-v0.2.0"


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    title: str | None
    published_at: datetime | None
    language: str
    normalized_text: str
    locators: tuple[EvidenceLocatorV02, ...]
    needs_review_reasons: tuple[str, ...]


class DocumentParser(Protocol):
    name: str
    version: str
    parse_contract_version: str

    def supports(self, media_type: str) -> bool: ...

    def parse(self, content: bytes, *, artifact_sha256: str) -> ParsedDocument: ...


class ExpectedParseError(RuntimeError):
    def __init__(self, code: str) -> None:
        if _STABLE_CODE_PATTERN.fullmatch(code) is None:
            raise ValueError("parse error must use a stable uppercase code")
        self.code = code
        super().__init__(code)


def validate_review_reason(code: str) -> None:
    if _STABLE_CODE_PATTERN.fullmatch(code) is None:
        raise ValueError("review reason must use a stable uppercase code")
