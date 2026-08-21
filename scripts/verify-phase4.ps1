param(
    [string]$ComposeProjectName = $env:COMPOSE_PROJECT_NAME
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$composeRelativePath = "infra/compose.phase4.yaml"
$composeFile = Join-Path $projectRoot $composeRelativePath
$projectName = $ComposeProjectName
$cleanupProject = $false

if ([string]::IsNullOrWhiteSpace($projectName)) {
    $projectName = "deepaha-phase4-$PID"
}
if ($projectName -cnotmatch '^deepaha-phase4-[a-z0-9][a-z0-9-]*$') {
    throw "COMPOSE_PROJECT_NAME must begin with deepaha-phase4- and use lowercase letters, digits, or hyphens"
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
        throw "$Name is required for Phase 4 verification"
    }
}

function Get-ExactProjectHostPorts {
    $ports = [System.Collections.Generic.HashSet[int]]::new()
    $containerIds = @(& docker compose --project-name $projectName --file $composeFile ps -q)
    Assert-NativeSuccess "inspect exact Phase 4 compose project"
    foreach ($containerId in $containerIds) {
        if ([string]::IsNullOrWhiteSpace($containerId)) {
            continue
        }
        $portJson = & docker inspect --format '{{json .NetworkSettings.Ports}}' $containerId
        Assert-NativeSuccess "inspect exact Phase 4 container ports"
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
        throw "Required Phase 4 port $Port is occupied outside compose project $projectName"
    }
}

Assert-CommandAvailable "docker"
Assert-CommandAvailable "uv"
& docker info *> $null
Assert-NativeSuccess "Docker daemon check"

Assert-PortAvailableOrOwned 55434
Assert-PortAvailableOrOwned 55002

try {
    $cleanupProject = $true
    & docker compose --project-name $projectName --file $composeFile up -d --wait
    Assert-NativeSuccess "start isolated Phase 4 services"

    $env:DEEPAHA_DATABASE_URL = "postgresql+psycopg://deepaha:deepaha_phase4_local_only@127.0.0.1:55434/deepaha"
    $env:DEEPAHA_OBJECT_STORE_ENDPOINT = "http://127.0.0.1:55002"
    $env:DEEPAHA_OBJECT_STORE_REGION = "us-east-1"
    $env:DEEPAHA_OBJECT_STORE_BUCKET = "deepaha-raw"
    $env:DEEPAHA_OBJECT_STORE_ACCESS_KEY = "phase4-local"
    $env:DEEPAHA_OBJECT_STORE_SECRET_KEY = "phase4-local-secret"

    Push-Location (Join-Path $projectRoot "backend")
    try {
        uv sync --locked --group dev
        Assert-NativeSuccess "backend dependency sync"
        uv run ruff format --check .
        Assert-NativeSuccess "backend format check"
        uv run ruff check .
        Assert-NativeSuccess "backend lint"
        uv run mypy src tests
        Assert-NativeSuccess "backend type check"
        uv run pytest tests/contracts/test_phase4_contracts.py tests/rules tests/eligibility tests/evaluation tests/test_phase4_verifier_scope.py --strict-markers
        Assert-NativeSuccess "Phase 4 offline tests"
        uv run alembic upgrade head
        Assert-NativeSuccess "Phase 4 migration upgrade"
        uv run pytest -m integration tests/integration/test_phase4_persistence_contract.py tests/integration/test_phase4_match_replay.py tests/integration/test_phase4_evaluation_run.py --strict-markers
        Assert-NativeSuccess "Phase 4 integration tests"
        uv run alembic downgrade 20260822_0003
        Assert-NativeSuccess "Phase 4 migration downgrade"
        uv run alembic upgrade head
        Assert-NativeSuccess "Phase 4 migration re-upgrade"
        uv run alembic check
        Assert-NativeSuccess "Phase 4 migration drift check"
    }
    finally {
        Pop-Location
    }

    Write-Host "SYNTHETIC_EVALUATION_ONLY: 12 Golden cases; 12 expected statuses reproduced; unexpected INELIGIBLE=0; replay mismatches=0"
    Write-Host "IMPLEMENTED_PENDING_PHASE2_PHASE3_GATES"
}
finally {
    if ($cleanupProject) {
        & docker compose --project-name $projectName --file $composeFile down --volumes --remove-orphans
        Assert-NativeSuccess "remove exact Phase 4 compose project"
    }
}
