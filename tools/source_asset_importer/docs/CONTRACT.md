# 数据与接口契约

## 原设计与本次明确化

原始依据在 `docs/baseline/`。原提示词定义 Handoff 顶层和来源/Brief 内容，但未给出所有嵌套对象的精确程序字段名、附件传输格式或数据库模型。本代码将这些空白明确成 **import-profile.v1**，不声称原文早已规定这些实现细节。

Handoff 的 `schema_version` 不变：`deepaha.source-intelligence.run.v2.2`。`prompt_version` 沿用 `2.2.1`。本工具版本 `0.2.0` 与二者独立。完整示例在 `examples/demo_Handoff.json`；规范化视图 Schema 在 `schemas/normalized_handoff.schema.json`。运行时还执行 Schema 无法充分表达的引用、路径、哈希与数据库检查，以 `contract.py` 为准。

## 输入

选择真实 `.json` 文件。默认最大 JSON 8 MiB、单依赖 20 MiB、整包 64 MiB、最多 100 个依赖、最多 20000 个研究资产、JSON 深度 48。拒绝重复 JSON 字段、非有限数值、非法 Unicode 与已知凭据字段；这不是能识别所有秘密的语义扫描器，用户仍须审查交付资料。

顶层：run_metadata、demand_map、demand_delta、source_candidates、source_graph_delta、agent_acquisition_briefs、lifecycle_delta、pattern_delta、research_evidence、blind_spots、next_exploration_queue、manual_review_manifest、state_snapshot_ref、metrics、warnings，以及 schema_version。缺失必需字段报错，不自动补空数组。

`package_complete=true` 表示本次结构与依赖完整，不代表研究全部完成或历史状态完整。`PARTIAL` / `STANDALONE_RESEARCH_RESULT` 可接收，但显式警告、保持候选；包结构不完整或依赖缺失则拒绝入库。

来源严格保持原提示词列出的档案字段。`recommended_seed` 是 URL 文本；`authority_assessment` 为文本或对象；`evidence_refs` 是证据键数组。URL 仅做语法/明显内部地址排除，不联网、不验证官方身份、不执行网页。

Brief 使用 snake_case 字段，包括 `source_ref`, `brief_key`, `revision`, `base_revision`，及 recommended_seed、source_role、authority、source_topology、opportunity_pattern、navigation_advice、discovery_strategy、source_network、evidence_hotspots、attachment_pattern、change_pattern、observed_access_shape、agent_capability_needs、known_obstacles、stop_escalation_rule、expected_candidate_evidence_package、suggested_revisit_pattern、scout_confidence、recon_evidence、last_checked_at。也接受明确的英文标题式拼写（如 Recommended Seed），只规范字段拼写；同义键值冲突直接拒绝，原始字节不改写。

研究证据使用：evidence_key、url、title、checked_at、observation、locator；支持有限拼写别名（page_title、observed_at 等，见代码）。不虚构页面核验时间和观察内容。

关系使用 from_ref / to_ref / edge_type / evidence_refs / confidence；生命周期提案使用 entity_ref / entity_type（source 或 brief，省略时为 source）/ operation / reason / evidence_refs / confidence。来源与证据引用须在本包或已知同 producer 情报库存在。不解析 ChatGPT 引用标记来假装已取得原件。

需求/盲区/队列等未提供稳定键的内容，按规范化内容生成**内部研究资产键**，明确不是原系统 Source ID；原始字段完整保留。盲区/队列也接受文本项。语义、官方性和建议合理性不由导入器自动裁决。

## 附件扩展

原提示词要求必要文件有清单但没有冻结字段。本次在 `run_metadata.file_dependencies` 采用：

```json
[
  {
    "relative_path": "evidence/sample.txt",
    "sha256": "实际文件SHA256的64位小写十六进制值",
    "size_bytes": 123
  }
]
```

选择 Handoff 后仅从它所在目录读取清单中的文件。禁止绝对路径、盘符、`..`、符号链接、未声明文件及哈希不符。示意值不能用来通过校验。没有依赖则无需该字段。不读取 State 的全量副本；state_snapshot_ref 只是归档定位，不自动当服务器可访问地址。

客户端把原始 JSON 和附件字节 base64 装入 HTTP 信封；服务端重新验证字节和清单。base64 只是传输编码，不是加密；传输安全依赖 HTTPS。文件从未在导入端被执行。

## 两个版本域

`revision / base_revision` 是 **Scout 外部台账版本**；入库后 `system_revision` 是研究资产的**系统版本**。两者不可混用，正式 Source ID 又是另一个身份。

更新可携带已知匹配的外部 base_revision；或显式携带从真实回执得到的 `system_base_revision`。同时提供时两者都不能冲突。外部版本复用但内容不同会拒绝。缺少可核验基线不强制覆盖，要求补齐回执/旧记录或交人工。

来源档案原文未强制 revision。新来源可不提供（保留 null），但以后变更若没有可对照的外部版本，就需明确的 system_base_revision。程序不会替 Scout 捏造历史版本号。

## 数据库处理

整批事务：原始包、所有资产与版本、附件、已解析引用、人工身份、允许动作和回执一起提交或回滚。研究暂存的新版本不替换生产有效来源/Brief。

幂等键为服务端确定的 producer + run_key，核对实际包哈希。同键不同字节拒绝。不同批次继续按稳定候选键与“精确规范化机构 + 完整 URL 身份”检查来源，保留旧入口指纹和别名；URL 查询参数、片段不被删掉。

名字相近不自动合并。旧入口被重新发现但与当前记录不同，提示历史身份冲突而非新建。MERGE / RETIRE / SUPERSEDE 等仅保存研究提案，不执行正式来源治理。

## HTTP API v1（本次新增协议，未声称现网已存在）

统一前缀：`/api/scout-import/v1`。

| 方法与路径 | 作用 |
|---|---|
| GET /capabilities | 验证协议、环境、存储目标、权限、是否接入正式批准 |
| POST /preview | 只读校验并返回计划、冲突与短期确认令牌 |
| POST /commit | 明确确认后重新校验并整批提交 |
| GET /batches/by-run/{run_key} | 按当前身份命名空间查询真实已保存回执 |

POST preview 信封必需键：handoff_b64、files、expected_environment、approve_sources。files 每项仅为 relative_path 和 content_b64。

POST commit 再增加 confirmation_token 与 `confirmed: true`。不接受客户端自报 actor、producer、管理员身份、SQL 或任意 API 路径。拒绝未知动作字段。

身份由宿主授权提供。确认令牌绑定 actor、producer、目标 ID、环境、包哈希、数据库代数、预览计划摘要、政策版本、批准来源清单与过期时间。默认 10 分钟。

## 回执

`schema_version=deepaha.source-intelligence.import-receipt.v1`。包含 run_key、receipt_key、真实系统 batch_id、target_id、environment、reference_backend、执行身份、完成时间、原始/整包哈希、逐项资产 ID/版本映射、实际 Source ID（不可核验则 null）、批准状态、附件哈希与计数。

本地/测试/预发布分别使用 DEMO_IMPORTED、TEST_IMPORTED、STAGING_IMPORTED；仅实际生产集成才可使用 IMPORTED。非生产 feedback_scope 明确禁止冒充正式反馈。`wma_automatically_started=false` 恒为真约束：本工具不负责调度 WMA。

先提交，再独立事务回读；客户端提交响应与 GET 回执再比对。提交响应丢失只尝试查询回执，不自动重发写入。回执上传资料库是可选步骤，不是事务组成部分，也不影响正式采集。
