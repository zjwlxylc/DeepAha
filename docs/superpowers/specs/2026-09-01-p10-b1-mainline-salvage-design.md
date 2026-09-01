# P10-B1 主线打捞设计

日期：2026-09-01
状态：已确认范围内的实施设计
基线：`d806e305c4b9239a81cce0216a237cd90f89f367`

## 1. 目标与成功标准

本任务只恢复一条可验证的官方源原始证据链：系统接收一个已获准的官方源请求，通过现有静态 HTTP 能力取得内容，在任何正式写入前完成来源策略和内容校验，然后一次性持久化来源、原始快照、SHA-256、取得时间、全文件证据定位与冻结的来源包（SourceBundle）血缘。

成功必须同时满足：

1. 请求只允许绑定启用中的官方一手源、启用中的已批准端点、主证据用途和单次静态 HTTP 配方。
2. 成功结果能从冻结的 `SourceBundleRevision` 逐级追溯到 `AcquisitionRun`、`AcquisitionEvaluation`、`CaptureObservation`、`RawArtifact`、`Document`、精确 `ParseAttempt` 和精确 `EvidenceRef`，并能由对象键取回且复核原始字节。
3. 相同幂等键和相同规范化请求载荷的重放直接返回既有冻结结果，不再次发起网络请求，也不新增数据库行或对象。
4. 相同幂等键下的载荷漂移在网络、数据库和对象存储写入前被拒绝。
5. 来源策略拒绝、网络失败、内容校验失败或持久化失败不留下本次请求的半成品正式记录；若对象在数据库事务失败前刚被创建，则按键和 SHA-256 补偿删除。
6. 不创建 Candidate、Opportunity 或资格/发布记录，不调用 Provider，不包含特定 Gold 样本、真实站点标识、坐标或哈希的生产逻辑。
7. 新迁移保持单一 Alembic head；从当前主线 `20260826_0033` 升级保留旧数据和旧 Opportunity 路径；存在新请求历史时降级明确拒绝且不删除数据。

## 2. 范围边界

本次包含：

- 一个冻结的官方源请求契约、结果契约和同步任务入口。
- 现有来源策略、静态 HTTP 传输与内容校验的复用。
- `SourceBundle` 的请求身份扩展，以及相应迁移、约束和不可变守卫。
- 原始 HTML/文本字节的内容寻址对象、完整文件定位和证据血缘持久化。
- 合成离线 HTML fixture、单元测试、PostgreSQL/S3 集成测试和迁移兼容测试。

本次不包含：

- B2–B5、Candidate、Opportunity、资格判断、公开发布或 UI。
- 列表发现、附件跟随、浏览器自动化、Excel、PDF、DOCX、OCR、文档智能（Document Intelligence）或模型网关。
- 真实 Provider、API Key、真实官方站点配置或在线验收。
- 对审计提交或冻结审计证据的修改。

## 3. 方案选择

### 方案 A：最小扩展既有事实链（采用）

为 `SourceBundle` 增加互斥的请求身份 `request_key + request_payload_sha256`，允许尚无 Opportunity 的来源包；复用既有来源、采集、评估、文档和 P9-B 来源包表。取得与校验先在内存完成，成功后在一个数据库事务中创建完整链路，并对新建对象提供失败补偿。

优点是复用已经关闭工程门的血缘约束，不产生第二套平行事实模型，且迁移面只涉及请求身份和可空 Opportunity 绑定。代价是需要为跨 PostgreSQL/S3 的写入增加窄范围补偿，并修正既有不可变触发器对 `NULL` 的比较。

### 方案 B：恢复历史三段式/浏览器 B1（不采用）

历史提交同时带入列表发现、附件、JSON、Excel、浏览器运行时、真实源配置和更广的命令入口。审计已经证明这条路径引入主线集成回归及历史迁移不兼容，且明显超出本任务的最小静态官方内容证据链。

### 方案 C：新建独立 P10 官方证据表（不采用）

单独建表可以避免修改 `SourceBundle`，但会复制 Observation、Evaluation、Run、Document 和来源包已有的身份及血缘语义，给后续 B2 造成双轨迁移与审计债务。

## 4. 请求契约与准入

`OfficialEvidenceRequest` 是冻结、禁止额外字段的契约，包含：

- `request_key`：调用方给出的稳定幂等键，格式为 1–128 位字母、数字、点、下划线、冒号或短横线。
- `source_id`、`endpoint_id`、`recipe_id`：既有 UUIDv7 身份。
- `requested_url`：不得包含凭据，主机必须与端点和配方白名单一致。
- `contract_version = 1.0.0`。

规范化载荷 SHA-256 由契约版本、三个身份和规范化 URL 生成，不包含运行时间。服务加载数据库中的 Source/Endpoint 和传入的版本化 `SourceRecipe` 后，还必须满足：

- Source 为 `OFFICIAL_PRIMARY` 且启用。
- Endpoint 启用且 `browser_policy = NEVER`，`robots_decision` 为 `ALLOWED` 或 `NOT_APPLICABLE`，`content_use_basis` 不为 `UNKNOWN`，策略版本与配方一致。
- Recipe 启用，`usage_role = PRIMARY_EVIDENCE`，`discovery.kind = NONE`，只有一个 `STATIC_HTTP` 步骤，`maximum_requests = 1`。
- 请求 URL 通过端点与配方的主机、路径、媒体类型和响应大小限制；运行时最多发起一次请求且不跟随 3xx，超时取 Endpoint 与配方总预算的较小值，响应 MIME 必须精确进入白名单。

以上任一条件不满足均在传输和正式写入前失败。

## 5. 执行与持久化流程

```text
OfficialEvidenceTask
  -> 校验冻结请求契约并计算 payload SHA-256
  -> 以 request_key 读取既有 SourceBundle
       -> hash 相同且存在 FROZEN revision：返回重放结果
       -> hash 不同：PAYLOAD_DRIFT
  -> PostgreSQL advisory transaction lock(request_key)
  -> 再次检查重放/漂移，加载并校验 Source / Endpoint / SourceRecipe
  -> PostgreSQL advisory transaction lock(endpoint_id)
  -> 锁内检查限速，collect_http_attempts 最多一次静态请求
  -> ContentValidator 在内存确认 VALID
  -> PostgreSQL advisory transaction lock(content_sha256)
  -> 单事务写入：
       按 (source_id, content_sha256) 复用或创建 RawArtifact + 新 CaptureObservation
       AcquisitionEvaluation(VALID) + AcquisitionRun(COMPLETE)
       Document(raw snapshot) + ParseAttempt(SUCCEEDED)
       EvidenceRef(full_document, "*", quote_sha256=content SHA)
       SourceBundle(request identity)
       SourceBundleRevision + PRIMARY_NOTICE member(精确 evidence/parse ID) -> FROZEN
  -> 提交并返回不可变结果
```

这里的 `Document` 只声明原始快照身份，解析器名为 `deepaha-raw-snapshot`；不抽取正文块、不运行文档智能。`EvidenceRef` 使用现有 `0.1.0/full_document/*` 定位，`quote_sha256` 等于完整原始字节 SHA-256。

`AcquisitionRun.strategy_attempts` 只保存安全的身份、状态和血缘 ID，不保存响应正文、Cookie、Token 或敏感头。一次请求对应一个 Observation、一个 VALID Evaluation 和一个 COMPLETE Run。

## 6. 幂等、并发与失败原子性

幂等以 `request_key` 为调用身份，以 `request_payload_sha256` 检测语义漂移。第一次数据库查询允许快速重放；未命中后在同一事务内按 `request_key -> endpoint_id -> content_sha256` 的固定顺序取得 PostgreSQL advisory transaction lock。请求锁阻止并发载荷漂移先发网络，Endpoint 锁把限速判断与网络请求串行化，正文锁保护内容对象和补偿。数据库唯一索引是请求身份的最终防线。

网络和内容校验发生在正式写入前，因此这些失败不会产生 Observation、失败 Run 或原始对象。持久化阶段采用一个数据库事务。对象存储无法与 PostgreSQL 组成原子事务，因此服务在写对象前记录该内容键是否已存在：

- 对象原已存在时，任何失败都不删除它。
- 对象及对应 RawArtifact 均由本次新建且数据库事务失败时，仅在当前键的 SHA-256 仍相同时补偿删除；已有 RawArtifact 依赖的缺失对象被恢复后不得补偿删除。
- 补偿失败会以 `OfficialEvidencePersistenceError` 暴露，不能宣称请求完成；数据库仍回滚。该错误要求运维处理孤立对象，不能自动重试为成功。
- 补偿和安全回滚成功后，非既有策略、采集、校验、漂移等领域异常统一包装为 `OFFICIAL_EVIDENCE_PERSISTENCE_FAILED`；对外异常抑制显式底层 cause，不得向调用方或默认 traceback 泄漏 S3、数据库或来源包服务的底层异常类型和消息。

补偿在正文事务锁释放前执行，再回滚数据库事务，避免另一个相同正文请求已提交后被前一失败请求删除对象。精确重放同时校验对象 metadata、实际字节长度和实际 SHA-256，不只信任对象头。

事务提交与可补偿的持久化阶段分开处理。若 `commit()` 返回异常，提交结果可能已经生效，此时不得删除对象或继续把失败当作普通回滚；任务返回 `OFFICIAL_EVIDENCE_COMMIT_OUTCOME_UNKNOWN`，保留对象，并允许调用方用同一请求键重放以确认最终状态。

冻结来源包是成功提交的一部分；任何 DRAFT 来源包都不得被当作成功重放。持久化错误测试通过受控故障注入验证数据库零增量和对象零残留。

## 7. 数据库变更

新迁移 `20260901_0034` 只做以下变更：

1. `source_bundles` 增加可空 `request_key` 与 `request_payload_sha256`。
2. `opportunity_id` 改为可空，并以检查约束保证身份严格互斥：要么 Opportunity 非空且请求字段均空，要么 Opportunity 为空且两个请求字段均非空。
3. 为 `request_key` 建立非空条件下的唯一索引，并约束键和 SHA 格式。
4. `source_bundle_revisions.opportunity_id/opportunity_version` 改为成对可空；新增仅按 `source_bundle_id` 的外键和 `NULL` 安全绑定触发器。
5. 将既有 revision 不可变触发器中的 Opportunity 比较改为 `IS DISTINCT FROM`，避免空值绕过。
6. `source_bundle_members` 增加可空 `evidence_ref_id` 与 `parse_attempt_id`；旧 Opportunity member 可同时为空，请求 member 必须同时非空并与文档、工件、解析契约精确一致。两项身份进入新请求成员哈希，绑定后的 EvidenceRef/ParseAttempt 不可更新或删除。

升级不改写旧行；旧 Opportunity 来源包仍满足新约束。降级前检查新请求身份、无 Opportunity revision 或任一非空 EvidenceRef/ParseAttempt 成员绑定是否存在：存在则明确失败，不删除历史；不存在时恢复 `20260826_0033` 结构和原触发器定义。该拒绝避免删除精确身份列后，旧哈希函数与已冻结成员哈希静默失配。

## 8. 测试与验收

单元测试覆盖：

- 请求规范化哈希稳定、无关运行时间不进入哈希。
- 非官方源、非批准端点、发现型/多请求/浏览器配方和 URL 漂移在传输前拒绝。
- 内容校验失败不进入持久化。

PostgreSQL/S3 集成测试使用通用 `official.example` 和合成 HTML fixture，覆盖：

- 成功后完整的数据库外键血缘、SHA、时间、对象字节、完整文件定位与冻结来源包。
- Candidate 和 Opportunity 行数保持为零。
- 精确重放时各相关表行数、桶内对象数和传输调用数零增量。
- 同键载荷漂移在网络、数据库和对象前零增量。
- 网络/内容失败无正式记录和对象。
- 对象写入后的受控事务失败会回滚数据库并补偿删除新对象。
- 同键漂移和同 Endpoint 的并发请求在 transport 前串行化；相同正文请求在补偿期间由正文锁隔离。
- 同 Source 相同正文、不同 URL 复用 RawArtifact/Document/ParseAttempt/EvidenceRef，但保留各自 Observation、Run 和请求 bundle。
- 精确重放拒绝 metadata 正常但实际对象字节被篡改的情况。
- 3xx 响应不会触发第二次 transport 调用；提交结果未知不会补偿删除可能已提交链路依赖的对象。
- 上传后的普通持久化故障会完成锁内补偿和事务回滚，并以无显式底层 cause 的稳定持久化错误暴露；既有领域错误分类保持不变。cleanup 和 rollback 自身失败也覆盖相同的对外错误边界。

迁移测试覆盖：

- 空数据库升级到唯一 head，`alembic current` 与 `alembic check` 正常。
- 从 `20260826_0033` 创建完整冻结的旧 Opportunity/Version/SourceBundle/Revision/Member 后升级，旧 ID、字段和服务路径保持可用，并能继续创建、冻结下一 revision。
- 无新 B1 历史时可降级到 `20260826_0033` 再升级。
- 有新请求来源包时降级失败且数据仍在。
- Opportunity member 含任一精确 EvidenceRef/ParseAttempt 绑定时降级失败且冻结哈希保持不变。

最终还需运行全仓验证、同一候选环境的完整 integration 矩阵、生产代码 Gold 特例搜索和 Provider 调用搜索。验收结论只说明工程实现与验证结果，不表示真人、真实环境或发布资格已经完成。
