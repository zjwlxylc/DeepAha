# DeepAha 开发文档索引

本目录把产品 Blueprint 转换为可执行、可验证、可持续维护的工程基线。这里的内容描述“应该如何开发”，不代表代码已经存在或指标已经达成。

## 文档地图

| 文档 | 作用 | 何时阅读 |
| --- | --- | --- |
| [系统开发路线](./system-roadmap.md) | 阶段顺序、依赖、交付物、Gate 和停止条件 | 规划版本与决定下一阶段时 |
| [系统架构基线](./architecture.md) | 模块边界、运行拓扑、数据流、错误处理和技术选择 | 新增模块、接口或基础设施前 |
| [领域契约 v0.1](./domain-contracts-v0.1.md) | 核心实体、枚举、证据定位和跨模块契约 | 设计数据库、API、Schema 或测试夹具时 |
| [领域契约 v0.2](./domain-contracts-v0.2.md) | Phase 2 已实现、Release Qualification 完成前不得标记 STABLE 的 Endpoint、采集观察、解析尝试和结构化定位契约 | 评审 Phase 2 实现时 |
| [领域契约 v0.3](./domain-contracts-v0.3.md) | Phase 3 已实现、Release Qualification 完成前不得标记 STABLE 的 Opportunity/Version/Event/identity 契约 | 评审 Phase 3 实现时 |
| [领域契约 v0.4](./domain-contracts-v0.4.md) | Phase 4 已实现、Release Qualification 完成前不得标记 STABLE 的规则、资格、MatchSnapshot 与 EvaluationRun 契约 | 评审 Phase 4 实现时 |
| [领域契约 v0.5](./domain-contracts-v0.5.md) | Phase 6 已实现、Release Qualification 完成前不得标记 STABLE 的 UserState、个人排序与行动契约 | 评审 Phase 6 实现时 |
| [领域契约 v0.6](./domain-contracts-v0.6.md) | Phase 7 已实现、Release Qualification 完成前不得标记 STABLE 的反馈、审核、标签与双轨验证契约 | 评审 Phase 7 实现时 |
| [质量与发布策略](./quality-and-release.md) | 测试层级、Golden Dataset、指标证据和发布流程 | 编写测试、评估或准备发布时 |
| [Blueprint v1.2 基线协调](../superpowers/specs/2026-08-21-blueprint-v1.2-baseline-reconciliation-design.md) | 新旧 Blueprint 权威、D8–D12 和阶段映射 | 解释 Phase 2 及后续范围变化时 |
| [Phase 0 设计](../superpowers/specs/2026-08-21-phase-0-engineering-foundation-design.md) | 第一个可交付子项目的设计与验收边界 | 开始创建代码仓库骨架前 |
| [Phase 0 实现计划](../superpowers/plans/2026-08-21-phase-0-engineering-foundation.md) | 可逐项执行的脚手架与验证步骤 | 实际执行 Phase 0 时 |
| [Phase 1 设计](../superpowers/specs/2026-08-21-phase-1-domain-contract-and-raw-evidence-design.md) | 领域契约、原始证据、存储边界和退出条件 | 评审或维护 Phase 1 时 |
| [Phase 1 实现计划](../superpowers/plans/2026-08-21-phase-1-domain-contract-and-raw-evidence.md) | Task 1–7 的 TDD 实施与验证顺序 | 复核 Phase 1 实现证据时 |
| [Phase 1 Gate](../gates/phase-1/README.md) | 本地/新鲜副本/远程 CI 证据与 Gate 判定 | 判断 Phase 1 是否可以关闭时 |
| [Phase 2 设计](../superpowers/specs/2026-08-21-phase-2-source-ingestion-and-document-evidence-design.md) | 观察式采集、三格式解析、证据定位和 Gate 边界 | 开始或评审 Phase 2 时 |
| [Phase 2 实现计划](../superpowers/plans/2026-08-21-phase-2-source-ingestion-and-document-evidence.md) | Task 1–11 的 TDD 实施、live 观察与验证顺序 | 新窗体执行 Phase 2 时 |
| [Phase 2 Gate](../gates/phase-2/README.md) | Engineering Gate 结论与仍在进行的 live/新鲜副本/最终候选 Release Qualification | 判断 Phase 2 工程或发布资格状态时 |
| [Phase 3 设计](../superpowers/specs/2026-08-22-phase-3-opportunity-resolution-versioning-and-change-design.md) | Opportunity 归并、版本、变化与 identity 审计设计 | 评审 Phase 3 候选实现时 |
| [Phase 3 实现计划](../superpowers/plans/2026-08-22-phase-3-opportunity-resolution-versioning-and-change.md) | Task 1–7 的严格 TDD、验证与堆叠交付顺序 | 执行或复核 Phase 3 时 |
| [Phase 3 Gate](../gates/phase-3/README.md) | Phase 3 Engineering Gate、Release Qualification 与 v0.3 成熟度证据 | 判断 Phase 3 工程或发布资格状态时 |
| [Phase 4 设计](../superpowers/specs/2026-08-22-phase-4-rules-eligibility-and-evaluation-design.md) | 受控规则、资格保护、版本回放和合成评估边界 | 评审 Phase 4 设计时 |
| [Phase 4 实现计划](../superpowers/plans/2026-08-22-phase-4-rules-eligibility-and-evaluation.md) | Task 1–10 的 TDD、隔离验证与堆叠交付顺序 | 执行或复核 Phase 4 时 |
| [Phase 4 Gate](../gates/phase-4/README.md) | Phase 4 Engineering Gate、Release Qualification、合成评估边界与 v0.4 成熟度证据 | 判断 Phase 4 工程或发布资格状态时 |
| [Phase 5 设计](../superpowers/specs/2026-08-22-phase-5-public-trust-layer-design.md) | 公开可信目录、只读 API 与 Web/PWA 边界 | 评审 Phase 5 时 |
| [Phase 5 实现计划](../superpowers/plans/2026-08-22-phase-5-public-trust-layer.md) | Phase 5 TDD、浏览器验证与堆叠交付顺序 | 复核 Phase 5 实现证据时 |
| [Phase 5 Gate](../gates/phase-5/README.md) | Phase 5 工程、真实 Gold Release Qualification 与公开 API 成熟度证据 | 判断 Phase 5 状态时 |
| [Phase 6 设计](../superpowers/specs/2026-08-22-phase-6-profile-match-personal-action-design.md) | 渐进画像、授权隔离、确定性匹配与个人行动设计 | 评审 Phase 6 时 |
| [Phase 6 实现计划](../superpowers/plans/2026-08-22-phase-6-profile-match-personal-action.md) | Phase 6 Task 1–8 的 TDD、浏览器、Gate 与堆叠交付顺序 | 执行或复核 Phase 6 时 |
| [Phase 6 Gate](../gates/phase-6/README.md) | Phase 6 四轴状态、合成证据边界、授权安全与真人资格缺口 | 判断 Phase 6 工程或发布资格状态时 |
| [Phase 7 设计](../superpowers/specs/2026-08-22-phase-7-feedback-review-validation-design.md) | 不可变反馈、受控审核、标签资产、双轨验证和发布 HOLD 边界 | 评审 Phase 7 时 |
| [Phase 7 实现计划](../superpowers/plans/2026-08-22-phase-7-feedback-review-validation.md) | Phase 7 Task 1–10 的 TDD、浏览器、Gate 与堆叠交付顺序 | 执行或复核 Phase 7 时 |
| [Phase 7 Gate](../gates/phase-7/README.md) | Phase 7 四轴、合成/真人分轨、授权安全与远程候选证据 | 判断 Phase 7 工程或发布资格状态时 |

## 文档状态词

状态必须按轴记录，禁止把实现、工程验收、真实环境验证和契约成熟度压成级联状态：

- 实现状态：`PLANNED`、`IN_PROGRESS`、`IMPLEMENTED`。
- Engineering Gate：`OPEN`、`CLOSED`。
- Release Qualification：`NOT_STARTED`、`IN_PROGRESS`、`QUALIFIED`、`FAILED`、`BLOCKED`。
- 契约成熟度：`PROPOSED`、`IMPLEMENTED`、`STABLE`。
- 文档自身还可使用 `VERIFIED` 和 `SUPERSEDED`；历史文档中的 `PROPOSED` 不追溯改写为
  `PLANNED`，但不得用历史词汇覆盖当前状态。

当前状态：Phase 0 工程基础和 Phase 1 领域契约/原始证据历史 Gate 已 `CLOSED`。Phase 2 代码、
迁移、来源采集和三格式解析已 `IMPLEMENTED`，Engineering Gate 已 `CLOSED`；live 24 小时观察、
新鲜副本和最终候选验证尚未完成，因此 [Phase 2 Release Qualification](../gates/phase-2/README.md)
为 `IN_PROGRESS`，领域契约 v0.2 为 `IMPLEMENTED`、不得标记 `STABLE`。Phase 3 机会归并、版本
与变化已 `IMPLEMENTED`，自身 Engineering Gate 已 `CLOSED`；Phase 3 Release Qualification 为
`NOT_STARTED`，领域契约 v0.3 为 `IMPLEMENTED`、不得标记 `STABLE`。Phase 3 不继承 Phase 2
Release Qualification 的阻塞状态，但仍不得合并、发布或声称 Release Qualification 已完成。
Phase 4 规则、资格与评估已 `IMPLEMENTED`，Engineering Gate 已 `CLOSED`；Release
Qualification 为 `NOT_STARTED`，领域契约 v0.4 为 `IMPLEMENTED`、不得标记 `STABLE`。受控
堆叠开发不构成合并、发布或 Release Qualification 授权。Phase 5 公开可信层已
`IMPLEMENTED`、Engineering Gate `CLOSED`、Release Qualification `NOT_STARTED`，公开 API
契约成熟度为 `IMPLEMENTED`；其 3 条合成机会不替代 200 条真实 Gold 资格。Phase 6 画像、
匹配与个人行动已 `IMPLEMENTED`，Engineering Gate `CLOSED`，Release Qualification
`NOT_STARTED`，v0.5 成熟度 `IMPLEMENTED`；本地合成、浏览器和 CI 证据不替代真人完成、理解、
认知负担或真实高意图动作。
Phase 7 反馈、审核与双轨验证已 `IMPLEMENTED`，Engineering Gate `CLOSED`；stacked draft PR #8
的精确候选 `63536985...` 已通过八项远程 CI。Release Qualification `NOT_STARTED`，v0.6 成熟度
`IMPLEMENTED`、不得标记 `STABLE`。固定合成反馈/审核夹具的真人参与者为 `0`，唯一
`EXPLANATION_CLARITY` 方向只是工程输入，发布决定为 `HOLD_MISSING_HUMAN_EVIDENCE`。

## 维护规则

1. 产品边界和业务不变量以根目录 `AGENTS.md` 和 Blueprint v1.2 为准；Phase 0–1 的已关闭 Gate 按其版本化历史证据解释。
2. 总体路线只描述阶段与 Gate；具体实现细节放入对应阶段的 spec 和 plan。
3. 每个阶段开始前创建独立 spec；spec 经自审后再创建独立 implementation plan。
4. 下一阶段开发以前一阶段 Engineering Gate `CLOSED` 为治理前提；Release Qualification 未完成
   只阻塞对应发布和契约 `STABLE`。真实代码、迁移和契约依赖仍须按顺序集成并重新验证。
5. 数据契约发生破坏性变化时，必须同时更新契约文档、迁移策略、测试夹具和 API 版本说明。
6. 技术版本、价格、法规和外部服务能力在实施前重新核验；路线图中的版本是 2026-08-21 的规划基线。
7. 文档不得用“已完成”“已通过”描述尚无运行证据的计划。

## 开发原则摘要

- 架构形态：模块化单体（modular monolith），按进程拆分 API、Worker 和 Web，不按业务模块提前拆微服务。
- 实施方式：契约优先（contract-first）、测试驱动（TDD）、纵向切片（vertical slice）、Gate 驱动扩张。
- 事实源：PostgreSQL 与不可变原始证据；Redis、向量索引和 LLM 输出都不是事实源。
- AI 边界：写入时智能（Write-time Intelligence）；LLM 负责理解与候选，确定性规则负责高影响裁决。
- 首个纵向切片：一个真实官方机会从原始证据进入系统，形成 Opportunity、规则、资格四态、公开可信卡和反馈事件。
