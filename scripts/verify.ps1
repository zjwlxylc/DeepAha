$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

function Assert-VerificationExitCode {
    param([Parameter(Mandatory = $true)][string]$Operation)

    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE"
    }
}

& powershell -NoProfile -ExecutionPolicy Bypass -File (
    Join-Path $projectRoot "scripts/tests/local-manual-test.Tests.ps1"
)
Assert-VerificationExitCode "local manual-test launcher tests"

Push-Location (Join-Path $projectRoot "backend")
try {
    uv sync --locked --group dev
    Assert-VerificationExitCode "backend dependency sync"
    uv run ruff format --check .
    Assert-VerificationExitCode "backend format check"
    uv run ruff check .
    Assert-VerificationExitCode "backend lint"
    uv run mypy src tests
    Assert-VerificationExitCode "backend type check"
    uv run pytest
    Assert-VerificationExitCode "backend tests"
}
finally {
    Pop-Location
}

Push-Location (Join-Path $projectRoot "web")
try {
    corepack pnpm install --frozen-lockfile
    Assert-VerificationExitCode "web dependency install"
    corepack pnpm lint
    Assert-VerificationExitCode "web lint"
    corepack pnpm typecheck
    Assert-VerificationExitCode "web type check"
    corepack pnpm test
    Assert-VerificationExitCode "web tests"
    corepack pnpm build
    Assert-VerificationExitCode "web build"
}
finally {
    Pop-Location
}
