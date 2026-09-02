# P10-B1 Independent Review Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复独立只读审查发现的 P10-B1 对象生命周期竞态、并发准入、请求预算、RawArtifact 复用和冻结证据绑定问题，同时保持 B1 范围与单一候选提交。

**Architecture:** 将请求键、Endpoint 和正文哈希三把 PostgreSQL advisory transaction lock 按固定顺序放入同一事务。内容寻址对象按 SHA 跨 Source 共享，B1 失败只回滚数据库并保留对象，不以局部或过时状态执行删除。请求型 SourceBundleMember 增加精确 EvidenceRef/ParseAttempt 身份并纳入不可变成员哈希；旧 Opportunity bundle 继续允许空身份且保持旧哈希格式。RawArtifact 继续以 `(source_id, content_sha256)` 为内容身份，本次采集元数据由 CaptureObservation 保存。

**Tech Stack:** Python 3.14、SQLAlchemy 2、PostgreSQL 18、Alembic、S3-compatible ObjectStore、pytest、Pydantic 2

**Spec:** `docs/superpowers/specs/2026-09-01-p10-b1-mainline-salvage-design.md`

## Global Constraints

- 基线提交保持 `d806e305c4b9239a81cce0216a237cd90f89f367`，首轮候选保持一个提交；PR #9 Critical follow-up 使用一个独立修复提交追加到原分支，不改写已审查提交。
- 不创建 Candidate、Opportunity、资格、发布、UI、浏览器执行、Excel/PDF/DOCX/OCR、Provider、模型网关、真实来源或 Gold 特判。
- 失败不得留下本次请求的半成品正式记录；任何失败请求都不得根据局部所有权假设删除可能被正式链路引用的共享对象。
- 旧 Opportunity SourceBundle 的字段、哈希和服务行为必须保持兼容。
- 每项生产行为先写失败测试并观察预期失败，再写最小实现。

---

### Task 1: 将并发准入与失败安全对象生命周期纳入同一事务

**Files:**
- Modify: `backend/src/deepaha/acquisition/official_evidence.py`
- Modify: `backend/tests/integration/test_p10b1_official_evidence.py`

**Interfaces:**
- Consumes: `OfficialEvidenceTask.run(request)`, PostgreSQL advisory locks, shared content-addressed ObjectStore
- Produces: 固定 `request_key -> endpoint_id -> content_sha256` 锁顺序；数据库失败时对象保留与独立提交结果边界

- [x] **Step 1: 写跨 Source 共享对象失败测试**

失败请求 A 上传对象后暂停；另一 Source B 通过不共享 B1 advisory lock 的通用导入路径提交同 SHA 的正式 RawArtifact，再让 A 进入失败处理。断言 B 的数据库引用和共享对象均保留。

```python
assert failing_store.uploaded.wait(timeout=2)
successful = import_raw_artifact(session=other_source_session, ...)
other_artifact_committed.set()
with pytest.raises(OfficialEvidencePersistenceError):
    failing_future.result(timeout=5)
assert object_store.get_bytes(key=object_key) == VALID_BODY
```

- [x] **Step 2: 运行测试并确认当前实现失败**

Run: `uv run pytest -m integration tests/integration/test_p10b1_official_evidence.py::test_failed_capture_never_deletes_object_committed_for_another_source -q`

Expected: FAIL with `NoSuchKey`；另一 Source 的 RawArtifact 已提交，但失败请求删除了共享对象。

- [x] **Step 3: 写同键漂移和 Endpoint 限速并发测试**

同 request key 不同 payload 时，第二请求不得调用 transport；不同 request key 同 Endpoint 时，第二请求也不得在第一请求完成前调用 transport。

```python
assert first_transport.entered.wait(timeout=2)
second_future = executor.submit(second_runner.run, second_request)
assert not second_transport.entered.wait(timeout=0.2)
```

- [x] **Step 4: 运行测试并确认当前实现失败**

Run: `uv run pytest -m integration tests/integration/test_p10b1_official_evidence.py -k "concurrent and (drift or endpoint)" -q`

Expected: FAIL；当前锁在网络之后取得，第二 transport 会被调用。

- [x] **Step 5: 实现固定锁顺序与失败安全对象保留**

`run()` 保留只读快速重放；未命中后开启显式事务，依次取得 request、endpoint、content locks。request 和 endpoint 锁后完成二次重放、策略和限速检查，再执行网络。正文锁内写入对象和正式链路；普通异常只回滚数据库，保留对象，避免单次请求的局部快照误删其他写入路径已提交的证据。

```python
transaction = session.begin()
try:
    _lock(session, request.request_key, seed=0)
    _lock(session, str(request.endpoint_id), seed=2)
    acquired, validation = self._acquire_and_validate(...)
    _lock(session, digest, seed=1)
    result = self._persist(...)
    transaction.commit()
    return result
except Exception:
    transaction.rollback()
    raise
```

- [x] **Step 6: 运行 Task 1 测试并确认通过**

Run: `uv run pytest -m integration tests/integration/test_p10b1_official_evidence.py -q`

Expected: PASS。

---

### Task 2: 强制单次静态请求、预算和媒体策略

**Files:**
- Modify: `backend/src/deepaha/acquisition/official_evidence.py`
- Modify: `backend/tests/acquisition/test_official_evidence.py`
- Modify: `backend/tests/integration/test_p10b1_official_evidence.py`

**Interfaces:**
- Consumes: `SourceEndpoint.browser_policy`, `SourceRecipe.maximum_requests`, `maximum_elapsed_seconds`, `expected_media_types`
- Produces: 一次 STATIC_HTTP、超时不超过配方预算、精确 MIME 白名单、拒绝 `FALLBACK`

- [x] **Step 1: 写策略和运行预算失败测试**

增加 `browser_policy='FALLBACK'` 的策略拒绝测试；Endpoint `max_attempts=3` 时，脚本首个网络错误、第二个成功，断言只调用一次并失败；响应 `application/octet-stream` 时不得持久化。

```python
with pytest.raises(OfficialEvidencePolicyError):
    validate_official_evidence_policy(request, source, fallback_endpoint, recipe)
with pytest.raises(OfficialEvidenceAcquisitionError):
    runner.run(request)
assert len(transport.requests) == 1
```

- [x] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/acquisition/test_official_evidence.py -q`

Run: `uv run pytest -m integration tests/integration/test_p10b1_official_evidence.py -k "single_attempt or media_type" -q`

Expected: FAIL；当前允许 FALLBACK、重试并捕获白名单外正文。

- [x] **Step 3: 实现策略与运行约束**

策略要求 `browser_policy == 'NEVER'`。运行端点副本固定 `max_attempts=1`，`timeout_seconds=min(endpoint.timeout_seconds, recipe.maximum_elapsed_seconds)`，并传入 `capture_unexpected_content=False`。

```python
endpoint_contract = _endpoint_contract(endpoint).model_copy(
    update={
        "url": request.requested_url,
        "max_attempts": 1,
        "timeout_seconds": min(endpoint.timeout_seconds, recipe.maximum_elapsed_seconds),
    }
)
```

- [x] **Step 4: 运行 Task 2 测试并确认通过**

Run: `uv run pytest tests/acquisition/test_official_evidence.py -q`

Run: `uv run pytest -m integration tests/integration/test_p10b1_official_evidence.py -q`

Expected: PASS。

---

### Task 3: 按内容身份复用 RawArtifact

**Files:**
- Modify: `backend/src/deepaha/acquisition/official_evidence.py`
- Modify: `backend/tests/integration/test_p10b1_official_evidence.py`

**Interfaces:**
- Consumes: `RawArtifact(source_id, content_sha256)` 唯一身份、`CaptureObservation` 本次采集元数据
- Produces: 同 Source 同正文可被不同合法请求复用；每个请求仍有独立 Observation/Run/Document/Bundle

- [x] **Step 1: 写同正文顺序复用失败测试**

为同一 Source 配置两个独立 Endpoint/Recipe 和不同 URL，返回相同正文。断言两个结果复用同一 `raw_artifact_id`，但拥有不同 request bundle 和 Observation，结果时间来自各自 Observation。

```python
assert first.raw_artifact_id == second.raw_artifact_id
assert first.source_bundle_id != second.source_bundle_id
assert count(CaptureObservation) == 2
```

- [x] **Step 2: 运行测试并确认当前实现失败**

Run: `uv run pytest -m integration tests/integration/test_p10b1_official_evidence.py::test_same_source_same_bytes_reuse_artifact_across_requests -q`

Expected: FAIL with `RAW_ARTIFACT_PROVENANCE_CONFLICT`。

- [x] **Step 3: 实现内容身份复用**

正文锁内通过 `import_raw_artifact()` 按 `(source_id, content_sha256)` 复用 RawArtifact 内容身份并验证 object key、SHA 和 size。失败路径不推断共享对象的局部所有权，不执行对象删除。返回的 `retrieved_at` 使用本次 CaptureObservation 的完成时间。

- [x] **Step 4: 运行 Task 3 测试并确认通过**

Run: `uv run pytest -m integration tests/integration/test_p10b1_official_evidence.py -q`

Expected: PASS。

---

### Task 4: 将 EvidenceRef 和 ParseAttempt 纳入冻结成员身份

**Files:**
- Modify: `backend/migrations/versions/20260901_0034_p10b1_official_request_bundles.py`
- Modify: `backend/src/deepaha/p9b/models.py`
- Modify: `backend/src/deepaha/p9b/provenance.py`
- Modify: `backend/src/deepaha/acquisition/official_evidence.py`
- Modify: `backend/tests/integration/test_p10b1_migration.py`
- Modify: `backend/tests/integration/test_p10b1_official_evidence.py`
- Modify: `backend/tests/integration/test_p9b_gateway_value_migration.py`

**Interfaces:**
- Consumes: `BundleMemberSpec`, immutable `SourceBundleMember`, `EvidenceRef`, `ParseAttempt`
- Produces: request member 的精确 `evidence_ref_id` 与 `parse_attempt_id`，成员哈希与重放均使用这两个身份

- [x] **Step 1: 写迁移与冻结绑定失败测试**

断言 0034 后 member 有两个可空 FK；Opportunity member 允许均为空；request member 缺任一身份或身份与 document/artifact 不一致时数据库拒绝。绑定后的 EvidenceRef/ParseAttempt 更新或删除被触发器拒绝。

- [x] **Step 2: 写重放完整性失败测试**

成功请求后验证 member 保存精确身份。用包装 ObjectStore 返回被篡改正文但保留正确 metadata，精确重放必须抛 `OfficialEvidencePersistenceError`。锁后二次重放也必须执行相同验证。

```python
with pytest.raises(OfficialEvidencePersistenceError):
    tampered_runner.run(request)
```

- [x] **Step 3: 运行测试并确认失败**

Run: `uv run pytest -m integration tests/integration/test_p10b1_migration.py tests/integration/test_p10b1_official_evidence.py -q`

Expected: FAIL；当前没有成员列、精确绑定或真实字节验证。

- [x] **Step 4: 实现迁移、模型与成员哈希**

0034 为 `source_bundle_members` 增加两个可空 UUID FK。请求型 revision 的插入触发器要求两个身份存在且分别精确绑定 full-document EvidenceRef 与 SUCCEEDED ParseAttempt；绑定行被引用后拒绝 UPDATE/DELETE。`BundleMemberSpec` 新增两个可空字段，只有非空时才把 ID 加入 `_member_payload()`，从而保持旧 Opportunity 哈希不变。

- [x] **Step 5: 实现精确重放验证**

`_load_replay()` 要求请求 revision 恰有一个 member，并按 member 的精确 ID 加载 EvidenceRef、ParseAttempt、Observation、Document 和 RawArtifact，核对全部交叉身份。`_verify_object()` 同时校验 metadata 与 `get_bytes()` 的真实 SHA/size；快速重放和锁后二次重放都调用它。

- [x] **Step 6: 运行 Task 4 测试并确认通过**

Run: `uv run pytest -m integration tests/integration/test_p10b1_migration.py tests/integration/test_p10b1_official_evidence.py tests/integration/test_p9b_fact_persistence.py -q`

Expected: PASS。

---

### Task 5: 补齐 0033 完整旧 bundle 兼容回归

**Files:**
- Modify: `backend/tests/integration/test_p10b1_migration.py`
- Modify: `backend/tests/integration/test_p9b_gateway_value_migration.py`

**Interfaces:**
- Consumes: 0033 完整 Opportunity/Version/SourceBundle/Revision/Member 历史；0034 `BundleService.create_revision()`
- Produces: 升级后旧完整链路可继续创建和冻结 revision，安全降级后旧行仍存在

- [x] **Step 1: 扩展迁移测试并确认当前覆盖不足**

在 0033 使用现有 Graph fixture 创建来源、采集、Document、Evidence 和 OpportunityVersion，再用旧列集合插入 FROZEN SourceBundle revision/member。升级 0034 后通过 BundleService 创建并冻结下一 revision；降级回 0033 后核对两个 revision 和成员仍存在。

- [x] **Step 2: 更新历史测试兼容列**

历史 0028 测试的测试专用兼容 helper 同时给 `source_bundle_members` 增加两个可空列，使当前 ORM helper 能在旧迁移快照上构造数据；被测迁移本身不依赖这些列。

- [x] **Step 3: 运行迁移回归**

Run: `uv run pytest -m integration tests/integration/test_p10b1_migration.py tests/integration/test_p9b_gateway_value_migration.py tests/integration/test_local_human_test_migration.py -q`

Expected: PASS。

---

### Task 6: 文档、范围与完整验证

**Files:**
- Modify: `docs/superpowers/specs/2026-09-01-p10-b1-mainline-salvage-design.md`
- Modify: `docs/superpowers/plans/2026-09-01-p10-b1-mainline-salvage.md`
- Create: `docs/superpowers/plans/2026-09-02-p10-b1-review-remediation.md`

**Interfaces:**
- Consumes: Tasks 1–5 的最终实现
- Produces: 与实现一致的设计、计划、验证证据和单一候选提交

- [x] **Step 1: 更新设计与原计划**

记录三锁顺序、失败安全对象保留、一次请求预算、RawArtifact 内容复用、精确 EvidenceRef/ParseAttempt 冻结和真实对象字节重放验证；不把候选写成已合并或 Release Qualification 已完成。

- [x] **Step 2: 运行定向和全量验证**

Run:

```powershell
uv run pytest tests/acquisition/test_official_evidence.py tests/artifacts/test_local_file_store.py -q
uv run pytest -m integration --strict-markers
uv run alembic heads
uv run alembic current
uv run alembic check
.\scripts\verify.ps1
.\scripts\verify-phase8.ps1 -ComposeProjectName deepaha-phase8-p10b1reviewfix
```

Expected: 全部 exit 0；单一 0034 head；无自动迁移差异。

- [x] **Step 3: 运行范围审计**

确认新增生产代码中的 Provider/模型调用、Gold 特判、Candidate/Opportunity 创建、浏览器执行和文档智能均为 0。

- [x] **Step 4: 修订唯一候选提交**

```powershell
git add backend/src/deepaha/acquisition/official_evidence.py backend/src/deepaha/p9b/models.py backend/src/deepaha/p9b/provenance.py backend/migrations/versions/20260901_0034_p10b1_official_request_bundles.py backend/tests/acquisition/test_official_evidence.py backend/tests/integration/test_p10b1_migration.py backend/tests/integration/test_p10b1_official_evidence.py backend/tests/integration/test_p9b_gateway_value_migration.py docs/superpowers/specs/2026-09-01-p10-b1-mainline-salvage-design.md docs/superpowers/plans/2026-09-01-p10-b1-mainline-salvage.md docs/superpowers/plans/2026-09-02-p10-b1-review-remediation.md
git diff --cached --check
git commit --amend --no-edit
git rev-list --count d806e305c4b9239a81cce0216a237cd90f89f367..HEAD
git status --short
```

Expected: 首轮候选时基线到 HEAD 为 1 个提交，工作树干净；该步骤本身不推送、不合并、不部署。PR #9 Critical follow-up 完成后基线到 HEAD 为 2 个提交，仍不合并、不部署。

## Plan Self-Review

- Spec coverage: Critical、5 个 Important 与迁移测试 Minor 均映射到 Task 1–5。
- Scope: 只修改 B1 采集、P9-B 来源包绑定、0034 迁移、测试和直接文档。
- Type consistency: `BundleMemberSpec.evidence_ref_id` 与 `parse_attempt_id` 均为 `UUID | None`；数据库列同为 nullable UUID。
- Compatibility: 旧 Opportunity member 的两个新字段保持 `NULL`，旧成员哈希 payload 不增加键。

## Final Independent Review Follow-up

最终独立复审未发现 Critical，但在合并前识别出三项 Important，均按 TDD 补充回归并修复：

- [x] B1 禁止跟随 3xx，确保 `maximum_requests = 1` 对实际 transport 调用成立，单次 timeout 不超过配方预算。
- [x] 将普通持久化异常与 `commit()` 结果未知分离；提交异常不得删除对象，并返回稳定的结果未知错误。
- [x] 0034 降级在任一成员含精确 EvidenceRef/ParseAttempt 身份时拒绝，避免删除列后冻结哈希与旧函数失配。
- [x] 重新运行全仓、完整 integration、Alembic 与 Phase 8 验证；再次独立复审精确候选提交作为下一道门。
- [x] 再次独立复审确认前三项关闭，并识别普通持久化失败仍泄漏底层异常；回滚后现统一为 `OFFICIAL_EVIDENCE_PERSISTENCE_FAILED`，领域错误和提交结果未知分支保持独立。
- [x] 重新执行完整验证；对修订后的精确候选提交进行最后独立复审作为下一道门。
- [x] 最后复审识别显式 `__cause__` 仍暴露底层异常；普通、rollback 和 commit-unknown 分支现均抑制对外异常链，并补充故障注入测试。
- [x] 重新执行最终完整验证；复核精确候选提交作为下一道门。

## PR #9 Critical Follow-up

- [x] 以真实 PostgreSQL/S3 并发测试复现跨 Source 共享对象误删：通用导入已提交 RawArtifact 后，失败 B1 请求按过时局部快照删除同 SHA 对象，测试稳定出现 `NoSuchKey`。
- [x] 采用最小失败安全修复：B1 失败只回滚数据库，不再调用 `delete_if_matches()`；正式数据库引用优先，不确定时允许暂留孤立对象。
- [x] 移除 `CompensatingObjectStore` 窄协议和过时的补偿测试，保留通用对象存储删除能力但不让 B1 推断共享对象所有权。
- [x] 运行完整验证、更新原 PR #9，并保持 `Release Qualification=NOT_STARTED`、不得标记 `STABLE`。
