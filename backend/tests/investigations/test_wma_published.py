"""Exercise the installed SDK 0.3.4 on a mocked REST transport, never the cloud."""

import asyncio
import copy
import json
import traceback
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import httpx2
import pytest
from pydantic import SecretStr

from deepaha.investigations.wma import DirectWmaClient, DirectWmaError, WmaBinding, WmaSessionRef

sdk = pytest.importorskip("cloud_agent_sdk")
httpx = pytest.importorskip("httpx")


@pytest.fixture(autouse=True)
def prompt_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    async def prompt(self: Any, text: str, options: Any) -> Any:
        calls.append(text)
        return SimpleNamespace(stop_reason="end_turn")

    monkeypatch.setattr(sdk.Session, "prompt", prompt)
    return calls


class ControlPlane:
    def __init__(self) -> None:
        self.manifest: dict[str, Any] = {
            "id": "agent-public",
            "name": "Synthetic investigator",
            "manifestVersion": "1.0",
            "description": "Synthetic release",
            "system_prompt": "synthetic private prompt",
            "useWorkspaceRoot": True,
            "skills": [
                {
                    "name": "browser-use",
                    "scope": "USER",
                    "downloadUrl": "https://openplatform-cdn.codebuddy.cn/s/skill.zip?skill_id=31&sign=old&revision=7",
                }
            ],
        }
        self.agent: dict[str, Any] = {
            "id": 101,
            "agentId": "agent-public",
            "agentName": "Synthetic investigator",
            "enabled": True,
            "model": "agnes-2.5-flash",
        }
        self.version: dict[str, Any] = {
            "id": 201,
            "agentId": 101,
            "versionNumber": "v1",
            "isCurrent": True,
            "status": 1,
            "model": "agnes-2.5-flash",
            "manifest": self.manifest,
        }
        self.actual = copy.deepcopy(self.manifest)
        self.actual.update(system_prompt="***", settingsJson={"model": "agnes-2.5-flash"})
        self.actual["skills"][0]["downloadUrl"] = self.actual["skills"][0]["downloadUrl"].replace(
            "sign=old", "sign=rotated"
        )
        self.actual["envs"] = [{"key": "PROVIDER_ENV", "value": "private-environment"}]
        self.actual["secrets"] = [{"key": "CODEBUDDY_API_KEY", "value": "***"}]
        self.requests: list[tuple[str, str, dict[str, Any] | None]] = []
        self.on_session_create: Callable[[], None] | None = None
        self.extra_current = False
        self.session_runtime = "runtime-1"
        self.session_identity = "published-session"
        self.prompts: list[str] = []
        self.session_create_failure = False
        self.agent_pages: list[list[dict[str, Any]]] | None = None
        self.info_override: dict[str, Any] = {}

    def response(self, request: Any) -> Any:
        path = request.url.path.removeprefix("/v2/agentos")
        body = json.loads(request.content) if request.content else None
        self.requests.append((request.method, path, body))
        data: dict[str, Any]
        if path == "/agents":
            page = int(request.url.params.get("page", "1"))
            pages = self.agent_pages or [[self.agent]]
            data = {
                "items": pages[page - 1],
                "total": sum(map(len, pages)),
                "page": page,
                "pageSize": 100,
            }
        elif path == "/agents/101":
            data = self.agent | {"manifest": self.manifest}
        elif path == "/agents/101/versions":
            items = [self.version]
            if self.extra_current:
                items.append(self.version | {"id": 202})
            data = {"items": items, "total": len(items), "page": 1, "pageSize": 100}
        elif path == "/agents/101/versions/201":
            data = self.version
        elif path == "/runtimes":
            assert request.method == "POST"
            assert body is not None
            assert body["visibility"] == "PRIVATE"
            data = self.runtime()
        elif path == "/runtimes/runtime-1":
            data = self.runtime()
        elif path == "/agents/sessions":
            assert body == {"agentId": "101", "runtimeId": "runtime-1", "sessionName": "task-1"}
            if self.on_session_create is not None:
                self.on_session_create()
            if self.session_create_failure:
                return httpx.Response(500, json={"code": 500, "message": "synthetic-api-key"})
            data = self.session()
        elif path == "/runtimes/runtime-1/sessions/published-session":
            data = self.session() | {"agentManifest": self.actual} | self.info_override
        else:
            pytest.fail("unexpected SDK route")
        return httpx.Response(200, json={"code": 0, "data": data})

    def runtime(self) -> dict[str, Any]:
        return {
            "id": "runtime-1",
            "runtimeName": "task-1",
            "status": "RUNNING",
            "createdAt": "2026-09-07T00:00:00Z",
            "updatedAt": "2026-09-07T00:00:00Z",
            "sessions": [{"sessionId": "default-session", "sessionStatus": "IDLE"}],
            "links": {
                "sandboxLink": {
                    "endpoint": "https://sandbox.example",
                    "dataPlaneEndpoint": "https://sandbox.example",
                    "sandboxId": "sandbox-1",
                },
                "acpLink": {
                    "url": "https://sandbox.example/acp",
                    "token": "synthetic-token",
                    "tokenExpiresAt": 2000000000,
                },
            },
        }

    def session(self) -> dict[str, Any]:
        return {
            "runtimeId": self.session_runtime,
            "sessionId": self.session_identity,
            "sessionName": "task-1",
            "sessionStatus": "IDLE",
            "createdAt": "2026-09-07T00:00:00Z",
            "updatedAt": "2026-09-07T00:00:00Z",
        }


@asynccontextmanager
async def adapter(
    state: ControlPlane,
    *,
    public_id: str = "agent-public",
    create_timeout: float = 120,
    session_delay: float = 0,
) -> AsyncIterator[DirectWmaClient]:
    async def control(request: Any) -> Any:
        if request.url.path.endswith("/agents/sessions") and session_delay:
            await asyncio.sleep(session_delay)
        return state.response(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(control)) as http:
        factory = SimpleNamespace(
            CloudAgentClient=lambda **kw: sdk.CloudAgentClient(http_client=http, **kw),
            RequestOptions=sdk.RequestOptions,
            SessionCreateOptions=sdk.SessionCreateOptions,
            RuntimeCreateOptions=sdk.RuntimeCreateOptions,
            ManifestBuilder=sdk.ManifestBuilder,
            PromptOptions=sdk.PromptOptions,
        )
        c = DirectWmaClient(
            WmaBinding(SecretStr("synthetic-api-key"), public_id, "cloud-agent", "1.0"),
            sdk=factory,
            create_timeout_seconds=create_timeout,
            transport=httpx2.MockTransport(lambda r: httpx2.Response(200, content=b"original")),
        )
        try:
            yield c
        finally:
            await c.aclose()


def test_real_sdk_published_session_route_and_signed_url_rotation() -> None:
    state = ControlPlane()
    checkpoints: list[tuple[str, str | None]] = []

    async def scenario() -> None:
        async with adapter(state) as c:
            release = await c.inspect_release()
            ref = await c.create("task-1", checkpoint=lambda r, s: checkpoints.append((r, s)))
            assert ref == WmaSessionRef("runtime-1", "published-session")
            evidence = c.binding_evidence()
            assert release["source"] == "CONTROL_PLANE"
            assert release["agent_numeric_id"] == "101"
            assert release["release_id"] == "201" and release["release_version"] == "v1"
            assert evidence["prompt_visibility"] == "MASKED_BY_PROVIDER"
            assert evidence["prompt_hash_verified"] is False
            assert evidence["model_evidence"] == "CONFIGURATION_ONLY"
            persisted = json.dumps({"release": release, "binding": evidence})
            for private in (
                "synthetic private prompt",
                "sign=",
                "private-environment",
                "skill.zip",
            ):
                assert private not in persisted
            release["release_id"] = "caller-tampered"
            assert (await c.inspect_release())["release_id"] == "201"

    asyncio.run(scenario())
    assert checkpoints == [("runtime-1", None), ("runtime-1", "published-session")]
    posts = [path for method, path, _ in state.requests if method == "POST"]
    assert posts == ["/runtimes", "/agents/sessions"]
    assert not any("default-session" in path for _, path, _ in state.requests)


@pytest.mark.parametrize(
    "fault",
    [
        "disabled",
        "numeric_id",
        "ambiguous",
        "no_current",
        "unpublished",
        "model",
        "prompt",
        "masked_prompt",
        "skills",
        "unsupported",
        "identity",
    ],
)
def test_release_failures_prevent_all_resource_creation(fault: str) -> None:
    state = ControlPlane()
    if fault == "disabled":
        state.agent["enabled"] = False
    elif fault == "ambiguous":
        state.extra_current = True
    elif fault == "no_current":
        state.version["isCurrent"] = False
    elif fault == "unpublished":
        state.version["status"] = 0
    elif fault == "model":
        state.version["model"] = ""
    elif fault == "prompt":
        state.manifest["system_prompt"] = " "
    elif fault == "masked_prompt":
        state.manifest["system_prompt"] = "***"
    elif fault == "skills":
        state.manifest["skills"] = []
    elif fault == "unsupported":
        state.manifest["plugins"] = [{"unexamined": True}]
    elif fault == "identity":
        state.version["agentId"] = 999

    async def scenario() -> None:
        async with adapter(
            state, public_id="101" if fault == "numeric_id" else "agent-public"
        ) as c:
            with pytest.raises(DirectWmaError):
                await c.create("task-1")

    asyncio.run(scenario())
    assert all(method == "GET" for method, _, _ in state.requests)


@pytest.mark.parametrize(
    "fault", ["model", "skill_id", "other_parameter", "path", "prompt", "skills", "identity"]
)
def test_binding_mismatch_preserves_both_checkpoints_and_forbids_prompt(fault: str) -> None:
    state = ControlPlane()
    if fault == "model":
        state.actual["settingsJson"]["model"] = "other-model"
    elif fault in {"skill_id", "other_parameter", "path"}:
        old, new = {
            "skill_id": ("skill_id=31", "skill_id=32"),
            "other_parameter": ("revision=7", "revision=8"),
            "path": ("skill.zip", "different.zip"),
        }[fault]
        state.actual["skills"][0]["downloadUrl"] = state.actual["skills"][0]["downloadUrl"].replace(
            old, new
        )
    elif fault == "prompt":
        state.actual["system_prompt"] = ""
    elif fault == "skills":
        state.actual["skills"] = []
    else:
        state.actual["id"] = "wrong-agent"
    checkpoints: list[tuple[str, str | None]] = []

    async def scenario() -> None:
        async with adapter(state) as c:
            with pytest.raises(DirectWmaError):
                await c.create("task-1", checkpoint=lambda r, s: checkpoints.append((r, s)))
            with pytest.raises(DirectWmaError):
                await c.prompt("must not investigate", 0.1)

    asyncio.run(scenario())
    assert checkpoints == [("runtime-1", None), ("runtime-1", "published-session")]


def test_release_changed_during_session_creation_is_rejected() -> None:
    state = ControlPlane()
    state.on_session_create = lambda: state.version.update(versionNumber="v2")

    async def scenario() -> None:
        async with adapter(state) as c:
            with pytest.raises(DirectWmaError, match="WMA_RELEASE_CHANGED"):
                await c.create("task-1")

    asyncio.run(scenario())


def test_prompt_rechecks_release_and_session_without_sending_on_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = ControlPlane()

    async def prompt(self: Any, text: str, options: Any) -> Any:
        state.prompts.append(text)
        return SimpleNamespace(stop_reason="end_turn")

    monkeypatch.setattr(sdk.Session, "prompt", prompt)

    async def scenario() -> None:
        async with adapter(state) as c:
            await c.create("task-1")
            state.actual["settingsJson"]["model"] = "other-model"
            with pytest.raises(DirectWmaError):
                await c.prompt("must not investigate", 1)

    asyncio.run(scenario())
    assert state.prompts == []


def test_resume_can_download_without_release_lookup_and_cannot_prompt(
    prompt_calls: list[str],
) -> None:
    state = ControlPlane()
    state.agent["enabled"] = False

    async def scenario() -> None:
        async with adapter(state) as c:
            await c.resume(WmaSessionRef("runtime-1", "published-session"))
            assert await c.download("/workspace/old.bin", 10) == b"original"
            with pytest.raises(DirectWmaError):
                await c.prompt("must not investigate", 1)

    asyncio.run(scenario())
    assert not any(path.startswith("/agents") for _, path, _ in state.requests)
    assert prompt_calls == []


def test_invalid_release_error_does_not_echo_raw_configuration() -> None:
    state = ControlPlane()
    state.manifest["plugins"] = ["synthetic-api-key", "synthetic private prompt"]

    async def scenario() -> None:
        async with adapter(state) as c:
            with pytest.raises(DirectWmaError) as caught:
                await c.create("task-1")
            rendered = "".join(traceback.format_exception(caught.value))
            assert "synthetic-api-key" not in rendered
            assert "synthetic private prompt" not in rendered

    asyncio.run(scenario())


def test_real_sdk_session_create_failure_keeps_runtime_checkpoint_and_never_retries() -> None:
    state = ControlPlane()
    state.session_create_failure = True
    checkpoints: list[tuple[str, str | None]] = []

    async def scenario() -> None:
        async with adapter(state) as c:
            with pytest.raises(DirectWmaError) as caught:
                await c.create("task-1", checkpoint=lambda r, s: checkpoints.append((r, s)))
            assert "synthetic-api-key" not in "".join(traceback.format_exception(caught.value))

    asyncio.run(scenario())
    assert checkpoints == [("runtime-1", None)]
    assert sum(path == "/agents/sessions" for _, path, _ in state.requests) == 1


def test_control_plane_lookup_paginates_and_matches_public_identifier_exactly() -> None:
    state = ControlPlane()
    state.agent_pages = [
        [state.agent | {"id": 102, "agentId": "agent-public-other"}],
        [state.agent],
    ]

    async def scenario() -> None:
        async with adapter(state) as c:
            result = await c.inspect_release()
            assert result["agent_numeric_id"] == "101"

    asyncio.run(scenario())
    assert sum(path == "/agents" for _, path, _ in state.requests) == 2
    assert not any(path == "/agents/102" for _, path, _ in state.requests)


def test_ambiguous_public_identifier_is_rejected() -> None:
    state = ControlPlane()
    state.agent_pages = [[state.agent, state.agent | {"id": 102}]]

    async def scenario() -> None:
        async with adapter(state) as c:
            with pytest.raises(DirectWmaError, match="WMA_AGENT_NOT_UNIQUE"):
                await c.inspect_release()

    asyncio.run(scenario())


def test_prompt_rechecks_current_release_and_sends_at_most_once(prompt_calls: list[str]) -> None:
    state = ControlPlane()

    async def scenario() -> None:
        async with adapter(state) as c:
            await c.create("task-1")
            assert await c.prompt("one investigation", 1) == "end_turn"
            with pytest.raises(DirectWmaError):
                await c.prompt("must not run again", 1)

    asyncio.run(scenario())
    assert prompt_calls == ["one investigation"]


def test_changed_release_before_prompt_never_sends_and_invalidates_evidence(
    prompt_calls: list[str],
) -> None:
    state = ControlPlane()

    async def scenario() -> None:
        async with adapter(state) as c:
            await c.create("task-1")
            state.version["versionNumber"] = "v2"
            with pytest.raises(DirectWmaError, match="WMA_RELEASE_CHANGED"):
                await c.prompt("must not investigate", 1)
            with pytest.raises(DirectWmaError, match="WMA_SESSION_NOT_VERIFIED"):
                c.binding_evidence()

    asyncio.run(scenario())
    assert prompt_calls == []


def test_session_info_falls_back_to_sdk_rest_when_dto_omits_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = ControlPlane()
    original_info = sdk.Session.info

    async def filtered_info(self: Any, opts: Any = None) -> Any:
        data = await original_info(self, opts)
        values = data.model_dump(by_alias=True)
        values.pop("agentManifest")
        return values

    monkeypatch.setattr(sdk.Session, "info", filtered_info)

    async def scenario() -> None:
        async with adapter(state) as c:
            await c.create("task-1")
            assert c.binding_evidence()["session_binding"] == "PUBLISHED_AGENT_SESSION"

    asyncio.run(scenario())
    assert sum("/sessions/published-session" in path for _, path, _ in state.requests) == 2


@pytest.mark.parametrize("field", ["runtime", "session"])
def test_session_metadata_identity_mismatch_is_rejected(field: str) -> None:
    state = ControlPlane()
    if field == "runtime":
        state.info_override["runtimeId"] = "other-runtime"
    else:
        state.info_override["sessionId"] = "other-session"

    async def scenario() -> None:
        async with adapter(state) as c:
            with pytest.raises(DirectWmaError):
                await c.create("task-1")

    asyncio.run(scenario())


def test_signature_parameter_on_unrecognized_host_is_not_ignored() -> None:
    state = ControlPlane()
    for manifest in (state.manifest, state.actual):
        manifest["skills"][0]["downloadUrl"] = manifest["skills"][0]["downloadUrl"].replace(
            "openplatform-cdn.codebuddy.cn", "different.example"
        )

    async def scenario() -> None:
        async with adapter(state) as c:
            with pytest.raises(DirectWmaError, match="WMA_SESSION_CONFIGURATION_MISMATCH"):
                await c.create("task-1")

    asyncio.run(scenario())


def test_published_signature_rotation_during_create_does_not_change_release() -> None:
    state = ControlPlane()

    def rotate_signature() -> None:
        skill = state.manifest["skills"][0]
        skill["downloadUrl"] = skill["downloadUrl"].replace("sign=old", "sign=another")

    state.on_session_create = rotate_signature

    async def scenario() -> None:
        async with adapter(state) as c:
            release = await c.inspect_release()
            await c.create("task-1")
            assert (await c.inspect_release())["configuration_sha256"] == release[
                "configuration_sha256"
            ]

    asyncio.run(scenario())


def test_changed_release_after_inspection_is_rejected_before_runtime_creation() -> None:
    state = ControlPlane()

    async def scenario() -> None:
        async with adapter(state) as c:
            await c.inspect_release()
            state.version["versionNumber"] = "v2"
            with pytest.raises(DirectWmaError, match="WMA_RELEASE_CHANGED"):
                await c.create("task-1")

    asyncio.run(scenario())
    assert all(method == "GET" for method, _, _ in state.requests)


@pytest.mark.parametrize("fault", ["description", "settings", "unsupported", "different_prompt"])
def test_other_comparable_session_configuration_must_match(fault: str) -> None:
    state = ControlPlane()
    if fault == "description":
        state.actual["description"] = "Different release"
    elif fault == "settings":
        state.actual["settingsJson"]["unapprovedSetting"] = True
    elif fault == "unsupported":
        state.actual["plugins"] = []
    else:
        state.actual["system_prompt"] = "Different non-masked prompt"

    async def scenario() -> None:
        async with adapter(state) as c:
            with pytest.raises(DirectWmaError):
                await c.create("task-1")

    asyncio.run(scenario())


def test_visible_prompt_hash_match_is_reported_only_when_content_is_available() -> None:
    state = ControlPlane()
    state.actual["system_prompt"] = state.manifest["system_prompt"]

    async def scenario() -> None:
        async with adapter(state) as c:
            await c.create("task-1")
            evidence = c.binding_evidence()
            assert evidence["prompt_hash_verified"] is True
            assert evidence["prompt_visibility"] == "VISIBLE_HASH_MATCH"
            assert "synthetic private prompt" not in json.dumps(evidence)

    asyncio.run(scenario())


def test_whole_create_window_bounds_session_creation_and_retains_runtime() -> None:
    state = ControlPlane()
    checkpoints: list[tuple[str, str | None]] = []

    async def scenario() -> None:
        async with adapter(state, create_timeout=0.1, session_delay=0.2) as c:
            with pytest.raises(DirectWmaError, match="WMA_TIMEOUT"):
                await c.create("task-1", checkpoint=lambda r, s: checkpoints.append((r, s)))
            with pytest.raises(DirectWmaError):
                c.binding_evidence()

    asyncio.run(scenario())
    assert checkpoints == [("runtime-1", None)]
