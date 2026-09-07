"""Direct WMA transport; remote outputs remain unapproved candidate material.

SDK surface: codebuddy-cloud-agent-sdk 0.3.4, CloudAgentClient.runtimes,
Runtime.sessions and PromptOptions(timeout_ms). File transfer uses the SDK-issued
Sandbox Data Plane link, never a URL supplied by an investigation result.
"""

from __future__ import annotations

import asyncio
import copy
import importlib
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit

import httpx2
from pydantic import SecretStr

from deepaha.investigations.published import (
    PublishedBindingError,
    PublishedRelease,
    resolve_release,
    verify_session,
)


class DirectWmaError(RuntimeError):
    """A stable, non-secret failure suitable for a persisted task status."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _identifier(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value) is None:
        raise DirectWmaError("WMA_INVALID_IDENTITY")
    return value


@dataclass(frozen=True)
class WmaBinding:
    api_key: SecretStr = field(repr=False)
    agent_id: str
    source_app: str
    # Legacy field name: this is only the basic Runtime manifest schema version.
    # Published Agent release IDs/versions are resolved from the control plane.
    agent_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.api_key, SecretStr) or not self.api_key.get_secret_value():
            raise DirectWmaError("WMA_INVALID_BINDING")
        for value in (self.agent_id, self.source_app, self.agent_version):
            _identifier(value)


@dataclass(frozen=True)
class WmaSessionRef:
    """Only these identifiers may be persisted; link tokens are refreshed by SDK."""

    runtime_id: str
    session_id: str

    def __post_init__(self) -> None:
        _identifier(self.runtime_id)
        _identifier(self.session_id)


def _remote_path(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("/workspace/")
        or len(value) > 2048
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or any(character in value for character in ("\\", "%", "?", "#"))
        or any(part in {"", ".", ".."} for part in value.split("/")[1:])
        or str(PurePosixPath(value)) != value
    ):
        raise DirectWmaError("WMA_INVALID_REMOTE_PATH")
    return value


def _positive_timeout(value: float) -> float:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
        raise DirectWmaError("WMA_INVALID_TIMEOUT")
    return value


class DirectWmaClient:
    """One task's SDK connection, with no automatic prompt retry or result approval.

    The calling service owns the absolute task deadline and durable state. This
    adapter bounds individual operations and exposes only a terminal stop reason,
    identifiers and byte strings. It does not register a thought/event callback.
    """

    def __init__(
        self,
        binding: WmaBinding,
        *,
        request_timeout_seconds: float = 30.0,
        create_timeout_seconds: float = 120.0,
        sdk: Any | None = None,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self._binding = binding
        self._timeout = _positive_timeout(request_timeout_seconds)
        self._create_timeout = _positive_timeout(create_timeout_seconds)
        if sdk is None:
            try:
                sdk = importlib.import_module("cloud_agent_sdk")
            except ImportError:
                raise DirectWmaError("WMA_SDK_UNAVAILABLE") from None
        self._sdk = sdk
        try:
            self._client = sdk.CloudAgentClient(
                api_key=binding.api_key.get_secret_value(),
                source_app=binding.source_app,
                timeout_ms=max(1, int(self._timeout * 1000)),
                retry=False,
            )
        except Exception:
            raise DirectWmaError("WMA_SDK_INITIALIZATION_FAILED") from None
        self._http = httpx2.AsyncClient(
            timeout=httpx2.Timeout(self._timeout),
            transport=transport,
            follow_redirects=False,
            trust_env=False,
        )
        self._runtime: Any | None = None
        self._session: Any | None = None
        self._release: PublishedRelease | None = None
        self._binding_evidence: dict[str, object] | None = None
        self._prompt_allowed = False

    async def inspect_release(self) -> dict[str, object]:
        """Freeze the current release once; callers receive only safe metadata copies."""
        try:
            if self._release is None:
                async with asyncio.timeout(self._timeout):
                    self._release = await resolve_release(
                        self._client, self._sdk, self._binding.agent_id, self._timeout
                    )
            return self._release.evidence()
        except PublishedBindingError as error:
            raise DirectWmaError(error.code) from None
        except TimeoutError:
            raise DirectWmaError("WMA_TIMEOUT") from None
        except DirectWmaError:
            raise
        except Exception:
            raise DirectWmaError("WMA_RELEASE_INSPECTION_FAILED") from None

    async def _assert_current_release(self) -> None:
        fresh = await resolve_release(
            self._client, self._sdk, self._binding.agent_id, self._timeout
        )
        if self._release is None:
            self._release = fresh
        elif not self._release.matches(fresh):
            raise DirectWmaError("WMA_RELEASE_CHANGED")

    async def _verify_bound_session(self) -> dict[str, object]:
        if self._release is None or self._runtime is None or self._session is None:
            raise DirectWmaError("WMA_SESSION_NOT_VERIFIED")
        opts = self._sdk.RequestOptions(timeout_ms=max(1, int(self._timeout * 1000)), retry=False)
        async with asyncio.timeout(self._timeout):
            # SDK 0.3.4 calls this method info(); its SessionInfo preserves extra
            # agentManifest fields. Never use the basic Runtime's default session.
            raw = await self._session.info(opts=opts)
            if hasattr(raw, "model_dump"):
                raw = raw.model_dump(by_alias=True)
            if not isinstance(raw, dict) or "agentManifest" not in raw:
                raw = await self._client._rest.get(
                    f"/runtimes/{self._runtime.id}/sessions/{self._session.id}", None, opts
                )
        return verify_session(raw, self._release, str(self._runtime.id), str(self._session.id))

    def binding_evidence(self) -> dict[str, object]:
        if self._binding_evidence is None:
            raise DirectWmaError("WMA_SESSION_NOT_VERIFIED")
        return copy.deepcopy(self._binding_evidence)

    async def create(
        self, task_key: str, *, checkpoint: Callable[[str, str | None], None] | None = None
    ) -> WmaSessionRef:
        _identifier(task_key)
        if self._runtime is not None or self._session is not None:
            raise DirectWmaError("WMA_RESOURCE_ALREADY_BOUND")
        self._prompt_allowed = False
        self._binding_evidence = None
        try:
            async with asyncio.timeout(self._create_timeout):
                await self._assert_current_release()
                if self._release is None:
                    raise DirectWmaError("WMA_RELEASE_INSPECTION_FAILED")
                manifest = (
                    self._sdk.ManifestBuilder()
                    .id(self._binding.agent_id)
                    .name("DeepAha Opportunity Investigator")
                    .version(self._binding.agent_version)
                    .build()
                )
                runtime = await self._client.runtimes.create(
                    self._sdk.RuntimeCreateOptions(
                        runtime_name=task_key,
                        agent_manifest=manifest,
                        visibility="PRIVATE",
                        timeout_ms=max(1, int(self._create_timeout * 1000)),
                        retry=False,
                    )
                )
                self._runtime = runtime
                runtime_id = _identifier(str(runtime.id))
                if checkpoint is not None:
                    checkpoint(runtime_id, None)
                session = await runtime.sessions.create(
                    self._sdk.SessionCreateOptions(
                        agent_id=str(self._release.metadata["agent_numeric_id"]),
                        session_name=task_key,
                        timeout_ms=max(1, int(self._timeout * 1000)),
                        retry=False,
                    )
                )
                self._session = session
                ref = WmaSessionRef(runtime_id=str(runtime.id), session_id=str(session.id))
                if checkpoint is not None:
                    checkpoint(ref.runtime_id, ref.session_id)
                evidence = await self._verify_bound_session()
                await self._assert_current_release()
                self._binding_evidence = evidence
                self._prompt_allowed = True
                return ref
        except PublishedBindingError as error:
            raise DirectWmaError(error.code) from None
        except TimeoutError:
            raise DirectWmaError("WMA_TIMEOUT") from None
        except DirectWmaError:
            raise
        except Exception:
            raise DirectWmaError("WMA_CREATE_FAILED") from None

    async def resume(self, ref: WmaSessionRef) -> None:
        self._prompt_allowed = False
        self._binding_evidence = None
        try:
            async with asyncio.timeout(self._timeout):
                runtime = await self._client.runtimes.get(ref.runtime_id)
                session = await runtime.sessions.get(ref.session_id)
                if str(runtime.id) != ref.runtime_id or str(session.id) != ref.session_id:
                    raise DirectWmaError("WMA_RESUME_IDENTITY_MISMATCH")
                self._runtime, self._session = runtime, session
        except TimeoutError:
            raise DirectWmaError("WMA_TIMEOUT") from None
        except DirectWmaError:
            raise
        except Exception:
            raise DirectWmaError("WMA_RESUME_FAILED") from None

    def _data_plane(self) -> tuple[str, dict[str, str]]:
        try:
            if self._runtime is None:
                raise ValueError
            links = self._runtime.runtime_info.links
            endpoint = str(links.sandbox_link.data_plane_endpoint)
            token = links.acp_link.token
            url = urlsplit(endpoint)
            if (
                url.scheme != "https"
                or not url.hostname
                or url.username is not None
                or url.password is not None
                or url.query
                or url.fragment
                or url.path not in {"", "/"}
                or not isinstance(token, str)
                or not token
                or any(ord(char) < 32 or ord(char) == 127 for char in token)
            ):
                raise ValueError
            return endpoint.rstrip("/") + "/files", {"X-Access-Token": token}
        except Exception:
            raise DirectWmaError("WMA_DATA_PLANE_UNAVAILABLE") from None

    async def upload(self, remote_path: str, content: bytes) -> None:
        path = _remote_path(remote_path)
        if not isinstance(content, bytes):
            raise DirectWmaError("WMA_BYTES_REQUIRED")
        endpoint, headers = self._data_plane()
        try:
            async with asyncio.timeout(self._timeout):
                async with self._http.stream(
                    "POST",
                    endpoint,
                    headers=headers,
                    params={"path": path},
                    files={"file": (PurePosixPath(path).name, content)},
                ) as response:
                    if response.status_code != 200:
                        raise DirectWmaError("WMA_UPLOAD_FAILED")
        except TimeoutError:
            raise DirectWmaError("WMA_TIMEOUT") from None
        except DirectWmaError:
            raise
        except Exception:
            raise DirectWmaError("WMA_UPLOAD_FAILED") from None

    async def prompt(self, text: str, timeout_seconds: float) -> str:
        timeout_seconds = _positive_timeout(timeout_seconds)
        if self._session is None:
            raise DirectWmaError("WMA_SESSION_REQUIRED")
        if not self._prompt_allowed:
            raise DirectWmaError("WMA_SESSION_NOT_VERIFIED")
        # A failed/uncertain prompt must be recovered by downloading; never retry it.
        self._prompt_allowed = False
        self._binding_evidence = None
        try:
            deadline = asyncio.get_running_loop().time() + timeout_seconds
            async with asyncio.timeout(timeout_seconds):
                await self._assert_current_release()
                self._binding_evidence = await self._verify_bound_session()
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise TimeoutError
                result = await self._session.prompt(
                    text,
                    self._sdk.PromptOptions(
                        timeout_ms=max(1, int(remaining * 1000)), include_thinking=False
                    ),
                )
                reason = result.stop_reason
                if reason not in {
                    "end_turn",
                    "max_tokens",
                    "max_turn_requests",
                    "refusal",
                    "cancelled",
                }:
                    raise DirectWmaError("WMA_UNRECOGNIZED_STOP_REASON")
                return str(reason)
        except PublishedBindingError as error:
            raise DirectWmaError(error.code) from None
        except TimeoutError:
            raise DirectWmaError("WMA_TIMEOUT") from None
        except DirectWmaError:
            raise
        except Exception:
            raise DirectWmaError("WMA_PROMPT_FAILED") from None

    async def download(self, remote_path: str, max_bytes: int) -> bytes:
        path = _remote_path(remote_path)
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
            raise DirectWmaError("WMA_INVALID_SIZE_LIMIT")
        endpoint, headers = self._data_plane()
        headers["Accept-Encoding"] = "identity"
        try:
            async with asyncio.timeout(self._timeout):
                async with self._http.stream(
                    "GET", endpoint, headers=headers, params={"path": path}
                ) as response:
                    if response.status_code == 404:
                        raise DirectWmaError("WMA_ARTIFACT_NOT_FOUND")
                    if response.status_code != 200:
                        raise DirectWmaError("WMA_DOWNLOAD_FAILED")
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise DirectWmaError("WMA_UNSUPPORTED_CONTENT_ENCODING")
                    declared_length = response.headers.get("content-length")
                    if declared_length and int(declared_length) > max_bytes:
                        raise DirectWmaError("WMA_ARTIFACT_TOO_LARGE")
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(content) + len(chunk) > max_bytes:
                            raise DirectWmaError("WMA_ARTIFACT_TOO_LARGE")
                        content.extend(chunk)
                    return bytes(content)
        except TimeoutError:
            raise DirectWmaError("WMA_TIMEOUT") from None
        except DirectWmaError:
            raise
        except Exception:
            raise DirectWmaError("WMA_DOWNLOAD_FAILED") from None

    async def aclose(self) -> None:
        try:
            try:
                async with asyncio.timeout(self._timeout):
                    if self._session is not None:
                        await self._session.disconnect()
            finally:
                async with asyncio.timeout(self._timeout):
                    await self._client.aclose()
        except TimeoutError:
            raise DirectWmaError("WMA_TIMEOUT") from None
        except Exception:
            raise DirectWmaError("WMA_CLOSE_FAILED") from None
        finally:
            await self._http.aclose()
            self._runtime = None
            self._session = None
            self._prompt_allowed = False
