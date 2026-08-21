import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from deepaha.contracts.phase1 import ContractModel, SourceSchema
from deepaha.contracts.phase2 import SourceEndpointSchema
from deepaha.sources.models import Source, SourceEndpoint


class SourcePolicyConflict(RuntimeError):
    """Raised when a stable registry identity is reused with changed meaning."""


class SourceRegistryEntry(ContractModel):
    source: SourceSchema
    endpoints: tuple[SourceEndpointSchema, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_owned_endpoints(self) -> Self:
        if any(endpoint.source_id != self.source.source_id for endpoint in self.endpoints):
            raise ValueError("endpoint source_id must match owning source")
        return self


class SourceRegistryManifest(ContractModel):
    schema_version: Literal["0.2.0"]
    sources: tuple[SourceRegistryEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def reject_duplicate_identities(self) -> Self:
        source_ids: set[UUID] = set()
        public_ids: set[str] = set()
        canonical_urls: set[str] = set()
        endpoint_ids: set[UUID] = set()
        endpoint_keys: set[tuple[UUID, str, str]] = set()
        for entry in self.sources:
            source = entry.source
            _add_unique(source_ids, source.source_id, "source_id")
            _add_unique(public_ids, source.public_id, "public_id")
            _add_unique(canonical_urls, str(source.canonical_url), "canonical_url")
            for endpoint in entry.endpoints:
                _add_unique(endpoint_ids, endpoint.endpoint_id, "endpoint_id")
                key = (endpoint.source_id, str(endpoint.url), endpoint.policy_version)
                _add_unique(endpoint_keys, key, "endpoint policy key")
        return self


@dataclass(frozen=True, slots=True)
class RegistryImportResult:
    created_sources: int
    created_endpoints: int


def _add_unique[T](seen: set[T], value: T, label: str) -> None:
    if value in seen:
        raise ValueError(f"duplicate {label}")
    seen.add(value)


def load_registry_manifest(path: Path) -> SourceRegistryManifest:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("registry manifest must not contain a UTF-8 BOM")
    payload: object = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("registry manifest must contain a JSON object")
    return SourceRegistryManifest.model_validate(payload)


def import_registry(session: Session, manifest: SourceRegistryManifest) -> RegistryImportResult:
    created_sources = 0
    created_endpoints = 0
    for entry in manifest.sources:
        source = _find_source(session, entry.source)
        if source is None:
            source = _new_source(entry.source)
            session.add(source)
            session.flush()
            created_sources += 1
        else:
            _require_source_replay(source, entry.source)

        for endpoint_schema in entry.endpoints:
            endpoint = _find_endpoint(session, endpoint_schema)
            if endpoint is None:
                session.add(_new_endpoint(endpoint_schema))
                session.flush()
                created_endpoints += 1
            else:
                _require_endpoint_replay(endpoint, endpoint_schema)

    return RegistryImportResult(
        created_sources=created_sources,
        created_endpoints=created_endpoints,
    )


def _find_source(session: Session, schema: SourceSchema) -> Source | None:
    matches = session.scalars(
        select(Source).where(
            (Source.source_id == schema.source_id)
            | (Source.public_id == schema.public_id)
            | (Source.canonical_url == str(schema.canonical_url))
        )
    ).all()
    if not matches:
        return None
    if len(matches) != 1 or matches[0].source_id != schema.source_id:
        _conflict("source identity collision")
    return matches[0]


def _find_endpoint(session: Session, schema: SourceEndpointSchema) -> SourceEndpoint | None:
    matches = session.scalars(
        select(SourceEndpoint).where(
            (SourceEndpoint.endpoint_id == schema.endpoint_id)
            | (
                (SourceEndpoint.source_id == schema.source_id)
                & (SourceEndpoint.url == str(schema.url))
                & (SourceEndpoint.policy_version == schema.policy_version)
            )
        )
    ).all()
    if not matches:
        return None
    if len(matches) != 1 or matches[0].endpoint_id != schema.endpoint_id:
        _conflict("endpoint identity collision")
    return matches[0]


def _new_source(schema: SourceSchema) -> Source:
    return Source(
        source_id=schema.source_id,
        public_id=schema.public_id,
        canonical_url=str(schema.canonical_url),
        authority_name=schema.authority_name,
        tier=schema.tier.value,
        jurisdiction=schema.jurisdiction,
        active=schema.active,
        created_at=schema.created_at,
        updated_at=schema.updated_at,
    )


def _new_endpoint(schema: SourceEndpointSchema) -> SourceEndpoint:
    return SourceEndpoint(
        endpoint_id=schema.endpoint_id,
        source_id=schema.source_id,
        url=str(schema.url),
        allowed_hosts=list(schema.allowed_hosts),
        expected_media_types=list(schema.expected_media_types),
        browser_policy=schema.browser_policy.value,
        minimum_interval_seconds=schema.minimum_interval_seconds,
        timeout_seconds=schema.timeout_seconds,
        max_attempts=schema.max_attempts,
        robots_url=str(schema.robots_url) if schema.robots_url is not None else None,
        robots_decision=schema.robots_decision.value,
        robots_checked_at=schema.robots_checked_at,
        content_use_basis=schema.content_use_basis.value,
        license_name=schema.license_name,
        license_url=str(schema.license_url) if schema.license_url is not None else None,
        attribution=schema.attribution,
        fixture_storage_allowed=schema.fixture_storage_allowed,
        usage_note=schema.usage_note,
        policy_version=schema.policy_version,
        active=schema.active,
        verified_at=schema.verified_at,
        created_at=schema.created_at,
        updated_at=schema.updated_at,
    )


def _require_source_replay(row: Source, schema: SourceSchema) -> None:
    expected = {
        "source_id": schema.source_id,
        "public_id": schema.public_id,
        "canonical_url": str(schema.canonical_url),
        "authority_name": schema.authority_name,
        "tier": schema.tier.value,
        "jurisdiction": schema.jurisdiction,
        "active": schema.active,
        "created_at": schema.created_at,
        "updated_at": schema.updated_at,
    }
    _require_replay(row, expected, "source")


def _require_endpoint_replay(row: SourceEndpoint, schema: SourceEndpointSchema) -> None:
    expected = {
        "endpoint_id": schema.endpoint_id,
        "source_id": schema.source_id,
        "url": str(schema.url),
        "allowed_hosts": list(schema.allowed_hosts),
        "expected_media_types": list(schema.expected_media_types),
        "browser_policy": schema.browser_policy.value,
        "minimum_interval_seconds": schema.minimum_interval_seconds,
        "timeout_seconds": schema.timeout_seconds,
        "max_attempts": schema.max_attempts,
        "robots_url": str(schema.robots_url) if schema.robots_url is not None else None,
        "robots_decision": schema.robots_decision.value,
        "robots_checked_at": schema.robots_checked_at,
        "content_use_basis": schema.content_use_basis.value,
        "license_name": schema.license_name,
        "license_url": str(schema.license_url) if schema.license_url is not None else None,
        "attribution": schema.attribution,
        "fixture_storage_allowed": schema.fixture_storage_allowed,
        "usage_note": schema.usage_note,
        "policy_version": schema.policy_version,
        "active": schema.active,
        "verified_at": schema.verified_at,
        "created_at": schema.created_at,
        "updated_at": schema.updated_at,
    }
    _require_replay(row, expected, "endpoint")


def _require_replay(row: object, expected: dict[str, object], label: str) -> None:
    for field, value in expected.items():
        if getattr(row, field) != value:
            _conflict(f"changed {label} field: {field}")


def _conflict(detail: str) -> None:
    raise SourcePolicyConflict(f"SOURCE_POLICY_CONFLICT: {detail}")


__all__ = [
    "RegistryImportResult",
    "SourcePolicyConflict",
    "SourceRegistryManifest",
    "import_registry",
    "load_registry_manifest",
]
