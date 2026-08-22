$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$phase3ComposeFile = Join-Path $projectRoot "infra/compose.phase3.yaml"
$phase3ComposeProject = "deepaha-phase3-$PID"
$phase3Failure = $null
$phase3CleanupExitCode = 0

$env:DEEPAHA_DATABASE_URL = "postgresql+psycopg://deepaha:deepaha_phase3_local_only@127.0.0.1:55433/deepaha"
$env:DEEPAHA_OBJECT_STORE_ENDPOINT = "http://127.0.0.1:55001"
$env:DEEPAHA_OBJECT_STORE_REGION = "us-east-1"
$env:DEEPAHA_OBJECT_STORE_BUCKET = "deepaha-raw"
$env:DEEPAHA_OBJECT_STORE_ACCESS_KEY = "phase3-local"
$env:DEEPAHA_OBJECT_STORE_SECRET_KEY = "phase3-local-secret"

function Assert-Phase3ExitCode {
    param([Parameter(Mandatory = $true)][string]$Operation)

    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE"
    }
}

try {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $projectRoot "scripts/verify.ps1")
    Assert-Phase3ExitCode "baseline verification"

    docker compose -f $phase3ComposeFile -p $phase3ComposeProject up -d --wait postgres s3
    Assert-Phase3ExitCode "Phase 3 service startup"

    docker compose -f $phase3ComposeFile -p $phase3ComposeProject exec -T postgres postgres --version
    Assert-Phase3ExitCode "PostgreSQL version inspection"
    docker compose -f $phase3ComposeFile -p $phase3ComposeProject exec -T s3 python -c "import moto; print(f'Moto {moto.__version__}')"
    Assert-Phase3ExitCode "Moto version inspection"

    Push-Location (Join-Path $projectRoot "backend")
    try {
        uv sync --locked --group dev
        Assert-Phase3ExitCode "locked backend dependency sync"

        uv run alembic upgrade head
        Assert-Phase3ExitCode "Phase 3 migration"

        uv run pytest -m integration --strict-markers
        Assert-Phase3ExitCode "Phase 3 integration tests"

        uv run pytest tests/contracts tests/opportunities `
            -m "not integration and not live_source" --strict-markers
        Assert-Phase3ExitCode "Phase 3 contract and opportunity tests"

        uv run alembic check
        Assert-Phase3ExitCode "Alembic metadata check"
    }
    finally {
        Pop-Location
    }
}
catch {
    $phase3Failure = $_
}
finally {
    docker compose -f $phase3ComposeFile -p $phase3ComposeProject down --remove-orphans
    $phase3CleanupExitCode = $LASTEXITCODE
}

if ($null -ne $phase3Failure) {
    throw $phase3Failure
}
if ($phase3CleanupExitCode -ne 0) {
    throw "Phase 3 service cleanup failed with exit code $phase3CleanupExitCode"
}
