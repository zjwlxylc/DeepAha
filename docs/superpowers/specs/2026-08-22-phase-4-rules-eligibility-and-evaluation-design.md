# DeepAha Phase 4 规则、资格与评估设计

> 治理更新（2026-08-22）：本文正文保留最初受控堆叠执行的历史前提和措辞，不机械改写。
> Phase 2 closing commit `6c8a8fb63c68cfbb0f4cf54b6032bfb49a0ef65c` 与 Phase 3 closing
> commit `8003a1c2ab2485a1173b2d4bb9deafbbab6e949c` 已通过历史保留 merge commit
> `09526c61a1a0410e9a9127c989ecfaecf3f0ea02` 完整纳入 Phase 4。当前四轴状态为：
> Implementation `IMPLEMENTED`，Engineering Gate `CLOSED`，Release Qualification
> `NOT_STARTED`，v0.4 Contract Maturity `IMPLEMENTED`。正文中的
> `PROPOSED_IMPLEMENTATION_BLOCKED_BY_PHASE2_PHASE3_GATES`、`BLOCKED_BY_PHASE2`、
> `IMPLEMENTED_PENDING_PHASE2_PHASE3_GATES`、Phase 2 `OPEN` / Phase 3 blocked，以及
> v0.2-v0.4 `PROPOSED` 均为当时执行边界，现已由四轴治理状态取代；它们不代表当前状态。

> 状态：`PROPOSED_IMPLEMENTATION_BLOCKED_BY_PHASE2_PHASE3_GATES`
>
> 日期：2026-08-22
>
> 目标阶段：Phase 4
>
> 精确实现起点：`5a5847be266980e83eccd8718c23b77e788ee481`
>
> 前置 Gate：Phase 2 `OPEN`；Phase 3 `BLOCKED_BY_PHASE2`
>
> 候选契约：`0.4.0`
>
> 最大允许交付状态：`IMPLEMENTED_PENDING_PHASE2_PHASE3_GATES`

本文授权在独立堆叠分支实现 Phase 4 候选，但不授权合并、发布、把 v0.3/v0.4
标记为 `STABLE`、关闭 Phase 3/4 Gate，或声称最终验证完成。Phase 2 或 Phase 3
任一 closing commit 改变基础契约时，必须更新到精确 closing commit，完成兼容审查，
并重新执行全部本地、迁移、新鲜副本与远程验证。

## 1. 目的

Phase 4 在已版本化 Opportunity 之上建立最小、确定性、可审计的资格判断与评估回放：

```text
OpportunityVersion + evidenced RuleSet + ProfileSnapshot
  + major catalog/mapping versions + scenario clock
  -> typed Rule Compiler
  -> deterministic Eligibility Engine
  -> EligibilityResult (four states)
  -> immutable MatchSnapshot
  -> versioned EvaluationRun
```

本阶段只证明：

1. 受控 Rule DSL 能拒绝未知操作、类型错误、缺失引用、循环和无法确定的编译输入。
2. 专业、学历、毕业年份/应届身份、年龄日期边界、户籍/地区、证书与缺失字段可以由
   固定输入产生确定性逐规则结果。
3. `INELIGIBLE` 只能由至少一条确定性冲突规则和官方证据产生；缺失、模糊、冲突或
   仅语义候选不能被错误否定。
4. MatchSnapshot 固定所有输入与组件版本，相同输入可以重放，版本差异可以解释。
5. 许可安全或合成 Golden Dataset、20 个母画像和 100 个版本化合成画像可以批量运行，
   但只承担覆盖、边界、反事实和固定样本回归责任。
6. 评估证据如实区分实现、本地验证、远程 CI、合成评估与前序 Gate 阻塞。

Phase 4 不实现画像采集、用户 API、排序、个人行动、LLM、模型网关或 UI。

## 2. 依据与已核验起点

### 2.1 上位不变量

- 核心链路为
  `Source -> RawArtifact -> Document -> Opportunity -> Version/Event -> RuleSet -> Match -> Action`。
- 资格只允许 `ELIGIBLE`、`LIKELY_ELIGIBLE`、`UNCERTAIN`、`INELIGIBLE`。
- `INELIGIBLE` 必须由确定性冲突规则和官方证据支持。
- 信息缺失、公告模糊、证据冲突或仅语义候选时，最高只能进入 `UNCERTAIN`。
- 资格与排序分离；排序永远不能覆盖硬资格。
- 专业匹配优先使用官方目录、专业代码与人工批准映射；语义模型只可提出候选。
- 固定证据优先级为：

```text
最新官方更正 > 正式岗位/政策附件 > 原始正式公告 > 官方 FAQ/指南
> 人工批准目录映射 > LLM 语义推断
```

- 规则、画像、机会、匹配和评估都必须版本化；模拟画像、隐藏真值、期望机会集合和
  场景时钟必须可回放。
- 模拟结果不能证明真人信任、留存、付费、真实准确率或生产风险水平。

### 2.2 当前仓库事实

- Phase 1 Gate 已 `CLOSED`，v0.1 的历史稳定契约不改写。
- Phase 2 Gate 仍 `OPEN`，v0.2 仍为 `PROPOSED`。
- Phase 3 最终候选提交为 `5a5847be266980e83eccd8718c23b77e788ee481`；其精确
  GitHub Actions run `32524131142` 四个 jobs 均为 `success`，stacked draft PR #3
  仍 open/draft/unmerged；v0.3 仍为 `PROPOSED`。
- 当前 Alembic head 为 `20260822_0003`；OpportunityVersion、Event、字段证据、稳定
  public ID 和 identity action 已形成候选输入边界。
- 当前 worktree 是独立 linked worktree，分支为
  `codex/phase-4-rules-eligibility-evaluation`，精确 HEAD 等于 Phase 3 候选 SHA。
- Phase 2 live 观察使用 `deepaha-phase2-live-gate`、PostgreSQL 55432、Moto 55000；
  Phase 4 禁止访问、停止、复用或监控它们。

### 2.3 已发现的基线可复现性缺口

当前机器的 Git 系统配置为 `core.autocrlf=true`。Phase 3 合成 Resolver fixture 的 Git blob
是 LF，SHA-256 为批准值
`1ab32974f7dc982bb6cf12b8d023a53b136136b1c254779003b789734d8f7f82`；工作树被检出为
CRLF 后 SHA-256 变为
`16c981ca6c8366331efd24a1bb2b2c2ec9df265e2348d1be33ecdddbff3a9fdc`，导致根验证唯一失败。

实现前先增加精确 `.gitattributes` 规则，使该合成 fixture 目录固定 `eol=lf`；不修改 fixture
语义或批准 Git blob。修复后必须确认工作树字节恢复批准 SHA，并重新运行根验证。该变更是
Phase 3 固定字节测试在 Windows worktree 上可复现的最小前置修复，不是 Phase 3 业务改动。

## 3. 设计假设与成功条件

### 3.1 明确假设

1. RuleSet 的输入是已由人工或上游确定性流程结构化的规则，不从 Document 自由文本临时
   抽取规则。
2. Phase 4 规则只使用受控字段、操作符和显式 Rule ID 依赖，不执行任意代码或动态表达式。
3. OpportunityVersion 是正式规则的机会侧版本边界；规则证据必须引用已持久化 EvidenceRef，
   并证明 EvidenceRef 属于对应 Document。
4. ProfileSnapshot 是最小、版本化输入；它可以是合成画像，但本阶段没有真实用户账户、
   采集同意或画像编辑 API。
5. 专业目录与人工映射是固定、版本化评估资产；本阶段不声称覆盖任一完整国家/地区目录。
6. 场景时钟是显式 `LocalDate`，日期边界不读取执行当天。
7. MatchSnapshot 是资格快照，不包含排序分数；未来 Ranking 只能引用它，不能修改其状态。
8. Golden Dataset 的“Gold”表示人工固定的回归真值，不等于 200 个真实 Gold Opportunity。

### 3.2 可验证成功条件

- v0.1/v0.2/v0.3 Schema bytes 与 Python import paths 在实现前后不变；默认 exporter 仍为 v0.1。
- v0.4 Pydantic、JSON Schema、示例、ORM、迁移与真实 PostgreSQL 约束一致。
- Alembic 空数据往返
  `0001 -> 0002 -> 0003 -> 0004 -> 0003 -> 0004` 通过；存在 v0.4 数据时 downgrade
  明确拒绝且不删除数据。
- Rule Compiler 对全部受控字段/操作组合生成确定性拓扑顺序，并拒绝未知操作、类型错误、
  缺失依赖、非法操作数数量和循环。
- 固定 Golden Dataset 覆盖四态与所有指定领域边界；所有预期非 `INELIGIBLE` 用例的
  意外 `INELIGIBLE` 数为 0。
- 所有固定 `INELIGIBLE` 用例至少有一个 deterministic conflict leaf，且该 leaf 引用
  precedence 300–600 的官方证据。
- 相同 OpportunityVersion、RuleSet、ProfileSnapshot、目录/映射版本、engine/compiler
  版本与 scenario clock 重放得到相同结果、逐规则输出与 input SHA。
- 修改任一版本或一个反事实字段会产生可解释的 MatchSnapshot/Evaluation diff，而不会
  静默覆盖历史。
- 20 个母画像与 100 个合成画像均通过 Schema、分层覆盖审计和批量回放；固定版本和字节
  SHA 可复核。
- Phase 4 verifier 只使用 `deepaha-phase4-$PID`、PostgreSQL 55434、Moto 55002，并只
  清理自身 project。
- 默认测试和 CI 不访问实时站点、浏览器或模型。
- 本地/新鲜/远程验证成功后，最终状态仍为
  `IMPLEMENTED_PENDING_PHASE2_PHASE3_GATES`。

## 4. 范围

### 4.1 包含

- 候选 v0.4 契约、Schema、示例和契约说明。
- `RuleSet`、`Rule`、`RuleEvidence`、`ProfileSnapshot`、`EligibilityResult`、
  `MatchSnapshot`、`EvaluationRun` 及必要子对象。
- PostgreSQL 18/Alembic 扩展迁移与 ORM；旧数据不重写。
- 最小 typed Rule DSL、Rule Compiler、循环/类型/操作数校验。
- 专业精确代码、目录祖先、人工批准映射和语义候选的受控解析。
- 学历、毕业年份、应届身份、出生日期边界、户籍/地区、证书与缺失字段规则。
- 确定性 Eligibility Engine、四态聚合、逐规则解释和官方证据保护。
- MatchSnapshot 持久化、幂等输入摘要和确定性重放。
- 许可安全/合成 Golden Dataset、20 母画像、100 版本化合成画像与批量评估。
- Phase 4 verifier、CI job、Gate 候选证据包和范围/秘密/产物审查。

### 4.2 明确不包含

- Phase 5 公开机会索引、详情页、搜索、Web/PWA 或任何 UI。
- Phase 6 真实画像采集、账户、偏好排序、PriorityScore、个人行动、API。
- LLM、Model Gateway、prompt、模型供应商、实时语义推断或模型评分。
- Redis、Valkey、Celery、pgvector、调度器、Worker 或异步编排。
- Playwright、Docling、OCR、扫描件或解析器改造。
- 通知、反馈、审核 UI、商业化、生产云、真实用户或真实画像。
- Phase 2 live 采集、heartbeat、Source Registry、端口或 Gate 状态修改。
- Phase 3 merge、Resolver、Version/Event 或 identity 行为修改。
- 用合成数据计算、宣称或近似生产 `INELIGIBLE <=0.5%`。

## 5. 方案比较

### 5.1 方案 A：类型化规则图 + 纯编译器/引擎 + 事务服务（采用）

- 原子规则使用受控字段和操作符；组合规则引用 Rule ID。
- 编译器构建有向无环图，输出不可变执行计划。
- 专业匹配是字段解析适配器，不扩张 DSL 为通用编程语言。
- 引擎和回放是纯函数；数据库服务只验证外键、持久化输入/输出并保证幂等。

优点：类型、循环、证据和回放可以独立测试；执行面最小；符合模块化单体边界。代价：需要
显式字段注册表和编译步骤。

### 5.2 方案 B：直接解释 RuleSet JSONB（不采用）

代码更少，但每次运行都重复猜测类型/拓扑，循环和未知操作容易在运行期才暴露；无法稳定区分
“无效规则”与“用户信息不足”，也削弱编译版本与回放证据。

### 5.3 方案 C：JSON Logic/CEL/自定义通用表达式语言（不采用）

表达力更强，但 Phase 4 只需少量确定性规则。通用语言会增加解析、安全、资源限制、升级兼容
和解释复杂度，诱导业务规则隐藏在难审计表达式中。

## 6. 候选 v0.4 公共契约

### 6.1 兼容策略

- `contracts/schemas/v0.1.0/`、`v0.2.0/`、`v0.3.0/` 永久保留并逐字节回归。
- 新类型只放入 `deepaha.contracts.phase4`；不移动或重命名旧类型。
- exporter 新增显式 `--version 0.4.0`；未指定版本仍导出 v0.1。
- `PHASE4_SCHEMAS` 复制 v0.3 兼容集合，再增加 Phase 4 对象。
- 新 Schema 只写 `contracts/schemas/v0.4.0/`；示例只使用固定 UUIDv7、`example.gov`、
  合成画像和无业务事实的文字。

### 6.2 受控值

```text
EligibilityStatus = ELIGIBLE | LIKELY_ELIGIBLE | UNCERTAIN | INELIGIBLE

RuleOperator =
  EQ | NE | IN | NOT_IN | GTE | LTE | BETWEEN |
  CONTAINS_ANY | CONTAINS_ALL | EXISTS | NOT_EXISTS |
  AND | OR | NOT

RuleValueType = STRING | INTEGER | DATE | STRING_SET | BOOLEAN

RuleOutcome = SATISFIED | CONFLICT | UNKNOWN

RuleEvidenceAuthority =
  LATEST_OFFICIAL_CORRECTION |
  FORMAL_OFFICIAL_ATTACHMENT |
  ORIGINAL_OFFICIAL_NOTICE |
  OFFICIAL_FAQ_GUIDANCE |
  HUMAN_APPROVED_MAPPING |
  LLM_SEMANTIC_INFERENCE

EvidenceRelation = SUPPORTS | CONTRADICTS

EducationLevel =
  SECONDARY | ASSOCIATE | BACHELOR | MASTER | DOCTORATE

StudentStatus =
  ENROLLED | GRADUATING | RECENT_GRADUATE | EMPLOYED | OTHER

EvaluationComponent = RULE_ENGINE | ELIGIBILITY | MATCH_REPLAY

EvaluationRunStatus = RUNNING | COMPLETED | FAILED
```

`LLM_SEMANTIC_INFERENCE` 只为契约边界和负面测试保留；Phase 4 没有生成它的模型路径。

### 6.3 规则字段注册表

DSL 只允许以下字段；字段类型是编译器的一部分，调用者不能覆盖：

| field | value type | 典型操作 |
| --- | --- | --- |
| `education_level` | STRING | `IN`、`EQ` |
| `major_code` | STRING | `IN`（经专业解析器） |
| `graduation_year` | INTEGER | `EQ`、`IN`、`BETWEEN` |
| `student_status` | STRING | `IN`、`EQ` |
| `birth_date` | DATE | `GTE`、`LTE`、`BETWEEN` |
| `hukou_region` | STRING | `IN`、`EQ` |
| `residence_region` | STRING | `IN`、`EQ` |
| `target_regions` | STRING_SET | `CONTAINS_ANY`、`CONTAINS_ALL` |
| `certificates` | STRING_SET | `CONTAINS_ANY`、`CONTAINS_ALL` |

新字段或操作组合需要新契约版本或明确兼容扩展；运行时不能接受任意路径。

### 6.4 `RuleEvidence`

```yaml
evidence_ref_id: EntityId
document_id: EntityId
authority: RuleEvidenceAuthority
precedence: integer 100..600
relation: SUPPORTS | CONTRADICTS
effective_at: Instant
assertion_sha256: Sha256
```

authority 与 precedence 固定映射：600、500、400、300、200、100。Pydantic 和编译器均拒绝
不匹配。多个最高 precedence 证据若 relation 冲突，该 Rule 的证据状态为冲突，结果只能
`UNKNOWN`；较低 precedence 的矛盾证据不覆盖更高正式证据，但保留在快照中解释。

### 6.5 `Rule`

```yaml
rule_id: EntityId
code: non-empty stable machine code
operator: RuleOperator
field: controlled field | null
value_type: RuleValueType | null
value: JsonValue | null
operand_rule_ids: [unique EntityId]
required: boolean
reason_template: non-empty string
evidence: [RuleEvidence]
```

形状约束：

- 原子操作要求 `field` 与 `value_type`；`EXISTS/NOT_EXISTS` 不带 value。
- `EQ/NE/GTE/LTE` 要求单值；`BETWEEN` 要求两个有序同类型值。
- `IN/NOT_IN/CONTAINS_ANY/CONTAINS_ALL` 要求非空、去重、稳定排序的同类型数组。
- `AND/OR` 至少两个 operand；`NOT` 恰好一个 operand；组合规则不带 field/value/evidence。
- 原子 required Rule 必须至少有一个 Evidence；组合结果继承冲突 leaf 的 Evidence。
- `code` 在同一 RuleSet version 内唯一；Rule ID 在同一版本内唯一。

### 6.6 `RuleSet`

```yaml
rule_set_id: EntityId
version: VersionNumber
opportunity_id: EntityId
opportunity_version: VersionNumber
rules: [non-empty Rule]
root_rule_ids: [non-empty unique EntityId]
review_status: APPROVED
rule_schema_version: "0.4.0"
created_at: Instant
```

Phase 4 只评估显式 `APPROVED` RuleSet。root 必须引用当前 rules；未从 root 可达的规则、
缺失引用和循环都由编译器拒绝。版本行不可变。

### 6.7 `ProfileAttributes` 与 `ProfileSnapshot`

```yaml
ProfileAttributes:
  education_level: EducationLevel | null
  major_name: non-empty string | null
  major_code: non-empty string | null
  graduation_year: integer | null
  student_status: StudentStatus | null
  birth_date: LocalDate | null
  hukou_region: non-empty string | null
  residence_region: non-empty string | null
  target_regions: [unique non-empty string]
  certificates: [unique non-empty string]

ProfileSnapshot:
  profile_snapshot_id: EntityId
  profile_id: EntityId
  version: VersionNumber
  synthetic: boolean
  persona_family_id: EntityId | null
  attributes: ProfileAttributes
  scenario_clock: LocalDate
  profile_schema_version: "0.4.0"
  created_at: Instant
  created_by: non-empty string
  reviewed_by: non-empty string
  change_note: non-empty string
```

本阶段 fixture 强制 `synthetic=true`。生产个人身份、联系方式、完整生日日志、同意和保留期限
不在本阶段实现。ProfileSnapshot 不可修改；变化创建新 version。

### 6.8 `RuleEvaluation` 与 `EligibilityResult`

```yaml
RuleEvaluation:
  rule_id: EntityId
  outcome: SATISFIED | CONFLICT | UNKNOWN
  deterministic: boolean
  official_evidence: boolean
  reason_code: non-empty machine code
  evidence_ref_ids: [unique EntityId]
  missing_fields: [unique controlled field]

EligibilityResult:
  result_id: EntityId
  status: EligibilityStatus
  rule_evaluations: [non-empty RuleEvaluation]
  satisfied_rule_ids: [unique EntityId]
  conflict_rule_ids: [unique EntityId]
  unknown_rule_ids: [unique EntityId]
  missing_fields: [unique controlled field]
  review_reasons: [unique non-empty machine code]
  evaluated_at: Instant
  engine_version: non-empty string
```

ID 列表必须与逐规则 outcome 一致。Result 不包含排序分或概率。

### 6.9 `MatchSnapshot`

```yaml
snapshot_id: EntityId
opportunity_id: EntityId
opportunity_version: VersionNumber
rule_set_id: EntityId
rule_set_version: VersionNumber
profile_snapshot_id: EntityId
profile_version: VersionNumber
eligibility_result: EligibilityResult
compiler_version: non-empty string
engine_version: non-empty string
major_catalog_version: non-empty string
major_mapping_version: non-empty string
scenario_clock: LocalDate
input_sha256: Sha256
created_at: Instant
```

`input_sha256` 覆盖 canonical JSON：OpportunityVersion identity/hash、RuleSet identity/version/
内容、ProfileSnapshot identity/version/内容、目录/映射版本、compiler/engine version 和 scenario
clock。相同 input SHA 返回同一快照；任何版本差异生成新快照。

### 6.10 `EvaluationRun`

```yaml
EvaluationCaseResult:
  case_id: non-empty string
  expected_status: EligibilityStatus
  actual_status: EligibilityStatus
  passed: boolean
  match_snapshot_id: EntityId
  reason_codes: [unique non-empty string]

EvaluationMetrics:
  total_cases: integer >= 1
  passed_cases: integer >= 0
  unexpected_ineligible_count: integer >= 0
  replay_mismatch_count: integer >= 0
  status_counts: object keyed by EligibilityStatus

EvaluationRun:
  run_id: EntityId
  dataset_id: non-empty string
  dataset_version: non-empty string
  dataset_sha256: Sha256
  component: RULE_ENGINE | ELIGIBILITY | MATCH_REPLAY
  component_versions:
    contract: "0.4.0"
    compiler: non-empty string
    engine: non-empty string
    major_catalog: non-empty string
    major_mapping: non-empty string
  synthetic: boolean
  status: RUNNING | COMPLETED | FAILED
  case_results: [EvaluationCaseResult]
  metrics: EvaluationMetrics | null
  started_at: Instant
  completed_at: Instant | null
```

COMPLETED 要求 completed_at、非空 case results、metrics 与实际结果一致。FAILED 只保存已运行的
部分结果和稳定错误摘要；本阶段不保存异常堆栈或秘密。

## 7. Rule Compiler

### 7.1 输入与输出

```python
compile_rule_set(rule_set: RuleSetSchemaV04) -> CompiledRuleSet
```

`CompiledRuleSet` 是 frozen dataclass，包含按确定性拓扑顺序排列的 `CompiledRule`、root IDs、
字段注册表版本、compiler version 和 canonical SHA。它不持有 SQLAlchemy session。

### 7.2 编译步骤

1. 验证 RuleSet review/version/OpportunityVersion 形状。
2. 建立 Rule ID、code 和依赖索引，拒绝重复、缺失或不可达规则。
3. 依据固定字段注册表检查 value type 与 operator 合法组合。
4. 把 string/integer/date/string-set 编译为不可变规范值；拒绝隐式类型转换。
5. 验证 BETWEEN 顺序、集合非空去重、组合 operand 基数。
6. 用确定性 Kahn 拓扑排序；候选队列按 Rule UUID 排序；剩余节点表示循环并拒绝。
7. 计算 evidence precedence 状态和 canonical compiler SHA。

稳定错误码至少包括：

```text
RULE_UNKNOWN_OPERATOR
RULE_FIELD_NOT_ALLOWED
RULE_TYPE_MISMATCH
RULE_VALUE_SHAPE_INVALID
RULE_OPERAND_COUNT_INVALID
RULE_REFERENCE_MISSING
RULE_REFERENCE_UNREACHABLE
RULE_CYCLE_DETECTED
RULE_EVIDENCE_PRECEDENCE_INVALID
RULESET_NOT_APPROVED
```

错误不触发部分编译或猜测默认值。

## 8. 专业目录与人工映射

### 8.1 固定资产

Phase 4 提交两个纯合成、CC0 fixture：

- `major-catalog-v0.4.0-synthetic.json`：代码、父代码、名称、aliases。
- `major-mappings-v0.4.0-synthetic.json`：输入专业名/代码到批准目标代码，包含 actor、reason、
  evidence ID、reviewed_at。

资产均有 manifest SHA、版本和 `synthetic=true`。它们不声称复刻或覆盖真实教育部目录。

### 8.2 决议顺序

对 `major_code IN allowed_codes`：

1. profile code 精确命中 allowed code → `EXACT`，确定性满足。
2. profile code 的固定目录祖先命中 allowed code → `CATALOG`，确定性满足。
3. 人工批准 mapping 命中 allowed code → `APPROVED_MAPPING`，满足但使整体最高为
   `LIKELY_ELIGIBLE`。
4. fixture 显式提供 semantic candidate → `SEMANTIC_CANDIDATE`，Rule outcome 为 UNKNOWN，
   整体为 `UNCERTAIN`；本阶段不调用模型生成候选。
5. 完整有效 code 与目录均无匹配 → `NO_MATCH`，可形成确定性冲突。
6. 缺 code/name、目录版本缺失、mapping 冲突或未知 code → `UNKNOWN/CONFLICT`，不能形成
   `INELIGIBLE`。

目录和 mapping version 必须写入 MatchSnapshot；找不到指定版本时拒绝运行，不回退到
“最新版本”。

## 9. Eligibility Engine

### 9.1 原子求值

- 字段缺失：`UNKNOWN/MISSING_PROFILE_FIELD`。
- Rule 最高 precedence 证据同级冲突：`UNKNOWN/EVIDENCE_CONFLICT`。
- 仅 LLM/semantic evidence：`UNKNOWN/SEMANTIC_CANDIDATE_ONLY`。
- 比较、集合和日期条件真：`SATISFIED`。
- 条件假且输入完整、Rule 确定：`CONFLICT`。
- 日期使用 ISO LocalDate 和显式 scenario clock；不得读取系统日期。
- set 操作使用规范化、去重、排序值；不做模糊字符串相似度。

### 9.2 组合求值

- `AND`：任一 CONFLICT → CONFLICT；否则任一 UNKNOWN → UNKNOWN；否则 SATISFIED。
- `OR`：任一 SATISFIED → SATISFIED；否则任一 UNKNOWN → UNKNOWN；否则 CONFLICT。
- `NOT`：SATISFIED/CONFLICT 互换；UNKNOWN 保持 UNKNOWN。
- root 顺序与全部逐规则输出顺序来自 compiled topological order，不依赖 dict/数据库返回顺序。

### 9.3 四态聚合

按以下固定顺序：

1. 任一 required root 为 deterministic CONFLICT，且至少一个冲突 leaf 有 precedence 300–600
   官方 Evidence → `INELIGIBLE`。
2. 否则任一 required root UNKNOWN、任一冲突缺官方 Evidence、缺字段、公告/证据冲突或仅
   semantic candidate → `UNCERTAIN`。
3. 否则全部 required root SATISFIED，但任一满足依赖 precedence 200 人工映射或存在明确
   非关键 review reason → `LIKELY_ELIGIBLE`。
4. 否则全部 required root 由确定性官方证据满足 → `ELIGIBLE`。

禁止用概率、匹配百分比或排序分覆盖该状态。

## 10. PostgreSQL 18 与 ORM

### 10.1 新增表

```text
rule_sets
rules
rule_evidence
profile_snapshots
eligibility_results
match_snapshots
evaluation_runs
evaluation_case_results
```

规则表达式、画像 attributes 和逐规则结果可使用 JSONB，但关键身份、版本、状态、外键、
hash 和唯一性使用关系列与数据库约束。

### 10.2 RuleSet/Rule/Evidence

- `rule_sets` 复合主键 `(rule_set_id, version)`；复合外键到
  `(opportunity_id, opportunity_version)`；唯一 `(opportunity_id, opportunity_version, version)`。
- `rules` 复合主键 `(rule_set_id, rule_set_version, rule_id)`；保存 code/operator/field/
  value_type/value/operands/required/reason_template。
- `rule_evidence` 复合主键包含 Rule identity 与 evidence_ref_id；复合外键
  `(evidence_ref_id, document_id)` 保证定位；保存 authority/precedence/relation/effective/hash。
- RuleSet/Rule/Evidence 行不可更新；应用服务只追加新 RuleSet version。

### 10.3 ProfileSnapshot

- `profile_snapshot_id` UUIDv7 主键；唯一 `(profile_id, version)`。
- attributes 是 JSONB object；scenario_clock 是 date；synthetic、schema/version/audit 字段为列。
- 本阶段导入服务拒绝 `synthetic=false`，避免候选实现被误用为真实用户存储。

### 10.4 EligibilityResult 与 MatchSnapshot

- `eligibility_results` 引用 OpportunityVersion、RuleSet version、ProfileSnapshot；保存四态、
  rule results、缺失/审核 reason、engine version、evaluated_at。
- `match_snapshots` 以 UUIDv7 为主键，`eligibility_result_id` 唯一且删除受限；重复保存关键
  输入版本、component versions、scenario clock 和 input SHA 以便独立审计。
- `input_sha256` 唯一；同输入返回原快照，不创建第二个 Result。
- MatchSnapshot 与 Result 的 opportunity/rule/profile identity 由应用服务和集成测试逐字段
  验证；数据库外键阻止悬空版本。

### 10.5 EvaluationRun

- `evaluation_runs` 保存 dataset/version/SHA、component versions、synthetic、status、时间和
  metrics。
- `evaluation_case_results` 主键 `(run_id, case_id)`，引用 MatchSnapshot，保存 expected/
  actual/pass/reason codes。
- RUNNING → COMPLETED/FAILED 是唯一允许的更新；已完成 case result 和 metrics 不覆盖。
- FAILED 保留已完成 case rows；重试创建新 run ID，不改写旧 run。

### 10.6 Alembic revision `20260822_0004`

升级只新增表、约束和索引，不修改 v0.1–v0.3 表或历史行。降级前检查全部 v0.4 表；任一有
数据时抛出稳定 RuntimeError，空表才按依赖逆序删除。迁移和 ORM 必须通过 metadata diff。

## 11. 应用服务与事务边界

### 11.1 文件边界

```text
contracts/phase4.py       v0.4 public contract
rules/types.py            compiled immutable values
rules/compiler.py         syntax/type/graph/evidence compilation
rules/major.py            versioned synthetic catalog/mapping resolution
rules/models.py           RuleSet/Rule/Evidence ORM
profiles/models.py        ProfileSnapshot ORM
eligibility/engine.py     pure four-state evaluation
eligibility/service.py    persistence and deterministic replay orchestration
matching/models.py        EligibilityResult/MatchSnapshot ORM
evaluation/models.py      EvaluationRun/Case ORM
evaluation/runner.py      fixed dataset batch replay and metrics
```

不创建 API route、Worker、网络、对象存储或模型依赖。

### 11.2 Match transaction

```text
validate OpportunityVersion exists
  -> load exact RuleSet version and exact ProfileSnapshot
  -> load exact catalog/mapping versions
  -> compile RuleSet or reject structural invalidity
  -> canonicalize all input versions and compute input SHA
  -> existing input SHA: reload/validate and return existing snapshot
  -> pure eligibility evaluation
  -> assert INELIGIBLE evidence invariant
  -> insert EligibilityResult + MatchSnapshot in one transaction
  -> commit and return detached contract values
```

结构无效（未知 op、类型错误、循环、缺引用）拒绝运行并不保存 MatchSnapshot；业务不确定
（缺字段、证据冲突、semantic candidate）保存 `UNCERTAIN` 快照。

### 11.3 Evaluation transaction

EvaluationRun 先以 RUNNING 追加；每个 case 调用 Match service 并追加 case row。全部 case 完成后
从实际 rows 计算 metrics 并转 COMPLETED。预期错误转 FAILED 并保留已完成 rows；程序错误回滚
当前 case 后重新抛出，不伪造完成结果。

## 12. 固定 Golden Dataset 与合成画像

### 12.1 数据资产

```text
backend/tests/fixtures/evaluation/
  phase4-golden-dataset.json
  phase4-mother-profiles.json
  phase4-synthetic-profiles.json
  major-catalog-v0.4.0-synthetic.json
  major-mappings-v0.4.0-synthetic.json
  phase4-fixtures.manifest.json
```

全部文件标记 `synthetic=true`、`contains_personal_data=false`、`contains_business_facts=false`、
`license="CC0-1.0 synthetic fixture"`，并固定 UTF-8 LF bytes、SHA-256 和生成器版本。

### 12.2 Golden cases

固定用例至少覆盖：

- 四种 Eligibility 状态。
- 专业 exact、catalog ancestor、approved mapping、semantic candidate、no-match、missing、
  mapping conflict。
- 学历满足/冲突/缺失。
- 毕业年份与应届身份满足、边界、冲突、缺失。
- 出生日期精确边界、边界前后一天、缺失。
- 户籍/地区集合满足、冲突、缺失。
- 证书 contains-all 满足、缺一项、缺字段。
- 最新更正覆盖原公告、同级证据冲突、低优先级矛盾不覆盖。
- 组合 AND/OR/NOT、未知操作、类型错误、缺引用和循环。
- expected non-INELIGIBLE 的错误否定保护。

### 12.3 20 母画像与 100 合成画像

20 个母画像按人生阶段、学历/专业、地域、目标和约束分层；每个母画像生成 5 个确定性变体，
共 100 个 ProfileSnapshot。变体只改变一个或少量显式字段并递增 version/change note，支持：

- 资格边界覆盖；
- 单字段反事实；
- 缺失字段降级；
- 专业目录/映射路径；
- 场景时钟与毕业状态变化；
- 批量回放稳定性。

fixture 生成器本身不调用模型，不生成“真人行为”或商业指标。Golden expected status 由手工
固定 case 声明，不由被测引擎自标注。

### 12.4 指标边界

EvaluationRun 可以报告：用例数、通过数、四态计数、unexpected INELIGIBLE 数、replay mismatch
数。它不得报告或暗示：真人准确率、生产误杀率、信任、留存、行动、付费或市场结论。

固定数据集要求 `unexpected_ineligible_count = 0`。计划阈值 `<=0.5%` 只有在未来真实、独立
标注评估中证明后才能宣称。

## 13. 测试策略

### 13.1 契约

- 旧 renderer 与 checked-in bytes 完全一致。
- v0.4 Schema/exemplar/Pydantic 双重校验。
- Rule shape、evidence precedence、四态结果列表一致性、Match version/hash、EvaluationRun
  状态/metrics 反例。
- v0.4 exporter 只写新目录，默认仍写 v0.1。

### 13.2 Compiler

- 每个操作/字段合法组合与非法组合。
- 日期/整数不隐式转换；集合去重排序；BETWEEN 边界。
- 缺引用、不可达、组合基数、self-cycle、multi-node cycle。
- 对相同 RuleSet 输入，多次编译顺序/hash 相同。

### 13.3 Eligibility

- 每个领域规则的满足、冲突、缺失和边界。
- 证据 precedence 和同级冲突。
- 专业 exact/catalog/mapping/semantic/no-match/missing。
- AND/OR/NOT 三值逻辑。
- 四态聚合及 INELIGIBLE 官方证据 invariant。
- 排序字段不存在，输入中注入 score/priority 被 Schema 拒绝。

### 13.4 PostgreSQL 集成

- PostgreSQL 18、迁移 round trip、metadata diff。
- 旧数据升级逐字段不变；v0.4 数据 downgrade 拒绝。
- Rule/Evidence/OpportunityVersion 配对、Profile version、Match FK/hash/idempotency、Evaluation
  transition/Case FK 约束。
- Match service 在事务失败后不留下半个 Result/Snapshot。

### 13.5 回放与评估

- 相同输入两次返回同一 MatchSnapshot。
- 修改 Profile/RuleSet/Opportunity/engine/catalog/mapping/scenario 任一版本得到新 input SHA 与
  可解释 diff。
- Golden Dataset fixed cases 全部运行；expected non-INELIGIBLE 零意外否定。
- 20 母画像/100 合成画像 Schema、分层计数和批量回放。
- 两个空数据库上的语义输出相同；排除随机内部 UUID 后结果序列相同。

### 13.6 TDD 证据

每个实现任务：

1. 先写最小失败测试并读取正确失败原因。
2. 写使该测试通过的最小实现。
3. 运行定向测试与受影响回归。
4. 在提交前临时 mutation 或关键实现回退，确认目标测试会失败，再恢复绿色。
5. 运行新鲜、与风险相称的提交前验证后再提交/推送。

## 14. 独立集成环境

新增 `infra/compose.phase4.yaml`：

- PostgreSQL `127.0.0.1:55434 -> 5432`。
- Moto `127.0.0.1:55002 -> 5000`；Phase 4 当前不使用对象字节，但保持与完整 integration
  fixture/既有迁移测试一致。
- PostgreSQL 使用 tmpfs；Moto 不挂载仓库目录。
- project name 只由 verifier 以 `deepaha-phase4-$PID` 创建。
- cleanup 只执行该 project 的 `down --remove-orphans`；不使用 `-v`，不枚举其他 project。
- verifier 不调用 Phase 1/2/3 integration verifier，不引用 55432/55000/55433/55001。

## 15. CI 与验证入口

### 15.1 本地 verifier

`scripts/verify-phase4.ps1`：

1. 运行根 `scripts/verify.ps1`。
2. 启动 Phase 4 scoped compose。
3. locked backend sync。
4. Alembic upgrade head。
5. 运行全部 integration tests。
6. 运行 v0.1–v0.4 contracts、rules、eligibility、evaluation 定向测试。
7. 运行 `alembic check`。
8. finally 只清理本次 Phase 4 project。

### 15.2 GitHub Actions

新增 `phase4-rules-evaluation` job，并将 Phase 4 分支加入 push trigger：Python 3.14、
PostgreSQL 18.4、Moto 5.2.2、locked sync、migration、Phase 4 定向/集成测试与 Alembic check。
CI 不设置 live permission，不访问网页、浏览器或模型。

### 15.3 Stacked draft PR

允许创建 base `codex/phase-3-opportunity-resolution`、head
`codex/phase-4-rules-eligibility-evaluation` 的 stacked draft PR。标题和正文必须明确：

- Phase 2/3 Gate 阻塞；
- 不 merge、不 ready；
- v0.4 PROPOSED；
- 独立端口；
- 精确验证命令；
- Phase 2/3 closing commit 后更新基线并全量复验。

## 16. Gate 与证据包

### 16.1 状态语言

Phase 2/3 Gate 未关闭时只允许：

```text
Gate status: BLOCKED_BY_PHASE2_PHASE3
Implementation status: IMPLEMENTED_PENDING_PHASE2_PHASE3_GATES
v0.4 contract status: PROPOSED
```

禁止写 `STABLE`、`Gate CLOSED`、`released`、`production ready`、`final verification complete`。

### 16.2 候选证据包

```text
docs/gates/phase-4/
  README.md
  acceptance-results.md
  test-summary.md
  evaluation-summary.md
  security-and-compliance.md
  operations.md
  deferred-decisions.md
```

证据分别标记 planned、implemented、locally verified、remote CI、synthetic evaluation 和
blocked-by-Phase2/3。固定用例通过数不能变成真实准确率。

### 16.3 Phase 2/3 关闭后的强制步骤

1. 获取 Phase 2 与 Phase 3 的精确 closing commits、稳定契约与关闭证据。
2. 将 Phase 4 更新到精确 Phase 3 closing commit；不得继续依赖旧候选 SHA。
3. 比较 v0.2/v0.3 Schema bytes、imports、ORM、Alembic head、OpportunityVersion/EvidenceRef
   语义和 fixtures。
4. 基础契约变化时先更新 Phase 4 spec/plan/contract/migration/tests，不做静默兼容。
5. 分别验证空数据库、含 Phase 2/3 数据数据库、空 v0.4 downgrade/upgrade 和有 v0.4 数据
   downgrade 拒绝。
6. 重跑 root/Phase 4 verifier、Golden/100 profiles、新鲜克隆与远程 CI。
7. 重做 scope/secret/artifact、合成数据边界和 Gate 证据审查。
8. 只有 Phase 2/3/4 所有退出条件有真实证据后，才另行决定 v0.3/v0.4 STABLE、Gate 关闭、
   合并或发布；本次授权不包含该决定。

## 17. 失败模式

| 失败 | 系统行为 | 不允许 |
| --- | --- | --- |
| unknown operator/field | compile error | 运行期猜测含义 |
| value type/shape mismatch | compile error | 隐式字符串/日期/数字转换 |
| missing/cyclic Rule ref | compile error | 跳过节点或依赖输入顺序 |
| Profile field missing | UNKNOWN + missing field | 默认成 false 或 INELIGIBLE |
| evidence same-rank conflict | UNKNOWN/EVIDENCE_CONFLICT | 任取一条证据 |
| only semantic candidate | UNCERTAIN | 形成 SATISFIED/INELIGIBLE |
| approved major mapping positive | 最多 LIKELY_ELIGIBLE | 冒充官方 exact |
| major code unknown/mapping conflict | UNCERTAIN | 以 no-match 判否 |
| deterministic conflict without official Evidence | UNCERTAIN | INELIGIBLE |
| deterministic conflict with official Evidence | INELIGIBLE + exact leaf/evidence | 隐藏规则或证据 |
| scenario clock absent/mismatch | reject run | 使用系统当天 |
| input version asset absent | reject run | 回退到 latest |
| same input re-evaluation | return existing MatchSnapshot | 新建漂移快照 |
| Evaluation partial failure | FAILED + preserved completed cases | 标记 COMPLETED |
| v0.4 downgrade with data | explicit refusal, retain data | 删除/重写历史 |
| Phase 4 port occupied | fail and clean only own project | 操作其他 compose project |
| Phase 2/3 base changes | remain pending; update and fully reverify | 沿用旧 CI evidence |

## 18. 安全、隐私、许可与产物边界

- 全部 Phase 4 fixtures 为 CC0 合成数据，无真实用户、真实履历或官方原件。
- Profile fixture 只含测试需要的最小字段；日志、Gate 文档和 reason code 不打印完整属性。
- RuleEvidence 只保存内部 EvidenceRef ID、Document ID、hash 和权威等级，不复制原文。
- 不读取 Phase 2 live 数据库、S3、observation file、heartbeat 或运行日志。
- 不提交 `.env`、数据库、对象、volume、cache、`.venv`、`node_modules`、`.next`、cookie、
  token、Authorization header、密钥或真实个人数据。
- 测试凭据必须明确标注 disposable，只指向 Phase 4 scoped local/CI services。
- Phase 4 不作自动化重大人生决定的生产发布；所有用户文案仍应保留官方审核边界，但本阶段
  不实现 UI/API。

## 19. 风险与缓解

1. **前序契约未稳定。** 只交付 blocked candidate；closing commit 后强制更新与复验。
2. **DSL 变成通用语言。** 固定字段/操作注册表、无函数/循环/动态代码；新语义需契约演进。
3. **专业匹配误杀。** exact/catalog 才可确定；mapping 只正向 likely；semantic/unknown/conflict
   全部 uncertain。
4. **EvidenceRef 只有 ID 但规则值可能漂移。** RuleSet version 不可变、assertion SHA 和
   precedence 固定、MatchSnapshot 保存 RuleSet version/input hash。
5. **JSONB 约束有限。** Pydantic/Compiler 严格验证，数据库保存关键 FK/version/status/hash；
   真实数据库反例与 metadata diff 补充。
6. **画像含敏感字段。** 当前只接受 synthetic，字段最小，未来真实用户存储必须独立 spec。
7. **合成评估被误读。** 文档、Schema 和 metrics 明示 synthetic；不输出生产准确率。
8. **Match 与未来 Ranking 耦合。** v0.4 无 score/priority 字段；Ranking 只能成为后续独立层。
9. **Windows 行尾破坏固定 SHA。** 对固定 fixture 路径显式 `eol=lf` 并用 Git blob/工作树
   SHA 回归。

## 20. 明确未证明

- 不证明 Phase 2/3 Gate 已关闭，也不改变 v0.2/v0.3 PROPOSED 状态。
- 不证明 v0.4 已稳定、已发布或可用于真实用户决策。
- 不证明真实 `INELIGIBLE` 误杀率 `<=0.5%`、四态一致率 `>=95%` 或证据覆盖的生产水平。
- 不证明真实专业目录完整性、法规口径、全国地域规则或机构审核结果。
- 100 个合成画像不证明真人信任、理解、认知负担、留存、行动或付费。
- 不证明 Phase 5/6 UI/API/用户闭环、商业 Gate 或合规扩张。
- 不授权 merge、ready、release、STABLE 或 Gate 关闭。
