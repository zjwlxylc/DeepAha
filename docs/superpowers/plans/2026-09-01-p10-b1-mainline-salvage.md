# P10-B1 主线打捞实施计划

> 执行方式：在当前 Codex 隔离工作树中按任务顺序执行；每个行为先观察失败测试，再写最小实现。首轮候选保持单提交；PR #9 Critical follow-up 以一个独立、可审计的修复提交追加到原分支，不改写已审查提交。

**目标：** 在干净主线恢复一个通用、静态 HTTP、官方一手源到冻结原始证据包的最小事实链，并证明精确重放零增量、载荷漂移与失败零正式写入。

**架构：** 新同步任务入口在同一事务内按请求键、Endpoint、正文哈希顺序取得 PostgreSQL advisory transaction lock，锁内完成并发准入、单次静态请求、内容校验、现有内容身份复用和完整血缘持久化。`SourceBundle` 以互斥的 Opportunity 身份或请求身份存在；数据库失败只回滚正式行并保留内容寻址对象，不依据单次请求的局部状态执行删除。独立审查后的精确证据绑定、对象生命周期边界与完整迁移回归见 `2026-09-02-p10-b1-review-remediation.md`。

**技术栈：** Python 3.14、Pydantic 2、SQLAlchemy 2、PostgreSQL 18、Alembic、S3/Moto、pytest、uv。

---

## Task 1：锁定请求契约、准入和重放语义

**文件：**

- 新建：`backend/src/deepaha/acquisition/official_evidence.py`
- 新建：`backend/tests/acquisition/test_official_evidence.py`
- 修改：`backend/src/deepaha/acquisition/__init__.py`

**步骤 1：写失败测试**

添加以下测试：

- `test_payload_hash_is_canonical_and_excludes_request_key`
- `test_policy_rejects_non_official_or_non_static_recipe_before_transport`
- `test_task_is_exposed_as_the_acquisition_entrypoint`

测试使用冻结 `OfficialEvidenceRequest`、通用 `official.example` 和 ORM 策略对象；断言请求 SHA 稳定、发现型或浏览器配方被拒绝，并且任务类通过 acquisition 包形成唯一同步入口。内容失败的零持久化由 Task 3 的 PostgreSQL/S3 集成测试证明。

**步骤 2：运行并确认红灯**

```powershell
Set-Location backend
uv run pytest tests/acquisition/test_official_evidence.py -q
```

预期：因 `deepaha.acquisition.official_evidence` 尚不存在而收集失败。

**步骤 3：写最小契约和前置流程**

实现：

```python
class OfficialEvidenceRequest(AcquisitionContract):
    request_key: Annotated[str, StringConstraints(pattern=REQUEST_KEY_PATTERN)]
    source_id: EntityId
    endpoint_id: EntityId
    recipe_id: EntityId
    requested_url: HttpUrl
    contract_version: Literal["1.0.0"]

def request_payload_sha256(request: OfficialEvidenceRequest) -> str:
    payload = request.model_dump(mode="json", exclude={"request_key"})
    return sha256(canonical_json(payload).encode("utf-8")).hexdigest()
```

再实现 `OfficialEvidenceTask.run()` 的顺序骨架：查询重放、准入检查、内存采集、内容校验、调用 persistence port。所有错误使用稳定错误码，不包含正文或敏感头。

**步骤 4：运行并确认绿灯**

```powershell
uv run pytest tests/acquisition/test_official_evidence.py -q
uv run ruff check src/deepaha/acquisition/official_evidence.py tests/acquisition/test_official_evidence.py
```

## Task 2：增加请求型 SourceBundle 迁移与 ORM 契约

**文件：**

- 新建：`backend/migrations/versions/20260901_0034_p10b1_official_request_bundles.py`
- 修改：`backend/src/deepaha/p9b/models.py`
- 修改：`backend/src/deepaha/p9b/provenance.py`
- 新建：`backend/tests/integration/test_p10b1_migration.py`
- 修改：`backend/src/deepaha/local_human_test/extraction.py`
- 修改：`backend/tests/local_human_test/test_extraction.py`

**步骤 1：写失败迁移和服务测试**

添加以下测试：

- 从 `20260826_0033` 造一条旧 Opportunity/SourceBundle 路径，升级 head 后旧 ID、字段和 `BundleService.create_revision()` 路径保持有效。
- 空新历史可降级到 `20260826_0033` 再升级；存在请求型 bundle 时降级抛出稳定错误且行仍存在。
- `BundleService.create_request_revision()` 创建 Opportunity 为空的 DRAFT revision；任务入口负责重放既有冻结 revision，同 request key 不同 payload hash 拒绝。
- 请求型 revision 不能进入既有 Opportunity 模型抽取路径。

**步骤 2：运行并确认红灯**

```powershell
uv run pytest tests/local_human_test/test_extraction.py -q
uv run pytest -m integration tests/integration/test_p10b1_migration.py --strict-markers -q
```

预期：新 revision 不存在、ORM 无请求身份列、`BundleService` 无请求路径。

**步骤 3：实现最小迁移与模型**

迁移只执行：

```text
source_bundles + request_key + request_payload_sha256
source_bundles.opportunity_id nullable + XOR check + partial unique request_key
source_bundle_revisions opportunity pair nullable
bundle-only FK + NULL-safe binding trigger
p9b revision immutable guard 的两个 NULL-safe 比较
```

不改 `acquisition_runs`，不放宽 Document 媒体类型，不加入浏览器字段。

ORM 与迁移约束名称保持一致。`BundleService` 增加 `create_request_revision()`，内部复用 `_create_revision()`；冻结哈希对空 Opportunity 写 JSON `null`，对旧路径保持原字符串格式。

**步骤 4：运行迁移与定向测试**

```powershell
uv run pytest tests/local_human_test/test_extraction.py -q
uv run pytest -m integration tests/integration/test_p9b_fact_persistence.py tests/integration/test_p10b1_migration.py --strict-markers -q
uv run alembic heads
uv run alembic check
```

预期：定向测试通过、仅一个 `20260901_0034` head、无新迁移操作。

## Task 3：实现原始快照的事务持久化与失败安全对象保留

**文件：**

- 修改：`backend/src/deepaha/acquisition/official_evidence.py`
- 修改：`backend/src/deepaha/artifacts/s3.py`
- 修改：`backend/src/deepaha/artifacts/local_file.py`
- 修改：`backend/tests/artifacts/test_local_file_store.py`
- 修改：`backend/tests/integration/test_s3_object_store.py`
- 新建：`backend/tests/integration/test_p10b1_official_evidence.py`
- 新建：`backend/tests/fixtures/p10b1/official-notice.html`

**步骤 1：写失败存储测试**

先为对象存储添加行为测试：

- `stat_if_present` 对不存在键返回 `None`，存在键返回完整 metadata。
- `delete_if_matches` 只删除 SHA 相同对象；不匹配时拒绝。

再写 P10-B1 集成测试：

- 合成 fixture 成功后完整血缘、对象、SHA、取得时间、`full_document/*` EvidenceRef 与 FROZEN bundle 可追溯。
- Candidate/Opportunity 表零行。
- 相同请求重放时表计数、对象计数、transport 调用数零增量。
- 同键载荷漂移在 transport 和所有存储前零增量。
- 网络/内容失败无行无对象。
- 对象上传后注入事务失败，所有数据库行回滚且对象保留；跨 Source 正式引用不得被失败请求删除。

**步骤 2：运行并确认红灯**

```powershell
uv run pytest tests/artifacts/test_local_file_store.py tests/integration/test_s3_object_store.py tests/integration/test_p10b1_official_evidence.py -q
```

预期：缺少可恢复对象方法和持久化实现。

**步骤 3：实现最小持久化**

`S3ObjectStore` 与 `LocalFileObjectStore` 的 `stat_if_present` / `delete_if_matches` 保留为通用对象存储能力，但 B1 不以它们推断单次请求拥有共享对象。持久化函数在请求键锁后重查请求身份，在 Endpoint 锁内检查限速并最多发起一次静态请求，再取得正文哈希锁；随后创建本次 Observation、VALID Evaluation、COMPLETE Run，复用或创建 raw snapshot Document/ParseAttempt 与全文件 EvidenceRef，并把精确 EvidenceRef/ParseAttempt ID 写入冻结成员。事务异常时只回滚数据库并保留对象；孤立对象治理后置到具备全局引用复核和审计的独立流程。

**步骤 4：运行并确认绿灯**

```powershell
uv run pytest tests/artifacts/test_local_file_store.py tests/integration/test_s3_object_store.py tests/integration/test_p10b1_official_evidence.py -q
uv run mypy src tests
```

## Task 4：文档与范围静态核验

**文件：**

- 已新建：`docs/superpowers/specs/2026-09-01-p10-b1-mainline-salvage-design.md`
- 已新建：`docs/superpowers/plans/2026-09-01-p10-b1-mainline-salvage.md`

**步骤 1：检查设计与计划无占位**

```powershell
rg -n -i "TBD|TODO|FIXME|待定|占位|后续补充" docs/superpowers/specs/2026-09-01-p10-b1-mainline-salvage-design.md
git diff --check
```

预期：无匹配，diff 无空白错误。

**步骤 2：检查生产范围**

```powershell
rg -n -i "gold|浙江|zhejiang|xlsx|excel|pdf|docx|ocr|playwright|browser|provider|model.gateway|candidate|eligib|publication" backend/src backend/migrations/versions/20260901_0034_p10b1_official_request_bundles.py
```

检查所有命中：本次新增生产代码中 Gold 特例、真实 Provider 调用、浏览器、文档智能、Candidate/Opportunity 创建逻辑必须为零；通用现有枚举或旧代码不作为本次新增命中。

## Task 5：候选环境完整验证

**步骤 1：格式、静态和定向测试**

```powershell
Set-Location backend
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy src tests
uv run pytest tests/acquisition/test_official_evidence.py tests/local_human_test/test_extraction.py -q
uv run pytest -m integration tests/integration/test_p9b_fact_persistence.py tests/integration/test_p10b1_migration.py tests/integration/test_p10b1_official_evidence.py --strict-markers -q
```

**步骤 2：独立 PostgreSQL/S3 迁移矩阵**

以唯一 Compose project 启动 `infra/compose.phase8.yaml`，导出该项目的 PostgreSQL/S3 环境，然后运行：

```powershell
uv run alembic upgrade head
uv run alembic current
uv run alembic heads
uv run alembic check
uv run pytest tests/integration/test_p10b1_migration.py tests/integration/test_p10b1_official_evidence.py -q
```

**步骤 3：全仓与完整 integration**

```powershell
Set-Location ..
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1
Set-Location backend
uv run pytest -m integration --strict-markers
```

预期：全仓 0 失败；完整 integration 相比基线 0 新失败；P10-B1 定向全部通过；Provider 调用计数为 0。

**步骤 4：独立 Phase 8 回归与清理**

```powershell
Set-Location ..
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-phase8.ps1 -ComposeProjectName deepaha-phase8-p10b1candidate
```

预期：脚本退出码 0；随后只关闭本任务精确 Compose project 并删除其卷。

## Task 6：形成单一候选提交

**步骤 1：最终差异检查**

```powershell
git status --short
git diff --check
git diff --stat
git diff --name-only
```

确认所有改动都能追溯到 P10-B1，审计证据未变，未出现真实配置或密钥。

**步骤 2：提交并确认干净**

```powershell
git add backend/src/deepaha/acquisition/official_evidence.py backend/src/deepaha/acquisition/__init__.py backend/src/deepaha/artifacts/s3.py backend/src/deepaha/artifacts/local_file.py backend/src/deepaha/p9b/models.py backend/src/deepaha/p9b/provenance.py backend/src/deepaha/local_human_test/extraction.py backend/migrations/versions/20260901_0034_p10b1_official_request_bundles.py backend/tests/acquisition/test_official_evidence.py backend/tests/artifacts/test_local_file_store.py backend/tests/integration/test_s3_object_store.py backend/tests/integration/test_p10b1_migration.py backend/tests/integration/test_p10b1_official_evidence.py backend/tests/fixtures/p10b1/official-notice.html backend/tests/local_human_test/test_extraction.py docs/superpowers/specs/2026-09-01-p10-b1-mainline-salvage-design.md docs/superpowers/plans/2026-09-01-p10-b1-mainline-salvage.md
git commit -m "feat(p10b1): salvage official source evidence chain"
git status --short
git rev-parse HEAD
```

只报告候选提交，不推送、不合并、不部署、不启动 B2。
