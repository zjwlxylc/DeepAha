# DeepAha

DeepAha 青年机会智能系统：把分散、变化、复杂的机会信息转化为可理解、可判断、可行动的路径。

> 当前状态：`main` 已集成 Phase 1–8 的真实工程系统。Phase 1 历史 Gate 已 `CLOSED`；Phase 2–8 实现均为 `IMPLEMENTED`、Engineering Gate 均为 `CLOSED`。Phase 2 Release Qualification 因 live 重启窗口仅完成 1/5 轮且未完成新鲜副本/最终候选验证而记为 `FAILED`；Phase 3–8 Release Qualification 均未形成生产资格，v0.2–v0.7 只能标记 `IMPLEMENTED`、不得标记 `STABLE`。Phase 6/7 真人参与者仍为 `0`，Phase 8 只投递到合成 `TEST_INBOX`；当前发布决定保持 `HOLD_MISSING_HUMAN_EVIDENCE`，不代表生产发布或部署已获批。

开发路线与架构见 `docs/development/README.md`。

## 环境要求

- Python 3.14
- uv
- Node.js 24 LTS
- Corepack / pnpm

## 本地启动

### 面向人工使用的一键启动（Windows）

非技术用户可直接双击仓库根目录的：

- `启动 DeepAha 本地人工测试.cmd`
- 使用结束后双击 `停止 DeepAha 本地人工测试.cmd`

启动器会检查环境、启动隔离 PostgreSQL/S3、迁移数据库、准备合成身份、启动 API 与 Web，
并打开可直接操作的浏览器。该环境只包含合成工程夹具，真人参与者为 `0`，提醒只进入
`TEST_INBOX`；它不构成真人指标、生产部署或 Release Qualification 证据。详细说明和失败
恢复见 `docs/development/local-manual-testing.md`。

### 开发命令

后端：

```powershell
Set-Location backend
uv sync --locked --group dev
uv run uvicorn deepaha.main:app --app-dir src --reload
```

Web：

```powershell
Set-Location web
corepack pnpm install --frozen-lockfile
corepack pnpm dev
```

## 完整验证

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

Phase 1 需要 Docker Desktop 提供本地 PostgreSQL 18 与 S3 兼容测试服务：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-phase1.ps1
```

Phase 3 候选验证使用完全独立的 PostgreSQL/Moto 端口与 compose project：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-phase3.ps1
```

当前 `main` 的完整 Phase 1–8 工程矩阵使用隔离 PostgreSQL/Moto、迁移往返、后端/Web 与
Chromium 验证：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-phase8.ps1
```
