# DeepAha 开发文档索引

本目录把产品 Blueprint 转换为可执行、可验证、可持续维护的工程基线。这里的内容描述“应该如何开发”，不代表代码已经存在或指标已经达成。

**本次集成状态（2026-09-10，已合入 main 至 PR #24）：** 调查及证据回收、通用核验与持久定位、机会/岗位身份、独立字段审核、规则候选及独立规则裁决、受限资格内核、受信岗位条件快照及其私有管理页面已经分批合并；快照到持久化合成画像的实际回放、公告规则对精确岗位的独立适用性审阅和完整公告继承快照也已合并。最新主线提交为 `ab06b549dd113b12f4dc8d1e9cfec3e1656ab233`；PR #24 的最终候选 CI #103 全部九项通过，合并与候选同树，main CI #104 成功。尚未完成真实个人资格或发布资格。

| 当前工程环节 | 可复查记录 |
| --- | --- |
| 调查及共享证据核验、持久引用 | [调查底座](2026-09-08-intake-integration.md)、[通用证据块](2026-09-08-evidence-block-integration.md)、[共同核验回执](2026-09-08-generic-evidence-receipts.md) |
| 身份与独立字段事实 | [身份登记](2026-09-08-investigation-identity-integration.md)、[字段审核](2026-09-08-investigation-field-review.md) |
| 规则与受限资格计算 | [规则类型](2026-09-08-rule-candidate-types.md)、[独立规则审核](2026-09-08-investigation-rule-review.md)、[受限内核](2026-09-08-unit-qualification-core.md) |
| 数据库受信快照与管理入口 | [条件快照](2026-09-08-unit-qualification-snapshots.md)、[私有页面](2026-09-08-unit-snapshot-review-ui.md) |
| 精确目标与合成画像回放 | [八项集成及五场景重放](2026-09-08-trusted-unit-profile-replay.md)，PR #21 已合并 |
| 公告规则适用性审阅 | [来源与目标绑定、追加审阅和私有页面](2026-09-08-announcement-rule-applicability.md)，PR #22 已合并 |
| 公告继承快照 | [独立派生版本与完整来源](2026-09-09-announcement-inherited-snapshots.md)，PR #23 已合并 |
| 单位组身份边界 | [稳定身份与旧类型隔离](2026-09-10-group-identity-core.md)，PR #24 已合并 |
| 本批：单位组来源关联 | [完整成员、稳定身份和私有 API](2026-09-10-group-source-bindings.md)，本地验证通过，管理页面后续单独接入 |

最近固定公告的 WMA 调查已完成；同批文件仍为 **94 PASS / 0 FAIL / 30 Word UNVERIFIED，Delivery UNVERIFIED**。三十条旧 Word 引用缺少生产 Reader，诊断发现原文不等于机械通过。当前集成不重新调用 WMA、不改提示词或冻结原件。真实独立批准、完整适用范围、例外、Gold 与真人发布资格尚未完成；整体资格继续保留 UNCERTAIN。后续按[范围与例外集成顺序](../superpowers/plans/2026-09-08-unit-scope-integration-order.md)逐批推进。

下列为 2026-09-07 的历史检查记录；当前状态以上面的 2026-09-10 集成说明为准，原阶段 Gate 与历史证据不因此自动改写。

当时工作批次：[交付一 Direct WMA 内部调查](2026-09-07-delivery1-direct-wma-handoff.md)，位于独立候选分支、尚未合并部署。2026-09-07 实查发现的 [已发布 Agent 配置绑定问题](2026-09-07-delivery1-wma-binding-check.md) 已修正并通过真实连接、二进制传输及恢复检查；当时提示词修订候选未发布，公告校准与人工审核进展见交付说明。

最新接入检查：[Agnes 免费 API 与三路配置差异](evidence/2026-09-07-agnes-api-and-wma-routing.md)。用户已明确 WMA 模型由其在 WorkBuddy 后台固定配置；主仓不指定或覆盖模型。Agnes 直连可用，WMA 真实调查尚未通过，Codex 后续集中于接入和证据链路。

继续执行时已细分调查拒绝、输出/请求上限和取消的失败原因，页面给出中文说明；最新本地回归为后端调查/API 208 项、Web 118 项通过。该轮供应商发布查询返回 HTTP 500，未创建运行；详细范围和证据仍以同一交付说明为准。

## 文档地图

| 文档 | 作用 | 何时阅读 |
| --- | --- | --- |
| [系统开发路线](./system-roadmap.md) | 阶段顺序、依赖、交付物、Gate 和停止条件 | 规划版本与决定下一阶段时 |
| [系统架构基线](./architecture.md) | 模块边界、运行拓扑、数据流、错误处理和技术选择 | 新增模块、接口或基础设施前 |
| [领域契约 v0.1](./domain-contracts-v0.1.md) | 核心实体、枚举、证据定位和跨模块契约 | 设计数据库、API、Schema 或测试夹具时 |
| [领域契约 v0.2](./domain-contracts-v0.2.md) | Phase 2 已实现、当前 Release Qualification 失败且不得标记 STABLE 的 Endpoint、采集观察、解析尝试和结构化定位契约 | 评审 Phase 2 实现时 |
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
| [Phase 2 Gate](../gates/phase-2/README.md) | Engineering Gate 结论与已终止的 live/新鲜副本/最终候选 Release Qualification | 判断 Phase 2 工程或发布资格状态时 |
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
| [Phase 8 设计](../superpowers/specs/2026-08-22-phase-8-deadline-change-reminder-design.md) | 截止时间高影响变更提醒、事务性 Outbox 与 TEST_INBOX 边界 | 评审 Phase 8 时 |
| [Phase 8 实现计划](../superpowers/plans/2026-08-22-phase-8-deadline-change-reminder.md) | Phase 8 TDD、隔离验证、浏览器与 Gate 顺序 | 执行或复核 Phase 8 时 |
| [Phase 8 Gate](../gates/phase-8/README.md) | Phase 8 四轴状态、提醒治理、合成投递与真人/生产资格缺口 | 判断 Phase 8 工程或发布资格状态时 |

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
新鲜副本和最终候选验证未完成即终止，因此 [Phase 2 Release Qualification](../gates/phase-2/README.md)
为 `FAILED`，领域契约 v0.2 为 `IMPLEMENTED`、不得标记 `STABLE`。Phase 3 机会归并、版本
与变化已 `IMPLEMENTED`，自身 Engineering Gate 已 `CLOSED`；Phase 3 Release Qualification 为
`NOT_STARTED`，领域契约 v0.3 为 `IMPLEMENTED`、不得标记 `STABLE`。Phase 3 不继承 Phase 2
Release Qualification 的阻塞状态，但仍不得发布或声称 Release Qualification 已完成。
Phase 4 规则、资格与评估已 `IMPLEMENTED`，Engineering Gate 已 `CLOSED`；Release
Qualification 为 `NOT_STARTED`，领域契约 v0.4 为 `IMPLEMENTED`、不得标记 `STABLE`。受控
工程集成不构成发布或 Release Qualification 授权。Phase 5 公开可信层已
`IMPLEMENTED`、Engineering Gate `CLOSED`、Release Qualification `NOT_STARTED`，公开 API
契约成熟度为 `IMPLEMENTED`；其 3 条合成机会不替代 200 条真实 Gold 资格。Phase 6 画像、
匹配与个人行动已 `IMPLEMENTED`，Engineering Gate `CLOSED`，Release Qualification
`NOT_STARTED`，v0.5 成熟度 `IMPLEMENTED`；本地合成、浏览器和 CI 证据不替代真人完成、理解、
认知负担或真实高意图动作。
Phase 7 反馈、审核与双轨验证已 `IMPLEMENTED`，Engineering Gate `CLOSED`；最终候选
`151288574a44af43f147b5ddfd9ddf77ca3094ac` 的 GitHub Actions run `32571881831` 已通过八项
远程 CI。Release Qualification `NOT_STARTED`，v0.6 成熟度
`IMPLEMENTED`、不得标记 `STABLE`。固定合成反馈/审核夹具的真人参与者为 `0`，唯一
`EXPLANATION_CLARITY` 方向只是工程输入，发布决定为 `HOLD_MISSING_HUMAN_EVIDENCE`。
Phase 8 截止时间高影响变更提醒已 `IMPLEMENTED`，Engineering Gate `CLOSED`，Release
Qualification `NOT_STARTED`，v0.7 成熟度 `IMPLEMENTED`；投递端仅为合成 `TEST_INBOX`，
真实参与者和真实通知渠道均为 `0`，不得写成打开率、投诉率、留存率或行动指标。

## 维护规则

1. 产品边界和业务不变量以根目录 `AGENTS.md` 和 Blueprint v1.2 为准；Phase 0–1 的已关闭 Gate 按其版本化历史证据解释。
2. 总体路线只描述阶段与 Gate；具体实现细节放入对应阶段的 spec 和 plan。
3. 每个阶段开始前创建独立 spec；spec 经自审后再创建独立 implementation plan。
4. 下一阶段开发以前一阶段 Engineering Gate `CLOSED` 为治理前提；Release Qualification 未取得 `QUALIFIED`
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
