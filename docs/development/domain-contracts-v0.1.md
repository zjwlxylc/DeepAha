# DeepAha 领域契约 v0.1

> 状态：`PROPOSED`  
> 契约版本：`0.1.0`  
> 适用阶段：Phase 1—Phase 6 设计基线  
> 来源基线：`文档/DeepAha_青年机会智能系统_Blueprint_v1.0.1.docx`

## 1. 目的

本文定义 DeepAha 最早期的领域语言、数据边界和可演进接口。它不是数据库表设计，也不承诺 Phase 0 一次实现全部对象；其作用是避免采集、规则、匹配和评估模块各自发明不兼容的数据结构。

实现优先级遵循：原始证据（raw evidence）不可丢失，结构化结论可重建，公开结论可追溯，用户判断必须带状态与理由。

## 2. 基础类型

| 类型 | 约束 | 用途 |
|---|---|---|
| `EntityId` | UUIDv7 | 内部实体主键，按时间大致有序 |
| `PublicId` | `src_` 或 `opp_` 前缀加 32 位小写十六进制；稳定且不含敏感信息 | 对外 API 标识 |
| `Instant` | RFC 3339 UTC，例如 `2026-08-21T08:00:00Z` | 系统时间点 |
| `LocalDate` | ISO 8601 日期，例如 `2026-08-21` | 截止日期等业务日期 |
| `Sha256` | 64 位小写十六进制 | 内容去重和完整性验证 |
| `S3Uri` | `s3://<bucket>/<object_key>`，不含 endpoint 或凭据 | 原始或派生对象定位 |
| `VersionNumber` | 从 `1` 开始递增的整数 | 聚合根版本 |
| `Confidence` | `[0, 1]` 小数；不能代替证据 | 模型或解析置信度 |
| `JsonObject` | 有版本、可验证的 JSON 对象 | 尚未稳定的扩展字段 |

约定：

- JSON 字段与 API 使用 `snake_case`；TypeScript 客户端在边界层转换，不在服务端混用命名。
- 金额不得使用二进制浮点数，统一使用十进制定点值与 ISO 4217 币种。
- 所有时间点持久化为 UTC；原文中的时区和日期表达另行保留。
- 未知、缺失、不适用必须是不同语义，不能统一写成空字符串。
- 正式字段不能仅依靠自然语言文本表达状态。

## 3. 受控枚举

### 3.1 来源等级 `SourceTier`

| 值 | 含义 |
|---|---|
| `OFFICIAL_PRIMARY` | 发布政策或机会的第一方机构 |
| `OFFICIAL_AGGREGATOR` | 官方汇总、转载或服务平台 |
| `TRUSTED_SECONDARY` | 可核查的可信二级来源 |
| `COMMUNITY_SIGNAL` | 社区线索，仅用于发现，不可单独支撑正式结论 |

### 3.2 机会类型 `OpportunityType`

- `PUBLIC_INSTITUTION_JOB`：事业单位招聘
- `STATE_OWNED_ENTERPRISE_JOB`：国有企业招聘
- `CIVIL_SERVICE`：公务员与选调相关机会
- `GRASSROOTS_PROGRAM`：基层项目
- `YOUTH_POLICY_BENEFIT`：青年政策与权益
- `POSTGRAD_RECOMMENDATION`：推免与保研机会
- `ADMISSION_CHANGE`：升学政策或招生变化

类型增加需要迁移说明和 Golden Dataset（黄金数据集）样例，不能直接接受任意字符串。

### 3.3 机会状态 `OpportunityStatus`

`DRAFT`、`OPEN`、`CLOSING_SOON`、`CLOSED`、`CANCELLED`、`SUPERSEDED`、`UNKNOWN`

### 3.4 资格状态 `EligibilityStatus`

| 值 | 含义 |
|---|---|
| `ELIGIBLE` | 已知条件下满足 |
| `LIKELY_ELIGIBLE` | 已满足硬条件，但仍有非冲突性信息或语义映射需要确认 |
| `UNCERTAIN` | 信息缺失、公告模糊、证据冲突或只有模型语义推断 |
| `INELIGIBLE` | 存在明确不满足项 |

`INELIGIBLE` 必须有确定性冲突规则和官方证据；任何信息缺失、规则歧义或证据冲突都必须保持 `UNCERTAIN`，不得自动升级为“符合”或降级为“不符合”。

### 3.5 审核与发布状态

- `ReviewStatus`：`NOT_REQUIRED`、`PENDING`、`APPROVED`、`REJECTED`
- `PublicationStatus`：`INTERNAL`、`READY`、`PUBLISHED`、`WITHDRAWN`

## 4. 核心契约

以下 YAML 用于表达逻辑字段，不规定具体序列化工具或数据库列名。

### 4.1 `Source`

```yaml
source_id: EntityId
public_id: PublicId
canonical_url: string
authority_name: string
tier: SourceTier
jurisdiction: string | null
active: boolean
created_at: Instant
updated_at: Instant
```

不变量：规范 URL 唯一；来源等级变更必须记录操作者、原因和时间。

### 4.2 `RawArtifact`

```yaml
artifact_id: EntityId
source_id: EntityId
requested_url: string
resolved_url: string
retrieved_at: Instant
http_status: integer | null
media_type: string | null
content_sha256: Sha256
storage_uri: S3Uri
byte_size: positive integer
collector_version: string
metadata_schema_version: string
```

不变量：原始内容采用不可变存储。Phase 1 固定捕获重放以 `(source_id, content_sha256)` 去重；只有全部捕获元数据一致才返回原记录，元数据不一致必须报告 `RAW_ARTIFACT_PROVENANCE_CONFLICT`。数据库把公共 `storage_uri` 拆为 `storage_bucket` 与 `object_key`，不持久化 endpoint。进入实时采集前，Phase 2 必须另行定义每次抓取观察记录，不得静默吞掉新的抓取事实。

### 4.3 `Document`

```yaml
document_id: EntityId
artifact_id: EntityId
title: string | null
published_at: Instant | null
language: string
extracted_text_uri: string | null
parser_name: string
parser_version: string
parse_confidence: Confidence | null
created_at: Instant
```

解析失败不删除 `RawArtifact`；错误应记录为可重试的处理事件。

### 4.4 `EvidenceRef`

```yaml
document_id: EntityId
artifact_id: EntityId
locator:
  kind: page | paragraph | css_selector | text_span | full_document
  value: string
quote_sha256: Sha256 | null
```

`EvidenceRef` 是结论与原文之间的最小追溯单元。公共 Schema 保持值对象；数据库可增加不公开的内部 UUIDv7，并用 `(document_id, artifact_id)` 复合外键保证文档与原件配对。Phase 1 的 `full_document` locator 固定使用 `value="*"`。公开引用必须能回到正式来源；社区线索只能作为发现路径。

### 4.5 `Opportunity`

```yaml
opportunity_id: EntityId
public_id: PublicId
type: OpportunityType
canonical_title: string
issuer_name: string
jurisdiction: string | null
current_version: VersionNumber | null
status: OpportunityStatus
publication_status: PublicationStatus
created_at: Instant
updated_at: Instant
```

`Opportunity` 是稳定身份，内容变化存入版本；不得通过覆盖当前记录抹去历史。Phase 1 尚未实现 `OpportunityVersion` 时允许 `current_version=null`，表示稳定身份已建立但尚无版本；不得写入悬空的版本 `1` 或用 `0` 代替未知。

### 4.6 `OpportunityVersion`

```yaml
opportunity_id: EntityId
version: VersionNumber
effective_from: Instant
effective_to: Instant | null
summary: string
application_window:
  opens_on: LocalDate | null
  closes_on: LocalDate | null
  timezone: string | null
locations: [string]
application_url: string | null
eligibility_rule_set_id: EntityId | null
evidence_refs: [EvidenceRef]
content_sha256: Sha256
review_status: ReviewStatus
created_at: Instant
```

不变量：同一机会的版本号连续递增；正式发布版本至少有一条 `OFFICIAL_PRIMARY` 或经批准的 `OFFICIAL_AGGREGATOR` 证据链。

### 4.7 `OpportunityEvent`

```yaml
event_id: EntityId
opportunity_id: EntityId
from_version: VersionNumber | null
to_version: VersionNumber
event_type: CREATED | UPDATED | DEADLINE_CHANGED | CANCELLED | REOPENED
changed_fields: [string]
detected_at: Instant
evidence_refs: [EvidenceRef]
```

### 4.8 `OpportunityAlias`

```yaml
alias_id: EntityId
opportunity_id: EntityId
alias_text: string
alias_type: TITLE | URL | EXTERNAL_ID
source_id: EntityId | null
```

别名用于实体归并（entity resolution）；自动归并必须可撤销并保留依据。

### 4.9 `RuleSet` 与 `RuleExpression`

```yaml
rule_set_id: EntityId
version: VersionNumber
opportunity_id: EntityId
expressions: [RuleExpression]
evidence_refs: [EvidenceRef]
review_status: ReviewStatus
created_at: Instant
```

```yaml
rule_id: EntityId
field: string
operator: EQ | NE | IN | NOT_IN | GTE | LTE | BETWEEN | EXISTS | AND | OR | NOT
value: JsonObject | string | number | boolean | null
reason_template: string
source_text: string
confidence: Confidence | null
```

规则执行器只消费经过模式校验的表达式；大语言模型（Large Language Model, LLM）不得直接给出最终资格结论。

### 4.10 `EligibilityResult`

```yaml
result_id: EntityId
opportunity_id: EntityId
opportunity_version: VersionNumber
rule_set_id: EntityId
user_state_version_id: EntityId
status: EligibilityStatus
satisfied_rule_ids: [EntityId]
failed_rule_ids: [EntityId]
missing_fields: [string]
review_reasons: [string]
evaluated_at: Instant
engine_version: string
```

结果必须绑定机会版本、规则版本和用户状态版本，确保判断可重放。

### 4.11 `UserStateVersion`

```yaml
user_state_version_id: EntityId
user_id: EntityId
version: VersionNumber
effective_at: Instant
attributes: JsonObject
consent_version: string
created_at: Instant
```

首版仅保留匹配所必需的最小属性。敏感字段应分级、加密并设置独立保留期限；日志不得记录原始敏感值。

### 4.12 `MatchSnapshot`

```yaml
snapshot_id: EntityId
user_state_version_id: EntityId
opportunity_id: EntityId
opportunity_version: VersionNumber
eligibility_result_id: EntityId
score: integer
score_version: string
reason_codes: [string]
created_at: Instant
```

分数用于排序，不得替代资格状态。首版必须能用固定规则重算相同结果。

### 4.13 行为、反馈与评估

```yaml
ActionEvent:
  event_id: EntityId
  user_id: EntityId
  opportunity_id: EntityId
  action: VIEWED | SAVED | DISMISSED | APPLIED | COMPLETED
  occurred_at: Instant
  metadata: JsonObject

FeedbackEvent:
  feedback_id: EntityId
  user_id: EntityId | null
  opportunity_id: EntityId | null
  category: INCORRECT | OUTDATED | UNCLEAR | MISSING | OTHER
  message: string
  created_at: Instant

EvaluationRun:
  run_id: EntityId
  dataset_version: string
  component: PARSER | RESOLVER | RULE_ENGINE | MATCHER | GENERATOR
  implementation_version: string
  metrics: JsonObject
  started_at: Instant
  completed_at: Instant
```

## 5. API v1 最小边界

API 使用 `/api/v1` 前缀；Phase 0 只实现健康与版本端点，其余按路线阶段启用。

| 方法 | 路径 | 最早阶段 | 说明 |
|---|---|---:|---|
| `GET` | `/health/live` | 0 | 进程存活，不探测下游依赖 |
| `GET` | `/health/ready` | 0 | 就绪状态；Phase 0 无外部依赖时直接通过 |
| `GET` | `/version` | 0 | 构建和契约版本 |
| `GET` | `/opportunities` | 3 | 公开机会列表 |
| `GET` | `/opportunities/{public_id}` | 3 | 当前版本与证据摘要 |
| `GET` | `/opportunities/{public_id}/changes` | 3 | 版本变化 |
| `POST` | `/eligibility/evaluate` | 4 | 四态资格判断 |
| `POST` | `/matches` | 6 | 用户状态下的可解释匹配 |
| `POST` | `/feedback` | 7 | 纠错与缺失反馈 |

统一错误体：

```json
{
  "error": {
    "code": "stable_machine_code",
    "message": "human-readable message",
    "request_id": "opaque-request-id",
    "details": {}
  }
}
```

## 6. 契约演进规则

1. 契约采用语义化版本（Semantic Versioning）；删除字段、改变字段含义或缩小合法值域属于破坏性变更。
2. 数据库迁移与 API 迁移分开记录；内部表结构不能泄漏成公开契约。
3. 新增必填字段必须先提供默认迁移或双读窗口。
4. 枚举新增必须验证旧客户端的未知值行为。
5. 每次 Gate 评审固定本阶段实际实现的契约版本，并保存迁移和回滚证据。
6. 本文中的 `PROPOSED` 对象只有在对应阶段的测试、迁移和评审通过后才转为 `STABLE`。

## 7. 首轮明确不做

- 不把全部政策知识建成通用知识图谱。
- 不在契约层绑定具体向量数据库或模型供应商。
- 不允许 LLM 绕过规则引擎直接修改正式发布状态。
- 不以单一“匹配分”掩盖资格未知、资料缺失或证据冲突。
- 不为了未来多租户需求提前引入租户抽象。
