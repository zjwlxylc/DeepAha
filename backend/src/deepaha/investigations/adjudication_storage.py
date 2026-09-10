"""Exact review serialization, independent of PostgreSQL JSONB numeric rendering.

This codec checks integrity and the existing domain contract, not provenance or
authentication. Only the trusted adapter may write it. JSONB is a derived index,
never the input from which frozen text or its existing hashes are reconstructed.
"""

import json
from hashlib import sha256
from typing import Any, Literal, Self

from pydantic import model_validator

from deepaha.contracts.common import Sha256
from deepaha.investigations.cross_level_adjudication import AdjudicationPackage
from deepaha.investigations.group_contracts import GroupContract


def _encode(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate frozen JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite frozen JSON number: {value}")


def _decode(payload: str) -> dict[str, Any]:
    value = json.loads(payload, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    if not isinstance(value, dict) or _encode(value) != payload:
        raise ValueError("frozen JSON must use the existing deterministic Python representation")
    AdjudicationPackage.model_validate(value)
    return value


class StoredAdjudication(GroupContract):
    storage_version: Literal["adjudication-frozen-json/1.0.0"]
    payload_text: str
    payload_sha256: Sha256

    @model_validator(mode="after")
    def require_exact_bytes(self) -> Self:
        if sha256(self.payload_text.encode("utf-8")).hexdigest() != self.payload_sha256:
            raise ValueError("frozen review byte digest differs")
        _decode(self.payload_text)
        return self


def freeze_adjudication(value: dict[str, Any]) -> StoredAdjudication:
    # Validate without model_dump: normalizing legacy timestamp spelling would
    # alter the externally retained whole-package digest even if times are equal.
    AdjudicationPackage.model_validate(value)
    payload = _encode(value)
    if json.loads(payload) != value:
        raise ValueError("review payload must contain JSON objects, arrays and scalar values only")
    return StoredAdjudication(
        storage_version="adjudication-frozen-json/1.0.0",
        payload_text=payload,
        payload_sha256=sha256(payload.encode("utf-8")).hexdigest(),
    )


def thaw_adjudication(stored: dict[str, Any], *, expected_payload_sha256: str) -> dict[str, Any]:
    """Use a separately trusted receipt digest; the envelope is not its own trust root."""
    value = StoredAdjudication.model_validate(stored)
    if value.payload_sha256 != expected_payload_sha256:
        raise ValueError("frozen review differs from trusted payload digest")
    return _decode(value.payload_text)
