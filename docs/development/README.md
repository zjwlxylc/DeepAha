# DeepAha 开发文档索引

本目录把产品 Blueprint 转换为可执行、可验证、可持续维护的工程基线。这里的内容描述“应该如何开发”，不代表代码已经存在或指标已经达成。

## 文档地图

| 文档 | 作用 | 何时阅读 |
| --- | --- | --- |
| [系统开发路线](./system-roadmap.md) | 阶段顺序、依赖、交付物、Gate 和停止条件 | 规划版本与决定下一阶段时 |
| [系统架构基线](./architecture.md) | 模块边界、运行拓扑、数据流、错误处理和技术选择 | 新增模块、接口或基础设施前 |
| [领域契约 v0.1](./domain-contracts-v0.1.md) | 核心实体、枚举、证据定位和跨模块契约 | 设计数据库、API、Schema 或测试夹具时 |
| [领域契约 v0.2](./domain-contracts-v0.2.md) | Phase 2 已实现、Release Qualification 完成前不得标记 STABLE 的 Endpoint、采集观察、解析尝试和结构化定位契约 | 评审 Phase 2 实现时 |
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
为 `IN_PROGRESS`，领域契约 v0.2 为 `IMPLEMENTED`、不得标记 `STABLE`。Phase 3 及后续阶段
根据各自 Engineering Gate 独立验收，不再继承 Phase 2 Release Qualification 的阻塞状态。

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
