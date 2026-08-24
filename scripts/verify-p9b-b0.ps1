param(
    [string]$ComposeProjectName = $env:COMPOSE_PROJECT_NAME
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$composeRelativePath = "infra/compose.source-acquisition.yaml"
$composeFile = Join-Path $projectRoot $composeRelativePath
$projectName = $ComposeProjectName
$cleanupProject = $false

if ([string]::IsNullOrWhiteSpace($projectName)) {
    $projectName = "deepaha-p9b-b0-$PID"
}
if ($projectName -cnotmatch '^deepaha-p9b-b0-[a-z0-9][a-z0-9-]*$') {
    throw "COMPOSE_PROJECT_NAME must use the deepaha-p9b-b0- prefix"
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
        throw "$Name is required for P9-B0 verification"
    }
}

function Get-ExactProjectHostPorts {
    $ports = [System.Collections.Generic.HashSet[int]]::new()
    $containerIds = @(& docker compose --project-name $projectName --file $composeFile ps -q)
    Assert-NativeSuccess "inspect exact P9-B0 compose project"
    foreach ($containerId in $containerIds) {
        if ([string]::IsNullOrWhiteSpace($containerId)) {
            continue
        }
        $portJson = & docker inspect --format '{{json .NetworkSettings.Ports}}' $containerId
        Assert-NativeSuccess "inspect exact P9-B0 container ports"
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
        throw "Required P9-B0 port $Port is occupied outside compose project $projectName"
    }
}

Assert-CommandAvailable "docker"
Assert-CommandAvailable "uv"
Assert-CommandAvailable "corepack"
& docker info *> $null
Assert-NativeSuccess "Docker daemon check"
Assert-PortAvailableOrOwned 55439
Assert-PortAvailableOrOwned 55007

& powershell -ExecutionPolicy Bypass -File (Join-Path $projectRoot "scripts/verify.ps1")
Assert-NativeSuccess "root repository verification"

try {
    $cleanupProject = $true
    & docker compose --project-name $projectName --file $composeFile up -d --wait
    Assert-NativeSuccess "start isolated P9-B0 services"

    $env:DEEPAHA_DATABASE_URL = `
        "postgresql+psycopg://deepaha:deepaha_source_acquisition_local_only@127.0.0.1:55439/deepaha"
    $env:DEEPAHA_OBJECT_STORE_ENDPOINT = "http://127.0.0.1:55007"
    $env:DEEPAHA_OBJECT_STORE_REGION = "us-east-1"
    $env:DEEPAHA_OBJECT_STORE_BUCKET = "deepaha-raw"
    $env:DEEPAHA_OBJECT_STORE_ACCESS_KEY = "source-acquisition-local"
    $env:DEEPAHA_OBJECT_STORE_SECRET_KEY = "source-acquisition-local-secret"
    $env:DEEPAHA_ENVIRONMENT = "test"

    Push-Location (Join-Path $projectRoot "backend")
    try {
        uv run alembic upgrade head
        Assert-NativeSuccess "P9-B0 migration upgrade"
        uv run pytest `
            tests/contracts/test_phase9b_contracts.py `
            tests/p9b `
            tests/documents `
            tests/test_p9b_b0_verifier_scope.py `
            --strict-markers
        Assert-NativeSuccess "P9-B0 contracts and deterministic tests"
        uv run pytest -m integration `
            tests/integration/test_p9b_b0_migration.py `
            tests/integration/test_p9b_b0_persistence.py `
            tests/integration/test_document_service.py `
            --strict-markers
        Assert-NativeSuccess "P9-B0 PostgreSQL constraints and services"
        uv run pytest -m integration --strict-markers
        Assert-NativeSuccess "Phase 1 through Phase 8 PostgreSQL regression"
        uv run alembic check
        Assert-NativeSuccess "P9-B0 migration drift check"
        uv run alembic downgrade 20260823_0010
        Assert-NativeSuccess "P9-B0 empty migration downgrade"
        uv run alembic upgrade head
        Assert-NativeSuccess "P9-B0 migration re-upgrade"
        uv run alembic check
        Assert-NativeSuccess "P9-B0 re-upgrade drift check"
    }
    finally {
        Pop-Location
    }
}
finally {
    if ($cleanupProject) {
        & docker compose --project-name $projectName --file $composeFile `
            down --volumes --remove-orphans
    }
}
