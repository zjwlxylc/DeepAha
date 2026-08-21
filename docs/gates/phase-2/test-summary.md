# Phase 2 测试摘要

## 当前工作树环境

- 最近本地 GREEN 验证：2026-08-22T01:10:16+08:00 至 2026-08-22T01:11:01+08:00
- 实现基线 HEAD：`29b633205d377e29e6db06cf20552fbd2a30a111`
- uv `0.12.5`；Python `3.14.7`
- Ruff `0.16.4`；mypy `1.20.2`；pytest `9.1.1`；Alembic `1.19.1`
- Node.js `24.14.0`；项目锁定 pnpm `10.15.0`
- Docker Engine `29.6.1`；PostgreSQL `18.4`；Moto `5.2.2`

## 已实际运行

| 命令/区域 | 结果 |
| --- | --- |
| `powershell -ExecutionPolicy Bypass -File scripts/verify-phase2.ps1` | 退出码 0；根验证、服务启动、迁移、集成、定向测试、漂移检查和 scoped cleanup 全部完成。 |
| 默认后端测试 | `155 passed, 68 deselected`。 |
| Ruff / mypy | 74 个文件格式通过；Lint 通过；70 个源文件无类型错误。 |
| Web | Lint、TypeScript、1 个 Vitest 测试和 Next.js 生产构建通过。 |
| Phase 2 集成 | `68 passed, 155 deselected`；PostgreSQL 18.4 与 Moto 5.2.2。 |
| Phase 2 定向离线 | `148 passed`；contracts/sources/documents。 |
| live runner 回归 | `4 passed`；Windows PowerShell UTF-8 Registry、resume、输出白名单和最小间隔拒绝。 |
| Alembic | 应用 `20260821_0001`、`20260821_0002`；`No new upgrade operations detected.` |

## 故障注入

2026-08-22T00:57:23+08:00 临时把 GOV.UK HTML 测试期望 SHA 最后一位从 `8`
改为 `9`，运行同一 verifier。入口退出码为 1，默认测试结果为
`2 failed, 153 passed, 68 deselected`，两处失败均指向固定 HTML 字节 SHA 不匹配；随后恢复
正确 SHA，同一入口退出 0。该临时错误未提交。

## 尚未发生

- 精确候选提交的新鲜副本验证；
- 五轮 live 观察；
- 远程 CI 结论。
