# DeepAha

DeepAha 青年机会智能系统：把分散、变化、复杂的机会信息转化为可理解、可判断、可行动的路径。

> 当前状态：Phase 1 Gate 已 `CLOSED`。Phase 2 来源采集与文档证据已 `IMPLEMENTED` 并通过本地统一验证；[Phase 2 Gate](docs/gates/phase-2/README.md) 在 24 小时 live 观察、新鲜副本和远程 CI 完成前仍为 `OPEN`，领域契约 v0.2 仍为 `PROPOSED`。尚未进入 Phase 3，也未提供面向用户的业务功能。

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
