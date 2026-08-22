# DeepAha

DeepAha 青年机会智能系统：把分散、变化、复杂的机会信息转化为可理解、可判断、可行动的路径。

> 当前状态：Phase 1 历史 Gate 已 `CLOSED`。Phase 2 来源采集与文档证据已 `IMPLEMENTED`，Engineering Gate 已 `CLOSED`；[Phase 2 Release Qualification](docs/gates/phase-2/README.md) 因 24 小时 live 观察、新鲜副本和最终候选验证尚未完成而保持 `IN_PROGRESS`，领域契约 v0.2 为 `IMPLEMENTED`、不得标记 `STABLE`。Phase 3 机会归并、版本与变化已 `IMPLEMENTED`，自身 [Engineering Gate](docs/gates/phase-3/README.md) 已 `CLOSED`；Release Qualification 为 `NOT_STARTED`，领域契约 v0.3 为 `IMPLEMENTED`、不得标记 `STABLE`。本分支仍不提供面向用户的业务功能，Phase 3 未合并或发布。

开发路线与架构见 `docs/development/README.md`。

## 环境要求

- Python 3.14
- uv
- Node.js 24 LTS
- Corepack / pnpm

## 本地启动

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
