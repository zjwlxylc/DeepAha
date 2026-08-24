param(
    [string]$ComposeProjectName = $env:COMPOSE_PROJECT_NAME
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $projectRoot "infra/compose.source-acquisition.yaml"
$projectName = $ComposeProjectName
$cleanupProject = $false

if ([string]::IsNullOrWhiteSpace($projectName)) {
    $projectName = "deepaha-p9b-facts-$PID"
}
if ($projectName -cnotmatch '^deepaha-p9b-facts-[a-z0-9][a-z0-9-]*$') {
    throw "COMPOSE_PROJECT_NAME must use the deepaha-p9b-facts- prefix"
}
function Assert-NativeSuccess {
    param([Parameter(Mandatory = $true)][string]$Operation)

    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE"
    }
}

function Get-ExactProjectHostPorts {
    $ports = [System.Collections.Generic.HashSet[int]]::new()
    $containerIds = @(& docker compose --project-name $projectName --file $composeFile ps -q)
    Assert-NativeSuccess "inspect exact fact-chain compose project"
    foreach ($containerId in $containerIds) {
        if ([string]::IsNullOrWhiteSpace($containerId)) {
            continue
        }
        $portJson = & docker inspect --format '{{json .NetworkSettings.Ports}}' $containerId
        Assert-NativeSuccess "inspect exact fact-chain container ports"
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
        throw "Required fact-chain port $Port is occupied outside compose project $projectName"
    }
}

& docker info *> $null
Assert-NativeSuccess "Docker daemon check"
Assert-PortAvailableOrOwned 55439
Assert-PortAvailableOrOwned 55007

& powershell -ExecutionPolicy Bypass -File (Join-Path $projectRoot "scripts/verify.ps1")
Assert-NativeSuccess "root repository verification"

try {
    $cleanupProject = $true
    & docker compose --project-name $projectName --file $composeFile up -d --wait
    Assert-NativeSuccess "start isolated fact-chain services"

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
        Assert-NativeSuccess "fact-chain migration upgrade"
        uv run pytest `
            tests/contracts/test_phase9b_contracts.py `
            tests/p9b/test_fact_lifecycle.py `
            tests/p9b/test_rule_promotion.py `
            tests/test_p9b_fact_chain_verifier_scope.py `
            --strict-markers
        Assert-NativeSuccess "fact-chain contracts and deterministic boundary tests"
        uv run pytest -m integration `
            tests/integration/test_p9b_fact_persistence.py `
            tests/integration/test_p9b_fact_lifecycle_migration.py `
            --strict-markers
        Assert-NativeSuccess "fact-chain PostgreSQL and migration tests"
        uv run pytest -m integration --strict-markers
        Assert-NativeSuccess "Phase 1 through Phase 8 PostgreSQL regression"
        uv run alembic check
        Assert-NativeSuccess "fact-chain migration drift check"
        uv run alembic downgrade 20260824_0012
        Assert-NativeSuccess "fact-chain empty migration downgrade"
        uv run alembic upgrade head
        Assert-NativeSuccess "fact-chain migration re-upgrade"
        uv run alembic check
        Assert-NativeSuccess "fact-chain re-upgrade drift check"
    }
    finally {
        Pop-Location
    }

    Push-Location $projectRoot
    try {
        & git diff --check
        Assert-NativeSuccess "fact-chain diff check"
    }
    finally {
        Pop-Location
    }

    Write-Host "P9-B FACT PROMOTION SLICE ENGINEERING GATE=CLOSED"
    Write-Host "Independent human Gold evidence=NOT_OBSERVED"
    Write-Host "UnitRuleSet activation=DORMANT"
    Write-Host "Release Qualification=NOT_STARTED"
}
finally {
    try {
        if ($cleanupProject) {
            & docker compose --project-name $projectName --file $composeFile `
                down --volumes --remove-orphans
            Assert-NativeSuccess "remove exact fact-chain compose project"
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
    }
}
