import asyncio
import copy
import importlib
import json
import traceback
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict
from types import SimpleNamespace
from typing import Any

import httpx2
import pytest
from pydantic import SecretStr


def module() -> Any:
    return importlib.import_module("deepaha.investigations.wma")


class ChunkStream(httpx2.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.reads = 0
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            self.reads += 1
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


class SessionBoundary:
    id = "session-1"

    def __init__(self) -> None:
        self.prompts: list[tuple[str, Any]] = []
        self.failure: Exception | None = None
        self.delay = 0.0
        self.disconnected = False
        self.manifest: dict[str, Any] = {}

    async def info(self, opts: Any = None) -> Any:
        return {
            "runtimeId": "runtime-1",
            "sessionId": self.id,
            "agentManifest": self.manifest,
        }

    async def disconnect(self) -> None:
        self.disconnected = True

    async def prompt(self, text: str, options: Any) -> Any:
        self.prompts.append((text, options))
        if self.failure is not None:
            raise self.failure
        if self.delay:
            await asyncio.sleep(self.delay)
        return SimpleNamespace(stop_reason="end_turn")


class SessionsBoundary:
    def __init__(self, session: SessionBoundary) -> None:
        self.session = session
        self.resumed: list[str] = []

    def default(self) -> SessionBoundary:
        pytest.fail("the default session must never be selected")

    async def create(self, options: Any) -> SessionBoundary:
        assert options.agent_id == "101"
        assert options.retry is False
        return self.session

    async def get(self, session_id: str) -> SessionBoundary:
        self.resumed.append(session_id)
        assert session_id == self.session.id
        return self.session


class SdkBoundary:
    def __init__(self) -> None:
        self.session = SessionBoundary()
        self.runtime = SimpleNamespace(
            id="runtime-1",
            sessions=SessionsBoundary(self.session),
            runtime_info=SimpleNamespace(
                links=SimpleNamespace(
                    sandbox_link=SimpleNamespace(data_plane_endpoint="https://sandbox.example"),
                    acp_link=SimpleNamespace(token="private-data-token"),
                )
            ),
        )
        self.created: list[Any] = []
        self.retrieved: list[str] = []
        self.closed = False
        self.client_options: dict[str, Any] = {}
        self.manifest = {
            "id": "agent-1",
            "name": "Synthetic published agent",
            "manifestVersion": "1.0",
            "system_prompt": "Synthetic published instructions",
            "useWorkspaceRoot": True,
            "skills": [
                {
                    "name": "browser-use",
                    "scope": "USER",
                    "downloadUrl": "https://openplatform-cdn.codebuddy.cn/skill.zip?skill_id=1&sign=synthetic",
                }
            ],
        }
        self.session.manifest = copy.deepcopy(self.manifest)
        self.session.manifest.update(system_prompt="***", settingsJson={"model": "agnes-2.5-flash"})
        self.agent_info = SimpleNamespace(id="101", agent_id="agent-1", enabled=True)
        self.version = SimpleNamespace(
            id="201",
            agent_id="101",
            version_number="v1",
            is_current=True,
            status=1,
            model="agnes-2.5-flash",
            manifest=self.manifest,
        )

    async def list_agents(self, **options: Any) -> Any:
        return SimpleNamespace(items=[self.agent_info], total=1, page=1, page_size=100)

    async def get_agent(self, identity: str, opts: Any = None) -> Any:
        assert identity == "101"
        return SimpleNamespace(
            agent_info=self.agent_info,
            versions=SimpleNamespace(list=self.list_versions, get=self.get_version),
        )

    async def list_versions(self, **options: Any) -> Any:
        return SimpleNamespace(items=[self.version], total=1, page=1, page_size=100)

    async def get_version(self, identity: str, opts: Any = None) -> Any:
        assert identity == "201"
        return self.version

    def CloudAgentClient(self, **options: Any) -> Any:
        self.client_options = options
        return SimpleNamespace(
            runtimes=SimpleNamespace(create=self.create, get=self.get),
            aclose=self.aclose,
            agents=SimpleNamespace(list=self.list_agents, get=self.get_agent),
        )

    async def create(self, options: Any) -> Any:
        self.created.append(options)
        return self.runtime

    async def get(self, runtime_id: str) -> Any:
        self.retrieved.append(runtime_id)
        return self.runtime

    async def aclose(self) -> None:
        self.closed = True

    RuntimeCreateOptions = SimpleNamespace
    SessionCreateOptions = SimpleNamespace
    RequestOptions = SimpleNamespace
    PromptOptions = SimpleNamespace

    class ManifestBuilder:
        def __init__(self) -> None:
            self.values: dict[str, str] = {}

        def id(self, value: str) -> Any:
            self.values["id"] = value
            return self

        def name(self, value: str) -> Any:
            self.values["name"] = value
            return self

        def version(self, value: str) -> Any:
            self.values["version"] = value
            return self

        def build(self) -> dict[str, str]:
            return self.values


def client(sdk: SdkBoundary, handler: Callable[[httpx2.Request], httpx2.Response]) -> Any:
    m = module()
    return m.DirectWmaClient(
        m.WmaBinding(
            api_key=SecretStr("private-api-key"),
            agent_id="agent-1",
            source_app="cloud-agent",
            agent_version="1.0",
        ),
        sdk=sdk,
        transport=httpx2.MockTransport(handler),
        request_timeout_seconds=0.2,
        create_timeout_seconds=0.2,
    )


def test_binary_download_and_upload_readback_preserve_bytes() -> None:
    sdk = SdkBoundary()
    original = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\xff\r\n"
    requests: list[httpx2.Request] = []

    def transfer(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        assert request.headers["x-access-token"] == "private-data-token"
        assert request.url.params["path"] == "/workspace/task/artifact.doc"
        if request.method == "POST":
            assert original in request.content
            return httpx2.Response(200)
        return httpx2.Response(200, content=original)

    async def scenario() -> None:
        c = client(sdk, transfer)
        ref = await c.create("task-1")
        assert asdict(ref) == {"runtime_id": "runtime-1", "session_id": "session-1"}
        await c.upload("/workspace/task/artifact.doc", original)
        assert await c.download("/workspace/task/artifact.doc", max_bytes=32) == original
        await c.aclose()

    asyncio.run(scenario())
    assert [r.method for r in requests] == ["POST", "GET"]
    assert sdk.created[0].agent_manifest["id"] == "agent-1"
    assert sdk.created[0].agent_manifest["version"] == "1.0"
    assert sdk.closed
    assert sdk.session.disconnected


def test_resume_only_recovers_exact_runtime_and_session_without_investigation() -> None:
    sdk = SdkBoundary()

    async def scenario() -> None:
        c = client(sdk, lambda r: httpx2.Response(200, content=b"existing"))
        await c.resume(module().WmaSessionRef(runtime_id="runtime-1", session_id="session-1"))
        assert await c.download("/workspace/result/report.md", max_bytes=8) == b"existing"
        await c.aclose()

    asyncio.run(scenario())
    assert sdk.created == []
    assert sdk.retrieved == ["runtime-1"]
    assert sdk.runtime.sessions.resumed == ["session-1"]
    assert sdk.session.prompts == []


@pytest.mark.parametrize("status", [302, 404, 500])
def test_download_failure_does_not_restart_investigation_or_follow_redirect(status: int) -> None:
    sdk = SdkBoundary()
    requests: list[httpx2.Request] = []

    def transfer(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(status, headers={"location": "https://other.example/secret"})

    async def scenario() -> None:
        c = client(sdk, transfer)
        await c.create("task-1")
        with pytest.raises(module().DirectWmaError):
            await c.download("/workspace/task/a.bin", max_bytes=64)
        await c.aclose()

    asyncio.run(scenario())
    assert len(requests) == 1
    assert sdk.session.prompts == []


def test_streamed_oversize_download_stops_reading_and_closes_response() -> None:
    sdk = SdkBoundary()
    stream = ChunkStream([b"1234", b"5678", b"must-not-be-read"])

    async def scenario() -> None:
        c = client(sdk, lambda r: httpx2.Response(200, stream=stream))
        await c.create("task-1")
        with pytest.raises(module().DirectWmaError, match="WMA_ARTIFACT_TOO_LARGE"):
            await c.download("/workspace/task/a.bin", max_bytes=6)
        await c.aclose()

    asyncio.run(scenario())
    assert stream.reads == 2
    assert stream.closed


def test_compressed_response_is_rejected_before_decoding_or_reading_body() -> None:
    sdk = SdkBoundary()
    stream = ChunkStream([b"must-not-be-decompressed"])

    def transfer(request: httpx2.Request) -> httpx2.Response:
        assert request.headers["accept-encoding"] == "identity"
        return httpx2.Response(200, headers={"content-encoding": "gzip"}, stream=stream)

    async def scenario() -> None:
        c = client(sdk, transfer)
        await c.create("task-1")
        with pytest.raises(module().DirectWmaError, match="WMA_UNSUPPORTED_CONTENT_ENCODING"):
            await c.download("/workspace/task/a.bin", max_bytes=6)
        await c.aclose()

    asyncio.run(scenario())
    assert stream.reads == 0
    assert stream.closed


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "/workspace/../etc/passwd",
        "/workspace/a/../b",
        "/workspace//a",
        "/workspace/a\\b",
        "/workspace/a%2fb",
        "https://sandbox.example/file",
        "/workspace/",
    ],
)
def test_remote_path_rejected_before_transfer(path: str) -> None:
    sdk = SdkBoundary()
    requests: list[httpx2.Request] = []

    def transfer(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200)

    async def scenario() -> None:
        c = client(sdk, transfer)
        await c.create("task-1")
        for operation in (c.download(path, max_bytes=64), c.upload(path, b"x")):
            with pytest.raises(module().DirectWmaError, match="WMA_INVALID_REMOTE_PATH"):
                await operation
        await c.aclose()

    asyncio.run(scenario())
    assert requests == []


def test_prompt_uses_deadline_and_returns_only_stop_reason() -> None:
    sdk = SdkBoundary()

    async def scenario() -> None:
        c = client(sdk, lambda r: httpx2.Response(200))
        await c.create("task-1")
        assert await c.prompt("approved investigation", timeout_seconds=0.1) == "end_turn"
        await c.aclose()

    asyncio.run(scenario())
    assert len(sdk.session.prompts) == 1
    options = sdk.session.prompts[0][1]
    assert 0 < options.timeout_ms <= 100
    assert getattr(options, "on_chunk", None) is None


def test_prompt_timeout_never_retries() -> None:
    sdk = SdkBoundary()
    sdk.session.delay = 1

    async def scenario() -> None:
        c = client(sdk, lambda r: httpx2.Response(200))
        await c.create("task-1")
        with pytest.raises(module().DirectWmaError, match="WMA_TIMEOUT"):
            await c.prompt("approved investigation", timeout_seconds=0.01)
        await c.aclose()

    asyncio.run(scenario())
    assert len(sdk.session.prompts) == 1


def test_secret_bearing_sdk_error_and_binding_repr_are_redacted() -> None:
    sdk = SdkBoundary()
    sdk.session.failure = RuntimeError("private-api-key private-data-token thought body")

    async def scenario() -> None:
        c = client(sdk, lambda r: httpx2.Response(200))
        await c.create("task-1")
        with pytest.raises(module().DirectWmaError) as caught:
            await c.prompt("approved investigation", timeout_seconds=0.1)
        rendered = "".join(traceback.format_exception(caught.value))
        assert "private-api-key" not in rendered
        assert "private-data-token" not in rendered
        assert "thought body" not in rendered
        assert "private-api-key" not in repr(c)
        await c.aclose()

    asyncio.run(scenario())
    binding = module().WmaBinding(SecretStr("private-api-key"), "agent-1", "cloud-agent", "1.0")
    assert "private-api-key" not in repr(binding)
    assert "private-data-token" not in json.dumps(asdict(module().WmaSessionRef("r1", "s1")))


def test_missing_sdk_is_an_explicit_error(monkeypatch: pytest.MonkeyPatch) -> None:
    m = module()

    def missing(name: str) -> Any:
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(m.importlib, "import_module", missing)
    with pytest.raises(m.DirectWmaError, match="WMA_SDK_UNAVAILABLE"):
        m.DirectWmaClient(m.WmaBinding(SecretStr("private"), "agent-1", "cloud-agent", "1.0"))


def test_sdk_retries_are_disabled_for_runtime_creation() -> None:
    sdk = SdkBoundary()

    async def scenario() -> None:
        c = client(sdk, lambda r: httpx2.Response(200))
        await c.create("task-1")
        assert sdk.client_options["retry"] is False
        assert 0 < sdk.created[0].timeout_ms <= 200
        await c.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://sandbox.example",
        "https://user:password@x.test",
        "https://sandbox.example/?token=bad",
    ],
)
def test_invalid_sdk_data_plane_link_cannot_receive_token(endpoint: str) -> None:
    sdk = SdkBoundary()
    sdk.runtime.runtime_info.links.sandbox_link.data_plane_endpoint = endpoint

    async def scenario() -> None:
        c = client(sdk, lambda r: pytest.fail("invalid endpoint must not be contacted"))
        await c.create("task-1")
        with pytest.raises(module().DirectWmaError, match="WMA_DATA_PLANE_UNAVAILABLE"):
            await c.download("/workspace/task/a.bin", max_bytes=1)
        await c.aclose()

    asyncio.run(scenario())


def test_transport_error_does_not_include_token_or_url_credentials() -> None:
    sdk = SdkBoundary()

    def transfer(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("private-data-token private-api-key", request=request)

    async def scenario() -> None:
        c = client(sdk, transfer)
        await c.create("task-1")
        with pytest.raises(module().DirectWmaError) as caught:
            await c.download("/workspace/task/a.bin", max_bytes=1)
        assert "private-" not in "".join(traceback.format_exception(caught.value))
        await c.aclose()

    asyncio.run(scenario())


def test_real_sdk_resume_surface_uses_only_metadata_gets() -> None:
    sdk = pytest.importorskip("cloud_agent_sdk")
    httpx = pytest.importorskip("httpx")
    observed: list[str] = []

    def control(request: Any) -> Any:
        observed.append(request.method + " " + request.url.path)
        data: dict[str, Any]
        if request.url.path.endswith("/sessions/session-1"):
            data = {
                "runtimeId": "runtime-1",
                "sessionId": "session-1",
                "sessionStatus": "IDLE",
                "createdAt": "2026-09-07T00:00:00Z",
                "updatedAt": "2026-09-07T00:00:00Z",
            }
        else:
            data = {
                "id": "runtime-1",
                "runtimeName": "task-1",
                "status": "RUNNING",
                "createdAt": "2026-09-07T00:00:00Z",
                "updatedAt": "2026-09-07T00:00:00Z",
                "links": {
                    "sandboxLink": {
                        "dataPlaneEndpoint": "https://sandbox.example",
                        "endpoint": "https://sandbox.example",
                        "sandboxId": "sandbox-1",
                    },
                    "acpLink": {
                        "url": "https://sandbox.example/acp",
                        "token": "private-data-token",
                        "tokenExpiresAt": 2000000000,
                    },
                },
            }
        return httpx.Response(200, json={"code": 0, "data": data})

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(control)) as http:
            factory = SimpleNamespace(
                CloudAgentClient=lambda **kw: sdk.CloudAgentClient(http_client=http, **kw),
                PromptOptions=sdk.PromptOptions,
                RuntimeCreateOptions=sdk.RuntimeCreateOptions,
                ManifestBuilder=sdk.ManifestBuilder,
            )
            c = module().DirectWmaClient(
                module().WmaBinding(SecretStr("private-api-key"), "agent-1", "cloud-agent", "1.0"),
                sdk=factory,
                transport=httpx2.MockTransport(lambda r: httpx2.Response(200, content=b"original")),
            )
            await c.resume(module().WmaSessionRef("runtime-1", "session-1"))
            assert await c.download("/workspace/a.bin", max_bytes=8) == b"original"
            await c.aclose()

    asyncio.run(scenario())
    assert observed == [
        "GET /v2/agentos/runtimes/runtime-1",
        "GET /v2/agentos/runtimes/runtime-1/sessions/session-1",
    ]
