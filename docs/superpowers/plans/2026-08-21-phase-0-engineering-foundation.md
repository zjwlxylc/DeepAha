# DeepAha Phase 0 Engineering Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立可重复安装、可本地验证、可由 CI 验证的 DeepAha 后端与 Web 最小工程底座。

**Architecture:** 使用单仓库中的模块化单体（modular monolith）。后端是单一 FastAPI 部署单元，Phase 0 只含 `api` 与 `core`；Web 是独立 Next.js 应用。两端共享版本与文档约束，不共享运行时代码，也不提前创建业务模块。

**Tech Stack:** Python 3.14、uv、FastAPI、Pydantic v2、Ruff、mypy、pytest；Node.js 24 LTS、pnpm、Next.js 16.2 LTS、React 19.2、TypeScript、ESLint、Vitest；GitHub Actions。

**Spec:** `docs/superpowers/specs/2026-08-21-phase-0-engineering-foundation-design.md`

## Global Constraints

- 严格限制在 Phase 0；不得加入数据库、采集、LLM、规则、匹配、登录或业务假数据。
- 按测试驱动开发（Test-Driven Development, TDD）执行行为代码：先写失败测试，确认失败原因，再写最小实现。
- `设计/logo.png` 只作为语义与配色参考；未清底和矢量化前不得复制到 `web/public`。
- 依赖首次解析后必须提交 `uv.lock` 和 `pnpm-lock.yaml`。
- 每个任务提交前运行其验证命令；若当前目录没有 Git，Task 1 才允许初始化本地仓库。
- 不修改 `文档/`、`设计/` 和现有 `AGENTS.md`。

---

## Task 1: 初始化仓库与根工程约束

**Files:**

- Create: `.gitignore`
- Create: `.editorconfig`
- Create: `README.md`

**Interfaces:** 本任务不提供运行时接口；只建立版本控制和跨编辑器约束。

- [ ] **Step 1: 确认当前目录并初始化 Git**

Run:

```powershell
Get-Location
git status
```

Expected: 路径为 `D:\DeepAha`；若第二条报告“not a git repository”，执行：

```powershell
git init -b main
```

不得在其他路径执行初始化，也不得重置或覆盖已有仓库。

- [ ] **Step 2: 创建根工程文件**

`.gitignore`:

```gitignore
# Secrets and local configuration
.env
.env.*
!.env.example

# Python
__pycache__/
*.py[cod]
.mypy_cache/
.pytest_cache/
.ruff_cache/
.venv/
dist/

# Node and Next.js
node_modules/
.next/
coverage/

# Editors and operating systems
.idea/
.vscode/
.DS_Store
Thumbs.db
```

`.editorconfig`:

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
indent_style = space
indent_size = 2
trim_trailing_whitespace = true

[*.py]
indent_size = 4

[*.md]
trim_trailing_whitespace = false
```

`README.md` 初始内容：

```markdown
# DeepAha

DeepAha 青年机会智能系统：把分散、变化、复杂的机会信息转化为可理解、可判断、可行动的路径。

> 当前状态：Phase 0 工程基础建设。尚未提供业务功能。

开发路线与架构见 `docs/development/README.md`。
```

- [ ] **Step 3: 验证变更范围**

Run:

```powershell
git status --short
git diff --check
```

Expected: 只有三个新根文件和此前已存在的项目文档；`git diff --check` 无输出。

- [ ] **Step 4: 提交**

```powershell
git add .gitignore .editorconfig README.md docs AGENTS.md 文档 设计
git commit -m "chore: initialize DeepAha workspace"
```

若用户已有未提交改动，不把无法确认归属的文件加入本次提交；先按 `git status --short` 缩小 `git add` 范围。

---

## Task 2: 用测试驱动建立 FastAPI 最小后端

**Files:**

- Create: `backend/.python-version`
- Create: `backend/pyproject.toml`
- Create: `backend/src/deepaha/__init__.py`
- Create: `backend/src/deepaha/api/__init__.py`
- Create: `backend/src/deepaha/api/health.py`
- Create: `backend/src/deepaha/core/__init__.py`
- Create: `backend/src/deepaha/core/logging.py`
- Create: `backend/src/deepaha/core/settings.py`
- Create: `backend/src/deepaha/main.py`
- Create: `backend/tests/api/test_health.py`
- Create: `backend/tests/core/test_settings.py`
- Generate: `backend/uv.lock`

**Interfaces:**

- `create_app() -> FastAPI`
- `GET /api/v1/health/live -> {"status": "ok"}`
- `GET /api/v1/health/ready -> {"status": "ok"}`
- `GET /api/v1/version -> VersionResponse`
- 所有 HTTP 响应包含 `X-Request-ID`

- [ ] **Step 1: 创建后端项目配置**

`backend/.python-version`:

```text
3.14
```

`backend/pyproject.toml`:

```toml
[project]
name = "deepaha-api"
version = "0.1.0"
description = "DeepAha API"
requires-python = ">=3.14,<3.15"
dependencies = [
  "fastapi>=0.115,<1",
  "pydantic-settings>=2.10,<3",
  "uvicorn[standard]>=0.35,<1",
]

[dependency-groups]
dev = [
  "httpx>=0.28,<1",
  "mypy>=1.17,<2",
  "pytest>=8.4,<10",
  "ruff>=0.12,<1",
]

[tool.pytest.ini_options]
addopts = "-q"
pythonpath = ["src"]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py314"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "SIM"]

[tool.mypy]
python_version = "3.14"
strict = true
mypy_path = "src"
files = ["src", "tests"]
```

Run:

```powershell
Set-Location backend
uv lock
uv sync --locked --group dev
```

Expected: 生成 `uv.lock`，环境解析到 Python 3.14。

- [ ] **Step 2: 先写设置测试**

`backend/tests/core/test_settings.py`:

```python
import pytest

from deepaha.core.settings import Settings


def test_settings_have_versioned_defaults() -> None:
    settings = Settings()

    assert settings.app_name == "deepaha-api"
    assert settings.app_version == "0.1.0"
    assert settings.api_version == "v1"
    assert settings.contract_version == "0.1.0"


def test_settings_read_prefixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPAHA_ENVIRONMENT", "test")

    assert Settings().environment == "test"
```

Run:

```powershell
uv run pytest tests/core/test_settings.py
```

Expected: FAIL，原因是 `deepaha.core.settings` 尚不存在。

- [ ] **Step 3: 实现最小设置对象**

`backend/src/deepaha/__init__.py`:

```python
__version__ = "0.1.0"
```

`backend/src/deepaha/core/__init__.py` 和 `backend/src/deepaha/api/__init__.py` 保持空文件。

`backend/src/deepaha/core/settings.py`:

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DEEPAHA_", extra="ignore")

    app_name: str = "deepaha-api"
    app_version: str = "0.1.0"
    api_version: str = "v1"
    contract_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Run: `uv run pytest tests/core/test_settings.py`

Expected: PASS。

- [ ] **Step 4: 先写 HTTP 契约测试**

`backend/tests/api/test_health.py`:

```python
from fastapi.testclient import TestClient

from deepaha.main import app


client = TestClient(app)


def test_liveness() -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"]


def test_readiness() -> None:
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_contract() -> None:
    response = client.get("/api/v1/version")

    assert response.status_code == 200
    assert response.json() == {
        "app": "deepaha-api",
        "version": "0.1.0",
        "api_version": "v1",
        "contract_version": "0.1.0",
    }


def test_valid_request_id_is_preserved() -> None:
    response = client.get(
        "/api/v1/health/live",
        headers={"X-Request-ID": "phase-0-test"},
    )

    assert response.headers["X-Request-ID"] == "phase-0-test"
```

Run: `uv run pytest tests/api/test_health.py`

Expected: FAIL，原因是路由或 `deepaha.main` 尚不存在。

- [ ] **Step 5: 实现路由、日志与请求 ID**

`backend/src/deepaha/api/health.py`:

```python
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from deepaha.core.settings import Settings, get_settings


router = APIRouter(prefix="/api/v1", tags=["system"])


class HealthResponse(BaseModel):
    status: Literal["ok"]


class VersionResponse(BaseModel):
    app: str
    version: str
    api_version: str
    contract_version: str


@router.get("/health/live", response_model=HealthResponse)
def live() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=HealthResponse)
def ready() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/version", response_model=VersionResponse)
def version(settings: Settings = Depends(get_settings)) -> VersionResponse:
    return VersionResponse(
        app=settings.app_name,
        version=settings.app_version,
        api_version=settings.api_version,
        contract_version=settings.contract_version,
    )
```

`backend/src/deepaha/core/logging.py`:

```python
import json
import logging
from datetime import UTC, datetime
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        for key in ("method", "path", "status_code", "duration_ms", "request_id"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)
```

`backend/src/deepaha/main.py`:

```python
import logging
import re
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from deepaha.api.health import router as system_router
from deepaha.core.logging import configure_logging
from deepaha.core.settings import get_settings


REQUEST_ID_PATTERN = re.compile(r"^[!-~]{1,128}$")
logger = logging.getLogger("deepaha.http")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    application = FastAPI(title="DeepAha API", version=settings.app_version)

    @application.middleware("http")
    async def request_context(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        candidate = request.headers.get("X-Request-ID", "")
        request_id = candidate if REQUEST_ID_PATTERN.fullmatch(candidate) else uuid4().hex
        started = perf_counter()
        response = await call_next(request)
        duration_ms = round((perf_counter() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "http_request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "request_id": request_id,
            },
        )
        return response

    application.include_router(system_router)
    return application


app = create_app()
```

Run:

```powershell
uv run pytest
uv run ruff format .
uv run ruff check .
uv run mypy src tests
```

Expected: 全部 PASS；格式命令若修改文件，重新运行至无改动。

- [ ] **Step 6: 手动冒烟并提交**

Terminal A:

```powershell
uv run uvicorn deepaha.main:app --app-dir src --host 127.0.0.1 --port 8000
```

Terminal B:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/version
```

Expected: 返回四个版本字段。停止服务后：

```powershell
Set-Location ..
git add backend
git commit -m "feat: add Phase 0 API foundation"
```

---

## Task 3: 用组件测试驱动建立最小 Web 应用

**Files:**

- Create: `web/package.json`
- Create: `web/tsconfig.json`
- Create: `web/next-env.d.ts`
- Create: `web/next.config.ts`
- Create: `web/eslint.config.mjs`
- Create: `web/vitest.config.ts`
- Create: `web/vitest.setup.ts`
- Create: `web/app/layout.tsx`
- Create: `web/app/page.tsx`
- Create: `web/app/globals.css`
- Create: `web/tests/home.test.tsx`
- Generate: `web/pnpm-lock.yaml`

**Interfaces:** `/` 是服务端渲染首页；包含一个 `main` 区域、一个一级标题、正式中英文品牌文字和当前阶段说明。

- [ ] **Step 1: 创建包配置并锁定依赖**

`web/package.json`:

```json
{
  "name": "deepaha-web",
  "version": "0.1.0",
  "private": true,
  "packageManager": "pnpm@10.15.0",
  "engines": { "node": ">=24 <25" },
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "lint": "eslint .",
    "typecheck": "tsc --noEmit",
    "test": "vitest run"
  },
  "dependencies": {
    "next": "16.2.11",
    "react": "19.2.0",
    "react-dom": "19.2.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.8.0",
    "@testing-library/react": "^16.3.0",
    "@types/node": "^24.0.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^5.0.0",
    "eslint": "^9.0.0",
    "eslint-config-next": "16.2.11",
    "jsdom": "^26.0.0",
    "typescript": "^5.9.0",
    "vitest": "^3.2.0"
  }
}
```

Run:

```powershell
Set-Location web
corepack enable
corepack pnpm install
```

Expected: 生成 `pnpm-lock.yaml`，安装过程无 peer dependency 错误。若当前官方依赖要求更高的兼容补丁，只调整同一选定大/小版本内的补丁并在提交中记录原因。

- [ ] **Step 2: 创建 TypeScript、Next、ESLint 与 Vitest 配置**

`web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "react-jsx",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

`web/next-env.d.ts`:

```typescript
/// <reference types="next" />
/// <reference types="next/image-types/global" />
```

`web/next.config.ts`:

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
};

export default nextConfig;
```

`web/eslint.config.mjs`:

```javascript
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypeScript from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTypeScript,
  globalIgnores([".next/**", "coverage/**", "next-env.d.ts"]),
]);
```

`web/vitest.config.ts`:

```typescript
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
  },
});
```

`web/vitest.setup.ts`:

```typescript
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 3: 先写失败的首页组件测试**

`web/tests/home.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Home from "../app/page";


describe("DeepAha home", () => {
  it("presents the approved brand and current scope", () => {
    render(<Home />);

    expect(screen.getByRole("heading", { level: 1, name: "DeepAha" })).toBeVisible();
    expect(screen.getByText("Go Deep. Find the Aha.")).toBeVisible();
    expect(screen.getByText(/青年机会智能系统/)).toBeVisible();
    expect(screen.getByText(/工程基础建设/)).toBeVisible();
  });
});
```

Run: `corepack pnpm test`

Expected: FAIL，原因是 `app/page.tsx` 尚不存在。

- [ ] **Step 4: 实现最小页面与品牌样式**

`web/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";


export const metadata: Metadata = {
  title: "DeepAha",
  description: "DeepAha 青年机会智能系统",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
```

`web/app/page.tsx`:

```tsx
export default function Home() {
  return (
    <main className="shell">
      <section className="hero" aria-labelledby="brand-title">
        <p className="eyebrow">青年机会智能系统</p>
        <h1 id="brand-title">DeepAha</h1>
        <p className="tagline">Go Deep. Find the Aha.</p>
        <p className="mission">
          把分散、变化、复杂的机会信息，转化为可理解、可判断、可行动的路径。
        </p>
        <p className="status">Phase 0 · 工程基础建设</p>
      </section>
    </main>
  );
}
```

`web/app/globals.css`:

```css
:root {
  color-scheme: light;
  --ink: #102a43;
  --blue: #0b6fb8;
  --orange: #e66a1f;
  --paper: #f4f8fb;
}

* {
  box-sizing: border-box;
}

html,
body {
  min-height: 100%;
  margin: 0;
}

body {
  background: linear-gradient(145deg, #ffffff 0%, var(--paper) 100%);
  color: var(--ink);
  font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
}

.shell {
  display: grid;
  min-height: 100vh;
  place-items: center;
  padding: 2rem;
}

.hero {
  width: min(42rem, 100%);
  border-left: 0.35rem solid var(--orange);
  padding: 1rem 0 1rem 2rem;
}

.eyebrow,
.status {
  color: var(--blue);
  font-weight: 700;
  letter-spacing: 0.08em;
}

h1 {
  margin: 0.25rem 0;
  font-size: clamp(3.25rem, 12vw, 7rem);
  letter-spacing: -0.06em;
  line-height: 0.95;
}

.tagline {
  margin: 1rem 0;
  color: var(--orange);
  font-size: clamp(1.25rem, 4vw, 2rem);
  font-weight: 700;
}

.mission {
  max-width: 34rem;
  font-size: 1.1rem;
  line-height: 1.8;
}

.status {
  margin-top: 2rem;
  font-size: 0.85rem;
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    scroll-behavior: auto !important;
  }
}
```

Run:

```powershell
corepack pnpm test
corepack pnpm lint
corepack pnpm typecheck
corepack pnpm build
```

Expected: 全部 PASS；生产构建成功生成 `.next`。

- [ ] **Step 5: 手动检查并提交**

Run: `corepack pnpm dev`

Open: `http://127.0.0.1:3000`。

Verify: 标题、中文使命、阶段状态可见；窄屏无横向滚动；页面未加载 `设计/logo.png` 或外部追踪脚本。

```powershell
Set-Location ..
git add web
git commit -m "feat: add Phase 0 web foundation"
```

---

## Task 4: 建立统一验证入口与开发者说明

**Files:**

- Create: `scripts/verify.ps1`
- Modify: `README.md`

**Interfaces:** `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1` 是 Phase 0 本地完整验证入口。

- [ ] **Step 1: 写根验证脚本**

`scripts/verify.ps1`:

```powershell
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

Push-Location (Join-Path $projectRoot "backend")
try {
    uv sync --locked --group dev
    uv run ruff format --check .
    uv run ruff check .
    uv run mypy src tests
    uv run pytest
}
finally {
    Pop-Location
}

Push-Location (Join-Path $projectRoot "web")
try {
    corepack pnpm install --frozen-lockfile
    corepack pnpm lint
    corepack pnpm typecheck
    corepack pnpm test
    corepack pnpm build
}
finally {
    Pop-Location
}
```

- [ ] **Step 2: 将根 README 更新为可复现说明**

README 必须只记录已实现命令，包含：

````markdown
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
````

补充链接到 `docs/development/README.md`，并明确“Phase 0 尚无业务功能”。

- [ ] **Step 3: 从根目录执行完整验证**

```powershell
Set-Location D:\DeepAha
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

Expected: 脚本退出码为 `0`，所有后端和 Web 检查通过。

- [ ] **Step 4: 提交**

```powershell
git add scripts/verify.ps1 README.md
git commit -m "chore: add reproducible local verification"
```

---

## Task 5: 建立 GitHub Actions 持续集成

**Files:**

- Create: `.github/workflows/ci.yml`

**Interfaces:** 提供 `backend-quality` 与 `web-quality` 两个必需 CI 作业。

- [ ] **Step 1: 创建 CI 工作流**

`.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  backend-quality:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: "3.14"
          enable-cache: true
      - run: uv sync --locked --group dev
      - run: uv run ruff format --check .
      - run: uv run ruff check .
      - run: uv run mypy src tests
      - run: uv run pytest

  web-quality:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with:
          version: 10.15.0
      - uses: actions/setup-node@v4
        with:
          node-version: "24"
          cache: pnpm
          cache-dependency-path: web/pnpm-lock.yaml
      - run: pnpm install --frozen-lockfile
      - run: pnpm lint
      - run: pnpm typecheck
      - run: pnpm test
      - run: pnpm build
```

- [ ] **Step 2: 做本地 YAML 与命令一致性检查**

Run:

```powershell
Select-String -Path .github/workflows/ci.yml -Pattern 'uv run|pnpm '
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
```

Expected: CI 中的质量命令与本地脚本一致；完整验证通过；无空白错误。

- [ ] **Step 3: 提交**

```powershell
git add .github/workflows/ci.yml
git commit -m "ci: verify Phase 0 foundations"
```

推送到 GitHub 后必须观察实际 CI 成功，不能以本地结果代替远端工作流证据。

---

## Task 6: 关闭 Phase 0 Gate

**Files:**

- Create: `docs/gates/phase-0/README.md`
- Create: `docs/gates/phase-0/acceptance-results.md`
- Create: `docs/gates/phase-0/test-summary.md`
- Create: `docs/gates/phase-0/deferred-decisions.md`

**Interfaces:** 无运行时接口；这些文件是 Phase 1 的进入凭证。

- [ ] **Step 1: 在全新工作副本复现**

按根 README 安装并运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

记录操作系统、Python、uv、Node、pnpm 版本、提交哈希、开始/结束时间和每条命令结果。

- [ ] **Step 2: 写实际 Gate 证据**

`README.md` 记录目标、范围、结论和已知风险；`acceptance-results.md` 对设计文档第 2.2 节六条成功标准逐项给出命令或 CI 链接；`test-summary.md` 记录实际测试数量和结果；`deferred-decisions.md` 只记录已明确延期到具体阶段的事项。

禁止预填 `PASS`、伪造运行时间或复制计划文字充当证据。任何一项没有证据时，Gate 保持 `OPEN`。

- [ ] **Step 3: 最终范围与安全检查**

```powershell
git status --short
git diff --check
git grep -n -I -E 'TODO|FIXME|placeholder|example-secret' -- . ':(exclude)docs/superpowers/plans/*'
git log --oneline --decorate -6
```

Expected: 没有未解释的占位词、秘密或范围外业务代码；变更只属于 Phase 0。

- [ ] **Step 4: 提交 Gate 证据**

```powershell
git add docs/gates/phase-0
git commit -m "docs: close Phase 0 engineering gate"
```

只有实际验证和 CI 均通过时，`docs/gates/phase-0/README.md` 才能标记 `CLOSED`，随后才开始 Phase 1。
