# Phase 2 验收结果

> 实现状态：`IMPLEMENTED`
>
> Engineering Gate：`CLOSED`
>
> Release Qualification：`IN_PROGRESS`
>
> Release Qualification Activity：`LIVE_OBSERVATION_IN_PROGRESS`
>
> 领域契约 v0.2：`IMPLEMENTED`（不得标记 `STABLE`）

## Engineering Gate 证据

| # | 工程退出条件 | 当前状态 | 已有证据 |
| --- | --- | --- | --- |
| 1 | 相同真实语义抓取产生两条观察、一个 RawArtifact | `PASS` | 脚本化采集集成测试证明同字节两次成功保留两条 CaptureObservation 并复用一个 RawArtifact。 |
| 2 | 失败和 304 独立记录，且 Artifact 关系正确 | `PASS` | 集成测试覆盖失败不建 Artifact、304 引用既有 Artifact、每次尝试独立 observation 和稳定错误码。 |
| 3 | HTML/PDF/XLSX 产生确定性 Document、派生文本和 locator | `PASS` | 固定 fixture 与官方 GOV.UK HTML 的字节身份、解析结果和 locator replay 测试通过。 |
| 4 | 原始对象不被覆盖，解析升级保留旧 Document | `PASS` | DocumentService 集成测试比较解析前后 Artifact 身份，并证明新 parser version 创建新 Document、旧结果保留。 |
| 5 | v0.1/v0.2 Schema、迁移、ORM、契约一致 | `PASS` | 迁移 `20260821_0001 → 20260821_0002`、69 个隔离集成测试、确定性 Schema 测试及 `alembic check` 通过。 |
| 6 | 默认验证离线，代码审查、安全与 scope 无工程 blocker | `PASS` | 默认后端 `159 passed, 69 deselected`；Phase 2 定向 `152 passed`；没有未解决的 `Critical`/`Important`；Phase 2 增量产物、高风险凭据和新增大文件均 0 命中。 |
| 7 | 精确工程证据基线远程 CI 成功 | `PASS` | HEAD `55e9ab647e8a5f81a1786f77a66e291faa04d4c1` 的 [run 32518975541](https://github.com/zjwlxylc/DeepAha/actions/runs/32518975541) 为 `completed / success`，backend、web、integration 全部成功；审查提交后只有证据文档变更。 |
| 8 | Phase 2 分支未进入 Phase 3 功能范围 | `PASS` | Phase 2 变更没有 Resolver/Version/Event、资格规则、用户/API/UI 或未批准基础设施实现；后续阶段保留在独立分支。 |

## Release Qualification 证据

| # | 发布资格条件 | 当前状态 | 已有证据或缺口 |
| --- | --- | --- | --- |
| 1 | 十个官方 Endpoint 完成 live 窗口及健康/维护证据 | `IN_PROGRESS` | 当前文档证据为 1/5 轮、10/10 有效；尚无五轮、至少 24 小时、至少 50 个最终结果，不得写成通过。 |
| 2 | live 最终有效率达到 `>=98%` 且策略合规 | `NOT_STARTED` | 只有窗口完成后才能从仓库外 observation JSON 导出最终聚合值；不得删除失败结果或降低标准。 |
| 3 | 精确最终候选的新鲜副本复现 | `NOT_STARTED` | 尚未运行；不得用既有工作树或计划值替代。 |
| 4 | live 后最终候选统一验证和远程 CI 成功 | `NOT_STARTED` | 只能在不破坏 live 窗口的时点执行；当前工程基线 CI 不替代最终 Release Qualification 候选。 |

## 判定

Phase 2 Engineering Gate 的实现、契约、迁移、测试、安全、代码审查和 scope 证据已经满足，
判定为 `CLOSED`。Release Qualification 仍为 `IN_PROGRESS`，因此领域契约 v0.2 只能标记
`IMPLEMENTED`，不得标记 `STABLE`，也不得正式生产发布或声称真实环境验收完成。

Release Qualification 尚未完成不阻塞 Phase 3/4/5 正常工程开发或各自的 Engineering Gate；
若后续 live 或新鲜副本发现可复现的真实工程缺陷，再据缺陷影响重新评估 Phase 2 Engineering
Gate，而不是因等待时长本身形成下游级联阻塞。
