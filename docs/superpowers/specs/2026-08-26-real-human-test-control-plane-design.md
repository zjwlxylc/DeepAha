# DeepAha 真实人工测试控制台设计

日期：2026-08-26

状态：`PROPOSED`

## 1. 目的

把现有 Windows 一键启动器从“只展示合成工程夹具”扩展为一个可供项目负责人真实体验的本地产品环境。该环境必须同时覆盖：

- 从已审核官方来源执行受控实时采集；
- 保存官方原文、附件和完整采集证据；
- 通过 P9-B Gateway 调用真实 LLM；
- 展示模型输入身份、输出、token、延迟、费用状态和 Ledger；
- 由人类逐条审核 LLM 候选事实和规则；
- 只有人工批准的结果才进入本地公开机会库、个人匹配和行动流程；
- 在停止和重启后保留人工测试成果。

本设计只建立本地人工体验和验证能力。它不启动 Release Qualification，不把本地审核写成生产 Gold，不改变真人参与者仍为 `0` 的事实，也不自动批准生产发布。

## 2. 当前代码事实

1. 现有 `scripts/local-manual-test.ps1` 创建隔离 PostgreSQL/Moto，运行 Migration 后只执行 `tests.manual.seed_local_manual`；数据均为合成 fixture。
2. PostgreSQL 使用 `tmpfs`，停止时执行 `compose down --volumes`，因此结果不会跨轮保存。
3. 官方来源 Registry、20 条采集 Recipe、16 条真实官方资料回放语料和 live qualification 已存在；当前有 8 条 active Recipe。
4. P9-B 已实现 ProviderInvocation、EgressDecision、ModelCall、Attempt、Finalization、Ledger、SourceBundle、ExtractionCandidate、Fact Verification 和 Rule Approval。
5. P9-B 生产代码只有 `RecordedResponseAdapter`，没有真实 Provider Adapter，也没有 API/UI 调用入口。
6. P9-B ExtractionTargetScope 只允许 `OPPORTUNITY` 或 `UNIT`，SourceBundle 和 Gateway Intent 都要求 Opportunity 已存在。
7. 公开目录已有只读服务，但缺少受治理的发布写服务；现有 `PublicCatalogEntry` 也没有“本地人工批准”数据标签。

## 3. 第一性原理与不可破坏约束

### 3.1 可验证真相从官方字节开始

完整信任链必须是：

`官方 URL -> HTTP 观测 -> RawArtifact -> Document/DocumentBlock -> SourceBundleRevision -> ProviderInvocation -> ModelCall Ledger -> ExtractionCandidate -> Human Verification -> VerifiedFactSet -> OpportunityVersion -> PublicCatalogEntry`

任何 UI 结论必须能沿这条链回到官方原文。网页标题、LLM 输出和人工批准都不能替代原始证据。

### 3.2 LLM 是受审计的候选生成器，不是真相源

- LLM 只输出结构化候选事实、资格规则候选、证据块引用和不确定项。
- 缺失、冲突、超出证据或 Schema 无效时必须 abstain 或进入人工审核。
- LLM 不得自动发布 Opportunity，不得直接改变硬资格规则，不得决定 `INELIGIBLE`。
- 生产者身份必须是模型调用，验证者身份必须是人类 reviewer；不得复用同一个 Provider 响应完成“独立验证”。

### 3.3 所有外部副作用必须显式、有限并可停止

- 双击启动只启动本地服务和后台控制页，不自动访问官方站点或 Provider。
- 每一轮 live run 必须由 reviewer 在页面确认来源、Provider、模型和预算后启动。
- 默认官方请求硬上限为 9；LLM 调用硬上限为 8，串行执行。
- 单次 LLM 最大输入 12,000 tokens、最大输出 3,000 tokens、超时 90 秒、temperature 为 0。
- 超限停止后保留已完成证据；Provider outcome unknown 时遵循 P9-B 规则，不盲目重试。

### 3.4 密钥最小暴露

- Agnes AI API Key 使用 Windows DPAPI `CurrentUser` 加密。
- 密文与非敏感 Provider 配置保存到 `%LOCALAPPDATA%\DeepAha\manual-test\`，不放入仓库。
- 文件 ACL 只允许当前 Windows 用户和 SYSTEM；写入使用临时文件加原子替换。
- API Key 不进入命令行参数、环境快照、数据库、Ledger、日志、异常正文或浏览器响应。
- 后台只返回 `configured=true/false` 和更新时间，不回显密钥或尾号。
- 支持更新和删除密钥；删除后所有真实 Provider 操作 fail closed。

### 3.5 本地人工证据与发布证据分离

- live 官方采集标记为 `LIVE_OFFICIAL`，离线官方回放标记为 `OFFICIAL_REPLAY`，合成 fixture 标记为 `SYNTHETIC_FIXTURE`。
- 人工批准进入本地目录时使用 `LOCAL_HUMAN_REVIEWED`，不得冒充 `REAL_GOLD`。
- 页面持续显示 `Release Qualification=NOT_STARTED` 和 `real participants=0`。

## 4. 推荐架构

### 4.1 两层结构

核心层采用可复用的生产级服务：

- OpenAI-compatible Provider Adapter；
- 本地文件 ObjectStore；
- Live acquisition 到 Document 的编排；
- provisional Opportunity、SourceBundle、P9-B extraction、人工事实验证和本地发布服务；
- 数据库中的可恢复运行状态机。

本地壳层只负责 Windows 人工测试：

- DPAPI 密钥保管；
- loopback-only 后台 API 和页面；
- fixture reviewer 会话；
- 一键启动/停止、持久化卷和本地数据清理。

未来正式运行可以替换密钥保管与调度层，但复用采集、Gateway、事实和发布核心服务。

### 4.2 组件

1. `LocalProviderConfigStore`
   - 保存 provider、API base URL、协议、模型、model snapshot 和 DPAPI 密文。
   - URL 禁止 userinfo、query 和 fragment，只允许 HTTPS。

2. `LocalFileObjectStore`
   - 实现现有 ObjectStore Protocol。
   - 根目录固定为 `%LOCALAPPDATA%\DeepAha\manual-test\objects`。
   - object key 必须是规范相对路径；拒绝绝对路径和目录穿越。
   - create-exclusive 写入，重读并验证 SHA-256；不覆盖不一致对象。

3. `OpenAICompatibleProviderAdapter`
   - 只接受已构造的不可变 ProviderInvocation。
   - 使用 Bearer API Key 和配置的 endpoint path；默认协议为 OpenAI Chat Completions compatible。
   - 发送的 provider、model、messages 和 generation parameters 必须与 Gateway hash 的对象一致。
   - 保存原始响应到 ObjectStore，返回内部对象引用和受控 Provider response ID。
   - 429/5xx 映射为 retryable；确定性 4xx 映射为 non-retryable；请求可能已送达但没有响应时抛出 ProviderOutcomeUnknownError。
   - Provider 不报告费用时写 `COST_NOT_REPORTED`，不得估算成已报告金额。

4. `HumanTestRunService` 与独立 worker
   - API 只创建运行记录，不在 HTTP 请求线程中执行长任务。
   - launcher 启动一个独立 worker 进程；worker 使用数据库 lease 串行处理项目。
   - 状态：`CREATED -> ACQUIRING -> BOOTSTRAP_REVIEW/EXTRACTING -> FACT_REVIEW -> RULE_REVIEW -> READY_TO_PUBLISH -> COMPLETED`，以及 `PARTIAL`、`FAILED`、`CANCELLED`。
   - 重启后恢复未结束 run；未知 Provider outcome 进入人工处置而不是重新调用。

5. `ProvisionalOpportunityService`
   - 不扩写或削弱已验收的 P9-B target scope。
   - 对校验通过的 PRIMARY_EVIDENCE Document 创建仅 `INTERNAL` 可见的 provisional Opportunity。
   - title 来自确定性 parser，issuer 来自 Source Registry，status 固定为 `UNKNOWN`，canonical URL 来自采集终态 URL。
   - type 只能来自受治理 Recipe 的 `opportunity_type_hint`；缺少 hint、标题或稳定 URL 时进入 `BOOTSTRAP_REVIEW`，不得调用 LLM。
   - provisional 值必须在 UI 标记为“未验证引导字段”，永不直接公开。

6. `P9BExtractionCoordinator`
   - 为 provisional Opportunity 创建并冻结 SourceBundleRevision。
   - 只选择与 Bundle 精确绑定的 DocumentBlock，并执行最小化与分类。
   - 持久化 source/provider policy、EgressDecision、ModelTaskSpec 和 ModelCallIntent。
   - 调用 GatewayExecutor；解析成功后把每个字段写成 ExtractionCandidate，并绑定 exact block/evidence IDs。

7. `HumanFactReviewService`
   - reviewer 对每个候选选择 `APPROVE`、`REJECT`、`UNKNOWN` 或 `NEEDS_ADJUDICATION` 并填写原因。
   - 使用现有 FactLifecycleService，验证者身份为 `human:<reviewer_id>`。
   - 批准集合生成 VersionedVerifiedFactSet；被拒绝和 unknown 项仍保留。

8. `HumanRuleReviewService`
   - 仅从已验证事实生成 RuleCandidate。
   - reviewer 单独批准规则；没有批准规则时个人资格最高显示 `UNCERTAIN`。
   - 排名或解释不得覆盖硬资格结果。

9. `LocalCatalogPublicationService`
   - 把已验证事实映射为新的 OpportunityVersion，`review_status=APPROVED`。
   - 只有满足公开必填字段、官方证据、人工事实审核和内容使用边界时才创建/更新 PublicCatalogEntry。
   - collection kind 固定为 `LOCAL_HUMAN_REVIEWED`，publication_status 只影响本地环境。
   - 决策幂等；相同 key 加不同请求返回冲突。

## 5. 数据库变更

新增后继 Migration `0030`，不得改写 0023–0029。

新增三张编排表，不复制 P9-B 已有事实：

1. `local_human_test_runs`
   - run ID、mode、不可变 Recipe IDs、provider/model/config snapshot、预算、状态、计数、创建 reviewer、时间和终态原因。

2. `local_human_test_items`
   - item ID、run ID、recipe/source/acquisition evaluation/document/opportunity/source bundle/extraction run/model call/fact set 的可空阶段引用、状态、错误码和时间。

3. `local_human_test_review_decisions`
   - decision ID、item ID、decision kind、reviewer ID、request hash、reason、created_at；为每种操作提供唯一幂等约束。

同时修改：

- reviewer roles 增加 `LOCAL_TEST_OPERATOR`；review purpose 增加 `OPPORTUNITY_FACT_VALIDATION`，保留现有 feedback purpose；
- `public_catalog_entries.collection_kind` 增加 `LOCAL_HUMAN_REVIEWED`；
- 所有 UUID 使用 UUIDv7、时间为带时区值、状态和引用由数据库约束保护。

Provider 密钥和可解密密文绝不进入 Migration 或数据库。

## 6. 后台 API 与权限

所有端点位于 `/api/v1/local-human-test`，并同时要求：

- `environment=development`；
- `local_human_test_enabled=true`；
- 服务绑定 loopback；
- fixture reviewer session；
- 配置和运行操作需要 `LOCAL_TEST_OPERATOR`；
- 事实/规则批准需要 `VALIDATION_REVIEWER`。

端点：

- `GET/PUT /config/provider`
- `DELETE /config/provider/secret`
- `GET /sources`
- `GET/POST /runs`
- `GET /runs/{run_id}`
- `POST /runs/{run_id}/cancel`
- `GET /items` 与 `GET /items/{item_id}`
- `POST /items/{item_id}/bootstrap`
- `POST /items/{item_id}/facts/decision`
- `POST /items/{item_id}/rules/decision`
- `POST /items/{item_id}/publish`
- `POST /data/reset-challenge` 与 `DELETE /data`

写端点必须有 Idempotency-Key。错误响应不得包含 API Key、原始 Provider 错误正文或未授权资源存在性。

## 7. 后台页面

新增 `/review/human-test`，包含：

1. 概览：本地模式、数据标签、RQ 状态、服务/Provider 配置状态和最近运行。
2. Provider 配置：HTTPS base URL、协议、模型、model snapshot、掩码 API Key、保存/更新/删除；不提供密钥读取。
3. 新建运行：默认勾选 8 条 active Recipe，展示每条官方 host、角色、更新时间和请求上限；显示并确认预算。
4. 运行详情：按阶段显示每条 URL、HTTP/validation、Document、ModelCall、token、延迟、费用状态和错误码。
5. 事实审核：官方原文块与 LLM 候选并排，显示 raw/normalized value、confidence、abstention 和 exact evidence locator。
6. 规则审核：规则候选、依赖事实和可能影响；高影响规则醒目标识。
7. 发布预览：展示将写入公开卡片和个人匹配的字段；人工确认后发布。
8. 数据管理：停止不删除；清空要求输入一次性 challenge 并二次确认，且不能在 run 执行中操作。

所有页面必须区分 `LIVE_OFFICIAL`、`OFFICIAL_REPLAY`、`SYNTHETIC_FIXTURE` 和 `LOCAL_HUMAN_REVIEWED`。

## 8. 一键启动与持久化

- PostgreSQL 从 tmpfs 改为确定性 named volume，停止命令不再使用 `--volumes`。
- 本地 ObjectStore 使用 `%LOCALAPPDATA%` 文件目录，不依赖可丢失的 Moto 内存状态。
- 首次启动导入现有 Source Registry、active Recipe 和 reviewer，但不得重复覆盖人工结果。
- 合成 fixture 作为单独的“加载演示数据”操作，不再默认混入真实库。
- launcher 增加 worker 角色、PID/creation-time/command marker 所有权记录和日志。
- 停止仍只清理本轮进程、容器、浏览器 profile 和易失身份文件；持久数据库、对象和 DPAPI 配置保留。
- 清空由后台数据管理操作完成，并精确删除本地 human-test volume/object root；不触碰个人文档或其他 Docker 资源。

## 9. 失败和恢复

- Source 403/挑战页/类型不符：记录 validation，禁止 LLM。
- LLM 未配置或密钥解密失败：run 停在 `FAILED_CONFIG`，不访问 Provider。
- 预算耗尽：run 为 `PARTIAL_BUDGET_EXHAUSTED`，保留完成项。
- Provider 429/5xx：只按 ModelTaskSpec 和 P9-B Attempt 上限重试。
- timeout/连接断开且结果未知：`UNKNOWN_OUTCOME`，要求 reviewer 人工处置。
- JSON/Schema 无效：保存 raw response，item 为 `MODEL_OUTPUT_INVALID`，不生成事实。
- evidence block 不匹配：拒绝候选，记录 `EVIDENCE_BINDING_INVALID`。
- 进程重启：worker 通过 DB lease 恢复；不会重复创建 call 或发布。
- 发布冲突：保持 `READY_TO_PUBLISH` 并展示确定性冲突，不覆盖已有版本。

## 10. 测试策略

所有实现遵循测试驱动开发：先建立会失败的测试，再写最小实现。

- DPAPI：用抽象 protector 单元测试 round-trip、原子写、ACL 失败和日志无秘密；Windows 上运行真实 DPAPI 定向测试。
- LocalFileObjectStore：路径穿越、create-exclusive、hash、并发冲突和重启持久性。
- Provider Adapter：使用本地 HTTP stub 测试完整 payload、响应、token、429/5xx、4xx、timeout-before-send 和 unknown-after-send；不得在自动测试中调用真实 Provider。
- P9-B：证明 Gateway 内部 hash 与发送 payload 一致、未授权 adapter=0、重复 call 幂等、unknown 不重复发送、Ledger 与 raw object hash 一致。
- Acquisition：使用现有 replay 和 HTTP fixture 验证 active Recipe、预算、validation gate 和官方 provenance；常规测试不依赖外网。
- Coordinator：状态机、lease、重启恢复、部分成功、预算耗尽和阶段引用完整性。
- Human review：生产者/验证者独立、证据绑定、拒绝/unknown、规则门和发布幂等。
- API：development/loopback/role/purpose/idempotency/错误脱敏。
- Web：配置、预算确认、运行进度、证据并排、批准/拒绝、发布预览、持久化重启和二次清理。
- 一键验收：启动、离线回放、页面检查、停止、重启后数据仍在、精确清理。
- 真实 smoke：只能由页面显式触发，使用默认硬预算；输出只记录 Provider/model、状态、token、延迟、费用状态和 Ledger ID，不记录密钥或完整敏感响应。

## 11. 分阶段交付

1. 持久化底座、DPAPI 配置与后台只读概览；无外部调用。
2. OpenAI-compatible Adapter 和 P9-B 受控连接验证；默认 stub，真实调用由页面确认。
3. active 官方 Recipe 的 live/replay 运行、Document 列表和证据查看。
4. provisional Opportunity、SourceBundle、真实 LLM extraction 和事实审核。
5. verified fact publication、规则审核、公开目录和个人匹配薄链路。
6. 完整本地人工验收，随后另开独立工程验收；仍不启动 Release Qualification。

每一阶段都必须独立通过测试后才进入下一阶段，不能用后续 UI 掩盖前一阶段的数据或审计缺陷。

## 12. 完成标准

- 用户双击一次即可进入后台，不自动产生外部请求。
- 用户能保存并跨重启使用 DPAPI 加密的 Provider Key。
- 默认 8 条 active 官方 Recipe 可由页面选择并按硬预算运行。
- 至少一条 live 官方 Document 经 P9-B 调用真实 LLM，并显示完整审计证据。
- 每个已发布本地机会都有官方原文、DocumentBlock、ModelCall、ExtractionCandidate、人工决策和 OpportunityVersion 关系。
- 未经人工批准、无证据、Schema 无效或授权失败的内容绝不进入公开目录。
- 停止/重启保留数据；显式清理后只删除本地 human-test 自有数据。
- 自动测试不调用真实 Provider；真实 smoke 由用户显式点击并受预算限制。
- 不提交或输出 API Key，不修改个人资料目录，不推送、不部署、不启动 Release Qualification。
