# DeepAha

DeepAha 青年机会智能系统：把分散、变化、复杂的机会信息转化为可理解、可判断、可行动的路径。

> 当前状态：Phase 1 Gate 已 `CLOSED`；[Phase 2 Gate](docs/gates/phase-2/README.md) 仍为 `OPEN`，v0.2 仍为 `PROPOSED`。Phase 3 已在独立堆叠分支实现并通过本地候选验证，但[Phase 3 Gate](docs/gates/phase-3/README.md) 为 `BLOCKED_BY_PHASE2`，状态只能是 `IMPLEMENTED_PENDING_PHASE2_GATE`，v0.3 仍为 `PROPOSED`。尚未提供面向用户的业务功能，也未合并或发布 Phase 3。

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
