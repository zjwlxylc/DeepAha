# Phase 2 来源采集与文档证据 Gate

> 实现状态：`IMPLEMENTED`
>
> Engineering Gate：`CLOSED`
>
> Release Qualification：`FAILED`
>
> Release Qualification Activity：`TERMINATED_WITH_INSUFFICIENT_EVIDENCE`
>
> 领域契约 v0.2：`IMPLEMENTED`（不得标记 `STABLE`）
>
> 工程证据基线：`55e9ab647e8a5f81a1786f77a66e291faa04d4c1` 加本治理提交
>
> 证据更新时间：2026-08-23

## Engineering Gate 结论

Phase 2 的 v0.2 契约、PostgreSQL 扩展迁移/ORM、版本化 Source Registry、独立
CaptureObservation、同步 HTTP 采集、源健康/CLI、解析持久化、HTML/PDF/XLSX 确定性
解析器及结构化 Evidence Locator 已实现。等待期代码审查修复后，安全的根验证实际得到默认
后端 159 个通过，隔离基础设施集成测试 69 个通过，Phase 2 定向测试 152 个通过；Web
测试/构建与 Alembic 漂移检查通过，没有未解决的 `Critical` 或 `Important` 审查发现。

代码审查提交 `5779b619dc0260a87a83bee9c5be2d5b0ff77984` 之后到证据基线
`55e9ab647e8a5f81a1786f77a66e291faa04d4c1` 只有文档变更。精确基线的 GitHub Actions
[run 32518975541](https://github.com/zjwlxylc/DeepAha/actions/runs/32518975541) 已实际核验为
`completed / success`，`backend-quality`、`web-quality`、`integration` 全部成功。迁移、契约、
测试、安全、代码审查和 Phase 2 scope 均无新的工程 blocker，因此 Phase 2 Engineering Gate
真实判定为 `CLOSED`。

该结论允许 Phase 3 及后续阶段按各自 Engineering Gate 正常开发、评审和验收；不得再因 Phase 2
Release Qualification 未完成而使用 `BLOCKED_BY_PHASE2` 或 `IMPLEMENTED_PENDING_*` 级联状态。
真实的代码、迁移和契约依赖仍须按实际分支顺序集成并重新验证。

## Release Qualification 收口结论

2026-08-23 按用户明确指令终止当前 live 尝试并删除自动化。最终可计入的重启窗口仅完成
1/5 轮、10 个最终结果，10 个均有效，但既没有跨越至少 24 小时，也没有达到至少 50 个最终
结果。机器重启前的另一窗口虽然留下 4/5 轮、40/40 个有效结果的仓库外 JSON 摘要，但其
PostgreSQL `tmpfs` 与 S3 配对证据已丢失，已明确作废，不能与重启窗口合并。

精确最终候选的新鲜副本复现、live 后统一验证及最终候选远程 CI 均未运行。当前 Release
Qualification 因 `TERMINATED_WITH_INSUFFICIENT_EVIDENCE` 记为 `FAILED`，不是 `QUALIFIED`，
也不是有效率或工程实现失败。领域契约 v0.2 保持 `IMPLEMENTED`、不得标记 `STABLE`；不得
正式生产发布或声称真实环境验收完成。该结论不重开 Phase 2 Engineering Gate，也不阻塞
下游阶段正常工程开发。若未来重新申请 Phase 2 发布资格，必须经新的明确授权，从新的空环境、
独立证据文件和完整门槛重新开始，不能续接本次两个窗口。

详细证据见[代码审查](./code-review.md)、[验收结果](./acceptance-results.md)、
[测试摘要](./test-summary.md)、[来源观察](./source-observation-summary.md)、
[解析评估](./parser-evaluation-summary.md)与[安全合规](./security-and-compliance.md)。
