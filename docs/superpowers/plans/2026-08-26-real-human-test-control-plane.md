# DeepAha Real Human Test Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不自动访问外部网络、不削弱 P9-B 与人工责任边界的前提下，把现有 Windows 本地人工测试启动器扩展为可采集官方资料、调用真实 LLM、逐条人工审核并发布到本地产品页面的可恢复控制台。

**Architecture:** 复用现有 Source Registry、Acquisition、Document、P9-B Gateway、Fact Lifecycle 和 Rule Promotion，以数据库状态机串起完整信任链；本地 Windows 壳层只负责 DPAPI 密钥、loopback API、worker 与持久化生命周期。真实 Provider 与官方站点只在 reviewer 从页面显式创建 live run 后访问，自动测试全部使用现有 replay、fixture 或本地 HTTP stub。

**Tech Stack:** Python 3.14、FastAPI、SQLAlchemy 2、PostgreSQL 18、Alembic、httpx2、Windows DPAPI、Next.js 16、React 19、TypeScript 5.9、Vitest、Playwright、PowerShell、Docker Compose。

**Spec:** `docs/superpowers/specs/2026-08-26-real-human-test-control-plane-design.md`

## Global Constraints

- 不修改已验收的 Migration `0023`–`0029`；所有数据库变化只进入后继 Migration `0030`。
- 双击启动只启动 loopback 本地服务与 `/review/human-test`，不得自动访问官方站点或 Provider。
- live run 默认最多 9 次官方 HTTP 请求、8 次串行 LLM 调用；单次最多 12,000 input tokens、3,000 output tokens、90 秒 timeout、temperature `0`。
- API Key 只以 Windows DPAPI `CurrentUser` 密文保存在 `%LOCALAPPDATA%\DeepAha\manual-test\`；不得进入仓库、数据库、命令行、环境快照、Ledger、日志、异常正文或浏览器响应。
- 自动测试不得访问真实 Provider；真实调用只能由页面显式触发，且必须经过 P9-B Gateway。
- 数据标签固定为 `LIVE_OFFICIAL`、`OFFICIAL_REPLAY`、`SYNTHETIC_FIXTURE` 和 `LOCAL_HUMAN_REVIEWED`；本地人工结果不得标记为 `REAL_GOLD`。
- LLM 只产生候选；事实、规则和发布分别需要人类 reviewer 的明确决定，LLM 不得决定 `INELIGIBLE`。
- 停止保留 PostgreSQL、对象与 Provider 配置；只有带一次性 challenge 的独立清理操作能删除本控制台自有数据。
- 不读取或提交 `文档2/LLM-API.txt`；实现只操作后台表单提供的配置。
- 不触碰 `.workbuddy/`、`文档/`、`文档2/`、`设计/` 及其现有用户改动；不推送、不部署、不启动 Release Qualification。

## File Structure

- `backend/src/deepaha/local_human_test/contracts.py`：控制台枚举、不可变命令、预算、Provider 配置与 API DTO。
- `backend/src/deepaha/local_human_test/models.py`：run、item、review decision 三张编排表。
- `backend/src/deepaha/local_human_test/provider_config.py`：DPAPI、ACL、原子配置文件与脱敏状态。
- `backend/src/deepaha/artifacts/local_file.py`：满足现有 `ObjectStore` Protocol 的持久本地对象仓库。
- `backend/src/deepaha/p9b/openai_compatible.py`：唯一真实 Provider adapter，发送同一个 `ProviderInvocation`。
- `backend/src/deepaha/local_human_test/runs.py`：创建、租约、取消、恢复和预算状态机。
- `backend/src/deepaha/local_human_test/bootstrap.py`：Registry/Recipe 导入、采集、Document 与 provisional Opportunity。
- `backend/src/deepaha/local_human_test/extraction.py`：SourceBundle、Gateway、结构化输出与 ExtractionCandidate。
- `backend/src/deepaha/local_human_test/review.py`：人工事实/规则决定与 promotion。
- `backend/src/deepaha/local_human_test/publication.py`：VerifiedFactSet 到 OpportunityVersion/PublicCatalogEntry 的幂等发布。
- `backend/src/deepaha/local_human_test/worker.py`：单 worker DB lease 执行入口。
- `backend/src/deepaha/api/local_human_test.py`：development + loopback + reviewer 权限控制的后台 API。
- `web/lib/local-human-test.ts`、`web/app/review/human-test/**`：server-side API client、actions 与控制台页面。
- `scripts/local-manual-test.ps1`、`infra/compose.local-manual.yaml`：持久化数据库、worker、一键启动/停止和精确清理。

---

### Task 1: Migration 0030 与控制台领域契约

**Files:**
- Create: `backend/migrations/versions/20260826_0030_local_human_test_control_plane.py`
- Create: `backend/src/deepaha/local_human_test/__init__.py`
- Create: `backend/src/deepaha/local_human_test/contracts.py`
- Create: `backend/src/deepaha/local_human_test/models.py`
- Modify: `backend/src/deepaha/db/models.py`
- Modify: `backend/src/deepaha/review/auth.py`
- Modify: `backend/src/deepaha/review/models.py`
- Modify: `backend/src/deepaha/public_catalog/models.py`
- Test: `backend/tests/integration/test_local_human_test_migration.py`
- Test: `backend/tests/local_human_test/test_contracts.py`
- Test: `backend/tests/review/test_auth.py`

**Interfaces:**
- Produces: `RunMode`, `RunStatus`, `ItemStatus`, `ReviewDecisionKind`, `ExternalCallBudget`, `ProviderConfigSnapshot`, `CreateRunCommand`.
- Produces: `LocalHumanTestRun`, `LocalHumanTestItem`, `LocalHumanTestReviewDecision` SQLAlchemy models.
- Produces: `ReviewerRole.LOCAL_TEST_OPERATOR` and purpose constant `OPPORTUNITY_FACT_VALIDATION`.

- [ ] **Step 1: Write migration and contract failure tests**

```python
def test_0030_adds_local_control_tables_and_extends_closed_values(connection):
    upgrade_to(connection, "20260826_0030")
    assert table_names(connection) >= {
        "local_human_test_runs",
        "local_human_test_items",
        "local_human_test_review_decisions",
    }
    assert insert_local_reviewed_catalog_entry(connection).scalar_one() == "LOCAL_HUMAN_REVIEWED"


def test_external_call_budget_rejects_values_above_hard_limits():
    with pytest.raises(ValidationError):
        ExternalCallBudget(official_request_limit=10, llm_call_limit=8)
    with pytest.raises(ValidationError):
        ExternalCallBudget(official_request_limit=9, llm_call_limit=9)
```

- [ ] **Step 2: Run the new tests and observe the missing migration/types**

Run: `cd backend; uv run pytest -m integration tests/integration/test_local_human_test_migration.py -q`

Run: `cd backend; uv run pytest tests/local_human_test/test_contracts.py tests/review/test_auth.py -q`

Expected: FAIL because revision `0030`, local models and reviewer values do not exist.

- [ ] **Step 3: Add immutable contracts and constrained models**

```python
class RunMode(StrEnum):
    LIVE_OFFICIAL = "LIVE_OFFICIAL"
    OFFICIAL_REPLAY = "OFFICIAL_REPLAY"


class ExternalCallBudget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    official_request_limit: int = Field(default=9, ge=1, le=9)
    llm_call_limit: int = Field(default=8, ge=1, le=8)
    max_input_tokens: int = Field(default=12_000, ge=1, le=12_000)
    max_output_tokens: int = Field(default=3_000, ge=1, le=3_000)
    timeout_seconds: int = Field(default=90, ge=1, le=90)
    temperature: Literal[0] = 0


class CreateRunCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    mode: RunMode
    recipe_ids: tuple[str, ...]
    provider: ProviderConfigSnapshot
    budget: ExternalCallBudget
    reviewer_id: UUID
```

The run table must include UUIDv7 `run_id`, immutable JSONB `recipe_ids`, `provider_config_snapshot`, `budget`, counters, status, creator, timestamps, lease owner/expiry and terminal error code. The item table must include the stage references named by the spec and `UNIQUE(run_id, recipe_id)`. The decision table must include `idempotency_key`, `request_hash`, reason and `UNIQUE(item_id, decision_kind, idempotency_key)`.

- [ ] **Step 4: Implement Migration 0030 without rewriting history**

Use PostgreSQL check constraints for every enum, non-negative counters, UUIDv7 IDs, timestamp ordering and JSON object/array shapes. Drop and recreate only the affected named constraints for reviewer roles/purposes and public catalog collection kind. Downgrade must remove the three new tables and restore the exact pre-0030 constraints.

- [ ] **Step 5: Run migration round-trip and model tests**

Run: `cd backend; uv run pytest -m integration tests/integration/test_local_human_test_migration.py -q`

Run: `cd backend; uv run pytest tests/local_human_test/test_contracts.py tests/review/test_auth.py -q`

Expected: PASS; `alembic upgrade head`, downgrade to `0029`, and re-upgrade all succeed.

- [ ] **Step 6: Commit the bounded schema slice**

```powershell
git add backend/migrations/versions/20260826_0030_local_human_test_control_plane.py backend/src/deepaha/local_human_test backend/src/deepaha/db/models.py backend/src/deepaha/review/auth.py backend/src/deepaha/review/models.py backend/src/deepaha/public_catalog/models.py backend/tests/integration/test_local_human_test_migration.py backend/tests/local_human_test/test_contracts.py backend/tests/review/test_auth.py
git commit -m "feat: add local human test control schema"
```

### Task 2: DPAPI Provider 配置保管

**Files:**
- Create: `backend/src/deepaha/local_human_test/provider_config.py`
- Test: `backend/tests/local_human_test/test_provider_config.py`
- Test: `backend/tests/local_human_test/test_provider_config_windows.py`

**Interfaces:**
- Produces: `SecretProtector.protect(secret: bytes) -> bytes` and `unprotect(ciphertext: bytes) -> bytes`.
- Produces: `DirectoryHardener.harden(path: Path) -> None`.
- Produces: `LocalProviderConfigStore.save(command: SaveProviderConfig) -> ProviderConfigStatus`, `status()`, `load_for_invocation()`, `delete_secret()`.
- `load_for_invocation()` returns `ResolvedProviderConfig` containing `SecretStr`; no DTO exposes its value.

- [ ] **Step 1: Write failing secret-boundary tests**

```python
def test_store_round_trips_through_protector_without_plaintext_on_disk(tmp_path):
    store = make_store(tmp_path, protector=ReversibleTestProtector())
    store.save(valid_save_command(api_key=SecretStr("top-secret")))
    assert b"top-secret" not in (tmp_path / "provider.json").read_bytes()
    assert store.load_for_invocation().api_key.get_secret_value() == "top-secret"
    assert store.status().model_dump() == {
        "configured": True,
        "provider": "deepseek",
        "base_url": "https://example.invalid",
        "protocol": "openai_chat_completions",
        "model_id": "deepseek-v4-flash",
        "model_snapshot": "deepseek-v4-flash@configured",
        "updated_at": FIXED_TIME,
    }


def test_store_rejects_url_query_fragment_userinfo_and_non_https(tmp_path):
    for url in (
        "http://example.invalid",
        "https://u:p@example.invalid",
        "https://example.invalid?key=value",
        "https://example.invalid/#fragment",
    ):
        with pytest.raises(ProviderConfigError):
            make_store(tmp_path).save(valid_save_command(base_url=url))
```

Also assert atomic replacement, delete fail-closed, permission hardener failure leaves no new configuration, `repr`/exception/log capture contains no secret, and the public status has no key/tail/hash field.

- [ ] **Step 2: Run tests and observe missing store**

Run: `cd backend; uv run pytest tests/local_human_test/test_provider_config.py -q`

Expected: FAIL because the store and abstractions do not exist.

- [ ] **Step 3: Implement the store with dependency-injected crypto and ACL**

```python
class LocalProviderConfigStore:
    def __init__(self, root: Path, protector: SecretProtector, hardener: DirectoryHardener): ...

    def save(self, command: SaveProviderConfig) -> ProviderConfigStatus:
        self._hardener.harden(self._root)
        protected = self._protector.protect(command.api_key.get_secret_value().encode("utf-8"))
        payload = command.public_payload() | {"protected_api_key": b64encode(protected).decode()}
        self._atomic_write_json(payload)
        return self.status()
```

`WindowsDpapiProtector` must call `CryptProtectData`/`CryptUnprotectData` through `ctypes`, use `CRYPTPROTECT_UI_FORBIDDEN`, zero mutable plaintext buffers after use, and raise `ProviderConfigError` without including Windows error buffers that may contain inputs. `WindowsDirectoryHardener` must set inheritance off and grant only the current user plus `SYSTEM`; tests inject a fake hardener rather than modifying real ACLs.

- [ ] **Step 4: Run unit and real-Windows DPAPI tests**

Run: `cd backend; uv run pytest tests/local_human_test/test_provider_config.py -q`

Run on Windows: `cd backend; uv run pytest tests/local_human_test/test_provider_config_windows.py -q`

Expected: PASS; Windows test creates only a pytest temp directory and deletes it through pytest cleanup.

- [ ] **Step 5: Commit the credential boundary**

```powershell
git add backend/src/deepaha/local_human_test/provider_config.py backend/tests/local_human_test/test_provider_config.py backend/tests/local_human_test/test_provider_config_windows.py
git commit -m "feat: protect local provider configuration"
```

### Task 3: Persistent LocalFileObjectStore

**Files:**
- Create: `backend/src/deepaha/artifacts/local_file.py`
- Test: `backend/tests/artifacts/test_local_file_store.py`

**Interfaces:**
- Consumes: existing `ObjectMetadata`, `ObjectIntegrityError`, `ObjectStore`.
- Produces: `LocalFileObjectStore(root: Path, bucket: str)` implementing the existing protocol.

- [ ] **Step 1: Write failing integrity and path tests**

```python
def test_local_store_persists_and_verifies_bytes_across_instances(tmp_path):
    first = LocalFileObjectStore(tmp_path, "deepaha-raw")
    metadata = first.put_bytes_if_absent(
        key="live/2026/item.json", content=b"official", media_type="application/json",
        sha256=sha256(b"official").hexdigest(),
    )
    second = LocalFileObjectStore(tmp_path, "deepaha-raw")
    assert second.get_bytes(key=metadata.key) == b"official"
    assert second.stat(key=metadata.key).sha256 == metadata.sha256


@pytest.mark.parametrize("key", ["../secret", "/absolute", "C:/absolute", "a/../../b", "a\\..\\b"])
def test_local_store_rejects_non_canonical_keys(tmp_path, key):
    with pytest.raises(ValueError):
        LocalFileObjectStore(tmp_path, "deepaha-raw").stat(key=key)
```

Add tests for caller hash mismatch, same-key/same-bytes idempotency, same-key/different-bytes conflict, metadata corruption, concurrent exclusive create and no partial file after simulated replace failure.

- [ ] **Step 2: Run tests and observe missing implementation**

Run: `cd backend; uv run pytest tests/artifacts/test_local_file_store.py -q`

Expected: FAIL on import.

- [ ] **Step 3: Implement canonical path resolution and exclusive writes**

Store bytes at `<root>/<bucket>/<key>` and metadata at the adjacent `<name>.metadata.json`. Resolve every target and require it to remain below the resolved bucket root. Write bytes and metadata with create-exclusive mode, `flush` plus `os.fsync`, and publish by atomic rename. When the object exists, re-read bytes and metadata and return only if size and SHA-256 match exactly.

- [ ] **Step 4: Run object-store tests**

Run: `cd backend; uv run pytest tests/artifacts/test_local_file_store.py -q`

Expected: PASS, including concurrent conflict and restart persistence.

- [ ] **Step 5: Commit the persistent object store**

```powershell
git add backend/src/deepaha/artifacts/local_file.py backend/tests/artifacts/test_local_file_store.py
git commit -m "feat: add persistent local object store"
```

### Task 4: OpenAI-compatible Provider Adapter

**Files:**
- Create: `backend/src/deepaha/p9b/openai_compatible.py`
- Test: `backend/tests/p9b/test_openai_compatible_adapter.py`
- Test: `backend/tests/integration/test_local_provider_gateway.py`

**Interfaces:**
- Consumes: exact frozen `ProviderInvocation`, `ProviderAttemptResult`, `ProviderOutcomeUnknownError`, `ObjectStore`, `ResolvedProviderConfig`.
- Produces: `OpenAICompatibleProviderAdapter(config, object_store, transport)` with `provider`, `supports_idempotency=True`, `invoke(request)`.
- Produces: `ProviderTransport.send(*, url, headers, json_body, timeout_seconds) -> TransportResponse` so tests use an in-process stub.

- [ ] **Step 1: Write failing payload and error mapping tests**

```python
def test_adapter_sends_exact_gateway_invocation_and_stores_raw_response(store):
    invocation = provider_invocation(
        provider="deepseek",
        model_id="deepseek-v4-flash",
        messages=(ProviderMessage(role="user", content="Return JSON."),),
        max_output_tokens=3000,
        temperature=0,
        top_p=1,
        seed=7,
    )
    transport = RecordingTransport(success_response())
    result = make_adapter(store, transport).invoke(invocation)
    assert transport.single_json_body == {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": "Return JSON."}],
        "max_tokens": 3000,
        "temperature": 0,
        "top_p": 1,
        "seed": 7,
        "response_format": {"type": "json_object"},
    }
    assert result.raw_response_sha256 == store.stat(key=result.raw_response_object_key).sha256
```

Assert Authorization is `Bearer <secret>` inside the transport call but absent from captured logs/errors/results. Cover 400/401/403 as non-retryable, 408/429/5xx as retryable when a response is observed, connect failure before bytes are sent as retryable, and disconnect/timeout after send as `ProviderOutcomeUnknownError`.

- [ ] **Step 2: Run adapter tests and observe missing class**

Run: `cd backend; uv run pytest tests/p9b/test_openai_compatible_adapter.py -q`

Expected: FAIL on import.

- [ ] **Step 3: Implement one serialization boundary**

```python
def invocation_payload(request: ProviderInvocation) -> dict[str, object]:
    return {
        "model": request.model_id,
        "messages": [{"role": item.role, "content": item.content} for item in request.messages],
        "max_tokens": request.max_output_tokens,
        "temperature": request.temperature,
        "top_p": request.top_p,
        "seed": request.seed,
        "response_format": {"type": "json_object"},
    }
```

The adapter must reject provider/model mismatch before transport, join a validated base URL with the fixed configured path `/chat/completions`, send only this payload, store exact raw response bytes under `provider-responses/<model_call_id>/<attempt_id>.json`, and compute every result hash from stored bytes/parsed content. Provider-reported usage is authoritative; absent cost becomes `COST_NOT_REPORTED` with `monetary_cost=None`.

- [ ] **Step 4: Prove Gateway identity and adapter payload remain one request**

Run: `cd backend; uv run pytest -m integration tests/integration/test_local_provider_gateway.py tests/integration/test_p9b_gateway_execution.py -q`

Expected: PASS; the local transport records one send, mismatched Egress identity sends zero, duplicate identity preserves P9-B idempotency, and unknown outcome is not resent.

- [ ] **Step 5: Commit the real adapter without making a real call**

```powershell
git add backend/src/deepaha/p9b/openai_compatible.py backend/tests/p9b/test_openai_compatible_adapter.py backend/tests/integration/test_local_provider_gateway.py
git commit -m "feat: add audited OpenAI compatible adapter"
```

### Task 5: Run state machine, budget and DB lease worker

**Files:**
- Create: `backend/src/deepaha/local_human_test/runs.py`
- Create: `backend/src/deepaha/local_human_test/worker.py`
- Test: `backend/tests/local_human_test/test_runs.py`
- Test: `backend/tests/integration/test_local_human_test_runs.py`

**Interfaces:**
- Produces: `HumanTestRunService.create(command, idempotency_key)`, `request_cancel(run_id)`, `claim_next(worker_id, now)`, `renew_lease(...)`, `record_official_request(...)`, `record_llm_call(...)`, `transition_item(...)`, `complete_run(...)`.
- Produces: `HumanTestWorker.run_once() -> bool`; `True` means an item was claimed.
- Consumes later: `HumanTestItemProcessor.process(item_id)` protocol injected into worker.

- [ ] **Step 1: Write failing state and lease tests**

```python
def test_create_run_freezes_recipe_provider_and_budget_snapshots(session):
    run = service(session).create(create_run_command(), idempotency_key="run-1")
    assert run.status == "CREATED"
    assert tuple(run.recipe_ids) == ACTIVE_RECIPE_IDS
    assert "api_key" not in json.dumps(run.provider_config_snapshot)


def test_two_workers_cannot_claim_same_item(session_factory):
    item_id = seed_created_item(session_factory)
    first = service(session_factory).claim_next("worker-a", FIXED_TIME)
    second = service(session_factory).claim_next("worker-b", FIXED_TIME)
    assert first.item_id == item_id
    assert second is None
```

Cover all allowed transitions, forbidden skips, cancellation between stages, expired lease recovery, unknown-outcome manual hold, exactly 9 official request reservations, exactly 8 LLM call reservations, no counter increment after exhaustion and create idempotency conflict for same key/different request hash.

- [ ] **Step 2: Run tests and observe missing services**

Run: `cd backend; uv run pytest tests/local_human_test/test_runs.py -q`

Run: `cd backend; uv run pytest -m integration tests/integration/test_local_human_test_runs.py -q`

Expected: FAIL because state and lease methods do not exist.

- [ ] **Step 3: Implement compare-and-set transitions and `FOR UPDATE SKIP LOCKED` claims**

Every mutation must load the row under lock, check the exact prior state, update `updated_at`, and commit in one transaction. Budget reservation must happen before the side effect and remain consumed after an observed or unknown call. Worker leases use 60 seconds, renew before each external operation, and never process more than one item concurrently.

- [ ] **Step 4: Add a module entry point with no implicit external work**

```python
def main() -> int:
    settings = get_settings()
    require_local_human_test_environment(settings)
    worker = build_worker(settings)
    return worker.run_forever(poll_seconds=1.0)
```

Importing the module and starting the API must not claim a run. Only the separately launched worker loop processes already-created run rows.

- [ ] **Step 5: Run state, integration and restart tests**

Run: `cd backend; uv run pytest tests/local_human_test/test_runs.py -q`

Run: `cd backend; uv run pytest -m integration tests/integration/test_local_human_test_runs.py -q`

Expected: PASS; lease recovery continues from persisted stage references without duplicate calls.

- [ ] **Step 6: Commit the orchestration kernel**

```powershell
git add backend/src/deepaha/local_human_test/runs.py backend/src/deepaha/local_human_test/worker.py backend/tests/local_human_test/test_runs.py backend/tests/integration/test_local_human_test_runs.py
git commit -m "feat: add recoverable human test runs"
```

### Task 6: Governed acquisition and provisional Opportunity bootstrap

**Files:**
- Create: `backend/src/deepaha/local_human_test/bootstrap.py`
- Modify: `config/acquisition/recipes.v1.json`
- Test: `backend/tests/local_human_test/test_bootstrap.py`
- Test: `backend/tests/integration/test_local_human_test_acquisition.py`

**Interfaces:**
- Produces: `ActiveRecipeView` with recipe ID, source ID, official host, role, updated time, request cap and `opportunity_type_hint`.
- Produces: `HumanTestAcquisitionService.list_active_recipes()`, `acquire(item_id, mode) -> AcquiredDocument`.
- Produces: `ProvisionalOpportunityService.create(document_id, recipe_id) -> ProvisionalTarget | BootstrapReviewRequired`.
- Consumes: existing Source Registry importer, Recipe loader, acquisition orchestrator, Document service and LocalFileObjectStore.

- [ ] **Step 1: Add governed type hints and failing bootstrap tests**

Each of the 8 active Recipes gets one existing Opportunity type value in `opportunity_type_hint`; inactive recipes may omit it. Add schema/parser tests that reject an unknown type and prove active recipes expose the hint.

```python
def test_bootstrap_uses_only_deterministic_governed_fields(session):
    target = service(session).create(document_id=DOCUMENT_ID, recipe_id="gov-policy")
    assert target.opportunity.publication_status == "INTERNAL"
    assert target.opportunity.status == "UNKNOWN"
    assert target.opportunity.type == "YOUTH_POLICY_BENEFIT"
    assert target.opportunity.issuer_name == REGISTRY_ISSUER
    assert target.canonical_url == FINAL_OBSERVED_URL
```

Assert missing parser title, final stable URL, registry issuer or governed hint returns `BootstrapReviewRequired` and leaves `model_call_id` null.

- [ ] **Step 2: Run replay-only tests and observe missing orchestration**

Run: `cd backend; uv run pytest tests/acquisition/test_recipes.py tests/local_human_test/test_bootstrap.py -q`

Run: `cd backend; uv run pytest -m integration tests/integration/test_local_human_test_acquisition.py -q`

Expected: FAIL before implementation; tests never use network.

- [ ] **Step 3: Implement live/replay acquisition behind the same validation gate**

`OFFICIAL_REPLAY` must load the existing real-source corpus and label artifacts `OFFICIAL_REPLAY`. `LIVE_OFFICIAL` must call only the selected active Recipe endpoints, honor robots/access/size/type/redirect checks already implemented by Acquisition, reserve budget before every request and label artifacts `LIVE_OFFICIAL`. Challenge/login/403/type mismatch must persist validation and transition the item without creating an Opportunity or calling LLM.

- [ ] **Step 4: Implement provisional target without expanding P9-B scope**

Create version 1 through existing opportunity versioning services, with `review_status=PENDING` and explicit provenance identifying the deterministic bootstrap fields. Never set `READY`/`PUBLISHED`; never create a PublicCatalogEntry in this task.

- [ ] **Step 5: Run acquisition/bootstrap tests**

Run: `cd backend; uv run pytest tests/acquisition/test_recipes.py tests/local_human_test/test_bootstrap.py -q`

Run: `cd backend; uv run pytest -m integration tests/integration/test_local_human_test_acquisition.py tests/integration/test_real_acquisition_replay.py -q`

Expected: PASS; replay produces a Document and provisional INTERNAL Opportunity, validation failures produce adapter calls `0`.

- [ ] **Step 6: Commit the governed bootstrap slice**

```powershell
git add config/acquisition/recipes.v1.json backend/src/deepaha/local_human_test/bootstrap.py backend/tests/acquisition/test_recipes.py backend/tests/local_human_test/test_bootstrap.py backend/tests/integration/test_local_human_test_acquisition.py
git commit -m "feat: bootstrap governed acquisition targets"
```

### Task 7: P9-B extraction coordinator and strict structured candidates

**Files:**
- Create: `backend/src/deepaha/local_human_test/extraction.py`
- Test: `backend/tests/local_human_test/test_extraction.py`
- Test: `backend/tests/integration/test_local_human_test_extraction.py`

**Interfaces:**
- Produces: `P9BExtractionCoordinator.extract(item_id) -> ExtractionOutcome`.
- Produces: frozen `ModelExtractionEnvelope` with `facts: tuple[ModelFactCandidate, ...]`, `rules: tuple[ModelRuleCandidate, ...]`, `uncertainties: tuple[str, ...]`.
- Consumes: `BundleService`, P9-B policy/model contract builders, `GatewayExecutor`, `FactLifecycleService`, LocalFileObjectStore and run budget reservation.

- [ ] **Step 1: Write failing evidence and schema tests**

```python
def test_every_candidate_is_bound_to_an_exact_gateway_input_block(session):
    outcome = coordinator(session, response=valid_model_response()).extract(ITEM_ID)
    run_block_ids = set(load_extraction_run_block_ids(session, outcome.extraction_run_id))
    assert outcome.candidate_ids
    for candidate_id in outcome.candidate_ids:
        assert set(load_candidate_block_ids(session, candidate_id)) <= run_block_ids


def test_invalid_json_or_unknown_block_creates_no_candidate(session):
    outcome = coordinator(session, response=response_with_unknown_block()).extract(ITEM_ID)
    assert outcome.status == "EVIDENCE_BINDING_INVALID"
    assert count_candidates(session, ITEM_ID) == 0
```

Cover frozen SourceBundle, exact document membership, minimized block ordering, system prompt requiring JSON, max input budget, Gateway intent/hash consistency, raw response persistence, invalid schema, abstention, duplicate candidate identity and Provider unknown outcome.

- [ ] **Step 2: Run tests and observe missing coordinator**

Run: `cd backend; uv run pytest tests/local_human_test/test_extraction.py -q`

Run: `cd backend; uv run pytest -m integration tests/integration/test_local_human_test_extraction.py -q`

Expected: FAIL before implementation.

- [ ] **Step 3: Build one immutable prompt payload and route it through GatewayExecutor**

The system message must state that output is JSON, quote the exact schema version, prohibit unsupported facts, require evidence block IDs and allow abstention. The user message is a canonical JSON object containing only the frozen target identity and ordered minimized blocks. Build one tuple of `ProviderMessage`; use it to calculate the existing Gateway identity and pass it unchanged to `GatewayExecutor.execute`.

- [ ] **Step 4: Validate raw output before persisting any candidate**

Parse the stored raw Provider bytes, validate the complete envelope with Pydantic `extra="forbid"`, verify all evidence block IDs against `ExtractionRunInputBlock`, verify field names against the controlled allow-list, and only then persist the extraction run plus all candidates in one transaction. A malformed envelope leaves the raw response and ModelCall Ledger intact but produces zero candidates.

- [ ] **Step 5: Run extraction and P9-B regression tests**

Run: `cd backend; uv run pytest tests/local_human_test/test_extraction.py tests/p9b/test_gateway_state.py tests/p9b/test_fact_lifecycle.py -q`

Run: `cd backend; uv run pytest -m integration tests/integration/test_local_human_test_extraction.py tests/integration/test_p9b_gateway_execution.py tests/integration/test_p9b_fact_persistence.py -q`

Expected: PASS; `rg -n "\.invoke\(" backend/src/deepaha --glob "*.py"` shows the existing Gateway provider invocation as the only core call site.

- [ ] **Step 6: Commit the extraction slice**

```powershell
git add backend/src/deepaha/local_human_test/extraction.py backend/tests/local_human_test/test_extraction.py backend/tests/integration/test_local_human_test_extraction.py
git commit -m "feat: coordinate audited human test extraction"
```

### Task 8: Human fact/rule review and local publication

**Files:**
- Create: `backend/src/deepaha/local_human_test/review.py`
- Create: `backend/src/deepaha/local_human_test/publication.py`
- Test: `backend/tests/local_human_test/test_review.py`
- Test: `backend/tests/local_human_test/test_publication.py`
- Test: `backend/tests/integration/test_local_human_test_review_publication.py`

**Interfaces:**
- Produces: `HumanFactReviewService.decide(command, principal, idempotency_key)` and `promote(item_id, principal)`.
- Produces: `HumanRuleReviewService.propose_from_verified_facts(item_id)`, `decide(...)`.
- Produces: `LocalCatalogPublicationService.preview(item_id) -> PublicationPreview`, `publish(item_id, principal, idempotency_key) -> PublicationResult`.

- [ ] **Step 1: Write failing human-accountability tests**

```python
def test_unapproved_or_unknown_fact_cannot_enter_publication_preview(session):
    seed_candidates(session, decisions=("APPROVE", "UNKNOWN", "REJECT"))
    preview = publication_service(session).preview(ITEM_ID)
    assert set(preview.field_names) == set(approved_candidate_field_names(session))


def test_publish_requires_human_validation_and_official_evidence(session):
    with pytest.raises(LocalPublicationError):
        publication_service(session).publish(
            ITEM_ID, principal=model_principal(), idempotency_key="publish-1"
        )
    assert count_public_entries(session) == 0
```

Cover role plus `OPPORTUNITY_FACT_VALIDATION` purpose, `human:<reviewer_id>` verifier identity, producer/verifier independence, decision idempotency conflict, rejected/unknown retention, rule dependence on active VerifiedFactSet, no approved rule implies eligibility ceiling `UNCERTAIN`, required public fields, official evidence, content-use boundary, publication repeat and stale version conflict.

- [ ] **Step 2: Run tests and observe missing services**

Run: `cd backend; uv run pytest tests/local_human_test/test_review.py tests/local_human_test/test_publication.py -q`

Expected: FAIL before implementation.

- [ ] **Step 3: Delegate fact and rule integrity to existing P9-B services**

Map UI decisions to existing `FactVerificationDecisionSchemaV08` and call `FactLifecycleService.verify_candidate`. Promotion accepts only APPROVE decisions, records the human verifier and creates one ACTIVE `VersionedVerifiedFactSet`. Build `RuleCandidateSchemaV08` only from its verified facts; call `RulePromotionService.propose/decide`; never synthesize approval from a model response.

- [ ] **Step 4: Implement idempotent local publication**

Build a deterministic snapshot and field-evidence list from the active VerifiedFactSet, create a new `OpportunityVersion` with `review_status=APPROVED`, and insert/update `PublicCatalogEntry` with `collection_kind=LOCAL_HUMAN_REVIEWED`. Compare the decision request hash, current opportunity version and content SHA-256 before mutation. Any conflict leaves the item `READY_TO_PUBLISH` and preserves the old version.

- [ ] **Step 5: Run review/publication and existing catalog regressions**

Run: `cd backend; uv run pytest tests/local_human_test/test_review.py tests/local_human_test/test_publication.py tests/public_catalog -q`

Run: `cd backend; uv run pytest -m integration tests/integration/test_local_human_test_review_publication.py tests/integration/test_phase5_public_catalog_service.py -q`

Expected: PASS; only human-approved, officially evidenced values appear in the local catalog.

- [ ] **Step 6: Commit the accountability and publication slice**

```powershell
git add backend/src/deepaha/local_human_test/review.py backend/src/deepaha/local_human_test/publication.py backend/tests/local_human_test/test_review.py backend/tests/local_human_test/test_publication.py backend/tests/integration/test_local_human_test_review_publication.py
git commit -m "feat: add governed local opportunity publication"
```

### Task 9: Loopback-only control API

**Files:**
- Modify: `backend/src/deepaha/core/settings.py`
- Create: `backend/src/deepaha/api/local_human_test.py`
- Modify: `backend/src/deepaha/main.py`
- Test: `backend/tests/api/test_local_human_test.py`
- Test: `backend/tests/api/test_local_human_test_security.py`

**Interfaces:**
- Produces the exact endpoints from design section 6 under `/api/v1/local-human-test`.
- Consumes the services from Tasks 2, 5, 6, 8 and the existing reviewer bearer-session resolver.

- [ ] **Step 1: Write failing environment, loopback and secret-response tests**

```python
def test_provider_status_never_returns_secret(client, operator_headers):
    response = client.get("/api/v1/local-human-test/config/provider", headers=operator_headers)
    assert response.status_code == 200
    assert set(response.json()) == {
        "configured", "provider", "base_url", "protocol", "model_id",
        "model_snapshot", "updated_at",
    }


@pytest.mark.parametrize("host", ["example.com", "192.0.2.10", "10.0.0.8"])
def test_control_api_rejects_non_loopback_host(client, operator_headers, host):
    response = client.get(
        "/api/v1/local-human-test/sources", headers=operator_headers | {"host": host}
    )
    assert response.status_code == 404
```

Also cover disabled feature flag, non-development environment, missing/expired fixture reviewer, LOCAL_TEST_OPERATOR versus VALIDATION_REVIEWER permissions, required Idempotency-Key, same-key/different-body 409, run cancellation, reset challenge expiry/single use, active-run reset rejection and error redaction.

- [ ] **Step 2: Run API tests and observe 404/missing settings**

Run: `cd backend; uv run pytest tests/api/test_local_human_test.py tests/api/test_local_human_test_security.py -q`

Expected: FAIL because router and settings do not exist.

- [ ] **Step 3: Add explicit local settings and dependency guards**

```python
local_human_test_enabled: bool = False
local_human_test_root: Path | None = None
local_human_test_worker_id: str = "local-human-test-worker"
local_human_test_lease_seconds: int = Field(default=60, ge=30, le=300)
```

Router inclusion may be unconditional, but every endpoint dependency must return the same 404 when the feature is disabled, environment is not `development`, or request host is not `127.0.0.1`, `localhost` or `[::1]`. Mutating endpoints require reviewer auth and Idempotency-Key; facts/rules require `VALIDATION_REVIEWER` plus the new purpose.

- [ ] **Step 4: Implement DTO-only responses and deterministic problem codes**

Return model call IDs, hashes, token counts, latency and cost status; do not return raw stored Provider bytes through list endpoints. Evidence detail returns only authorized official document blocks. Catch config/provider errors and map to stable codes such as `PROVIDER_NOT_CONFIGURED`, `PROVIDER_OUTCOME_UNKNOWN`, `MODEL_OUTPUT_INVALID`; never expose upstream error bodies.

- [ ] **Step 5: Run API and application regressions**

Run: `cd backend; uv run pytest tests/api/test_local_human_test.py tests/api/test_local_human_test_security.py tests/api -q`

Expected: PASS; API import with feature disabled has no filesystem or network side effect.

- [ ] **Step 6: Commit the loopback API**

```powershell
git add backend/src/deepaha/core/settings.py backend/src/deepaha/api/local_human_test.py backend/src/deepaha/main.py backend/tests/api/test_local_human_test.py backend/tests/api/test_local_human_test_security.py
git commit -m "feat: expose local human test control API"
```

### Task 10: Human review console UI

**Files:**
- Create: `web/lib/local-human-test.ts`
- Create: `web/app/review/human-test/actions.ts`
- Create: `web/app/review/human-test/page.tsx`
- Create: `web/app/review/human-test/loading.tsx`
- Create: `web/app/review/human-test/error.tsx`
- Create: `web/app/review/human-test/runs/[runId]/page.tsx`
- Create: `web/app/review/human-test/items/[itemId]/page.tsx`
- Create: `web/components/human-test/provider-config-form.tsx`
- Create: `web/components/human-test/run-form.tsx`
- Create: `web/components/human-test/fact-review-panel.tsx`
- Create: `web/components/human-test/rule-review-panel.tsx`
- Create: `web/components/human-test/publication-preview.tsx`
- Create: `web/components/human-test/data-management.tsx`
- Test: `web/tests/local-human-test-client.test.ts`
- Test: `web/tests/local-human-test-page.test.tsx`
- Test: `web/tests/local-human-test-actions.test.ts`

**Interfaces:**
- Consumes: API endpoints and DTOs from Task 9; existing reviewer cookie/bearer server-side patterns.
- Produces: `/review/human-test` overview and nested run/item pages; browser never receives stored API key after save.

- [ ] **Step 1: Write failing UI boundary tests**

```tsx
it("labels local evidence and never renders a stored secret", async () => {
  render(await HumanTestPage());
  expect(screen.getByText("Release Qualification：NOT_STARTED")).toBeVisible();
  expect(screen.getByText("真人参与者：0")).toBeVisible();
  expect(screen.getByText("LOCAL_HUMAN_REVIEWED")).toBeVisible();
  expect(screen.queryByDisplayValue(/secret/i)).not.toBeInTheDocument();
});


it("requires explicit budget confirmation before creating a live run", async () => {
  render(<RunForm sources={eightActiveSources} defaults={defaultBudget} />);
  expect(screen.getByRole("button", { name: "开始受控真实运行" })).toBeDisabled();
  await userEvent.click(screen.getByRole("checkbox", { name: /确认来源与硬预算/ }));
  expect(screen.getByRole("button", { name: "开始受控真实运行" })).toBeEnabled();
});
```

Cover provider create/update/delete, eight default Recipes, live/replay distinction, status polling, HTTP validation failures, ModelCall metrics, side-by-side evidence/candidate, approve/reject/unknown decisions, rule high-impact warning, publication preview, reset challenge and all four data labels.

- [ ] **Step 2: Run tests and observe missing pages/components**

Run: `cd web; corepack pnpm test -- local-human-test`

Expected: FAIL on missing imports/routes.

- [ ] **Step 3: Implement a server-only API client and server actions**

Use `server-only`, existing reviewer session helpers and `cache: "no-store"`. Generate one UUID idempotency key per user action on the server; never place Provider key in a URL, log statement, hidden input after successful save or returned action state. Provider form uses a password input that becomes empty after save and renders only `configured` status.

- [ ] **Step 4: Implement progressive control pages**

Overview shows boundaries before controls. Run form lists source host/role/request cap and immutable budget. Item page renders official blocks and candidate evidence together, disables publish until fact requirements pass, shows `UNCERTAIN` when no approved rules exist, and labels provisional values as “未验证引导字段”. Data reset requires requesting a challenge and typing it back before delete is enabled.

- [ ] **Step 5: Run UI tests, typecheck and build**

Run: `cd web; corepack pnpm test -- local-human-test`

Run: `cd web; corepack pnpm typecheck`

Run: `cd web; corepack pnpm build`

Expected: PASS; routes render without contacting any real external host.

- [ ] **Step 6: Commit the control console**

```powershell
git add web/lib/local-human-test.ts web/app/review/human-test web/components/human-test web/tests/local-human-test-client.test.ts web/tests/local-human-test-page.test.tsx web/tests/local-human-test-actions.test.ts
git commit -m "feat: add local human test console"
```

### Task 11: Persistent one-click lifecycle and precise reset

**Files:**
- Modify: `infra/compose.local-manual.yaml`
- Modify: `scripts/local-manual-test.ps1`
- Modify: `scripts/tests/local-manual-test.Tests.ps1`
- Modify: `web/scripts/open-local-manual-browser.mjs`
- Modify: `backend/tests/manual/seed_local_manual.py`
- Modify: `backend/tests/manual/test_seed_local_manual.py`
- Modify: `docs/development/local-manual-testing.md`

**Interfaces:**
- Launcher sets `DEEPAHA_LOCAL_HUMAN_TEST_ENABLED=true` and `DEEPAHA_LOCAL_HUMAN_TEST_ROOT=%LOCALAPPDATA%\DeepAha\manual-test` for API/worker without passing a key.
- Runtime state records `api`, `web`, `worker`, and `browser` process ownership.
- Stop preserves the named PostgreSQL volume and `%LOCALAPPDATA%` objects/config.

- [ ] **Step 1: Update failing Pester tests for persistent semantics**

```powershell
It "starts API, web, worker and human-test browser without live calls" {
    $state.processes.role | Should -Be @("api", "web", "worker", "browser")
    $openedUrls | Should -Contain "http://127.0.0.1:3089/review/human-test"
    $externalCallCount | Should -Be 0
}

It "stops owned resources without deleting persistent data" {
    $dockerArguments | Should -Contain "down"
    $dockerArguments | Should -Not -Contain "--volumes"
    Test-Path $providerConfigPath | Should -BeTrue
}
```

Add tests that failure cleanup does not remove the named volume, exact ownership prevents touching another Compose project, worker PID identity is verified, repeated seed preserves human results, and explicit reset refuses paths outside the control root.

- [ ] **Step 2: Run launcher tests and observe old destructive behavior**

Run: `pwsh -NoProfile -File scripts/tests/local-manual-test.Tests.ps1`

Expected: FAIL because Compose uses tmpfs, stop passes `--volumes`, no worker exists and browser opens old fixture pages.

- [ ] **Step 3: Make PostgreSQL persistent and fixture loading explicit**

Replace tmpfs with a deterministic Compose named volume mounted at `/var/lib/postgresql/data`. Keep Moto only for legacy fixture flows; human-test services use LocalFileObjectStore. Migration and reviewer/source bootstrap remain idempotent, while synthetic opportunities are loaded only through an explicit command/action and never on every startup.

- [ ] **Step 4: Start the worker and open the control console**

Add a worker process command `uv run python -m deepaha.local_human_test.worker` with a unique command marker. Pass the local root, database URL, development mode and feature flag to API and worker. Open `/review/human-test` as the primary browser page. Do not load the API key into the parent PowerShell environment.

- [ ] **Step 5: Implement reset as an owned backend operation**

The API reset service must verify no active run, consume the one-time challenge, terminate no unrelated process, truncate only local-human-test rows plus their explicitly owned local publication graph, remove only the resolved `%LOCALAPPDATA%\DeepAha\manual-test\objects` directory and delete only the exact Compose volume label/name recorded for this project. Provider config deletion remains a separate explicit action.

- [ ] **Step 6: Run launcher and seed tests**

Run: `pwsh -NoProfile -File scripts/tests/local-manual-test.Tests.ps1`

Run: `cd backend; uv run pytest tests/manual/test_seed_local_manual.py -q`

Expected: PASS; start creates no live acquisition or Provider call, stop retains data, restart sees prior run rows.

- [ ] **Step 7: Commit the persistent lifecycle**

```powershell
git add infra/compose.local-manual.yaml scripts/local-manual-test.ps1 scripts/tests/local-manual-test.Tests.ps1 web/scripts/open-local-manual-browser.mjs backend/tests/manual/seed_local_manual.py backend/tests/manual/test_seed_local_manual.py docs/development/local-manual-testing.md
git commit -m "feat: persist local human test lifecycle"
```

### Task 12: Full offline verification and controlled real-smoke handoff

**Files:**
- Create: `scripts/verify-local-human-test-control-plane.ps1`
- Create: `scripts/tests/verify-local-human-test-control-plane.Tests.ps1`
- Modify: `docs/development/local-manual-testing.md`

**Interfaces:**
- Produces one offline verifier that never reads a Provider credential and never enables live source checks.
- Produces a documented manual real-smoke checklist executed only from `/review/human-test`.

- [ ] **Step 1: Write verifier scope tests before the verifier**

```powershell
It "runs offline checks and never enables external calls" {
    $content | Should -Match "pytest"
    $content | Should -Match "pnpm build"
    $content | Should -Match "local-manual-test.Tests.ps1"
    $content | Should -Not -Match "ALLOW_LIVE_SOURCE_CHECK\s*=\s*true"
    $content | Should -Not -Match "LLM-API.txt"
}
```

- [ ] **Step 2: Run scope test and observe missing verifier**

Run: `pwsh -NoProfile -File scripts/tests/verify-local-human-test-control-plane.Tests.ps1`

Expected: FAIL because verifier does not exist.

- [ ] **Step 3: Implement the offline verifier using existing commands**

Run locked dependency sync, Ruff, MyPy, non-live backend tests, explicit PostgreSQL integration suites for Tasks 1–9, Web lint/typecheck/test/build, Pester launcher tests, migration head/drift checks and a static scan proving real transport is reachable only through `GatewayExecutor`. Capture and propagate every native exit code; always stop only the verifier-owned Compose project in `finally`.

- [ ] **Step 4: Document the separate manual real-smoke procedure**

The checklist is: start locally; save Provider configuration in the form; verify masked configured state; select one active Recipe; verify displayed budget `official<=9`, `LLM<=8`; click live run once; inspect official URL/final URL/DocumentBlock/ModelCall/Ledger; approve or reject facts; preview; publish; verify local catalog label; stop; restart; verify persistence. It must state that this spends real Provider quota, accesses the selected public official site, does not constitute Release Qualification, and must never record the secret.

- [ ] **Step 5: Run the complete offline verifier twice**

Run: `pwsh -NoProfile -File scripts/verify-local-human-test-control-plane.ps1`

Run again: `pwsh -NoProfile -File scripts/verify-local-human-test-control-plane.ps1`

Expected: both exit `0`; no real Provider request; no live official request; verifier Compose remnants `0`; tracked diff contains only planned files.

- [ ] **Step 6: Run one-click persistence acceptance without external calls**

Run: `& '.\启动 DeepAha 本地人工测试.cmd'`

Verify locally: API ready `200`, `/review/human-test` `200`, no run exists until clicking, stop exits `0`, restart retains seeded reviewer/source and any offline replay run, second stop exits `0`, owned running processes/containers/networks are `0`, persistent volume remains exactly `1`.

- [ ] **Step 7: Review scope and commit verification assets**

Run: `git diff --check`

Run: `git status --short`

Run: `rg -n "API[_-]?KEY|Bearer |LLM-API.txt" backend web scripts docs/development --glob "!*.lock"`

Inspect every match and prove there is no literal credential or credential-file access. Stage only the verifier and affected development guide.

```powershell
git add scripts/verify-local-human-test-control-plane.ps1 scripts/tests/verify-local-human-test-control-plane.Tests.ps1 docs/development/local-manual-testing.md
git commit -m "test: verify local human test control plane"
```

## Final Evidence Gate

- [ ] `git diff <implementation-base>...HEAD --check` exits `0`.
- [ ] Migration head is exactly `0030`; downgrade to `0029` and re-upgrade preserve prior P9-B migrations unchanged.
- [ ] Backend Ruff, MyPy, unit and selected integration suites exit `0`.
- [ ] Web lint, typecheck, Vitest and production build exit `0`.
- [ ] Pester launcher and verifier scope tests exit `0`.
- [ ] Offline verifier runs twice with exit `0` and external call count `0`.
- [ ] `ProviderAdapter.invoke` remains reachable from production orchestration only through `GatewayExecutor`.
- [ ] No API response, log, database row, Ledger row, command line or environment snapshot contains the API key.
- [ ] Start performs no external call; stop preserves data; explicit reset removes only owned data.
- [ ] Personal files remain unstaged and unchanged by this implementation.
- [ ] Final status states `Engineering implementation only`; `Release Qualification=NOT_STARTED`; no push or deploy occurred.
