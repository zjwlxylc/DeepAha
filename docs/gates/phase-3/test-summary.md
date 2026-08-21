# Phase 3 测试摘要

## 当前本地环境

- 最近 GREEN：2026-08-22T04:15+08:00 至 04:16+08:00。
- 候选树基线：`14ab668ce719dac002f5afe136c28c72fa067d76` 加 Gate/CI 变更。
- uv `0.12.5`；Python `3.14.7`；Ruff `0.16.4`；mypy `1.20.2`；pytest `9.1.1`；Alembic `1.19.1`。
- Node.js `24.14.0`；项目锁定 pnpm `10.15.0`；Docker Engine `29.6.1`。
- verifier 实际输出：PostgreSQL `18.4`；Moto `5.2.2.dev`（镜像 tag 为 `5.2.2`）。

## 已实际运行

| 命令/区域 | 结果 |
| --- | --- |
| `scripts/verify-phase3.ps1` | 退出码 0；基线、独立服务、迁移、测试、漂移检查和 scoped cleanup 全部完成。 |
| 默认后端 | `243 passed, 107 deselected`；92 个文件格式通过、lint 通过、87 个源文件类型检查通过。 |
| Web | ESLint、TypeScript、1 个 Vitest 测试和 Next.js 生产构建通过。 |
| Phase 3 integration | `107 passed, 243 deselected`。 |
| contracts + opportunities | `123 passed`。 |
| Alembic | 应用 `20260821_0001`、`20260821_0002`、`20260822_0003`；`No new upgrade operations detected.` |

## 故障注入

临时把合成 Resolver fixture 的期望 SHA 末位从 `2` 改为 `3`。同一 verifier 退出码为 1，
默认后端为 `1 failed, 242 passed, 107 deselected`，唯一失败精确显示实际/期望 SHA 差异。
服务在基线失败前尚未启动，finally 仍只对本次 `deepaha-phase3-<PID>` 执行 cleanup。恢复
正确 SHA 后同一入口退出 0；临时错误未提交。

## 尚未发生

- Phase 2 closing commit 上的兼容差异与全量复验；
- 当前精确候选 SHA 的远程 CI；
- Phase 3 Gate 关闭、v0.3 STABLE、合并或发布。
