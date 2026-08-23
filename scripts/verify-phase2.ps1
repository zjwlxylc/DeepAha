$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$phase2ComposeFile = Join-Path $projectRoot "infra/compose.yaml"
$phase2ComposeProject = "deepaha-phase2-$PID"
$phase2Failure = $null
$phase2CleanupExitCode = 0

$env:DEEPAHA_DATABASE_URL = "postgresql+psycopg://deepaha:deepaha_local_only@127.0.0.1:55432/deepaha"
$env:DEEPAHA_OBJECT_STORE_ENDPOINT = "http://127.0.0.1:55000"
$env:DEEPAHA_OBJECT_STORE_REGION = "us-east-1"
$env:DEEPAHA_OBJECT_STORE_BUCKET = "deepaha-raw"
$env:DEEPAHA_OBJECT_STORE_ACCESS_KEY = "phase2-local"
$env:DEEPAHA_OBJECT_STORE_SECRET_KEY = "phase2-local-secret"

function Assert-Phase2ExitCode {
    param([Parameter(Mandatory = $true)][string]$Operation)

    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE"
    }
}

try {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $projectRoot "scripts/verify.ps1")
    Assert-Phase2ExitCode "baseline verification"

    docker compose -f $phase2ComposeFile -p $phase2ComposeProject up -d --wait postgres s3
    Assert-Phase2ExitCode "Phase 2 service startup"

    Push-Location (Join-Path $projectRoot "backend")
    try {
        uv sync --locked --group dev
        Assert-Phase2ExitCode "locked backend dependency sync"

        uv run alembic upgrade head
        Assert-Phase2ExitCode "Phase 2 migration"

        uv run pytest -m integration --strict-markers
        Assert-Phase2ExitCode "Phase 2 integration tests"

        uv run pytest tests/contracts tests/sources tests/documents `
            -m "not integration and not live_source" --strict-markers
        Assert-Phase2ExitCode "Phase 2 offline contract, source, and document tests"

        uv run alembic check
        Assert-Phase2ExitCode "Alembic metadata check"
    }
    finally {
        Pop-Location
    }
}
catch {
    $phase2Failure = $_
}
finally {
    docker compose -f $phase2ComposeFile -p $phase2ComposeProject down --remove-orphans
    $phase2CleanupExitCode = $LASTEXITCODE
}

if ($null -ne $phase2Failure) {
    throw $phase2Failure
}
if ($phase2CleanupExitCode -ne 0) {
    throw "Phase 2 service cleanup failed with exit code $phase2CleanupExitCode"
}
