# DeepAha Phase 3 Opportunity 归并、版本与变化设计

> 状态：`PROPOSED_IMPLEMENTATION_BLOCKED_BY_PHASE2_GATE`
>
> 日期：2026-08-22
>
> 目标阶段：Phase 3
>
> 精确实现起点：`64b09f508d9118a771195c4ab6449cc8487ab057`
>
> 前置 Gate：Phase 2 `OPEN`，领域契约 v0.2 仍为 `PROPOSED`
>
> 候选契约：`0.3.0`
>
> 本文授权实现受控的 Phase 3 候选，但不授权合并、发布、把 v0.3 标记为
> `STABLE`、关闭 Phase 3 Gate，或声称 Phase 3 已完成最终验证。Phase 2 Gate
> 关闭后，必须更新到实际关闭提交并重新执行全部验证。

## 1. 目的

Phase 3 把 Phase 2 产生的可回放 Document 组织成稳定 Opportunity，并把内容变化、
高影响事件和身份变更保存为可审计历史。它建立以下最小可信链路：

```text
Document + EvidenceRef + structured resolution facts
  -> deterministic Opportunity Resolver
  -> confirmed Document link or NEEDS_REVIEW candidate
  -> immutable OpportunityVersion + field-level diff
  -> immutable OpportunityEvent
  -> current Opportunity projection
  -> deterministic replay
```

本阶段只证明：

1. 正文、附件、岗位表、更正、延期和取消可以在强证据锚点下归入同一稳定
   Opportunity。
2. 不足、弱匹配或冲突输入不会自动硬合并，而是产生可审核候选。
3. 版本快照、字段级差异、事件和当前投影可以确定性回放。
4. 稳定 `public_id` 不随标题或版本变化；合并、拆分及其撤销不会删除或复用旧 ID。
5. 高影响变化绑定触发 Document 和具体 EvidenceRef，并遵守官方证据优先级。
6. v0.1/v0.2 契约字节、导入路径和旧数据库记录保持不变。

Phase 3 不实现自由文本抽取、LLM、规则资格、用户/API/UI、通知或反馈。Resolver
消费带证据的结构化事实，不从原始正文猜测业务字段。

## 2. 依据与已核验起点

### 2.1 上位依据

- Blueprint v1.2 把 Opportunity 定义为围绕同一资格、名额、时间窗口和行动入口持续
  演化的实体；公告、岗位表、附件、更正、延期、笔试/面试和结果是其文档或生命周期
  事件。
- Blueprint 的核心链路是
  `Source -> RawArtifact -> Document -> Opportunity -> Version/Event -> ...`。
- Blueprint 要求 Opportunity 具有稳定 `public_id`，合并后保留 alias；
  OpportunityVersion 必须带 `version`、`diff`、`source_doc` 和 `effective_at`，且可回放。
- 根目录 `AGENTS.md` 进一步锁定：不复用旧 ID；必要时支持受审计的合并、拆分和撤销；
  原始证据不可被解析结果覆盖。
- 证据优先级固定为：
  `最新官方更正 > 正式岗位/政策附件 > 原始正式公告 > 官方 FAQ/指南 > 人工批准映射 > LLM 语义推断`。

### 2.2 当前仓库事实

- Phase 1 Gate 已 `CLOSED`，v0.1 的 Source、RawArtifact、Document、EvidenceRef 和
  Opportunity 为历史 `STABLE` 契约。
- Phase 2 代码和迁移已实现；本地离线基线通过，但 live 观察、新鲜副本和 Gate 关闭仍
  未完成，因此 v0.2 仍为 `PROPOSED`。
- 当前 Alembic head 为 `20260821_0002`；`Opportunity.current_version` 允许 `null`，
  但尚无 OpportunityVersion/Event 表。
- EvidenceRef 数据库表拥有内部 `evidence_ref_id`，并保留 Document/Artifact 配对约束；
  v0.1/v0.2 公共 Schema 不暴露该内部 ID。
- 当前 worktree 是独立 linked worktree，分支为
  `codex/phase-3-opportunity-resolution`，起点工作树干净。
- Phase 2 live Gate 使用 compose project `deepaha-phase2-live-gate` 和主机端口
  PostgreSQL `55432`、Moto `55000`；本阶段禁止访问、停止或复用它们。

### 2.3 本轮已验证的干净基线

`scripts/verify.ps1` 在精确起点实际退出 0：Ruff、mypy、默认离线 pytest、Web Lint、
TypeScript、Vitest 和 Next.js build 均通过。该命令没有访问数据库、对象存储、实时站点、
浏览器或模型。

## 3. 设计假设与成功条件

### 3.1 明确假设

1. Resolver 的输入是 `ResolutionDocument`：Document ID、EvidenceRef ID、来源等级、
   文档角色、强身份锚点、引用 Document 和已结构化的字段 patch。字段抽取不属于本阶段。
2. 只有 `OFFICIAL_PRIMARY` 且存在强身份锚点的主公告可以自动创建 Opportunity。
3. `OFFICIAL_PRIMARY` 的附件/更正/延期/取消只有在强关联到既有 Document 或 alias 时才
   自动关联并生成版本；其他来源只产生候选。
4. 标题、机构、地域或相似度组合只是弱指纹，只能生成候选，不能触发自动合并。
5. merge/split/reversal 是显式、带 actor/reason 的应用服务操作；Resolver 不自动执行身份
   手术。
6. `Opportunity` 表是当前投影；Version/Event/IdentityAction 是历史事实。投影可以从历史
   重新计算，但历史事实不得原地覆盖或删除。
7. 本阶段不建立完整人工审核 UI。候选只保存 `PENDING` 状态和原因码，供 Phase 7 消费。

### 3.2 可验证成功条件

- `contracts/schemas/v0.1.0/` 和 `v0.2.0/` 的全部字节在实现前后相同。
- `deepaha.contracts.phase1`、`phase2` 及其既有导出函数保持可导入、行为不变。
- v0.3 Pydantic、JSON Schema、示例、ORM、迁移与真实 PostgreSQL 约束一致。
- Alembic 空数据往返
  `0001 -> 0002 -> 0003 -> 0002 -> 0003` 通过；有 v0.3 数据时 downgrade 明确拒绝，
  不删除或重写历史。
- 固定合成样本覆盖重复公告、正文+附件、岗位表、更正、延期、取消、冲突、误合并保护、
  稳定 ID、merge/split/reversal 和重复回放。
- 版本序列连续；每个新版本有且只有一个事件；字段 diff 能重建并校验对应快照哈希。
- 高影响更改全部引用触发 Document 与属于该 Document 的 EvidenceRef。
- current Opportunity 投影与 replay 结果逐字段一致。
- 独立 Phase 3 verifier 只使用 compose project `deepaha-phase3-$PID`、PostgreSQL
  `55433` 和 Moto `55001`，并只清理其自身 project。
- 默认测试和 CI 不访问实时站点、浏览器或模型。
- 本地与远程验证成功后，状态仍为 `IMPLEMENTED_PENDING_PHASE2_GATE`。

## 4. 范围

### 4.1 包含

- 候选领域契约 v0.3、JSON Schema、Pydantic、示例和契约说明。
- `OpportunityVersion`、`OpportunityEvent`、Document→Opportunity 审计关联、
  ResolutionCandidate、OpportunityAlias、IdentityAction/Member 的 ORM 与迁移。
- Opportunity 当前版本的可延迟复合外键，阻止悬空 `current_version`。
- 确定性 stable public ID、alias 索引、保守 Resolver 和候选决议。
- 版本快照、字段级 diff、字段证据优先级、事件分类和状态回放。
- 显式 merge、split、merge reversal、split reversal 的审计和身份图回放。
- 许可安全的纯合成 resolution fixture 与集成纵向样本。
- Phase 3 scoped compose、verifier、CI job 和诚实的阻塞 Gate 证据包。

### 4.2 明确不包含

- Phase 4 RuleSet、规则 DSL、Eligibility 四态、专业目录或画像。
- Ranking、MatchSnapshot、用户、API、Web/PWA、小程序或审核 UI。
- LLM、Model Gateway、向量相似度、pgvector 或模型生成真值。
- Redis、Valkey、Celery、调度器、Worker 或分布式工作流。
- Playwright、Docling、OCR、扫描件理解或新的 Document parser。
- 实时采集、Source Registry 改造或 Phase 2 live 运行行为修改。
- 通知、反馈、商业化、生产云、生产发布或数据清理器。
- 自动 merge/split、基于标题相似度的硬合并或不带证据的高影响变化。

## 5. 方案比较

### 5.1 方案 A：不可变历史 + 当前投影（采用）

- Version/Event/IdentityAction 追加写入；Opportunity 保存当前可查询投影。
- Resolver 和 version planner 是纯函数；应用服务负责事务和数据库约束。
- public ID 从强身份 key 确定性生成；merge/split 用身份动作日志表达。

优点：满足审计、回放和当前查询；与现有 SQLAlchemy/Alembic 模块化单体一致；没有引入
通用事件框架。代价：写事务必须同时追加历史并更新当前投影，需由集成测试锁住一致性。

### 5.2 方案 B：完整事件溯源（不采用）

所有 Opportunity 状态只由事件生成，不保留当前关系型投影。它理论上最纯，但会要求事件
存储、聚合版本并发控制、投影重建框架和更多运维入口，超出 Phase 3 最小范围。

### 5.3 方案 C：可变 Opportunity + 审计 JSON（不采用）

只更新 Opportunity 当前列，把变更摘要放入一个通用日志。实现较少，但无法用类型化契约、
外键和字段 diff 证明状态可回放，也无法安全表达 merge/split reversal。

## 6. 候选 v0.3 契约

### 6.1 兼容策略

- `contracts/schemas/v0.1.0/`、`v0.2.0/` 永久保留并逐字节回归。
- 新导出目录是 `contracts/schemas/v0.3.0/`，不覆盖旧文件。
- 新 Python 类型只放入 `deepaha.contracts.phase3`；不改名或移动 v0.1/v0.2 类型。
- exporter 新增 `--version 0.3.0`，原默认仍为 `0.1.0`。
- v0.3 目录包含 v0.2 的兼容对象和以下新增对象；示例只使用合成机构、URL 与事实。
- v0.3 在 Phase 2 和 Phase 3 Gate 均满足前保持候选，不得标记 `STABLE`。

### 6.2 受控枚举

```text
OpportunityDocumentRole =
  PRIMARY_NOTICE | ATTACHMENT | POSITION_TABLE | CORRECTION |
  DEADLINE_EXTENSION | CANCELLATION | RESULT | OFFICIAL_GUIDANCE

ResolutionDisposition = CREATED | LINKED | NEEDS_REVIEW

OpportunityEventType =
  CREATED | UPDATED | CORRECTED | DEADLINE_CHANGED |
  ATTACHMENT_REPLACED | CANCELLED | REOPENED

OpportunityAliasType = TITLE | URL | EXTERNAL_ID

OpportunityIdentityActionType =
  MERGE | SPLIT | MERGE_REVERSAL | SPLIT_REVERSAL

OpportunityIdentityMemberRole = SOURCE | TARGET | PARENT | CHILD

SnapshotField =
  canonical_title | type | issuer_name | jurisdiction | status |
  published_at | application_window.opens_on |
  application_window.closes_on | application_window.timezone |
  application_url | attachment_urls | locations
```

资格枚举和资格逻辑不进入 v0.3。

### 6.3 `OpportunitySnapshot`

```yaml
canonical_title: non-empty string
type: OpportunityTypeV02
issuer_name: non-empty string
jurisdiction: non-empty string | null
status: OpportunityStatus
published_at: Instant | null
application_window:
  opens_on: LocalDate | null
  closes_on: LocalDate | null
  timezone: non-empty IANA timezone | null
application_url: absolute http/https URL | null
attachment_urls: [unique absolute http/https URL]
locations: [unique non-empty string]
```

数组采用规范化、排序后的不可变 tuple。日期和 URL 保留业务含义，不从正文临时猜测。

### 6.4 `OpportunityFieldEvidence`

```yaml
field_path: SnapshotField
precedence: integer 100..600
evidence_ref_id: EntityId
effective_at: Instant
```

每个有值字段至多一条当前 field evidence。`precedence` 由系统按来源等级和文档角色派生，
不是调用者自由提供的“置信分”。

### 6.5 `OpportunityFieldChange`

```yaml
field_path: SnapshotField
before: JsonValue | null
after: JsonValue | null
evidence_ref_id: EntityId
```

`before` 和 `after` 不能相等。版本 1 使用 `before=null` 表达首次建立的字段。

### 6.6 `OpportunityVersion`

```yaml
opportunity_id: EntityId
version: VersionNumber
effective_from: Instant
source_document_id: EntityId
source_evidence_ref_id: EntityId
snapshot: OpportunitySnapshot
field_evidence: [OpportunityFieldEvidence]
changes: [non-empty OpportunityFieldChange]
content_sha256: Sha256
review_status: NOT_REQUIRED | PENDING | APPROVED | REJECTED
created_at: Instant
```

`content_sha256` 是 `snapshot + field_evidence` 的 UTF-8 canonical JSON 哈希。版本号从 1
开始连续递增；任何旧版本不可覆盖。

### 6.7 `OpportunityEvent`

```yaml
event_id: EntityId
opportunity_id: EntityId
from_version: VersionNumber | null
to_version: VersionNumber
event_type: OpportunityEventType
changed_fields: [unique SnapshotField]
changes: [non-empty OpportunityFieldChange]
source_document_id: EntityId
source_evidence_ref_id: EntityId
detected_at: Instant
```

`CREATED` 必须 `from_version=null,to_version=1`；其他事件必须
`to_version=from_version+1`。一个 OpportunityVersion 对应一个事件。

### 6.8 `DocumentOpportunityLink`

```yaml
link_id: EntityId
document_id: EntityId
opportunity_id: EntityId
role: OpportunityDocumentRole
resolution_key: non-empty string
resolver_version: non-empty string
source_evidence_ref_id: EntityId
linked_at: Instant
ended_at: Instant | null
ended_by_identity_action_id: EntityId | null
```

`ended_at` 与 `ended_by_identity_action_id` 必须同时为空或同时有值。结束关联只追加身份动作并
封闭当前有效区间，不删除旧关联。

### 6.9 `OpportunityResolutionCandidate`

```yaml
candidate_id: EntityId
document_id: EntityId
candidate_opportunity_ids: [unique EntityId]
proposed_role: OpportunityDocumentRole
proposed_snapshot: OpportunitySnapshot | null
reason_codes: [unique non-empty machine code]
resolver_version: non-empty string
source_evidence_ref_id: EntityId
review_status: PENDING | APPROVED | REJECTED
created_at: Instant
```

Phase 3 自动路径只创建 `PENDING`。批准/拒绝应用服务延期到 Phase 7；本阶段不把候选变成
线上事实。

### 6.10 `OpportunityAlias`

```yaml
alias_id: EntityId
opportunity_id: EntityId
alias_type: TITLE | URL | EXTERNAL_ID
alias_value: non-empty original string
normalized_value: non-empty normalized string
source_id: EntityId | null
source_document_id: EntityId
source_evidence_ref_id: EntityId
created_at: Instant
```

`public_id` 不是可移动 alias。每个 Opportunity 始终保留自己创建时的 public ID；merge 只
改变身份图的 canonical 解析，不改写或转移 public ID。

### 6.11 `OpportunityIdentityAction`

```yaml
action_id: EntityId
action_type: MERGE | SPLIT | MERGE_REVERSAL | SPLIT_REVERSAL
members:
  - opportunity_id: EntityId
    role: SOURCE | TARGET | PARENT | CHILD
reversal_of_action_id: EntityId | null
actor: non-empty string
reason: non-empty string
source_document_id: EntityId | null
source_evidence_ref_id: EntityId | null
occurred_at: Instant
```

形状约束：

- MERGE：一个 TARGET，至少一个 SOURCE，不能引用 reversal。
- SPLIT：一个 PARENT，至少两个 CHILD，不能引用 reversal。
- MERGE_REVERSAL：必须引用一个尚未撤销的 MERGE。
- SPLIT_REVERSAL：必须引用一个尚未撤销的 SPLIT。
- reversal 的 members 必须逐项复制原动作 members，便于单行审计和独立回放。
- 同一原动作最多被撤销一次；撤销本身不能被撤销。

## 7. PostgreSQL 18 与 ORM 设计

### 7.1 新增表

```text
opportunity_versions
opportunity_events
document_opportunity_links
opportunity_resolution_candidates
opportunity_aliases
opportunity_identity_actions
opportunity_identity_action_members
```

不增加通用 audit blob、事件总线或第二事实库。

### 7.2 `opportunity_versions`

- 复合主键 `(opportunity_id, version)`；Opportunity 外键删除受限。
- `source_document_id` 外键指向 Document。
- `(source_evidence_ref_id, source_document_id)` 复合外键证明 EvidenceRef 属于触发
  Document。
- `snapshot`、`field_evidence`、`changes` 使用 JSONB，并至少检查 object/array、非空
  changes 和 SHA 格式；精确形状由 Pydantic 再验证。
- 唯一 `(opportunity_id, content_sha256)` 防止相同状态重复建版。
- `effective_from`、`created_at` 使用带时区时间。

### 7.3 `opportunity_events`

- 主键 UUIDv7；`to_version` 复合外键指向对应 OpportunityVersion。
- `from_version` 为空仅允许 CREATED；否则复合外键指向前一版本。
- 唯一 `(opportunity_id, to_version)`，保证一版一个事件。
- 约束 CREATED/连续版本、受控 event type、非空 changed fields/changes。
- Document/EvidenceRef 使用与 Version 相同的配对外键。

### 7.4 当前版本完整性

在 `opportunities` 上增加可延迟复合外键：

```text
(opportunity_id, current_version)
  -> opportunity_versions(opportunity_id, version)
  DEFERRABLE INITIALLY DEFERRED
```

新建 Opportunity 时先以 `current_version=null` 插入，追加 version 1，再在同一事务更新
current projection。事务提交时不允许悬空版本。为保持 v0.1/v0.2 兼容，Opportunity 表的
当前投影只包含既有身份字段、`status`、`publication_status` 和 `current_version`；
application window、URL、附件和 locations 等完整当前内容从 `current_version` 指向的最新
OpportunityVersion 读取。replay 一致性逐字段比较 Opportunity 表现有投影列，并对完整
Snapshot 比较最新 Version。

### 7.5 Document、候选和 alias

- `evidence_refs` 增加唯一 `(evidence_ref_id, document_id)`，不改变旧行。
- `document_opportunity_links` 对当前未结束的 `document_id` 使用部分唯一索引，禁止一个
  Document 同时硬归属多个 Opportunity。
- link、candidate、alias 都使用 `(source_evidence_ref_id, source_document_id)` 复合外键。
- candidate 的候选 ID 和 reason code 使用 JSONB 数组；候选不是正式 link/version/event。
- alias 唯一范围：
  - URL：`(alias_type, normalized_value)`；
  - EXTERNAL_ID：`(alias_type, source_id, normalized_value)`；
  - TITLE 不全局唯一，只用于弱候选召回。

### 7.6 Identity Action

- action 追加写入，reversal 使用自引用外键；数据库约束 reversal 类型与 null 形状。
- member 表复合主键 `(action_id, opportunity_id, role)`；Opportunity 删除受限。
- member 数量和角色基数由 Pydantic/应用服务在同一事务校验。
- canonical merge redirect 和 split children 由按时间重放 action log 计算；Phase 3 不增加
  可变 redirect 表，避免投影与 action log 双重真相。

### 7.7 Alembic revision `20260822_0003`

升级顺序：

1. 给 EvidenceRef 增加兼容唯一约束。
2. 创建 Version、Event、link、candidate、alias、identity action/member 表。
3. 最后给 Opportunity 增加 current_version 复合外键。

降级前检查所有 v0.3 表是否含数据。任何表有行都抛出稳定 RuntimeError；空表才删除新
约束和表并回到 `20260821_0002`。旧机会、Document、EvidenceRef、v0.1/v0.2 locator
不重写。

## 8. 确定性 Opportunity Resolver

### 8.1 输入 `ResolutionDocument`

```python
@dataclass(frozen=True, slots=True)
class ResolutionDocument:
    document_id: UUID
    source_id: UUID
    source_tier: SourceTier
    evidence_ref_id: UUID
    role: OpportunityDocumentRole
    canonical_url: str | None
    external_id: str | None
    references_document_ids: tuple[UUID, ...]
    effective_at: datetime
    facts: OpportunityPatch
```

`OpportunityPatch` 的字段对应 Snapshot；字段可以缺失，但“未知”和“明确 null”必须使用
不同表示。实现使用显式 sentinel，不用空字符串或 `None` 同时表达两种语义。

### 8.2 强身份 key

按固定顺序生成：

```text
document:<referenced_document_id>
external:<source_id>:<normalized_external_id>
url:<normalized_absolute_url>
```

规则：

- URL 只做 scheme/host 大小写、默认端口、fragment 和末尾空路径规范化；不删除业务 query。
- external ID 只做 Unicode NFC、trim、空白压缩和大小写归一；作用域固定到 Source。
- reference Document 必须已经有一个有效 link。
- 一个输入的多个强 key 若解析到不同 Opportunity，结果是 `NEEDS_REVIEW/STRONG_KEY_CONFLICT`。

### 8.3 弱指纹

弱指纹只由 `type + normalized issuer + normalized title + jurisdiction` 生成。它只返回候选
Opportunity ID；永远不能产生自动 link/merge。已有弱候选时，新主公告进入
`NEEDS_REVIEW/POSSIBLE_DUPLICATE`。

### 8.4 创建规则与 stable public ID

自动创建必须同时满足：

- role 为 `PRIMARY_NOTICE`；
- source tier 为 `OFFICIAL_PRIMARY`；
- title、type、issuer、status 已提供；
- 至少一个 external ID 或 canonical URL 强 key；
- 没有强 key 冲突或弱重复候选；
- EvidenceRef 属于该 Document。

public ID 固定为：

```text
opp_ + sha256("deepaha:opportunity:v0.3:" + primary_identity_key).hexdigest()[0:32]
```

主 identity key 优先 external ID，再选 URL。数据库唯一约束和应用检查保护极低概率哈希
冲突；若同 public ID 已对应不同 identity key，保存候选
`NEEDS_REVIEW/PUBLIC_ID_COLLISION`，不能复用旧 ID。

### 8.5 自动关联规则

- 强 key 全部指向同一 Opportunity，且来源为 `OFFICIAL_PRIMARY`：创建 LINKED link。
- `OFFICIAL_AGGREGATOR` 只可对已存在的强 key 形成 link 候选；不自动更改正式版本。
- `TRUSTED_SECONDARY` 和 `COMMUNITY_SIGNAL` 只产生候选。
- ATTACHMENT、POSITION_TABLE、CORRECTION、DEADLINE_EXTENSION、CANCELLATION 和 RESULT
  没有强关联时一律 `NEEDS_REVIEW/MISSING_STRONG_RELATION`。
- 同一 Document 重放返回原 link/candidate，不新建重复记录或版本。

### 8.6 Resolver 输出

```python
ResolutionDecision(
    disposition=CREATED | LINKED | NEEDS_REVIEW,
    opportunity_id=UUID | None,
    public_id=str | None,
    candidate_opportunity_ids=tuple[UUID, ...],
    reason_codes=tuple[str, ...],
    resolution_key=str,
)
```

输出不带模糊百分比。相同已排序输入和相同索引必须字节级序列化一致。

## 9. 版本、字段 diff 与证据优先级

### 9.1 派生优先级

优先级只由系统函数生成：

| 来源与文档角色 | precedence |
| --- | ---: |
| `OFFICIAL_PRIMARY` + CORRECTION/DEADLINE_EXTENSION/CANCELLATION | 600 |
| `OFFICIAL_PRIMARY` + POSITION_TABLE/ATTACHMENT | 500 |
| `OFFICIAL_PRIMARY` + PRIMARY_NOTICE/RESULT | 400 |
| `OFFICIAL_PRIMARY` + OFFICIAL_GUIDANCE | 300 |
| `OFFICIAL_AGGREGATOR` | 250 |
| 人工批准映射（Phase 7 候选，Phase 3 不自动调用） | 200 |
| LLM 语义推断（Phase 3 禁止） | 100 |

只有 `OFFICIAL_PRIMARY` 的 300–600 输入可以自动写正式版本。其他输入即使值一致也只关联
文档或生成候选，不提升正式 field evidence。

### 9.2 字段更新规则

对每个 patch 字段：

1. 值与当前值相同：不建新版本。
2. incoming precedence 高于当前：采用并记录 diff。
3. precedence 相同且 incoming `effective_at` 严格更晚：采用。
4. precedence 相同且时间相同但值冲突：`NEEDS_REVIEW/EVIDENCE_CONFLICT`。
5. incoming precedence 更低且值冲突：`NEEDS_REVIEW/LOWER_PRIORITY_CONFLICT`。
6. 任何高影响字段缺 EvidenceRef：拒绝命令，不写 candidate/link/version。

一个 Document 的任一字段冲突时，本轮 patch 整体不发布，避免半应用；可以先保存 link 和
候选，但 Opportunity 当前投影不改变。

### 9.3 事件分类

同一版本只有一个 event type，按以下优先顺序选择：

1. status 变为 CANCELLED → `CANCELLED`
2. status 从 CANCELLED 变为 OPEN/CLOSING_SOON → `REOPENED`
3. `application_window.closes_on` 变化 → `DEADLINE_CHANGED`
4. `attachment_urls` 变化 → `ATTACHMENT_REPLACED`
5. role 为 CORRECTION 或其他正式字段变化 → `CORRECTED`
6. 其他变化 → `UPDATED`
7. 首版 → `CREATED`

取消不得删除申请窗口、附件或旧版本；当前 snapshot 只改变明确 patch 字段。

### 9.4 canonical JSON 与 hash

- UTF-8、Unicode NFC、sorted keys、无多余空白。
- datetime 使用 UTC RFC 3339 `Z`；date 使用 ISO 8601；tuple 序列固定排序。
- UUID 使用小写 canonical string；枚举使用 value。
- `content_sha256` 覆盖 snapshot 和 field evidence，不覆盖数据库 ID 或 created_at。

### 9.5 replay

`replay_opportunity_state(versions, events)` 必须：

1. 按 version 排序并要求从 1 连续递增。
2. 要求每版正好一个 to_version event，事件链连续。
3. 从空状态依次应用 `event.changes`。
4. 每步重建 Snapshot 与 FieldEvidence，重新计算 hash，并与 Version 比较。
5. 返回最新 snapshot；其 legacy 身份/状态字段必须与 Opportunity 表当前投影一致，完整
   Snapshot 必须与 `current_version` 指向的最新 Version 一致。

任何缺版、重复事件、错误 before 值、hash 不同或投影漂移都阻止 Gate。

## 10. merge、split 与 reversal

### 10.1 merge

显式命令指定一个 TARGET 和至少一个 SOURCE。服务要求：

- 所有 Opportunity 存在且互不相同；
- SOURCE 当前没有被另一个 active merge 指向；
- TARGET 不能经 active merge 回到任一 SOURCE，防止环；
- actor、reason 必填；可选 EvidenceRef 必须与 Document 配对。

成功只追加 MERGE action 和 members。源 Opportunity 行、public ID、Version/Event、alias 和
Document link 不删除、不转移。canonical lookup 重放 action 后把 SOURCE 解析到 TARGET；
alias owner 也经同一 canonical lookup 解析。

### 10.2 split

显式命令指定一个 PARENT 和至少两个已创建、各有新 public ID 的 CHILD。服务只追加
SPLIT action/members。父 ID 继续解析到父历史实体，同时 replay 暴露 active children；
不把一个旧 public ID 模糊重定向到多个 child。需要迁移的 Document link 或 alias 必须由
后续显式关联完成，不能自动猜测。

### 10.3 reversal

- reversal 引用原 MERGE/SPLIT action，类型必须匹配且原 action 尚未撤销。
- replay 将原 action 标记 inactive；历史 action 和 reversal 都保留。
- MERGE_REVERSAL 后 SOURCE public ID 再次解析到原 SOURCE。
- SPLIT_REVERSAL 后 parent 不再报告 active children；child 历史实体和 public ID 仍保留，
  不删除、不复用。
- reversal 失败不修改任何 action 或当前身份图。

### 10.4 确定性 identity replay

按 `(occurred_at, action_id)` 排序。先验证 reversal 引用，再应用 active MERGE/SPLIT，检测
merge 环和多 target。输出：

```python
IdentityState(
    canonical_by_opportunity: Mapping[UUID, UUID],
    split_children_by_parent: Mapping[UUID, tuple[UUID, ...]],
    active_action_ids: frozenset[UUID],
)
```

相同 action 序列重复回放必须相等。

## 11. 应用服务与事务边界

### 11.1 文件边界

```text
opportunities/
  models.py       ORM only
  types.py        frozen resolver/versioning input/output dataclasses
  identity.py     normalization, stable public ID, identity replay
  resolver.py     pure conservative resolution
  versioning.py   pure patch/diff/event/replay
  service.py      transaction and persistence orchestration
```

模块不访问网络、对象存储、模型或用户数据。

### 11.2 resolve transaction

```text
validate Document/EvidenceRef pair
  -> load existing link/candidate for idempotent replay
  -> load alias/link/identity index
  -> pure resolve decision
  -> NEEDS_REVIEW: insert candidate, commit, stop
  -> CREATED: insert Opportunity(current_version null) + aliases + link
  -> LINKED: insert link + missing evidence aliases
  -> pure version plan
  -> no semantic diff: commit link only
  -> conflict: insert candidate, do not create version
  -> diff: insert Version + Event, update Opportunity projection/current_version
  -> deferred FK checks at commit
```

唯一冲突采用重新读取后比较语义；不以捕获 IntegrityError 后盲目重试掩盖 public ID 或 alias
冲突。

### 11.3 幂等性

- 同一 Document 只能有一个当前 confirmed link。
- 同一 Document+resolver version+reason set 的候选只保存一次。
- 相同 Opportunity content hash 不创建第二个版本。
- 服务接收可注入 `clock` 和 `id_factory`；测试不用执行当天时间。
- 数据库事务失败不删除任何旧 Version/Event/Action。

## 12. 固定合成样本

仓库新增 `backend/tests/fixtures/opportunities/phase3-resolution-cases.json`，标记：

```json
{
  "schema_version": "0.3.0",
  "synthetic": true,
  "contains_business_facts": false,
  "license": "CC0-1.0 synthetic fixture"
}
```

样本使用 `example.gov`、固定 UUIDv7、固定 UTC 时间和手工可验的预期值，覆盖：

1. 主公告带 external ID，创建稳定 public ID 与 version 1。
2. 重复公告带同一 external ID，关联同一 Opportunity，不建重复 version。
3. 附件显式引用正文，关联同一 Opportunity。
4. 岗位表显式引用正文，新增 locations/attachment URL。
5. 最新官方更正改变一个普通字段，产生 CORRECTED。
6. 延期改变 closes_on，产生 DEADLINE_CHANGED。
7. 取消改变 status，产生 CANCELLED。
8. 低优先级冲突产生 NEEDS_REVIEW，当前版本不变。
9. 相同标题/机构但不同 external ID 只产生 POSSIBLE_DUPLICATE，不误合并。
10. 相同输入在两个空数据库回放得到相同 public ID、snapshot hashes、diff 和 event types。
11. merge、split、两类 reversal 的 action replay。

fixture 不包含真实用户数据、真实官方原件、token、cookie 或网络响应。

## 13. 测试策略

### 13.1 契约测试

- v0.1/v0.2 renderer 与已提交字节完全一致。
- v0.3 枚举、必填字段、UTC、UUIDv7、hash、事件连续性、identity action 形状和 extra
  fields 反例。
- v0.3 示例同时通过 Pydantic 与 Draft 2020-12 JSON Schema。
- exporter 只写 v0.3 目录，不碰旧目录。

### 13.2 纯单元测试

- 每个 test 先命名其能捕获的生产缺陷，再用手工字面量断言。
- Resolver：强 key、冲突 key、弱指纹、来源等级、non-primary 缺关系、稳定 public ID、
  幂等决策和确定排序。
- Versioning：首次快照、无差异、优先级、新旧时间、冲突、字段 diff、事件分类、canonical
  hash 和 replay 失败模式。
- Identity：merge/split/reversal、重复 reversal、环、多 target 和确定性 replay。
- 不 mock Resolver/Versioning；数据库边界使用真实 PostgreSQL 集成测试。

### 13.3 PostgreSQL 集成测试

- PostgreSQL 18、Alembic round trip、metadata diff 为空。
- current_version 悬空、错误 EvidenceRef/Document 配对、事件跳版、重复 to_version、非法
  identity shape、第二个 active Document link 被数据库拒绝。
- 有 v0.3 数据 downgrade 失败且行仍在。
- 旧 v0.1/v0.2 数据升级后逐字段不变。

### 13.4 纵向服务测试

- 固定样本依次运行，检查 link/candidate/version/event/alias 数量和字段。
- 正文、附件、岗位表、更正、延期、取消归入同一 public ID。
- conflict 与误合并保护不改变当前投影。
- replay 输出与 current Opportunity 一致。
- merge/split/reversal 不删除 Opportunity、Version、Event、alias 或 public ID。

### 13.5 TDD 证据

每个实现任务严格执行：

1. 写最小失败测试。
2. 运行并确认因缺少本任务行为而失败，而非 typo/fixture 错误。
3. 写最小生产实现。
4. 运行定向测试与受影响回归。
5. 在提交前做一次真实 mutation check 或临时回退关键实现，观察目标测试失败，再恢复绿色。

## 14. 独立集成环境

新增 `infra/compose.phase3.yaml`：

- compose project 只由 `scripts/verify-phase3.ps1` 以 `deepaha-phase3-$PID` 创建。
- PostgreSQL：`127.0.0.1:55433 -> 5432`。
- Moto：`127.0.0.1:55001 -> 5000`。
- PostgreSQL 数据使用 tmpfs；Moto 不挂载仓库目录。
- verifier 只对该 project 执行 `down --remove-orphans`，不使用 `-v`，不枚举或操作其他
  project。
- verifier 不调用固定占用 55432/55000 的 `verify-phase1.ps1` 或 `verify-phase2.ps1`；
  兼容性由同一数据库上的全部迁移/集成/契约测试证明。

## 15. CI 与验证入口

### 15.1 本地 verifier

`scripts/verify-phase3.ps1` 顺序：

1. 运行 `scripts/verify.ps1`。
2. 启动 Phase 3 scoped compose。
3. locked backend sync。
4. Alembic upgrade head。
5. 运行全部 integration tests。
6. 运行 v0.1/v0.2/v0.3 contract 与 opportunities 单元测试。
7. 运行 `alembic check`。
8. finally 只清理本次 Phase 3 project。

### 15.2 GitHub Actions

新增 `phase3-resolution` job：Python 3.14、PostgreSQL 18.4、Moto 5.2.2、锁文件安装、
迁移、Phase 3 定向/集成测试和 Alembic check。CI 不设置 live permission，不访问网页、
浏览器或模型。

### 15.3 远程验证

分支推送到 `origin/codex/phase-3-opportunity-resolution`。可以创建以
`phase-2-source-ingestion` 为 base 的 stacked draft PR 触发 CI；PR 只能 draft，不得
merge。只有读取 exact head 对应 required jobs 的 success 后才能写 `REMOTE CI PASS`。

## 16. Phase 3 Gate 与状态语言

### 16.1 受控并行状态

Phase 2 Gate OPEN 期间只允许：

```text
IMPLEMENTED_PENDING_PHASE2_GATE
```

含义：Phase 3 候选代码、测试和其分支 CI 可以成功，但基线依赖尚未稳定，不能成为稳定
阶段成果。

禁止写：`STABLE`、`Gate CLOSED`、`released`、`production ready`、`Phase 3 finally
verified`。

### 16.2 候选证据包

```text
docs/gates/phase-3/
  README.md
  acceptance-results.md
  test-summary.md
  resolver-evaluation-summary.md
  security-and-compliance.md
  operations.md
  deferred-decisions.md
```

每份文档分别标记 planned、implemented、locally verified、remote CI 和 blocked-by-Phase2；
不得把 spec、测试数量预期或 CI 配置当实际证据。

### 16.3 Phase 2 关闭后的强制步骤

1. 读取 Phase 2 Gate 实际关闭提交、v0.2 `STABLE` 契约与关闭证据。
2. 在不接触 live project 的前提下，把 Phase 3 分支更新到该提交。
3. 比较 v0.2 Schema 字节、Pydantic、ORM、Alembic head、fixtures 和 verifier 差异。
4. 若基础契约变化，先更新 v0.3 spec/plan/迁移/测试，不做静默兼容。
5. 从空数据库和含 v0.2 数据数据库分别运行迁移。
6. 重跑 `verify.ps1`、`verify-phase3.ps1`、新鲜克隆和远程 CI。
7. 重新生成范围、秘密、产物和 Gate 证据审查。
8. 只有 Phase 2 与 Phase 3 全部退出条件有真实证据，才另行决定 v0.3 STABLE 和
   Phase 3 Gate；本次授权不包含该决定。

## 17. 失败模式

| 失败 | 系统行为 | 不允许 |
| --- | --- | --- |
| 主公告没有 external ID/URL | NEEDS_REVIEW/MISSING_STABLE_ID_KEY | 由标题生成稳定 ID |
| 多个强 key 指向不同 Opportunity | NEEDS_REVIEW/STRONG_KEY_CONFLICT | 任取一个硬合并 |
| 仅弱指纹相同 | NEEDS_REVIEW/POSSIBLE_DUPLICATE | 相似度自动 merge |
| non-primary 文档没有引用 | NEEDS_REVIEW/MISSING_STRONG_RELATION | 新建孤立 Opportunity |
| 低优先级事实冲突 | candidate + 原版本不变 | 覆盖官方事实 |
| 同优先级同时间冲突 | candidate + 原版本不变 | 依赖输入顺序决定 |
| EvidenceRef 不属于 Document | 整个命令失败、事务回滚 | 保存不可追溯事件 |
| 新版本没有实际 diff | 只保存必要 link，不建版 | 空版本/空事件 |
| version/event 跳号或 hash 漂移 | replay/Gate 失败 | 修补当前投影掩盖历史 |
| merge 形成环/多 target | 命令失败、无 action | 写入不可回放身份图 |
| reversal 类型不匹配/重复 | 命令失败、原动作仍 active | 删除原 action |
| public ID 哈希碰撞 | NEEDS_REVIEW/PUBLIC_ID_COLLISION | 复用现有 public ID |
| Phase 3 downgrade 存在数据 | 明确拒绝，数据保留 | 自动删除/重写历史 |
| Phase 3 端口被占用 | verifier 失败并仅清理自身 project | stop/down Phase 2 project |
| Phase 2 基线后续变化 | 保持 pending，更新基线后全量复验 | 宣称当前分支最终完成 |

## 18. 安全、许可与产物边界

- fixtures 全部合成，不提交真实中国官方原文或 Phase 2 live 对象。
- 不读取、复制或写入 Phase 2 live 数据库/S3。
- 不提交 `.env`、数据库、对象、volume、cache、`.venv`、`node_modules`、`.next`、cookie、
  token、Authorization header 或密钥。
- 测试凭据必须标记为一次性本地/CI 常量，只指向 scoped disposable services。
- 日志和 Gate 文档不保存 response body、异常秘密或数据库 URL 密码。
- actor/reason 是审计元数据，不包含真实用户敏感信息。

## 19. 风险与缓解

1. **Phase 2 基线未稳定。** 候选实现严格 pending；关闭后更新基线并全量复验。
2. **现有 Document 没有结构化业务字段。** 用显式 ResolutionDocument 作为边界，不用临时
   文本猜测；后续 extractor 只能替换输入构造，不能改变 Resolver 语义。
3. **自动误合并高风险。** 自动路径只接受官方强 key；弱指纹和冲突全部候选化。
4. **版本表与当前投影双写漂移。** deferred FK、单事务和 replay 集成断言共同约束。
5. **身份操作复杂。** Phase 3 只实现显式 action log 与纯 replay，不做自动 link 迁移、
   批量修复或 UI。
6. **JSONB 约束不如完整关系列精细。** 公共契约由 Pydantic/JSON Schema 严格验证，数据库
   保留关键类型、非空、hash、FK 和唯一约束；不为每个 snapshot 字段建稀疏列。
7. **stable ID hash 极低概率碰撞。** 唯一约束加原 identity key 比较；冲突进入审核，不复用。
8. **测试环境端口冲突。** Phase 3 固定使用 55433/55001 和独立 project，绝不触碰
   55432/55000。

## 20. 明确未证明

- 本设计不证明 Phase 2 Gate 已关闭，也不改变 v0.2 `PROPOSED` 状态。
- 本设计不证明 Resolver 已达到 `>=98%` 归并精确率或 `>=95%` 高影响变化识别率；这些是
  需要版本化评估集证明的 Gate 目标。
- 合成样本不等于 200 个真实 Gold Opportunity，也不证明真实来源覆盖。
- 本设计不证明任何用户价值、资格可信、商业结果、合规扩张或生产安全。
- 本设计不授权 merge、发布或阶段 Gate 关闭。
