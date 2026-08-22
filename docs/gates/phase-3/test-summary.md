# Phase 3 测试摘要

## 当前本地环境

- 重新验证日期：2026-08-22。
- Phase 2 closing commit：`6c8a8fb63c68cfbb0f4cf54b6032bfb49a0ef65c`。
- 非重写整合提交：`66940b368b176774801d49a4d62446607630fdd8`。
- uv `0.12.5`；Python `3.14.7`；Ruff `0.16.4`；mypy `1.20.2`；pytest `9.1.1`；Alembic `1.19.1`。
- Node.js `24.14.0`；项目锁定 pnpm `10.15.0`；Docker Engine `29.6.1`。
- verifier 实际输出：PostgreSQL `18.4`；Moto `5.2.2.dev`（镜像 tag 为 `5.2.2`）。

## 已实际运行

| 命令/区域 | 结果 |
| --- | --- |
| `scripts/verify.ps1` | 退出码 0；后端质量/默认测试与 Web lint/typecheck/test/build 全部通过。 |
| `scripts/verify-phase3.ps1` | 退出码 0；根验证、独立服务、迁移、集成、contracts/opportunities、drift 和 scoped cleanup 全部完成。 |
| 默认后端 | `247 passed, 109 deselected`；92 个文件格式通过、lint 通过、87 个源文件类型检查通过。 |
| Web | ESLint、TypeScript、1 个 Vitest 测试和 Next.js 生产构建通过。 |
| Phase 3 integration | `109 passed, 247 deselected`。 |
| contracts + opportunities | `124 passed`。 |
| Alembic | 应用 `20260821_0001`、`20260821_0002`、`20260822_0003`；`No new upgrade operations detected.` |
| GitHub Actions | 精确最终提交的 `backend-quality`、`web-quality`、`integration`、`phase3-resolution` 结论记录在 PR #3；任一失败都要求重新打开 Engineering Gate 判定。 |

## RED/GREEN 证据

- 上游 v0.2 新增 URL 凭据约束后，v0.3 Schema 字节测试先失败；确定性 exporter 只刷新
  `v0.3.0/source-endpoint.schema.json` 后通过。
- Engineering Gate 自审新增 MERGE alias canonical owner 集成测试；RED 精确返回 SOURCE
  `...0061` 而非 TARGET `...0062`。索引加载应用 identity replay 后 GREEN，并同时验证
  MERGE_REVERSAL 恢复 SOURCE。

## 证据边界

这些检查证明当前代码、迁移和固定样本可复现，不证明真实来源 precision/recall、变化识别率、
生产性能或用户价值。上述项目属于尚未开始的 Phase 3 Release Qualification。
