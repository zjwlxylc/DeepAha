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
