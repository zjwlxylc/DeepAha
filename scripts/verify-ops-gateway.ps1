$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

function Assert-ExitCode {
    param([Parameter(Mandatory = $true)][string]$Operation)
    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE"
    }
}

Push-Location (Join-Path $projectRoot "ops-gateway")
try {
    uv sync --group dev
    Assert-ExitCode "ops gateway dependency sync"
    uv run ruff format --check .
    Assert-ExitCode "ops gateway format check"
    uv run ruff check .
    Assert-ExitCode "ops gateway lint"
    uv run pytest
    Assert-ExitCode "ops gateway tests"
}
finally {
    Pop-Location
}
