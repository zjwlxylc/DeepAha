param(
    [string]$ComposeProjectName = $env:COMPOSE_PROJECT_NAME,
    [string]$ControlledCorpusRoot
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$composeRelativePath = "infra/compose.source-acquisition.yaml"
$composeFile = Join-Path $projectRoot $composeRelativePath
$projectName = $ComposeProjectName
$cleanupProject = $false

if ([string]::IsNullOrWhiteSpace($projectName)) {
    $projectName = "deepaha-source-acquisition-$PID"
}
if ($projectName -cnotmatch '^deepaha-source-acquisition-[a-z0-9][a-z0-9-]*$') {
    throw "COMPOSE_PROJECT_NAME must begin with deepaha-source-acquisition- and use lowercase letters, digits, or hyphens"
}

function Assert-NativeSuccess {
    param([Parameter(Mandatory = $true)][string]$Operation)

    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE"
    }
}

function Assert-CommandAvailable {
    param([Parameter(Mandatory = $true)][string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is required for Source Acquisition Platform verification"
    }
}

function Get-ExactProjectHostPorts {
    $ports = [System.Collections.Generic.HashSet[int]]::new()
    $containerIds = @(& docker compose --project-name $projectName --file $composeFile ps -q)
    Assert-NativeSuccess "inspect exact Source Acquisition compose project"
    foreach ($containerId in $containerIds) {
        if ([string]::IsNullOrWhiteSpace($containerId)) {
            continue
        }
        $portJson = & docker inspect --format '{{json .NetworkSettings.Ports}}' $containerId
        Assert-NativeSuccess "inspect exact Source Acquisition container ports"
        $bindings = $portJson | ConvertFrom-Json
        foreach ($property in $bindings.PSObject.Properties) {
            foreach ($binding in @($property.Value)) {
                if ($null -ne $binding -and -not [string]::IsNullOrWhiteSpace($binding.HostPort)) {
                    [void]$ports.Add([int]$binding.HostPort)
                }
            }
        }
    }
    return $ports
}

function Assert-PortAvailableOrOwned {
    param([Parameter(Mandatory = $true)][int]$Port)

    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    if ($listeners.Count -eq 0) {
        return
    }
    $ownedPorts = Get-ExactProjectHostPorts
    if (-not $ownedPorts.Contains($Port)) {
        throw "Required Source Acquisition port $Port is occupied outside compose project $projectName"
    }
}

Assert-CommandAvailable "docker"
Assert-CommandAvailable "uv"
& docker info *> $null
Assert-NativeSuccess "Docker daemon check"
Assert-PortAvailableOrOwned 55439
Assert-PortAvailableOrOwned 55007

& powershell -ExecutionPolicy Bypass -File (Join-Path $projectRoot "scripts/verify.ps1")
Assert-NativeSuccess "root repository verification"
& powershell -ExecutionPolicy Bypass -File (Join-Path $projectRoot "scripts/verify-phase2.ps1")
Assert-NativeSuccess "historical Phase 2 verification"
& powershell -ExecutionPolicy Bypass -File (Join-Path $projectRoot "scripts/verify-phase8.ps1")
Assert-NativeSuccess "historical Phase 8 verification"

try {
    $cleanupProject = $true
    & docker compose --project-name $projectName --file $composeFile up -d --wait
    Assert-NativeSuccess "start isolated Source Acquisition services"

    $env:DEEPAHA_DATABASE_URL = "postgresql+psycopg://deepaha:deepaha_source_acquisition_local_only@127.0.0.1:55439/deepaha"
    $env:DEEPAHA_OBJECT_STORE_ENDPOINT = "http://127.0.0.1:55007"
    $env:DEEPAHA_OBJECT_STORE_REGION = "us-east-1"
    $env:DEEPAHA_OBJECT_STORE_BUCKET = "deepaha-raw"
    $env:DEEPAHA_OBJECT_STORE_ACCESS_KEY = "source-acquisition-local"
    $env:DEEPAHA_OBJECT_STORE_SECRET_KEY = "source-acquisition-local-secret"
    $env:DEEPAHA_ENVIRONMENT = "test"
    Remove-Item Env:DEEPAHA_REAL_SOURCE_CORPUS_BACKEND -ErrorAction SilentlyContinue
    if ([string]::IsNullOrWhiteSpace($ControlledCorpusRoot)) {
        Remove-Item Env:DEEPAHA_REAL_SOURCE_CORPUS_ROOT -ErrorAction SilentlyContinue
    }
    else {
        $resolvedCorpusRoot = (Resolve-Path -LiteralPath $ControlledCorpusRoot).Path
        $env:DEEPAHA_REAL_SOURCE_CORPUS_ROOT = $resolvedCorpusRoot
    }

    Push-Location (Join-Path $projectRoot "backend")
    try {
        uv sync --locked --group dev
        Assert-NativeSuccess "locked backend dependency sync"
        uv run ruff check src/deepaha/acquisition tests/acquisition `
            tests/integration/test_real_acquisition_replay.py `
            tests/integration/test_real_s02_opportunity_replay.py `
            tests/integration/test_real_integration_cost_gate.py
        Assert-NativeSuccess "Source Acquisition Ruff checks"
        uv run mypy src/deepaha/acquisition
        Assert-NativeSuccess "Source Acquisition mypy checks"
        uv run pytest `
            tests/acquisition `
            tests/sources/test_registry_manifest.py `
            tests/sources/test_official_source_manifest.py `
            tests/test_source_acquisition_verifier_scope.py `
            --strict-markers
        Assert-NativeSuccess "Source Acquisition offline unit, policy, replay, and scope tests"

        uv run alembic upgrade head
        Assert-NativeSuccess "Source Acquisition migration upgrade"
        uv run pytest -m integration `
            tests/integration/test_acquisition_document_gate.py `
            tests/integration/test_acquisition_evaluation_persistence.py `
            tests/integration/test_acquisition_evaluation_service.py `
            tests/integration/test_acquisition_fetchers.py `
            tests/integration/test_acquisition_health_migration.py `
            tests/integration/test_acquisition_health_persistence.py `
            tests/integration/test_acquisition_health.py `
            tests/integration/test_acquisition_migration.py `
            tests/integration/test_acquisition_orchestrator.py `
            tests/integration/test_real_acquisition_replay.py `
            tests/integration/test_real_s02_opportunity_replay.py `
            tests/integration/test_real_integration_cost_gate.py `
            --strict-markers
        Assert-NativeSuccess "Source Acquisition PostgreSQL, S3, migration, and controlled replay tests"
        uv run alembic downgrade 20260822_0008
        Assert-NativeSuccess "Source Acquisition empty migration downgrade"
        uv run alembic upgrade head
        Assert-NativeSuccess "Source Acquisition migration re-upgrade"
        uv run alembic check
        Assert-NativeSuccess "Source Acquisition migration drift check"
    }
    finally {
        Pop-Location
    }

    Push-Location $projectRoot
    try {
        & git diff --check
        Assert-NativeSuccess "Source Acquisition diff check"
    }
    finally {
        Pop-Location
    }
    Write-Host "SOURCE ACQUISITION PLATFORM ENGINEERING GATE=CLOSED"
    Write-Host "Release Qualification=NOT_STARTED"
    Write-Host "100-source/14-day target=NOT_RUN"
}
finally {
    try {
        if ($cleanupProject) {
            & docker compose --project-name $projectName --file $composeFile down --volumes --remove-orphans
            Assert-NativeSuccess "remove exact Source Acquisition compose project"
        }
    }
    finally {
        Remove-Item Env:DEEPAHA_DATABASE_URL -ErrorAction SilentlyContinue
        Remove-Item Env:DEEPAHA_OBJECT_STORE_ENDPOINT -ErrorAction SilentlyContinue
        Remove-Item Env:DEEPAHA_OBJECT_STORE_REGION -ErrorAction SilentlyContinue
        Remove-Item Env:DEEPAHA_OBJECT_STORE_BUCKET -ErrorAction SilentlyContinue
        Remove-Item Env:DEEPAHA_OBJECT_STORE_ACCESS_KEY -ErrorAction SilentlyContinue
        Remove-Item Env:DEEPAHA_OBJECT_STORE_SECRET_KEY -ErrorAction SilentlyContinue
        Remove-Item Env:DEEPAHA_ENVIRONMENT -ErrorAction SilentlyContinue
        Remove-Item Env:DEEPAHA_REAL_SOURCE_CORPUS_ROOT -ErrorAction SilentlyContinue
        Remove-Item Env:DEEPAHA_REAL_SOURCE_CORPUS_BACKEND -ErrorAction SilentlyContinue
    }
}
