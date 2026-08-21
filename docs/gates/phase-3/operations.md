# Phase 3 候选运维说明

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

## Phase 2 关闭后的强制流程

1. 获取 Phase 2 精确 closing commit，并将本候选更新到该提交之上。
2. 对 v0.2 Schema 字节、导入、迁移、ORM 与证据优先级做兼容差异审查。
3. 分别验证空数据库升级、已有 Phase 2 数据升级、空 v0.3 降级/再升级和有 v0.3 数据降级拒绝。
4. 运行 `scripts/verify.ps1` 与 `scripts/verify-phase3.ps1`。
5. 推送更新后的候选，检查精确 SHA 的全部远程 CI，并刷新 Gate 证据。
6. 只有前序 Gate 与本 Gate 均满足时，另行作出合并/发布/STABLE 决策。
