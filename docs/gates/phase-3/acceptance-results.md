# Phase 3 验收结果

> Gate 状态：`BLOCKED_BY_PHASE2`
>
> 实现状态：`IMPLEMENTED_PENDING_PHASE2_GATE`
>
> v0.3：`PROPOSED`

| # | Phase 3 退出条件 | 当前状态 | 已有证据或缺口 |
| --- | --- | --- | --- |
| 1 | v0.1/v0.2 字节与导入路径不变，v0.3 Schema/Pydantic/example 一致 | `LOCAL PASS` | contracts 定向测试包含旧字节回归与 v0.3 严格契约；v0.3 仍为 PROPOSED。 |
| 2 | PostgreSQL 迁移/ORM 支持 Version、Event、审计 link/alias/identity，旧数据不重写 | `LOCAL PASS` | `0001 → 0002 → 0003`、Phase 3 数据库约束、拒绝有 v0.3 数据的降级及 `alembic check` 已由 integration/verifier 执行。 |
| 3 | 正文、附件、岗位表、更正、延期、取消归入稳定 Opportunity | `LOCAL PASS (SYNTHETIC)` | 固定 CC0 合成 fixture 的 7 条主路径解析到同一 public_id；重复公告不新增版本。 |
| 4 | 不足或冲突时保守候选，不做不确定硬合并 | `LOCAL PASS (SYNTHETIC)` | 冲突与弱指纹误合并保护均为 NEEDS_REVIEW，且 Opportunity 投影/历史计数不变。 |
| 5 | Version 快照、字段 diff、高影响 Event 与 EvidenceRef 可回放 | `LOCAL PASS (SYNTHETIC)` | 版本/事件连续性、官方证据优先级、before/after、hash 漂移和两套新库重放相等测试通过。 |
| 6 | stable ID、alias、merge/split/reversal 追加可审计 | `LOCAL PASS (SYNTHETIC)` | 纯身份图与 PostgreSQL 服务测试覆盖环、多目标、重复撤销、成员复制、alias 不移动、失败原子性。 |
| 7 | 独立 verifier、CI 与范围/安全审查 | `PARTIAL` | 本地 `scripts/verify-phase3.ps1` 退出 0；远程 `phase3-resolution` 结论与最终候选 SHA 仍 PENDING。 |
| 8 | Phase 2 先关闭并重新验证 Phase 3 | `BLOCKED` | Phase 2 prerequisite 仍 OPEN；不得关闭 Phase 3 Gate。 |

所有 Resolver/变化/identity 业务场景证据均来自许可安全的合成样本，不是实际来源准确率、
生产性能或真实世界 `>=95%` 高影响变更识别率证明。
