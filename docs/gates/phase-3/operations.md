# Phase 3 工程验证运维说明

## 本地验证

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-phase3.ps1
```

入口先运行根验证，再创建唯一 `deepaha-phase3-$PID` project，使用 PostgreSQL 55433、Moto
55001，迁移到 head，执行所有 integration 与 contracts/opportunities，最后只 down 自己的
project。不得把该脚本改为调用 Phase 1/2 verifier，也不得复用 55432/55000。

## 迁移与回退

- 正向：`0001 → 0002 → 0003`；`0003` 不重写旧 Opportunity 数据。
- 空表可降级到 `0002` 再升级；存在 v0.3 历史数据时降级必须拒绝，避免删除 Version/Event/
  identity 事实。
- Version/Event/IdentityAction 是追加事实；Projection 可重放，不通过覆盖历史来“修复”。

## 上游基线变化流程

Phase 2 closing commit `6c8a8fb63c68cfbb0f4cf54b6032bfb49a0ef65c` 已通过非重写 merge
纳入，并完成 v0.2/v0.3 Schema 差异修复、空库/已有数据迁移、全量本地与独立 Phase 3
verifier、安全/scope 审查。若上游契约或迁移以后再变化，必须重新执行同一流程并重新判定
受影响的 Engineering Gate；不得沿用旧 SHA 证据。

## 发布边界

Engineering Gate `CLOSED` 不授权合并或发布。Phase 3 Release Qualification 当前为
`NOT_STARTED`；真实 Gold、真实来源、新鲜副本和生产相似环境证据必须通过独立候选流程保存，
不能复用合成样本结论。
