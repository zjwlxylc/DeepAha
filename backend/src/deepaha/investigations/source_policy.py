"""Explicit local intake approval is not promotion to primary evidence."""

import json
from pathlib import Path
from typing import Any

from deepaha.sources.models import Source, SourceEndpoint
from deepaha.sources.registry import load_registry_manifest

# A missing or corrupt local manifest is uncertainty, never a server error and
# never a leak: the source list and the readiness probe must stay usable (this
# also covers PRIMARY-only deployments where the aggregator allowlist is unused).
# Only file/shape errors are swallowed -- never bare ``Exception``.
_UNREADABLE_CONFIG = (OSError, ValueError, KeyError, json.JSONDecodeError)


def _samples_path() -> Path:
    return Path(__file__).resolve().parents[4] / "config/sources/direct-wma-samples.json"


def _local_registry_path() -> Path:
    return Path(__file__).resolve().parents[4] / "config/sources/direct-wma-local.json"


def sample_defaults(endpoint: SourceEndpoint) -> dict[str, Any]:
    """Return the configured sample row for ``endpoint``, or ``{}`` when unavailable."""
    try:
        samples = json.loads(_samples_path().read_text(encoding="utf-8"))
    except _UNREADABLE_CONFIG:
        return {}
    if not isinstance(samples, list):
        return {}
    return next(
        (
            row
            for row in samples
            if isinstance(row, dict) and row.get("endpoint_id") == str(endpoint.endpoint_id)
        ),
        {},
    )


def allowed_intake_source(
    source: Source, endpoint: SourceEndpoint, notice_url: str | None = None
) -> bool:
    if source.tier == "OFFICIAL_PRIMARY":
        return True
    if source.tier != "OFFICIAL_AGGREGATOR":
        return False
    try:
        manifest = load_registry_manifest(_local_registry_path())
    except _UNREADABLE_CONFIG:
        return False
    return any(
        entry.source.source_id == source.source_id
        and entry.source.tier.value == source.tier
        and approved.endpoint_id == endpoint.endpoint_id
        and approved.policy_version == endpoint.policy_version
        and str(approved.url) == endpoint.url
        and tuple(approved.allowed_hosts) == tuple(endpoint.allowed_hosts)
        and (notice_url is None or notice_url == endpoint.url)
        for entry in manifest.sources
        for approved in entry.endpoints
    )
