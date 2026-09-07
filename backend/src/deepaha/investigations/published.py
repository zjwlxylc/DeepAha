"""Strict interpretation of the SDK 0.3.4 published Agent control-plane shape.

Only digests and explicit metadata leave this module. Prompt contents and signed
skill URLs are never persisted, included in representations, or used in errors.
"""

from __future__ import annotations

import asyncio
import copy
import json
import re
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, NoReturn
from urllib.parse import unquote, urlsplit, urlunsplit


class PublishedBindingError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str = "WMA_UNSUPPORTED_MANIFEST") -> NoReturn:
    raise PublishedBindingError(code)


def _text(value: Any, *, limit: int = 1024) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        _fail()
    return value


def _numeric_id(value: Any) -> str:
    if isinstance(value, bool) or re.fullmatch(r"[1-9][0-9]{0,30}", str(value)) is None:
        _fail("WMA_AGENT_ID_KIND_INVALID")
    return str(value)


def _hash(value: Any) -> str:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except ValueError, TypeError:
        _fail()
    return sha256(encoded.encode()).hexdigest()


def _skill_url(value: Any) -> str:
    url = _text(value, limit=16384)
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or any(ord(char) < 32 or ord(char) == 127 for char in url)
    ):
        _fail()
    # Keep the path and every other raw query component byte-for-byte. Only the
    # known vendor CDN's temporary sign parameter is excluded from identity.
    if parsed.netloc == "openplatform-cdn.codebuddy.cn":
        components = parsed.query.split("&")
        components = [part for part in components if unquote(part.partition("=")[0]) != "sign"]
        return urlunsplit(parsed._replace(query="&".join(components)))
    return url


_MANIFEST_KEYS = {
    "id",
    "name",
    "description",
    "manifestVersion",
    "system_prompt",
    "skills",
    "useWorkspaceRoot",
    "settingsJson",
}


def _configuration(
    manifest: Any, public_id: str, model: str, *, session: bool = False
) -> tuple[dict[str, Any], str, list[dict[str, str]]]:
    if not isinstance(manifest, dict):
        _fail()
    allowed = _MANIFEST_KEYS | ({"envs", "secrets"} if session else set())
    if set(manifest) - allowed:
        _fail()
    if manifest.get("id") != public_id or manifest.get("manifestVersion") != "1.0":
        _fail("WMA_MANIFEST_IDENTITY_MISMATCH")
    config: dict[str, Any] = {
        "id": public_id,
        "name": _text(manifest.get("name")),
        "manifestVersion": "1.0",
    }
    for key in ("description", "useWorkspaceRoot"):
        if key in manifest:
            value = manifest[key]
            if key == "description" and not isinstance(value, str):
                _fail()
            if key == "useWorkspaceRoot" and not isinstance(value, bool):
                _fail()
            config[key] = value
    prompt = _text(manifest.get("system_prompt"), limit=1_000_000)
    if prompt == "***" and not session:
        _fail("WMA_PUBLISHED_PROMPT_UNAVAILABLE")
    settings = manifest.get("settingsJson")
    if settings is None and not session:
        settings = {"model": model}
    if not isinstance(settings, dict) or settings.get("model") != model:
        _fail("WMA_SESSION_MODEL_MISMATCH")
    config["settingsJson"] = copy.deepcopy(settings)
    skills = manifest.get("skills")
    if not isinstance(skills, list) or not 1 <= len(skills) <= 100:
        _fail("WMA_SKILLS_UNAVAILABLE")
    normalized: list[dict[str, str]] = []
    names: set[str] = set()
    for skill in skills:
        if not isinstance(skill, dict) or set(skill) != {"name", "downloadUrl", "scope"}:
            _fail()
        name = _text(skill["name"], limit=256)
        if name in names or skill["scope"] not in {"USER", "PROJECT"}:
            _fail()
        names.add(name)
        normalized.append(
            {
                "name": name,
                "scope": skill["scope"],
                "reference_sha256": sha256(_skill_url(skill["downloadUrl"]).encode()).hexdigest(),
            }
        )
    normalized.sort(key=lambda skill: (skill["name"], skill["scope"]))
    config["skills"] = normalized
    _hash(config)  # Reject values that cannot be represented as strict JSON.
    prompt_hash = "MASKED_BY_PROVIDER" if prompt == "***" else sha256(prompt.encode()).hexdigest()
    return config, prompt_hash, normalized


@dataclass(frozen=True, repr=False)
class PublishedRelease:
    metadata: dict[str, object] = field(repr=False)
    configuration: dict[str, Any] = field(repr=False)

    def evidence(self) -> dict[str, object]:
        return copy.deepcopy(self.metadata)

    def matches(self, other: PublishedRelease) -> bool:
        return self.metadata == other.metadata


async def _pages(namespace: Any, opts: Any, timeout: float, **filters: Any) -> list[Any]:
    items: list[Any] = []
    total: int | None = None
    for page in range(1, 101):
        async with asyncio.timeout(timeout):
            result = await namespace.list(page=page, page_size=100, opts=opts, **filters)
        if (
            not isinstance(result.total, int)
            or result.total < 0
            or result.page != page
            or not isinstance(result.items, list)
        ):
            _fail("WMA_CONTROL_PLANE_PAGINATION_INVALID")
        if total is None:
            total = result.total
        if result.total != total or (not result.items and len(items) < total):
            _fail("WMA_CONTROL_PLANE_PAGINATION_INVALID")
        items.extend(result.items)
        if len(items) == total:
            return items
        if len(items) > total:
            break
    _fail("WMA_CONTROL_PLANE_PAGINATION_INVALID")


async def resolve_release(
    client: Any, sdk: Any, public_id: str, timeout: float
) -> PublishedRelease:
    if public_id.isdigit():
        _fail("WMA_AGENT_ID_KIND_INVALID")
    opts = sdk.RequestOptions(timeout_ms=max(1, int(timeout * 1000)), retry=False)
    agents = await _pages(client.agents, opts, timeout, keyword=public_id)
    selected = [item for item in agents if item.agent_id == public_id]
    if len(selected) != 1:
        _fail("WMA_AGENT_NOT_UNIQUE")
    item = selected[0]
    identity = _numeric_id(item.id)
    if item.enabled is not True:
        _fail("WMA_AGENT_DISABLED")
    async with asyncio.timeout(timeout):
        agent = await client.agents.get(identity, opts=opts)
    info = agent.agent_info
    if _numeric_id(info.id) != identity or info.agent_id != public_id:
        _fail("WMA_AGENT_IDENTITY_MISMATCH")
    if info.enabled is not True:
        _fail("WMA_AGENT_DISABLED")
    versions = await _pages(agent.versions, opts, timeout)
    current = [version for version in versions if version.is_current is True]
    if len(current) != 1 or current[0].status != 1:
        _fail("WMA_CURRENT_RELEASE_UNAVAILABLE")
    release_id = _numeric_id(current[0].id)
    async with asyncio.timeout(timeout):
        release = await agent.versions.get(release_id, opts=opts)
    if (
        _numeric_id(release.id) != release_id
        or _numeric_id(release.agent_id) != identity
        or release.is_current is not True
        or release.status != 1
        or release.version_number != current[0].version_number
    ):
        _fail("WMA_RELEASE_IDENTITY_MISMATCH")
    model = _text(release.model, limit=256)
    version = _text(release.version_number, limit=128)
    config, prompt_hash, skills = _configuration(release.manifest, public_id, model)
    metadata: dict[str, object] = {
        "source": "CONTROL_PLANE",
        "agent_numeric_id": identity,
        "agent_id": public_id,
        "release_id": release_id,
        "release_version": version,
        "published_model": model,
        "prompt_sha256": prompt_hash,
        "configuration_sha256": _hash(config | {"prompt_sha256": prompt_hash}),
        "non_prompt_configuration_sha256": _hash(config),
        "skills_sha256": _hash(skills),
        "skills": skills,
    }
    return PublishedRelease(metadata, config)


def verify_session(
    raw: Any, release: PublishedRelease, runtime_id: str, session_id: str
) -> dict[str, object]:
    if hasattr(raw, "model_dump"):
        raw = raw.model_dump(by_alias=True)
    if (
        not isinstance(raw, dict)
        or str(raw.get("runtimeId")) != runtime_id
        or str(raw.get("sessionId")) != session_id
    ):
        _fail("WMA_SESSION_IDENTITY_MISMATCH")
    manifest = raw.get("agentManifest")
    config, prompt_hash, _skills = _configuration(
        manifest,
        str(release.metadata["agent_id"]),
        str(release.metadata["published_model"]),
        session=True,
    )
    if config != release.configuration:
        _fail("WMA_SESSION_CONFIGURATION_MISMATCH")
    masked = prompt_hash == "MASKED_BY_PROVIDER"
    if not masked and prompt_hash != release.metadata["prompt_sha256"]:
        _fail("WMA_SESSION_PROMPT_MISMATCH")
    return {
        "source": "CONTROL_PLANE",
        "agent_numeric_id": release.metadata["agent_numeric_id"],
        "agent_id": release.metadata["agent_id"],
        "release_id": release.metadata["release_id"],
        "release_version": release.metadata["release_version"],
        "session_binding": "PUBLISHED_AGENT_SESSION",
        "runtime_id": runtime_id,
        "session_id": session_id,
        "published_model": release.metadata["published_model"],
        "model_evidence": "CONFIGURATION_ONLY",
        "skills_sha256": release.metadata["skills_sha256"],
        "verified_non_prompt_configuration_sha256": _hash(config),
        "prompt_visibility": "MASKED_BY_PROVIDER" if masked else "VISIBLE_HASH_MATCH",
        "prompt_hash_verified": not masked,
    }
