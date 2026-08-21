# DeepAha Phase 1 领域契约与原始证据设计

> 状态：`PROPOSED`，等待用户确认关键决策后实施
> 日期：2026-08-21
> 目标阶段：Phase 1
> 前置 Gate：Phase 0 `CLOSED`
> 契约基线：`0.1.0`
> 本文描述计划方案，不表示代码、迁移、样本入库或验证已经完成。

## 1. 目的

Phase 1 锁定 DeepAha 最小领域语言，并建立第一条不可变原始证据链：固定官方响应的原始字节进入 S3 兼容对象存储，PostgreSQL 保存来源、哈希、对象定位和结构化实体，证据引用能够回到同一份原始输入。

本阶段只证明以下能力：

1. `Source`、`RawArtifact`、`Document`、`Opportunity`、`EvidenceRef` 的 v0.1 Schema 可校验、可持久化、可迁移。
2. 同一固定捕获事实重复导入是幂等的，不产生第二个 `RawArtifact`。
3. 原始字节不被解析输出覆盖，且可由来源 URL、抓取时间、SHA-256、存储桶和对象键共同复现。
4. `Document` 是文档/解析结果，`Opportunity` 是稳定机会身份；两者不是同一行、同一表或互相替代的对象。
5. JSON Schema、Pydantic 模型、SQLAlchemy 持久化模型、Alembic 迁移和契约测试保持一致。
6. Phase 1 Gate 可以在新鲜环境中重复执行并生成真实证据。

## 2. 设计依据与当前事实

### 2.1 已核验仓库基线

- 当前分支为 `main`，当前提交为 `22f11b8e99311067670d8bbf1394fb881bf7e872`。
- `origin` 为 `https://github.com/zjwlxylc/DeepAha.git`。
- 工作树在设计开始时干净。
- `docs/gates/phase-0/README.md` 和 `acceptance-results.md` 均将 Phase 0 Gate 标记为 `CLOSED`。
- GitHub Actions Run `32467979392` 的 `backend-quality` 与 `web-quality` 作业均为 `success`。
- Phase 1 尚无实现；开发文档中的 Phase 1 仍为 `PROPOSED`。

### 2.2 不可破坏的上位约束

- 核心链路是 `Source -> RawArtifact -> Document -> Opportunity -> Version / Event -> RuleSet -> Match -> Action`。
- `Document != Opportunity`。
- 原始证据不可被解析结果覆盖。
- PostgreSQL 是结构化事实源；对象存储保存原始字节；缓存、模型或向量索引都不是事实源。
- 内部 ID 使用 UUIDv7，时间点使用 UTC。
- 规划、实现和验证三种状态必须分开表达。

PostgreSQL 18 原生提供 `uuidv7()` 和 `uuid_extract_version()`；Python 3.14 标准库提供 `uuid.uuid7()`。本设计选择数据库默认生成内部 UUIDv7，并用数据库约束验证版本，应用侧仍可接收显式 UUIDv7 以支持固定测试数据。

## 3. 范围

### 3.1 本阶段包含

- 五个 Phase 1 领域契约及其 JSON Schema。
- PostgreSQL 18.4、SQLAlchemy 2.x、Alembic 和 Psycopg 3。
- 五类对象的持久化表、外键、唯一约束、检查约束和迁移回放。
- S3 子集接口：创建桶、按内容地址写入、读取、读取元数据、拒绝覆盖不一致对象。
- `boto3` S3 适配器及 Moto 5.2.2 本地开发/测试服务。
- 一个固定、可公开核验、许可清晰的官方 JSON 响应样本。
- 内容哈希、内容寻址对象键、重复导入去重、证据定位和原始字节回读校验。
- Phase 1 本地验证脚本、CI `integration` 作业和 Gate 证据包设计。

### 3.2 本阶段不包含

- Source Registry 调度、定时抓取、限速、重试、源健康或实时采集器。
- HTML、PDF、Excel、OCR 或通用 JSON 解析器。
- Opportunity Resolver、OpportunityVersion、OpportunityEvent、别名、合并、拆分或变化检测。
- LLM、Model Gateway、规则、资格、排序、用户、反馈、通知、Redis、pgvector 或业务页面。
- 生产云账号、生产对象存储、生产数据库、Kubernetes 或消息队列。
- 自动刷新固定官方样本；默认测试不访问网络。

## 4. 方案比较

### 4.1 方案 A：应用契约优先 + PostgreSQL + S3 适配器 + Moto（推荐）

- Pydantic v2 是契约作者源，导出并提交确定性的 JSON Schema。
- SQLAlchemy 模型与 Alembic 迁移独立存在，用测试证明两者无差异。
- `boto3` 实现真实 S3 API 子集；本地与 CI 使用 Moto 5.2.2。
- 固定官方样本从 GOV.UK Content API 一次性捕获，之后离线回放。

优点：代码量小；契约、数据库和对象存储边界都能真实测试；不需要生产云基础设施；新鲜环境可复现。缺点：Moto 是开发替身，不证明特定生产 S3 供应商的全部兼容性。

### 4.2 方案 B：JSON Schema 唯一源 + 代码生成 + LocalStack

- 手写 JSON Schema，再生成 Pydantic 类型。
- LocalStack 提供更完整的 AWS 风格本地环境。

优点：跨语言契约源更纯粹，AWS 行为覆盖更广。缺点：引入代码生成工具、生成物治理和较重容器；五个小契约不足以证明这些复杂度有价值。

### 4.3 方案 C：数据库优先 + 本地文件系统对象存储

- 从 SQLAlchemy/Alembic 推导契约。
- 原始字节写入本地目录。

优点：实现最少。缺点：契约被数据库细节反向定义；本地文件系统不能验证 S3 语义；不满足“Schema、迁移和契约测试一致”的设计意图。

### 4.4 不选择 MinIO 作为默认本地实现

MinIO 过去是常见选择，但其开源社区仓库已在 2026-04-25 归档，社区版改为源码分发；旧社区版本还存在后续安全维护边界。Phase 1 不需要用遗留对象存储引入额外供应链风险。若未来需要更接近生产的自托管 S3，必须另行核验活跃项目、许可证和安全版本。

## 5. 实施前必须确认的决策

以下选择会改变领域含义、证据模型或存储边界。实施计划以“推荐项”编写，但在用户明确确认前不得执行。

| ID | 决策 | 推荐项 | 替代项与代价 |
| --- | --- | --- | --- |
| D1 | `RawArtifact` 去重范围 | 唯一键为 `(source_id, content_sha256)`；只把完全相同的固定捕获事实视为重放 | 仅按哈希全局去重会丢失来源归属；按 URL 去重会重复存储同一内容 |
| D2 | 重复内容但捕获元数据不同 | 拒绝并返回 `RAW_ARTIFACT_PROVENANCE_CONFLICT`；Phase 2 设计独立捕获观察记录 | 静默返回旧行会丢失新抓取事实；本阶段新增第六个领域实体会扩大范围 |
| D3 | `Opportunity.current_version` | Phase 1 允许 `null`，含义是稳定身份已建立但尚无 Phase 3 版本；Phase 3 创建首版后写入正整数 | 写入 `1` 但没有 `OpportunityVersion` 会制造不可回放的悬空版本；不落库 Opportunity 会削弱实体分离证据 |
| D4 | 原始对象定位 | 数据库存 `storage_bucket` 与 `object_key`；契约向外组合为 `s3://bucket/key` 的 `storage_uri` | 保存 endpoint 会把环境配置写入事实；只保存 URI 难以施加对象键约束 |
| D5 | `EvidenceRef` 身份 | v0.1 公共 Schema 保持值对象；数据库增加内部 `evidence_ref_id` UUIDv7，并用复合外键锁定 Document/Artifact 配对 | 把 ID 加入公共 Schema 会扩大公开契约；复合自然主键会让 Phase 3 引用过重 |
| D6 | 本地 S3 实现 | `boto3` 适配器 + Moto 5.2.2；数据只用于本地/CI，不代表生产选择 | LocalStack 更重；文件系统不验证 S3；MinIO 当前维护边界不稳妥 |
| D7 | 固定官方样本 | GOV.UK Content API 的 Civil Service Fast Stream 官方新闻 JSON；OGL v3.0；仅作为契约样本 | 浙江/中国样本更贴近首发市场，但在提交完整原始页面前需要独立确认转载与开放许可 |

## 6. v0.1 领域契约

### 6.1 公共基础类型

| 类型 | 约束 |
| --- | --- |
| `EntityId` | RFC 9562 UUIDv7 |
| `PublicId` | `src_` 或 `opp_` 前缀 + 32 位小写十六进制；与内部 ID 独立 |
| `Instant` | 带时区的 RFC 3339；进入系统后转 UTC |
| `Sha256` | 64 位小写十六进制 |
| `S3Uri` | `s3://<bucket>/<object_key>`，不含 endpoint 和凭据 |
| `Confidence` | 十进制 `[0, 1]` |

JSON 字段使用 `snake_case`。未知使用 `null` 或明确枚举，禁止空字符串代替未知。

### 6.2 `Source`

```yaml
source_id: EntityId
public_id: PublicId  # src_...
canonical_url: absolute http/https URL
authority_name: non-empty string
tier: OFFICIAL_PRIMARY | OFFICIAL_AGGREGATOR | TRUSTED_SECONDARY | COMMUNITY_SIGNAL
jurisdiction: string | null
active: boolean
created_at: Instant
updated_at: Instant
```

不变量：`canonical_url` 唯一；`updated_at >= created_at`。Phase 1 没有更新 Source 等级的应用服务，因此不提前实现审核历史。

### 6.3 `RawArtifact`

```yaml
artifact_id: EntityId
source_id: EntityId
requested_url: absolute http/https URL
resolved_url: absolute http/https URL
retrieved_at: Instant
http_status: integer | null
media_type: string | null
content_sha256: Sha256
storage_uri: S3Uri
byte_size: positive integer
collector_version: non-empty string
metadata_schema_version: non-empty string
```

Phase 1 中的“重复导入”是同一固定捕获事实的重放，不是一次新的网络抓取。相同 `(source_id, content_sha256)` 且所有捕获元数据相同，返回原行并标记 `created=false`；哈希相同但 URL、时间、状态、媒体类型或采集版本不同，拒绝并暴露来源冲突。Phase 2 在进入实时采集前必须单独设计“每次抓取观察记录”，不得让 Phase 1 的幂等规则静默吞掉新抓取事实。

### 6.4 `Document`

```yaml
document_id: EntityId
artifact_id: EntityId
title: string | null
published_at: Instant | null
language: BCP 47 language tag
extracted_text_uri: S3Uri | null
parser_name: non-empty string
parser_version: non-empty string
parse_confidence: Confidence | null
created_at: Instant
```

Phase 1 固定样本使用 `parser_name=phase1_fixture_manifest`，只读取与样本一起审核过的标题、发布时间和语言，不实现通用 JSON 解析器。`extracted_text_uri` 保持 `null`。解析或结构化结果永远使用不同对象键，不能写回 `RawArtifact.storage_uri`。

### 6.5 `Opportunity`

```yaml
opportunity_id: EntityId
public_id: PublicId  # opp_...
type: OpportunityType
canonical_title: non-empty string
issuer_name: non-empty string
jurisdiction: string | null
current_version: positive integer | null
status: DRAFT | OPEN | CLOSING_SOON | CLOSED | CANCELLED | SUPERSEDED | UNKNOWN
publication_status: INTERNAL | READY | PUBLISHED | WITHDRAWN
created_at: Instant
updated_at: Instant
```

`current_version=null` 只表示 Phase 1 已建立稳定身份、尚未进入 Phase 3 版本化；不能解释为版本 `0`。固定样本 Opportunity 使用 `status=UNKNOWN`、`publication_status=INTERNAL`，因为新闻文档不能证明当前申请窗口。不得从样本推断“开放”“符合”或其他业务事实。

### 6.6 `EvidenceRef`

```yaml
document_id: EntityId
artifact_id: EntityId
locator:
  kind: page | paragraph | css_selector | text_span | full_document
  value: string
quote_sha256: Sha256 | null
```

Phase 1 只使用 `kind=full_document`，且 `value="*"`；`quote_sha256` 等于整个固定样本原始字节的 SHA-256。数据库必须证明 `document_id` 指向的 Document 正好由同一个 `artifact_id` 产生，不能拼接不相干的文档与原件。更细的页、段落、CSS、文本跨度语义在对应解析器进入 Phase 2 时分别定义。

### 6.7 Schema 作者源与导出

- `backend/src/deepaha/contracts/common.py` 定义基础类型、UTC 和 UUIDv7 校验。
- `backend/src/deepaha/contracts/phase1.py` 定义五个 Pydantic v2 Schema 与受控枚举。
- `backend/src/deepaha/contracts/export.py` 以固定顺序、UTF-8、两空格缩进、结尾换行导出五个 JSON Schema。
- 导出物保存到 `contracts/schemas/v0.1.0/`，并由测试证明重新导出没有差异。
- `contracts/examples/v0.1.0/phase-1-official-sample.json` 保存五个 Schema 的可校验例子；例子明确标注内部/未知状态，不作为 Gold 业务事实。

## 7. PostgreSQL 18 持久化设计

### 7.1 迁移与会话

- 使用 SQLAlchemy 2.x typed declarative mapping、Psycopg 3 和显式事务。
- Alembic 是唯一数据库迁移入口；应用启动不调用 `create_all()`。
- PostgreSQL 必须满足 `180000 <= server_version_num < 190000`。
- 数据库连接只从 `DEEPAHA_DATABASE_URL` 读取；日志不得输出密码。
- 初始迁移可从空库升级到 `head`，可回退到 `base`，再升级到 `head`。

### 7.2 表与关键约束

#### `sources`

- 主键 `source_id uuid default uuidv7()`，检查 `uuid_extract_version(source_id)=7`。
- `public_id` 唯一，检查 `^src_[0-9a-f]{32}$`。
- `canonical_url` 唯一且非空。
- `tier` 使用 `varchar` + CHECK，不使用 PostgreSQL native enum，避免枚举演进被数据库类型绑定。
- `updated_at >= created_at`。

#### `raw_artifacts`

- 主键 UUIDv7；`source_id` 外键指向 `sources`，删除受限。
- 唯一 `(source_id, content_sha256)`。
- SHA-256 检查 `^[0-9a-f]{64}$`；`byte_size > 0`；HTTP 状态为空或在 `100..599`。
- 持久化 `storage_bucket` 与 `object_key`；对象键检查为 `raw/sha256/<前两位>/<完整哈希>`。
- `storage_uri` 是模型属性，不额外持久化 endpoint。

#### `documents`

- 主键 UUIDv7；`artifact_id` 外键指向 `raw_artifacts`，删除受限。
- 唯一 `(artifact_id, parser_name, parser_version)`，允许同一原件由未来解析器版本产生多个 Document。
- 额外唯一 `(document_id, artifact_id)`，供 EvidenceRef 复合外键验证来源配对。
- `parse_confidence` 为空或在 `[0,1]`。

#### `opportunities`

- 主键 UUIDv7；`public_id` 唯一并检查 `^opp_[0-9a-f]{32}$`。
- 不含 `document_id`、`artifact_id` 或原始文本列。
- `current_version` 为空或 `>=1`，不允许 `0`。
- `type`、`status`、`publication_status` 使用 `varchar` + CHECK。
- `updated_at >= created_at`。

#### `evidence_refs`

- 内部主键 `evidence_ref_id` UUIDv7，不进入 v0.1 公共 Schema。
- `(document_id, artifact_id)` 复合外键指向 `documents(document_id, artifact_id)`。
- Phase 1 CHECK 要求 `full_document` 的 `locator_value='*'`；其他 locator kind 允许保存但本阶段不生成。
- `quote_sha256` 为空或为 64 位小写十六进制。

### 7.3 Schema、模型和迁移一致性

一致性不通过“快照整库 SQL”证明，而通过三类独立检查：

1. JSON Schema 属性与 Pydantic `model_fields` 完全一致。
2. Alembic `compare_metadata` 对已升级数据库和 SQLAlchemy `Base.metadata` 返回空差异。
3. 针对关键约束执行真实 PostgreSQL 写入反例：非 UUIDv7、错误哈希、负大小、重复来源内容、EvidenceRef 文档/原件错配、Opportunity 版本 `0` 必须被数据库拒绝。

## 8. S3 兼容对象存储

### 8.1 接口

```python
class ObjectStore(Protocol):
    def ensure_bucket(self) -> None: ...
    def put_bytes_if_absent(
        self,
        *,
        key: str,
        content: bytes,
        media_type: str | None,
        sha256: str,
    ) -> ObjectMetadata: ...
    def get_bytes(self, *, key: str) -> bytes: ...
    def stat(self, *, key: str) -> ObjectMetadata: ...
```

`ObjectMetadata` 至少包含 `bucket`、`key`、`byte_size`、`sha256` 和 `media_type`。

### 8.2 内容寻址与不可变性

对象键固定为：

```text
raw/sha256/{content_sha256[0:2]}/{content_sha256}
```

写入使用条件请求，目标不存在时才创建；目标已存在时读取元数据并验证哈希与大小。相同内容复用对象，不同内容绝不覆盖同一键。数据库事务失败后不删除对象，因为该对象键可能被并发导入复用；内容寻址的孤立对象可以由未来受审计清理流程处理，本阶段不实现清理器。

### 8.3 本地实现

- 本地/CI 运行 `motoserver/moto:5.2.2`，只启用测试凭据和测试桶。
- 应用仍通过标准 `boto3` S3 client 访问 endpoint，不依赖 Moto 私有 API。
- endpoint、region、bucket、access key、secret key 全部来自环境设置。
- 本地 PostgreSQL 18 把 `/var/lib/postgresql` 挂载为 Compose `tmpfs`；该路径符合 18+ 官方镜像的新 `PGDATA`/`VOLUME` 布局，避免匿名数据库卷跨验证遗留。
- Moto 数据不挂载到仓库目录，不提交对象内容、数据库文件或容器卷。
- 生产 S3 供应商与部署拓扑不在 Phase 1 决策内。

## 9. 固定官方样本

### 9.1 选择

固定响应：

```text
https://www.gov.uk/api/content/government/news/civil-service-fast-stream-named-uks-top-graduate-employer
```

该 URL 是 GOV.UK Content API 的官方 JSON 内容，描述 Civil Service Fast Stream。GOV.UK 说明大多数内容以 Open Government Licence v3.0 发布，可在遵守署名等条件下复用。选择它的原因是：

- 官方发布者和稳定来源可公开核验；
- 许可边界清晰，可把完整 JSON 响应作为测试夹具提交；
- JSON 原始字节较小，不含图片文件或真实用户数据；
- 文档标题是新闻标题，而 Opportunity 标题是项目身份，能直观证明 `Document != Opportunity`；
- 它只用于契约与证据链测试，不作为 DeepAha 中国首发市场的 Gold 样本或商业证据。

设计阶段的只读捕获身份已经固定，实施时必须取得同一组字节；若官方响应已经变化，则停止样本 Task 并重新评审，而不是静默接受新内容：

| 字段 | 固定值 |
| --- | --- |
| `retrieved_at` | `2026-08-21T09:59:08.005Z` |
| `http_status` | `200` |
| `media_type` | `application/json; charset=utf-8` |
| `byte_size` | `11662` |
| `content_sha256` | `1589f9177e197a578c8d37bd5a3bc869a17d7b0936f156666f69a2f88fbb9d2b` |
| `object_key` | `raw/sha256/15/1589f9177e197a578c8d37bd5a3bc869a17d7b0936f156666f69a2f88fbb9d2b` |

### 9.2 仓库内容

```text
backend/tests/fixtures/official/
├── civil-service-fast-stream-news-2025.json
├── civil-service-fast-stream-news-2025.manifest.json
└── README.md
```

manifest 必须保存：请求 URL、解析后 URL、实际捕获时间、HTTP 状态、媒体类型、字节数、SHA-256、OGL v3.0 名称与 URL、署名文本、捕获工具版本、元数据 Schema 版本，以及本样本“不代表当前申请开放、不代表中国首发覆盖”的限制。

实现时只把与上表身份完全一致的响应写入 fixture，并把同一组值写入 manifest。默认测试只读仓库夹具，不重新联网，也不把未来网页与固定哈希强行比较。

### 9.3 样本实体语义

- `Source.authority_name`：从官方响应发布者读取并固定在 manifest。
- `RawArtifact`：完整 JSON 响应原始字节。
- `Document.title`：官方新闻标题。
- `Opportunity.canonical_title`：`Civil Service Fast Stream`。
- `Opportunity.type`：`CIVIL_SERVICE`。
- `Opportunity.status`：`UNKNOWN`。
- `Opportunity.publication_status`：`INTERNAL`。
- `Opportunity.current_version`：`null`。
- `EvidenceRef`：`full_document` / `*`，quote hash 等于整个原始响应哈希。

样本不生成申请截止日、资格条件、地区适配或推荐结论。

## 10. 数据流与事务边界

```text
固定 fixture bytes + manifest
  -> 校验 manifest、许可字段、字节数和 SHA-256
  -> 获取或创建 Source
  -> 计算 content_sha256 与内容寻址 object_key
  -> S3 put-if-absent，并回读 metadata
  -> PostgreSQL INSERT RawArtifact ON CONFLICT DO NOTHING
  -> 相同捕获事实：返回已有 RawArtifact
  -> 不同捕获元数据：拒绝 provenance conflict
  -> 创建固定样本 Document
  -> 创建 full_document EvidenceRef
  -> 创建 INTERNAL / UNKNOWN / unversioned Opportunity
  -> 读回原始字节并再次校验 SHA-256
```

对象存储与 PostgreSQL 没有分布式事务。顺序固定为“对象成功写入并验证，再提交数据库事实”。如果数据库失败，对象保持不可变并允许重试；不能在回滚时删除可能被共享的内容地址对象。

## 11. 失败模式

| 失败 | 行为 | 可验证证据 |
| --- | --- | --- |
| fixture 与 manifest 哈希/大小不同 | 导入前拒绝，不写对象和数据库 | 单元测试 |
| S3 已有同键同内容 | 复用并返回相同元数据 | Moto 集成测试 |
| S3 已有同键但元数据不一致 | 报完整性错误，不覆盖 | Moto 集成测试 |
| 同一捕获事实重复导入 | 返回相同 `artifact_id`，表中只有一行 | PostgreSQL 集成测试 |
| 同哈希但捕获元数据不同 | 报 `RAW_ARTIFACT_PROVENANCE_CONFLICT` | PostgreSQL 集成测试 |
| 对象写入成功、数据库提交失败 | 保留对象；重试可恢复 | 故障注入测试 |
| EvidenceRef 拼错 Artifact | 复合外键拒绝 | 真实数据库约束测试 |
| `current_version=0` | CHECK 拒绝 | 真实数据库约束测试 |
| PostgreSQL 不是 18.x | 集成验证失败 | 版本断言 |
| 迁移与 ORM 漂移 | `compare_metadata` 非空并失败 | 迁移契约测试 |
| JSON Schema 导出漂移 | 重新导出与提交文件不同并失败 | 契约测试 |
| 官方页面之后变化 | 固定 fixture 不变；来源 URL 仍供人工核验 | manifest + 离线测试 |

## 12. 测试策略

### 12.1 契约测试

- 五个有效例子通过 Pydantic 与 JSON Schema 双重验证。
- UUIDv4、无时区时间、错误哈希、空 PublicId、非法枚举、`current_version=0` 和非法 locator 被拒绝。
- 重新导出的 JSON Schema 与仓库版本逐字节一致。

### 12.2 数据库集成测试

- PostgreSQL 18 版本检查。
- Alembic 空库升级、回退、再升级。
- ORM metadata 与迁移后的数据库无差异。
- 主键、外键、唯一键和 CHECK 反例。
- Schema 与 ORM 的持久化字段映射显式核对。

### 12.3 对象存储集成测试

- 首次写入、重复写入、读取、head metadata、哈希验证和拒绝冲突。
- 测试凭据只存在于测试环境变量。

### 12.4 纵向契约测试

- 固定样本第一次导入产生一个 RawArtifact。
- 第二次导入返回同一 ID，RawArtifact 行数仍为 `1`。
- 对象回读字节与 fixture 完全一致，SHA-256 与 manifest/数据库相同。
- `Document` 和 `Opportunity` 的 ID、表、标题和职责不同；两张表都没有把另一方当作主键或原始内容容器。
- EvidenceRef 的 Document/Artifact 配对由数据库外键保证。

## 13. Phase 1 Gate 设计

### 13.1 Gate 状态

- 实施开始后 Gate 为 `OPEN`。
- 只有本地新鲜环境与远程 CI 都有实际成功证据时才可改为 `CLOSED`。
- spec、plan、目标阈值或预期输出不能作为通过证据。

### 13.2 新鲜环境验证

验证入口：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
powershell -ExecutionPolicy Bypass -File scripts/verify-phase1.ps1
```

`verify-phase1.ps1` 使用独立 Compose project 启动 PostgreSQL 18.4 与 Moto 5.2.2，运行迁移、契约/集成/纵向测试和 Alembic 漂移检查，然后停止并删除本次临时容器。脚本不得删除用户既有数据库、对象存储目录或非本次 project 的卷。

### 13.3 CI

在现有 `backend-quality` 与 `web-quality` 之外增加 `integration`：

- 固定 Python 3.14、PostgreSQL 18.4 和 Moto 5.2.2。
- 从锁文件安装。
- 升级迁移至 head。
- 运行 `pytest -m integration` 和 `alembic check`。
- 不访问固定样本的网络来源。

### 13.4 Gate 证据包

```text
docs/gates/phase-1/
├── README.md
├── acceptance-results.md
├── test-summary.md
├── sample-provenance.md
└── deferred-decisions.md
```

- `README.md`：范围、结论、Gate 状态、验证提交和 CI 链接。
- `acceptance-results.md`：逐条映射退出条件与实际命令/断言。
- `test-summary.md`：运行时版本、命令、退出码、测试数量和迁移 revision。
- `sample-provenance.md`：来源、时间、许可、哈希、大小、对象键和限制。
- `deferred-decisions.md`：Phase 2 抓取观察实体、通用 parser、生产 S3 和 OpportunityVersion。

## 14. 成功标准追踪

| Phase 1 退出条件 | 设计响应 |
| --- | --- |
| 重复导入不产生第二份 RawArtifact | `(source_id, sha256)` 唯一约束 + `ON CONFLICT` + 纵向测试 |
| 原始字节和五类元数据共同复现 | 固定 fixture + manifest + S3 回读 + DB bucket/key/hash/time/URL |
| Document 与 Opportunity 明确分离 | 独立 Schema、类、表、ID、标题和生命周期；无直接替代字段 |
| Schema、迁移和契约测试一致 | 确定性 Schema 导出、Alembic compare_metadata、真实约束反例 |
| 新鲜环境可复现 | 锁文件、固定容器版本、离线 fixture、统一脚本、CI integration、Gate 证据包 |

## 15. 风险与缓解

1. **RawArtifact 与抓取事实的语义张力。** Phase 1 严格限定为固定捕获重放；元数据不同直接失败。Phase 2 在实时抓取前必须补足观察记录，不允许沿用静默去重。
2. **Opportunity 尚无版本表。** `current_version=null` 和 `INTERNAL/UNKNOWN` 防止制造已发布、可回放的假象；Phase 3 才创建首个版本。
3. **Moto 与生产 S3 存在差异。** Phase 1 只承诺使用标准 S3 子集；生产供应商兼容测试在选型后增加。
4. **固定样本不是中国首发 Gold 样本。** 它只用于工程契约和许可安全；中国官方样本进入 Gold 前单独评审许可、业务适配和证据粒度。
5. **对象写入与数据库提交非原子。** 内容寻址、先对象后数据库、禁止回滚删除，使重试安全；孤立对象清理不在本阶段。
6. **约束过度锁死未来解析器。** Phase 1 只对 `full_document` 生成路径做强断言；其他 locator 值域在对应解析器出现时再稳定。

## 16. 明确未做

- 没有实现或验证任何 Phase 1 代码。
- 没有创建数据库、对象桶、迁移或样本对象。
- 没有修改 Phase 0 历史 Gate 证据。
- 没有把 Run `32467979392` 写成 Phase 1 证据；它只证明当前 Phase 0 基线质量作业成功。
- 没有新增 API、Worker、实时网络路径或业务 UI。
- 没有进入 Phase 2 或提前定义 OpportunityVersion、解析器、规则与资格行为。

## 17. 外部技术与许可参考

- [PostgreSQL 18 UUID functions](https://www.postgresql.org/docs/18/functions-uuid.html)
- [Python 3.14 uuid module](https://docs.python.org/3.14/library/uuid.html)
- [Moto server mode](https://docs.getmoto.org/en/latest/docs/server_mode.html)
- [GOV.UK terms and conditions](https://www.gov.uk/help/terms-conditions)
- [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)
- [固定官方样本的公开页面](https://www.gov.uk/government/news/civil-service-fast-stream-named-uks-top-graduate-employer)
- [MinIO community repository status](https://github.com/minio/minio)
