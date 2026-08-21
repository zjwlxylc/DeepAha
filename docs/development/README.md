# DeepAha 开发文档索引

本目录把产品 Blueprint 转换为可执行、可验证、可持续维护的工程基线。这里的内容描述“应该如何开发”，不代表代码已经存在或指标已经达成。

## 文档地图

| 文档 | 作用 | 何时阅读 |
| --- | --- | --- |
| [系统开发路线](./system-roadmap.md) | 阶段顺序、依赖、交付物、Gate 和停止条件 | 规划版本与决定下一阶段时 |
| [系统架构基线](./architecture.md) | 模块边界、运行拓扑、数据流、错误处理和技术选择 | 新增模块、接口或基础设施前 |
| [领域契约 v0.1](./domain-contracts-v0.1.md) | 核心实体、枚举、证据定位和跨模块契约 | 设计数据库、API、Schema 或测试夹具时 |
| [领域契约 v0.2](./domain-contracts-v0.2.md) | Phase 2 已实现、Gate 关闭前仍为 PROPOSED 的 Endpoint、采集观察、解析尝试和结构化定位契约 | 评审 Phase 2 实现时 |
| [领域契约 v0.3](./domain-contracts-v0.3.md) | Phase 3 候选 Opportunity/Version/Event/identity 契约；受 Phase 2 Gate 阻塞，仍为 PROPOSED | 评审 Phase 3 候选实现时 |
| [领域契约 v0.4](./domain-contracts-v0.4.md) | Phase 4 候选规则、资格、MatchSnapshot 与 EvaluationRun 契约；受 Phase 2/3 Gate 阻塞，仍为 PROPOSED | 评审 Phase 4 候选实现时 |
| [质量与发布策略](./quality-and-release.md) | 测试层级、Golden Dataset、指标证据和发布流程 | 编写测试、评估或准备发布时 |
| [Blueprint v1.2 基线协调](../superpowers/specs/2026-08-21-blueprint-v1.2-baseline-reconciliation-design.md) | 新旧 Blueprint 权威、D8–D12 和阶段映射 | 解释 Phase 2 及后续范围变化时 |
| [Phase 0 设计](../superpowers/specs/2026-08-21-phase-0-engineering-foundation-design.md) | 第一个可交付子项目的设计与验收边界 | 开始创建代码仓库骨架前 |
| [Phase 0 实现计划](../superpowers/plans/2026-08-21-phase-0-engineering-foundation.md) | 可逐项执行的脚手架与验证步骤 | 实际执行 Phase 0 时 |
| [Phase 1 设计](../superpowers/specs/2026-08-21-phase-1-domain-contract-and-raw-evidence-design.md) | 领域契约、原始证据、存储边界和退出条件 | 评审或维护 Phase 1 时 |
| [Phase 1 实现计划](../superpowers/plans/2026-08-21-phase-1-domain-contract-and-raw-evidence.md) | Task 1–7 的 TDD 实施与验证顺序 | 复核 Phase 1 实现证据时 |
| [Phase 1 Gate](../gates/phase-1/README.md) | 本地/新鲜副本/远程 CI 证据与 Gate 判定 | 判断 Phase 1 是否可以关闭时 |
| [Phase 2 设计](../superpowers/specs/2026-08-21-phase-2-source-ingestion-and-document-evidence-design.md) | 观察式采集、三格式解析、证据定位和 Gate 边界 | 开始或评审 Phase 2 时 |
| [Phase 2 实现计划](../superpowers/plans/2026-08-21-phase-2-source-ingestion-and-document-evidence.md) | Task 1–11 的 TDD 实施、live 观察与验证顺序 | 新窗体执行 Phase 2 时 |
| [Phase 2 Gate](../gates/phase-2/README.md) | 已实现能力、本地证据与仍缺失的 live/新鲜副本/CI 证据 | 判断 Phase 2 是否允许关闭时 |
| [Phase 3 设计](../superpowers/specs/2026-08-22-phase-3-opportunity-resolution-versioning-and-change-design.md) | Opportunity 归并、版本、变化与 identity 审计设计 | 评审 Phase 3 候选实现时 |
| [Phase 3 实现计划](../superpowers/plans/2026-08-22-phase-3-opportunity-resolution-versioning-and-change.md) | Task 1–7 的严格 TDD、验证与堆叠交付顺序 | 执行或复核 Phase 3 时 |
| [Phase 3 Gate](../gates/phase-3/README.md) | 本地候选证据、远程 CI 与 Phase 2 前置阻塞 | 判断 Phase 3 候选状态时 |
| [Phase 4 设计](../superpowers/specs/2026-08-22-phase-4-rules-eligibility-and-evaluation-design.md) | 受控规则、资格保护、版本回放和合成评估边界 | 评审 Phase 4 候选设计时 |
| [Phase 4 实现计划](../superpowers/plans/2026-08-22-phase-4-rules-eligibility-and-evaluation.md) | Task 1–10 的 TDD、隔离验证与堆叠交付顺序 | 执行或复核 Phase 4 时 |
| [Phase 4 Gate](../gates/phase-4/README.md) | 本地/远程候选证据、合成评估边界和双 Gate 阻塞 | 判断 Phase 4 候选状态时 |

## 文档状态词

所有开发文档只使用以下状态，禁止混用：

- `PROPOSED`：已形成方案，尚未开始实现。
- `IN_PROGRESS`：存在正在执行的任务，但尚未通过完整验收。
- `IMPLEMENTED`：代码已合入工作区，未必通过阶段 Gate。
- `VERIFIED`：指定测试和证据已经运行并满足文档中的验收条件。
- `SUPERSEDED`：被明确的新版本替代，只保留历史参考。

当前状态：Phase 0/1 Gate 已 `CLOSED`；Phase 2 已实现但其 live Gate 仍 `OPEN`，v0.2 仍为 `PROPOSED`。Phase 3 候选状态为 `IMPLEMENTED_PENDING_PHASE2_GATE`，[Phase 3 Gate](../gates/phase-3/README.md) 为 `BLOCKED_BY_PHASE2`，v0.3 仍为 `PROPOSED`。经明确授权，Phase 4 在下一层独立分支形成候选实现，但状态上限为 `IMPLEMENTED_PENDING_PHASE2_PHASE3_GATES`，[Phase 4 Gate](../gates/phase-4/README.md) 不得关闭，v0.4 仍为 `PROPOSED`。受控堆叠开发不得被解释为绕过前序 Gate、合并或发布授权。

## 维护规则

1. 产品边界和业务不变量以根目录 `AGENTS.md` 和 Blueprint v1.2 为准；Phase 0–1 的已关闭 Gate 按其版本化历史证据解释。
2. 总体路线只描述阶段与 Gate；具体实现细节放入对应阶段的 spec 和 plan。
3. 每个阶段开始前创建独立 spec；spec 经自审后再创建独立 implementation plan。
4. 前一阶段未通过退出条件时，不得提前执行依赖它的阶段。
5. 数据契约发生破坏性变化时，必须同时更新契约文档、迁移策略、测试夹具和 API 版本说明。
6. 技术版本、价格、法规和外部服务能力在实施前重新核验；路线图中的版本是 2026-08-21 的规划基线。
7. 文档不得用“已完成”“已通过”描述尚无运行证据的计划。

## 开发原则摘要

- 架构形态：模块化单体（modular monolith），按进程拆分 API、Worker 和 Web，不按业务模块提前拆微服务。
- 实施方式：契约优先（contract-first）、测试驱动（TDD）、纵向切片（vertical slice）、Gate 驱动扩张。
- 事实源：PostgreSQL 与不可变原始证据；Redis、向量索引和 LLM 输出都不是事实源。
- AI 边界：写入时智能（Write-time Intelligence）；LLM 负责理解与候选，确定性规则负责高影响裁决。
- 首个纵向切片：一个真实官方机会从原始证据进入系统，形成 Opportunity、规则、资格四态、公开可信卡和反馈事件。
