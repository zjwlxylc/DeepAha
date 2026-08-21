Gate status: BLOCKED_BY_PHASE2
Implementation status: IMPLEMENTED_PENDING_PHASE2_GATE
v0.3 contract status: PROPOSED
Phase 2 prerequisite: OPEN

# Phase 3 Opportunity 归并、版本与变化候选 Gate

证据更新时间：2026-08-22。当前实现基线为 `14ab668ce719dac002f5afe136c28c72fa067d76`
加本 Gate/CI 变更；精确候选提交将在本地与远程验证后记录。

## 当前结论

候选 v0.3 契约、PostgreSQL/Alembic 扩展、保守 Resolver、Version/Event、字段级 diff、
确定性重放以及 merge/split/reversal 追加式审计已实现。本地统一 Phase 3 入口实际退出 0：
默认后端 `243 passed, 107 deselected`，集成 `107 passed, 243 deselected`，contracts 与
opportunities `123 passed`，Web 测试/构建与 Alembic 漂移检查通过。

这不是 Gate 关闭结论。Phase 2 Gate 仍为 `OPEN`，所以 Phase 3 只能是
`IMPLEMENTED_PENDING_PHASE2_GATE`；不得合并、发布、把 v0.3 标记为 `STABLE`，也不得声称
已完成最终验证。远程 CI 当前为 `PENDING`。

Phase 2 关闭后必须更新到它的精确 closing commit，做契约兼容差异审查，并重新执行空库、
已有数据、全量本地、独立 Phase 3 和远程 CI 验证后，才能重新判定本 Gate。

详细证据见[验收结果](./acceptance-results.md)、[测试摘要](./test-summary.md)、
[Resolver 评估](./resolver-evaluation-summary.md)、[安全合规](./security-and-compliance.md)、
[运维说明](./operations.md)与[延期决策](./deferred-decisions.md)。
