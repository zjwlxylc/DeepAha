# DeepAha 领域契约 v0.2

> 状态：`PROPOSED`
>
> 契约版本：`0.2.0`
>
> 适用阶段：Phase 2 设计与实现
>
> 上位基线：Blueprint v1.2、D8–D12
>
> 当前已验证的运行契约仍是 `0.1.0`。本文只有在 Pydantic、JSON Schema、PostgreSQL 迁移、ORM、契约测试和 Phase 2 Gate 一致通过后，才能转为 `STABLE`。

## 1. 演进目的

v0.2 在不改写 v0.1 历史数据的前提下解决四个 Phase 2 前置问题：

1. 扩展 Blueprint v1.2 已批准的高价值成长机会类型。
2. 用 `CaptureObservation` 区分“不可变内容”与“每次网络观察”。
3. 用 `SourceEndpoint` 保存可执行的采集和内容使用边界。
4. 用版本化、结构化 Evidence Locator 表达 HTML、PDF 和 Excel 定位。

`Document != Opportunity`、原始证据不可覆盖、PostgreSQL 是结构化事实源、对象存储保存不可变字节等 v0.1 不变量继续有效。

## 2. 兼容策略

- `contracts/schemas/v0.1.0/` 永久保留，现有样本和历史记录继续按 v0.1 校验。
- 新 Schema 输出到 `contracts/schemas/v0.2.0/`，不覆盖 v0.1 文件。
- v0.2 EvidenceRef 接受 legacy v0.1 locator 或新的 v0.2 locator；Phase 2 新解析器只生成 v0.2 locator。
- 数据库采用扩展迁移：先增加表、列和新 CHECK，再由新代码写 v0.2；不重写旧 EvidenceRef。
- Opportunity 枚举扩展后，旧七个值仍保持原义和合法性。

## 3. 新增和扩展枚举

### 3.1 `OpportunityTypeV02`

保留 v0.1 全部值，并增加：

- `COMPETITION`：有明确主办方、报名边界和官方证据的比赛。
- `RESEARCH_PROGRAM`：科研参与、研究训练或正式研究项目机会。
- `SCHOLARSHIP`：奖学金、资助或助学类正式机会。
- `YOUTH_DEVELOPMENT_PROGRAM`：非商业导流的青年成长、实践或培养计划。

可信培训、普通商业课程、普通民企全量岗位和无法核验主办方的活动不因枚举扩展自动进入系统。

### 3.2 采集枚举

```text
CaptureOutcome = SUCCEEDED | NOT_MODIFIED | FAILED
BrowserPolicy = NEVER | FALLBACK
ContentUseBasis = OPEN_LICENSE | OFFICIAL_PUBLIC_ACCESS | LINK_ONLY | UNKNOWN
RobotsDecision = ALLOWED | NOT_APPLICABLE | DISALLOWED | UNKNOWN
ParseOutcome = SUCCEEDED | NEEDS_REVIEW | FAILED
```

`OFFICIAL_PUBLIC_ACCESS` 只表示无需登录即可访问，不等于允许复制整站；公开展示和测试夹具仍分别遵守最小引用与许可判断。

## 4. `SourceEndpoint`

`Source` 表达发布机构或来源身份；`SourceEndpoint` 表达具体可轮询入口和策略。一个 Source 可以有多个 Endpoint。

```yaml
endpoint_id: EntityId
source_id: EntityId
url: absolute http/https URL
allowed_hosts: [non-empty hostname]
expected_media_types: [non-empty string]
browser_policy: NEVER | FALLBACK
minimum_interval_seconds: integer >= 1
timeout_seconds: integer between 1 and 120
max_attempts: integer between 1 and 3
robots_url: absolute http/https URL | null
robots_decision: ALLOWED | NOT_APPLICABLE | DISALLOWED | UNKNOWN
robots_checked_at: Instant
content_use_basis: OPEN_LICENSE | OFFICIAL_PUBLIC_ACCESS | LINK_ONLY | UNKNOWN
license_name: string | null
license_url: absolute http/https URL | null
attribution: string | null
fixture_storage_allowed: boolean
usage_note: non-empty string
policy_version: non-empty string
active: boolean
verified_at: Instant
created_at: Instant
updated_at: Instant
```

不变量：

- `url` 的 host 必须在 `allowed_hosts` 中。
- 只有 `robots_decision` 为 `ALLOWED` 或 `NOT_APPLICABLE` 的 Endpoint 才能启用；`robots_checked_at` 是人工或受控检查的证据时间，不表示规则永远不变。
- `OPEN_LICENSE` 必须同时提供 `license_name` 和 `license_url`。
- `fixture_storage_allowed=true` 只能用于已经记录开放许可或得到明确授权的内容。
- `LINK_ONLY` 和 `UNKNOWN` 的完整响应不得作为仓库 fixture 提交。
- Endpoint URL 不得包含 username/password 用户信息；Endpoint 也不得配置登录、验证码、
  付费墙绕过或未授权的请求头/cookie。重定向目标遵守同一凭据禁令和 host/IP 策略。
- `updated_at >= created_at`。同一 `(source_id,url,policy_version)` 含义不可变；策略变化必须递增 `policy_version` 并创建新 Endpoint 版本，旧行只允许停用，不得就地改写策略字段。

## 5. `CaptureObservation`

每次 HTTP 尝试创建一条观察记录。重试属于同一个 `collection_run_id`，通过递增 `attempt_number` 区分。

```yaml
observation_id: EntityId
collection_run_id: EntityId
attempt_number: integer >= 1
endpoint_id: EntityId
source_id: EntityId
requested_url: absolute http/https URL
resolved_url: absolute http/https URL | null
started_at: Instant
completed_at: Instant
outcome: SUCCEEDED | NOT_MODIFIED | FAILED
http_status: integer | null
response_etag: string | null
response_last_modified: string | null
artifact_id: EntityId | null
error_code: string | null
collector_name: non-empty string
collector_version: non-empty string
policy_version: non-empty string
```

不变量：

- 唯一键为 `(collection_run_id, attempt_number)`；`completed_at >= started_at`。
- `SUCCEEDED` 必须引用本次响应字节对应的 `RawArtifact`，且 `error_code=null`。
- `NOT_MODIFIED` 必须使用 HTTP `304`，引用条件请求所对应的已有 `RawArtifact`，且 `error_code=null`。
- `FAILED` 必须 `artifact_id=null` 且 `error_code` 非空；不得为错误页面伪造成功 RawArtifact。
- 相同内容在不同时间成功抓取时，只复用一个 RawArtifact，但保留多条 CaptureObservation。
- `source_id` 必须与 Endpoint 及引用 RawArtifact 的 Source 一致。
- 错误码使用稳定、无秘密的机器码；响应正文、cookie、token 和完整异常堆栈不写入观察表。

## 6. `ParseAttempt`

解析失败或低置信度必须可审计，但 Phase 2 不建立完整人工审核系统。

```yaml
parse_attempt_id: EntityId
artifact_id: EntityId
parser_name: non-empty string
parser_version: non-empty string
started_at: Instant
completed_at: Instant
outcome: SUCCEEDED | NEEDS_REVIEW | FAILED
document_id: EntityId | null
error_code: string | null
input_media_type: non-empty string
```

不变量：

- 唯一键为 `(artifact_id, parser_name, parser_version)`。
- `SUCCEEDED` 和 `NEEDS_REVIEW` 必须引用由同一 Artifact 产生的 Document。
- `FAILED` 必须 `document_id=null` 且 `error_code` 非空。
- `NEEDS_REVIEW` 只标记后续审核候选，不能发布事实或创建 OpportunityVersion。
- 解析器升级生成新 Document/ParseAttempt，不覆盖旧解析结果。

## 7. Evidence Locator v0.2

### 7.1 Legacy locator

v0.2 Schema 继续接受 v0.1：

```yaml
kind: page | paragraph | css_selector | text_span | full_document
value: non-empty string
```

legacy locator 只用于读取既有数据；Phase 2 新解析器不得生成新的 legacy locator。

### 7.2 HTML locator

```yaml
schema_version: "0.2.0"
kind: html_selector
selector: non-empty CSS selector
text_sha256: Sha256
```

`selector` 必须在固定原始 HTML 上定位到目标节点；对节点规范化可见文本计算 `text_sha256`，防止相同 selector 在新页面结构上指向不同内容。

### 7.3 PDF locator

```yaml
schema_version: "0.2.0"
kind: pdf_page_text
page_number: integer >= 1
text_start: integer >= 0
text_end: integer > text_start
text_sha256: Sha256
```

偏移量基于该解析器版本生成的单页规范化文本，不基于整个 PDF 或渲染像素。页码使用用户可见的 1-based 编号。

### 7.4 Spreadsheet locator

```yaml
schema_version: "0.2.0"
kind: spreadsheet_range
sheet_name: non-empty string
start_row: integer >= 1
end_row: integer >= start_row
start_column: integer >= 1
end_column: integer >= start_column
cells_sha256: Sha256
```

哈希输入是按行优先顺序编码的规范化单元格值和坐标，不执行公式、不加载宏、不访问外部链接。

### 7.5 持久化

数据库保留 v0.1 的 `locator_kind`、`locator_value`，并增加：

```text
locator_schema_version varchar(16) not null default '0.1.0'
locator_payload jsonb null
```

约束：

- legacy 行：`locator_schema_version='0.1.0'`、`locator_value is not null`、`locator_payload is null`。
- v0.2 行：`locator_schema_version='0.2.0'`、`locator_value is null`、`locator_payload is not null`。
- v0.2 `locator_kind` 只能是 `html_selector`、`pdf_page_text`、`spreadsheet_range`。
- Pydantic 和数据库分别验证 payload 形状；应用读取后必须再通过对应 locator Schema。

## 8. 派生对象存储

解析结果不能覆盖 `raw/sha256/...`。规范文本对象键固定为：

```text
derived/documents/{artifact_sha256}/{parser_name}/{parser_version}/text.txt
```

其中 `parser_name` 和 `parser_version` 只能包含 `[a-z0-9._-]`。派生对象同样采用 put-if-absent；相同键但不同字节视为 `DERIVED_OBJECT_CONFLICT`，不能覆盖。

## 9. 明确延期

- Opportunity Resolver、OpportunityVersion、OpportunityEvent 和更正/延期归并进入 Phase 3。
- 资格规则、LLM 最终裁决、用户画像和排序不进入 v0.2。
- 实时 LLM provider、Celery/Valkey、Redis、向量检索和异步编排不进入 Phase 2 初始实现。
- `InstitutionAccount`、`CommercialPlacement`、高校后台和商业价格对象不进入当前契约。
- 完整审核工作流延期到 Phase 7；Phase 2 只保存 `NEEDS_REVIEW` 状态和原因码。

## 10. 转为 `STABLE` 的条件

- v0.1 与 v0.2 Schema 均能在同一代码版本中确定性导出和校验。
- PostgreSQL 18 可从 Phase 1 revision 升级、降级再升级，Alembic metadata 无差异。
- 新机会枚举在 Schema、ORM CHECK、迁移和测试中一致。
- 新抓取相同内容产生两条观察、一个 RawArtifact；失败抓取产生观察但不产生 RawArtifact。
- legacy 与 v0.2 locator 均可读；HTML/PDF/Excel 新定位能回放并验证哈希。
- ParseAttempt 能保留成功、需审核和永久失败，不覆盖原始证据。
- 新鲜环境能运行统一验证，并且没有提交秘密、数据库文件、对象存储内容或未经许可的来源原件。
