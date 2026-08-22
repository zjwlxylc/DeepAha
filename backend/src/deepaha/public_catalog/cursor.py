import base64
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from deepaha.public_catalog.schemas import PublicOpportunitySort


class InvalidCursor(ValueError):
    """The cursor is malformed or does not belong to the selected sort."""


class _CursorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    v: Literal[1]
    sort: PublicOpportunitySort
    key: str = Field(min_length=1, max_length=64)
    public_id: str = Field(pattern=r"^opp_[0-9a-f]{32}$")


@dataclass(frozen=True)
class CursorPosition:
    sort: PublicOpportunitySort
    key: date | datetime
    public_id: str


def _serialize_key(sort: PublicOpportunitySort, key: date | datetime) -> str:
    if sort is PublicOpportunitySort.PUBLISHED_DESC:
        if not isinstance(key, datetime) or key.tzinfo is None:
            raise ValueError("published cursor key must be an aware datetime")
        return key.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(key, datetime) or not isinstance(key, date):
        raise ValueError("deadline cursor key must be a date")
    return key.isoformat()


def encode_cursor(
    sort: PublicOpportunitySort,
    key: date | datetime,
    public_id: str,
) -> str:
    payload = _CursorPayload(v=1, sort=sort, key=_serialize_key(sort, key), public_id=public_id)
    canonical = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(canonical).decode("ascii").rstrip("=")


def decode_cursor(value: str, expected_sort: PublicOpportunitySort) -> CursorPosition:
    try:
        padding = "=" * (-len(value) % 4)
        decoded = base64.b64decode(value + padding, altchars=b"-_", validate=True)
        payload = _CursorPayload.model_validate_json(decoded)
        if payload.sort is not expected_sort:
            raise InvalidCursor("cursor sort does not match selected sort")
        if payload.sort is PublicOpportunitySort.PUBLISHED_DESC:
            key: date | datetime = datetime.fromisoformat(payload.key.replace("Z", "+00:00"))
            if not isinstance(key, datetime) or key.tzinfo is None:
                raise ValueError("published cursor key must include timezone")
            key = key.astimezone(UTC)
        else:
            if "T" in payload.key:
                raise ValueError("deadline cursor key must be a date")
            key = date.fromisoformat(payload.key)
    except InvalidCursor:
        raise
    except (ValueError, UnicodeDecodeError, ValidationError) as error:
        raise InvalidCursor("invalid public opportunity cursor") from error
    return CursorPosition(sort=payload.sort, key=key, public_id=payload.public_id)
