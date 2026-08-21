$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$phase1ComposeFile = Join-Path $projectRoot "infra/compose.yaml"
$phase1ComposeProject = "deepaha-phase1-$PID"
$phase1Failure = $null
$phase1CleanupExitCode = 0

$env:DEEPAHA_DATABASE_URL = "postgresql+psycopg://deepaha:deepaha_local_only@127.0.0.1:55432/deepaha"
$env:DEEPAHA_OBJECT_STORE_ENDPOINT = "http://127.0.0.1:55000"
$env:DEEPAHA_OBJECT_STORE_REGION = "us-east-1"
$env:DEEPAHA_OBJECT_STORE_BUCKET = "deepaha-raw"
$env:DEEPAHA_OBJECT_STORE_ACCESS_KEY = "phase1-local"
$env:DEEPAHA_OBJECT_STORE_SECRET_KEY = "phase1-local-secret"

function Assert-Phase1ExitCode {
    param([Parameter(Mandatory = $true)][string]$Operation)

    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE"
    }
}

try {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $projectRoot "scripts/verify.ps1")
    Assert-Phase1ExitCode "baseline verification"

    docker compose -f $phase1ComposeFile -p $phase1ComposeProject up -d --wait postgres s3
    Assert-Phase1ExitCode "Phase 1 service startup"

    Push-Location (Join-Path $projectRoot "backend")
    try {
        uv sync --locked --group dev
        Assert-Phase1ExitCode "locked backend dependency sync"

        uv run alembic upgrade head
        Assert-Phase1ExitCode "Phase 1 migration"

        uv run pytest -m integration --strict-markers
        Assert-Phase1ExitCode "Phase 1 integration tests"

        uv run alembic check
        Assert-Phase1ExitCode "Alembic metadata check"
    }
    finally {
        Pop-Location
    }
}
catch {
    $phase1Failure = $_
}
finally {
    docker compose -f $phase1ComposeFile -p $phase1ComposeProject down --remove-orphans
    $phase1CleanupExitCode = $LASTEXITCODE
}

if ($null -ne $phase1Failure) {
    throw $phase1Failure
}
if ($phase1CleanupExitCode -ne 0) {
    throw "Phase 1 service cleanup failed with exit code $phase1CleanupExitCode"
}
