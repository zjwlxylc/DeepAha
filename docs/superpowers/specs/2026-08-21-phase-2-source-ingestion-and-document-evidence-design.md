# DeepAha Phase 2 采集观察与文档证据设计

> 状态：`PROPOSED`，设计决策已获用户全权授权，等待按实施计划执行
>
> 日期：2026-08-21
>
> 目标阶段：Phase 2
>
> 前置 Gate：Phase 1 `CLOSED`
>
> 当前运行契约：`0.1.0`；目标契约：`0.2.0`
>
> 本文描述计划方案，不表示采集器、解析器、迁移、十个来源观察或 Phase 2 Gate 已经实现或验证。

## 1. 目的

Phase 2 建立从登记官方入口到可回放 Document 的最小可信链路：每一次网络尝试形成独立 `CaptureObservation`，成功响应的原始字节复用 Phase 1 的不可变 `RawArtifact`，确定性解析器生成版本化 Document、派生文本和结构化 Evidence Locator。

本阶段只证明：

1. 实时重复抓取不会丢失新的观察，也不会重复保存相同 RawArtifact。
2. Source Registry 明确入口、主机、频率、格式、robots 判断和内容使用边界。
3. HTML、文本型 PDF 和 XLSX 能在固定夹具上确定性解析并回到具体原文位置。
4. 失败、未变化和低置信度可审计，不覆盖上次原始证据或伪造业务事实。
5. 十个代表性官方入口可以进行有界、合规、显式开启的观察运行，并形成源健康证据。

Phase 2 不判断多个 Document 是否属于同一个 Opportunity，不抽取最终资格规则，也不向用户发布业务结果。

## 2. 已核验起点

- Phase 1 分支提交 `fb3dd924cc85c19cc8a13564cebc441f4d569521` 已关闭 Gate。
- 现有 v0.1 JSON Schema、Pydantic、SQLAlchemy、Alembic 和 PostgreSQL 约束已通过 Phase 1 证据包验证。
- `RawArtifact` 以 `(source_id, content_sha256)` 去重；不同抓取元数据当前会显式报告 provenance conflict。
- S3 兼容接口和 Moto 本地实现已存在；不得退回仓库文件系统保存原始字节。
- Phase 1 明确延期了实时观察、Source Registry、HTML/PDF/Excel 解析和更细定位。
- Blueprint v1.2 已按 D8 晋升；D9–D12 是本设计的领域和技术边界。

## 3. 范围

### 3.1 包含

- v0.2 Pydantic/JSON Schema 与 v0.1 兼容导出。
- `SourceEndpoint`、`CaptureObservation`、`ParseAttempt` 的 PostgreSQL 表、ORM 和约束。
- OpportunityType v0.2 的四个已批准新增值。
- Evidence Locator v0.2 判别联合和 JSONB 持久化。
- Source Registry 导入、查询、启停和源健康汇总。
- 同步 HTTP GET 采集应用服务、显式重试、条件请求、host/redirect/大小/媒体类型保护。
- 无调度器的 CLI：按 Endpoint 采集或运行已批准的来源清单。
- HTML、文本型 PDF、XLSX 三个确定性解析器和统一 `DocumentParser` 接口。
- 解析派生文本的 S3 兼容不可变存储。
- 固定离线夹具、一个许可清晰的官方 HTML 样本、十个官方入口清单和显式 live 验证命令。
- Phase 2 本地/CI 验证脚本和 Gate 证据包。

### 3.2 不包含

- 定时调度器、分布式队列、Celery、Valkey、Redis 或并发 Worker 编排。
- Scrapy、全站爬取、URL frontier、登录、验证码、cookie 会话或限制绕过。
- Playwright 默认采集；只有后续经批准的 Endpoint 证明静态 HTTP 无法取得公开内容时才单独增加。
- OCR、扫描 PDF、图片、DOCX、PPTX 或通用附件图谱。
- Docling、PaddleOCR 或实时 LLM provider；本阶段固定样本不需要它们。
- Opportunity Resolver、OpportunityVersion、OpportunityEvent、变更检测和发布状态推断。
- Model Gateway、规则、资格、排序、画像、用户、反馈、通知、业务 API 或页面。
- 生产对象存储、生产数据库、云账号、Kubernetes、pgvector 或向量检索。
- 把十个来源的网页内容提交为仓库 fixture；无明确许可时只提交入口策略和运行证据。

## 4. 方案比较

### 4.1 方案 A：同步观察服务 + 确定性格式适配器（采用）

- 以应用服务/CLI 显式触发采集，不引入队列或调度器。
- `httpx2` 负责 HTTP；Phase 1 导入服务负责不可变对象和 RawArtifact。
- `lxml`、`pypdf`、`openpyxl` 分别处理 HTML、文本型 PDF 和 XLSX。
- 每种格式转换成 DeepAha 自有 ParsedDocument 与 Evidence Locator，不泄漏第三方对象。

优点：最少基础设施即可验证所有关键语义；故障容易复现；依赖可单独替换。缺点：不提供长期无人值守调度，也不覆盖扫描件和复杂版面。

### 4.2 方案 B：Docling + Celery/Valkey 一次到位（拒绝）

优点：格式和异步能力更广。缺点：在固定 Gold 样本证明收益前引入大型依赖、模型资产、队列语义和额外故障面；Valkey 与 Celery 的组合也尚无本项目验证。本阶段不采用。

### 4.3 方案 C：每个来源写一次性脚本（拒绝）

优点：单个来源起步快。缺点：无法统一观察、重试、证据、合规和源健康；十个来源会复制错误处理。只允许通过数据配置 Endpoint，不为每个站点复制采集主流程。

## 5. 依赖准入

Phase 2 只新增以下运行依赖，并在锁定前执行 Python 3.14、Windows、Linux CI、许可证和固定夹具验证：

| 依赖 | 约束 | 用途 | 不允许的扩张 |
| --- | --- | --- | --- |
| `httpx2` | `>=2.12,<3` | HTTP GET、流式大小限制、条件请求 | 不实现登录会话或浏览器仿真 |
| `lxml[cssselect]` | `>=6.1,<7` | 安全 HTML DOM、CSS 定位 | 不访问外部实体或网络 |
| `pypdf` | `>=6.16,<7` | 文本型 PDF 分页文本 | 不声称 OCR 或布局理解 |
| `openpyxl` | `>=3.1.5,<4` | XLSX 原生单元格读取 | 不执行宏、公式或外部链接 |
| `defusedxml` | `>=0.7,<1` | 加固 OOXML/XML 处理 | 不放宽 XML 安全限制 |

准入失败只阻断对应格式 Task，不得用关闭安全检查、降级 Python 或引入全套 Document AI 绕过。Docling 保留为未来基准候选：只有代表性中文 PDF/表格夹具证明 `pypdf` 无法满足 Phase 2 目标，才创建独立依赖决策。

## 6. 模块边界

```text
sources/
  models.py              SourceEndpoint, CaptureObservation
  registry.py            manifest validation/import/query
  transport.py           HttpTransport protocol + httpx2 adapter
  collector.py           policy, retry, observation, RawArtifact coordination
  health.py              observation-derived health summary
  cli.py                 explicit operator entry point

documents/
  models.py              Document, EvidenceRef, ParseAttempt
  parser.py              DocumentParser protocol and ParsedDocument types
  service.py             select parser, store derived text, persist attempts
  html.py                lxml adapter
  pdf.py                 pypdf adapter
  spreadsheet.py         openpyxl adapter
```

边界要求：

- `collector` 只取得响应和保存观察/RawArtifact，不解析业务字段。
- 解析器只消费已经持久化的 RawArtifact 字节，不直接访问网络。
- 解析器输出 DeepAha 类型，不向其他模块暴露 lxml、pypdf 或 openpyxl 对象。
- Opportunity 模块仅接受枚举契约扩展；Phase 2 不创建或修改 Opportunity 行。
- CLI 只编排公开应用服务，不直接写 ORM 表。

## 7. Source Registry

### 7.1 登记内容

Registry 使用版本化 JSON manifest，映射到 v0.2 `Source` 和 `SourceEndpoint`。每个 Endpoint 必须记录：

- 官方机构与来源等级；
- 规范入口 URL 和允许跳转的 host；
- 预期媒体类型；
- 最小抓取间隔、超时和最多三次尝试；
- robots URL、最近核验时间和 `ALLOWED | NOT_APPLICABLE | DISALLOWED | UNKNOWN` 决策；
- 内容使用依据、许可/条款 URL、仓库 fixture 是否允许及限制说明；
- 策略版本和核验时间。

只有 robots 决策为 `ALLOWED` 或 `NOT_APPLICABLE`、内容使用依据不为 `UNKNOWN` 的 Endpoint 才能启用。`LINK_ONLY` 可以观察公开响应元数据和本地原始证据，但不能把响应提交到仓库或公开复制全文。

### 7.2 十个代表性官方入口

Phase 2 清单覆盖以下来源角色，各一项以上，总数固定为十个：

1. 国家公务员招录；
2. 人力资源和社会保障部就业/招聘政策；
3. 国务院国资委招聘；
4. 中国政府网青年就业或政策；
5. 教育部奖学金/学生资助；
6. 共青团中央青年项目；
7. 浙江省人力资源和社会保障厅事业单位招聘；
8. 浙江省人事考试；
9. 浙江省科技部门科研计划；
10. 浙江省教育部门奖助学或成长项目。

实施时必须逐项保存实际 URL、host、robots 和使用边界核验结果；若入口失效或禁止采集，用同一角色的官方入口替换并在 manifest commit 中说明，不能降低为二手来源。

### 7.3 健康不是可变真相字段

Source 健康由观察记录计算，不在 Source 表保存一个可被覆盖的布尔值。最小汇总包括：

- `last_attempt_at`、`last_success_at`；
- `consecutive_failures`；
- 最近 24 小时成功/未变化/失败次数；
- 最近 artifact ID 和内容哈希；
- 解析成功、需审核和失败次数；
- 人工维护分钟数由 Gate 运行记录，不从日志猜测。

## 8. 采集数据流

```text
operator CLI
  -> load active SourceEndpoint
  -> validate robots/content-use/host/rate policy
  -> create collection_run_id
  -> HTTP attempt 1..max_attempts
       -> one CaptureObservation per attempt
       -> 2xx non-empty response: import/reuse RawArtifact, observation SUCCEEDED
       -> 304: reference previous RawArtifact, observation NOT_MODIFIED
       -> timeout/429/5xx: FAILED observation, bounded retry
       -> permanent 4xx/policy/media/size error: FAILED observation, stop
  -> commit each attempt outcome
  -> optional parse command reads persisted RawArtifact
```

### 8.1 HTTP 安全规则

- 只允许 `http`/`https`，生产候选 Endpoint 必须使用 `https`；HTTP 仅供本地测试替身。
- 请求 host 和每次 redirect host 必须位于 `allowed_hosts`。
- 默认拒绝 loopback、link-local、private、multicast 和保留 IP；本地测试通过注入 transport，不关闭生产保护。
- User-Agent 固定为 `DeepAha/0.2 (+https://github.com/zjwlxylc/DeepAha)`。
- 单响应最多 `25_000_000` 字节，流式读取超限即停止且不写 RawArtifact。
- 只接受 Endpoint 声明的媒体类型；缺失或不匹配时记录失败。
- 不保存 cookie、Authorization、Set-Cookie、完整响应头或异常堆栈。
- 条件请求只发送上次成功观察中的 ETag/Last-Modified，不自行推断内容未变化。

### 8.2 重试分类

可重试：连接超时、连接重置、HTTP `429`、`500`、`502`、`503`、`504`。最多三次，使用注入 Sleeper 的确定性退避 `0s, 1s, 2s`；测试 Sleeper 不真实等待。

不可重试：策略拒绝、host/redirect 不允许、`304` 无先前 Artifact、其他 `4xx`、空响应、超限、媒体类型不匹配、RawArtifact provenance 冲突。

稳定错误码在 spec 中固定为：

```text
ROBOTS_NOT_APPROVED
HOST_NOT_ALLOWED
REDIRECT_HOST_NOT_ALLOWED
RATE_LIMIT_NOT_ELAPSED
NETWORK_TIMEOUT
NETWORK_ERROR
HTTP_RETRYABLE_EXHAUSTED
HTTP_PERMANENT
NOT_MODIFIED_WITHOUT_ARTIFACT
RESPONSE_TOO_LARGE
MEDIA_TYPE_NOT_ALLOWED
EMPTY_RESPONSE
RAW_ARTIFACT_PROVENANCE_CONFLICT
```

## 9. 解析架构

### 9.1 统一接口

```python
class DocumentParser(Protocol):
    name: str
    version: str

    def supports(self, media_type: str) -> bool: ...
    def parse(self, content: bytes, *, artifact_sha256: str) -> ParsedDocument: ...
```

`ParsedDocument` 是 frozen dataclass，包含：

```text
title: str | None
published_at: datetime | None
language: str
normalized_text: str
locators: tuple[EvidenceLocatorV02, ...]
needs_review_reasons: tuple[str, ...]
```

解析器不创建数据库 ID，不写对象存储，不提交事务。`DocumentService` 负责选择唯一支持的解析器、持久化派生文本、Document、EvidenceRef 和 ParseAttempt。

### 9.2 规范文本

- UTF-8、LF 换行、Unicode NFC。
- 删除行尾空白；连续空行压缩为一个；不改写数字、日期或原文词语。
- 空文本不能产生成功 Document；对原始字节和规范文本分别计算 SHA-256。
- 派生对象键遵守 v0.2 契约，冲突时报告 `DERIVED_OBJECT_CONFLICT`，绝不覆盖。

### 9.3 HTML

- 使用禁用网络与外部实体的 lxml HTML parser。
- 标题只来自非空 `<title>`；语言只来自有效 `html[lang]`，否则 `und`。
- 正文优先选择单个 `<main>`，其次单个 `<article>`，否则 `<body>`；删除 script/style/noscript/template。
- 每个非空块级节点生成确定性 CSS selector、规范化可见文本和 `text_sha256`。
- 不从普通正文猜测发布时间、截止日、机构或资格。

### 9.4 PDF

- 只处理未加密、页数 `1..500` 的文本型 PDF。
- 逐页调用 pypdf 文本提取；标题和语言默认未知，除非固定样本显式证明可靠 metadata。
- 每页文本单独规范化，Document 文本用换页符分隔。
- 非空片段生成 1-based 页码、页内文本偏移和 `text_sha256`。
- 所有页面均无有效文本时写 `FAILED/PDF_TEXT_EMPTY`；部分页面为空时生成 Document 并标记 `NEEDS_REVIEW/PDF_PAGE_TEXT_MISSING`。
- 加密、页数超限或损坏分别使用稳定错误码，不启用 OCR fallback。

### 9.5 XLSX

- 只接受 `.xlsx` 对应媒体类型；拒绝 `.xlsm`、宏和外部链接。
- 解包前检查 ZIP：最多 10,000 个 entry、总未压缩大小不超过 `100_000_000` 字节、路径不得逃逸。
- openpyxl 使用 `read_only=True`、`data_only=False`、`keep_links=False`。
- 公式只作为原始公式字符串保存，不求值；图片、批注、隐藏对象不作为事实。
- 按工作表和行列顺序输出坐标+规范值；每个非空行生成 `spreadsheet_range` locator 和单元格哈希。
- 工作簿没有非空单元格时写 `FAILED/XLSX_EMPTY`。

## 10. 幂等性与事务

- 每次 HTTP attempt 独立提交 CaptureObservation；后续 attempt 失败不能抹去前一条观察。
- 成功响应先写内容寻址对象，再在一个数据库事务中 import/reuse RawArtifact 并写 observation。
- 相同 Endpoint 和相同字节的新抓取产生新的 observation、复用同一 RawArtifact；不会触发 Phase 1 provenance conflict，因为新抓取元数据属于 observation，不再改写 RawArtifact 首次捕获信息。
- ParseAttempt 唯一 `(artifact_id, parser_name, parser_version)`；相同版本重放返回已有结果。
- 解析器版本变化允许同一 Artifact 产生新 Document 和派生对象；旧结果不可覆盖。
- 数据库回滚不删除内容寻址对象；对象清理继续延期，不在本阶段实现。

## 11. 失败模式与状态表达

| 失败 | 记录 | 不允许 |
| --- | --- | --- |
| robots/使用边界未批准 | FAILED observation + 稳定错误码 | 发出网络请求 |
| 临时网络错误 | 每次 FAILED observation，最多三次 | 无限重试或只保留最终错误 |
| 永久 HTTP/媒体错误 | FAILED observation | 把错误页当正式 RawArtifact |
| 相同内容再次成功 | 新 SUCCEEDED observation + 原 RawArtifact | 第二份 RawArtifact 或吞掉观察 |
| HTML 结构无正文 | FAILED ParseAttempt | 保存空 Document |
| PDF 部分页无文本 | NEEDS_REVIEW + 已定位的有效页 | 声称 OCR 已覆盖 |
| XLSX 宏/压缩异常 | FAILED ParseAttempt | 执行宏、公式或外部链接 |
| 派生对象键冲突 | 显式冲突错误 | 覆盖旧解析文本 |
| Evidence locator 无法回放 | 测试/Gate 失败 | 发布无法定位的结构化事实 |

## 12. 样本与许可

### 12.1 默认离线夹具

- HTML、PDF、XLSX 各有一个最小合成 fixture，只验证格式边界，不包含真实业务事实。
- 合成 PDF/XLSX 由固定测试构造脚本生成后提交最终字节和 SHA；默认测试不在运行时重新生成以免库版本改变字节。
- 恶意/失败 fixture 只保存最小字节：HTML 空正文、加密/空文本 PDF、宏扩展名或超限 ZIP 元数据。

### 12.2 官方固定 HTML 样本

继续使用 Phase 1 GOV.UK OGL 主题，捕获其公开 HTML 页面。manifest 必须记录 URL、实际捕获时间、status、media type、byte size、SHA-256、OGL v3.0、署名、第三方资产未包含，以及“不代表当前申请开放/中国首发覆盖”。只有完整响应和许可核验同时成功才提交；不得用手工重写 HTML 冒充原始响应。

### 12.3 中国官方来源

十个来源清单中的响应默认只进入本地/CI 外的临时 PostgreSQL 和对象存储。仓库只提交 SourceEndpoint 策略、URL、核验日期和 live 运行摘要，不提交完整网页、附件或对象存储内容。若某来源存在明确开放许可，可在独立样本决策中升级，不在本计划中推断许可。

## 13. 测试策略

### 13.1 契约与迁移

- v0.1 renderer 字节完全不变；v0.2 renderer 确定性。
- 新旧 EvidenceRef 示例均通过 v0.2 Schema。
- OpportunityType 新值在 Pydantic、JSON Schema、ORM CHECK、迁移和真实 PostgreSQL 写入中一致。
- migration `0001 -> 0002 -> 0001 -> 0002` 通过，`alembic check` 无 diff。

### 13.2 采集

- 使用 `httpx2` 可控 transport，不访问真实网络。
- 覆盖 200、304、redirect、timeout、429、5xx、永久 4xx、超限、媒体类型、空响应和 host/IP 拒绝。
- 核心回归：同字节两次成功 = 两条 observation + 一个 RawArtifact。
- 重试测试断言每次 attempt 都有行且退避序列固定，不真实 sleep。

### 13.3 解析

- 每个 parser 先写 RED 测试，再写最小实现。
- 固定字节重放必须得到相同规范文本 SHA、Document 字段和 locator payload。
- locator resolver 从原始 fixture 重新定位并验证片段哈希。
- 测试不调用外部模型、浏览器或网络。

### 13.4 Live 验证

Live 命令默认关闭，必须显式设置 `DEEPAHA_ALLOW_LIVE_SOURCE_CHECK=true`。Phase 2 Gate 要求十个 Endpoint 在至少 24 小时内完成五轮策略间隔观察，共至少 50 次最终运行结果；有效 `SUCCEEDED + NOT_MODIFIED` 比率达到计划目标 `>=98%`，所有失败均有 observation 和稳定错误码，期间不为适配单个页面修改通用采集器。

Live 结果证明“这些入口在观察窗口内可按策略访问”，不证明长期 SLA、机会发现覆盖率或转载许可。

## 14. 可观测与成本证据

Phase 2 Gate 保存：

- 每 Endpoint 的观察次数、成功/未变化/失败和连续失败；
- 响应字节、RawArtifact 去重率、解析耗时和派生字节；
- 每种 parser 的成功、需审核、失败和 Evidence locator 回放率；
- 十个来源配置、排障和策略维护的人工分钟数；
- 每个高价值 Document 的采集+解析运行成本口径，但不设商业结论阈值。

不得用吞吐量、公告数量或成功 HTTP 数替代机会价值、字段准确率或真实行动。

## 15. Phase 2 Gate

### 15.1 退出条件

1. 同一内容的两次真实语义抓取产生两个 CaptureObservation、一个 RawArtifact，且每次时间/URL/status 可重放。
2. 失败和 304 均有独立记录；失败不创建 RawArtifact，304 必须引用已有 Artifact。
3. 十个代表性官方 Endpoint 完成规定的 live 观察窗口并有源健康/维护证据。
4. 固定 HTML、PDF、XLSX 分别生成确定性 Document、派生文本和可回放的结构化 locator。
5. 原始对象没有被派生结果覆盖；解析升级保留旧 Document。
6. v0.1 与 v0.2 Schema、迁移、ORM 和契约测试一致；v0.2 达到条件后才标记 `STABLE`。
7. 新鲜环境可复现默认测试、集成测试和固定样本；默认测试不依赖实时网络。
8. 没有进入 Phase 3、引入未批准基础设施、提交秘密/真实用户数据/数据库文件/对象内容或无许可来源原件。

### 15.2 Gate 证据包

```text
docs/gates/phase-2/
├── README.md
├── acceptance-results.md
├── test-summary.md
├── source-observation-summary.md
├── parser-evaluation-summary.md
├── sample-provenance.md
├── security-and-compliance.md
├── operations.md
└── deferred-decisions.md
```

在 live 窗口、完整验证和远程 CI 尚未实际成功前，Gate 必须保持 `OPEN`。计划阈值、预期测试数和候选 URL 不能写成通过证据。

## 16. 明确延期

- Phase 3：Document → Opportunity 归并、版本、事件、更正、延期、稳定 ID 合并/拆分。
- 后续 Phase 2 扩展候选：Playwright、Docling、OCR、LLM Model Gateway；只有固定失败样本和新 spec 才能启用。
- Phase 4：规则、资格四态、Golden Dataset 业务字段准确率。
- Phase 5+：公开页面、用户系统、排序、反馈、提醒和商业功能。
- Phase 9/Gate F：高校试点、机构账户、付费、招聘服务许可适用性和规模化合规审核。
