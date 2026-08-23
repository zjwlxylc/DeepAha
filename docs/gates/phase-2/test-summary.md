# Phase 2 测试摘要

## 当前工作树环境

- 最近本地 GREEN 验证：2026-08-23T08:13+08:00
- 代码审查基线 HEAD：`5779b619dc0260a87a83bee9c5be2d5b0ff77984`
- uv `0.12.5`；Python `3.14.7`
- Ruff `0.16.4`；mypy `1.20.2`；pytest `9.1.1`；Alembic `1.19.1`
- Node.js `24.14.0`；项目锁定 pnpm `10.15.0`
- Docker Engine `29.6.1`；PostgreSQL `18.4`；Moto `5.2.2`

## 已实际运行

| 命令/区域 | 结果 |
| --- | --- |
| `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`（Release Qualification 收口文档） | 2026-08-23 退出码 0；默认后端 `159 passed, 69 deselected`，Web lint、TypeScript、1 个 Vitest 测试与 Next.js 生产构建通过。 |
| `powershell -ExecutionPolicy Bypass -File scripts/verify-phase2.ps1`（`29b6332`） | 退出码 0；根验证、服务启动、迁移、集成、定向测试、漂移检查和 scoped cleanup 全部完成。 |
| `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`（`5779b61`） | 退出码 0；未占用 live 基础设施。默认后端 `159 passed, 69 deselected`。 |
| Ruff / mypy | 74 个文件格式通过；Lint 通过；70 个源文件无类型错误。 |
| Web | Lint、TypeScript、1 个 Vitest 测试和 Next.js 生产构建通过。 |
| Phase 2 集成（`5779b61`，隔离端口 55434/55002） | `69 passed, 159 deselected`；PostgreSQL 18.4 与 Moto 5.2.2，`alembic check` 无漂移。 |
| Phase 2 定向离线（`5779b61`） | `152 passed`；contracts/sources/documents。 |
| live runner 回归 | `4 passed`；Windows PowerShell UTF-8 Registry、resume、输出白名单和最小间隔拒绝。 |
| Alembic | 应用 `20260821_0001`、`20260821_0002`；`No new upgrade operations detected.` |

隔离集成第一次使用测试 bucket `deepaha-raw-review`，唯一失败是既有测试明确断言 bucket
`deepaha-raw`；这不是产品失败。保持相同隔离容器、改用测试契约要求的 bucket 后重跑得到
`69 passed, 159 deselected`。临时容器按精确名称删除；当次验证期间 live 的 55432/55000 容器
持续健康，当前收口时已另行删除。

## 远程 CI

| 提交 | Run | 实际结论 |
| --- | --- | --- |
| `64b09f508d9118a771195c4ab6449cc8487ab057` | [32507301635](https://github.com/zjwlxylc/DeepAha/actions/runs/32507301635) | `completed / success` |
| `ed0bf33beb5c00ed30ee95c8ade26f84f10186fc` | [32515719316](https://github.com/zjwlxylc/DeepAha/actions/runs/32515719316) | `completed / success` |
| `5779b619dc0260a87a83bee9c5be2d5b0ff77984` | [32518043724](https://github.com/zjwlxylc/DeepAha/actions/runs/32518043724) | `completed / success` |
| `55e9ab647e8a5f81a1786f77a66e291faa04d4c1` | [32518975541](https://github.com/zjwlxylc/DeepAha/actions/runs/32518975541) | `completed / success`；`backend-quality`、`web-quality`、`integration` 全部成功 |

## 故障注入

2026-08-22T00:57:23+08:00 临时把 GOV.UK HTML 测试期望 SHA 最后一位从 `8`
改为 `9`，运行同一 verifier。入口退出码为 1，默认测试结果为
`2 failed, 153 passed, 68 deselected`，两处失败均指向固定 HTML 字节 SHA 不匹配；随后恢复
正确 SHA，同一入口退出 0。该临时错误未提交。

## Engineering Gate 判定

代码审查基线之后到 `55e9ab6` 只有证据文档变更；现有离线、隔离集成、迁移、定向测试和精确
HEAD 远程 CI 证据支持 Phase 2 Engineering Gate `CLOSED`。

## Release Qualification 未完成并已终止

- live 后精确最终候选提交的新鲜副本验证；
- 五轮 live 观察；
- live 后精确最终 Release Qualification 候选的统一验证与远程 CI。

当前有效重启窗口仅完成 1/5 轮、10/10 个有效结果；机器重启前的 4/5 轮窗口因配对的临时
数据库/S3 证据丢失而作废。上述三项验证没有完成，当前 Release Qualification 按
`TERMINATED_WITH_INSUFFICIENT_EVIDENCE` 记为 `FAILED`。这不推翻现有 Engineering Gate
结论，也不允许把 v0.2 标记为 `STABLE`。
