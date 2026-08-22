param(
    [string]$ComposeProjectName = $env:COMPOSE_PROJECT_NAME
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$composeRelativePath = "infra/compose.phase7.yaml"
$composeFile = Join-Path $projectRoot $composeRelativePath
$projectName = $ComposeProjectName
$cleanupProject = $false

if ([string]::IsNullOrWhiteSpace($projectName)) {
    $projectName = "deepaha-phase7-$PID"
}
if ($projectName -cnotmatch '^deepaha-phase7-[a-z0-9][a-z0-9-]*$') {
    throw "COMPOSE_PROJECT_NAME must begin with deepaha-phase7- and use lowercase letters, digits, or hyphens"
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
        throw "$Name is required for Phase 7 verification"
    }
}

function Get-ExactProjectHostPorts {
    $ports = [System.Collections.Generic.HashSet[int]]::new()
    $containerIds = @(& docker compose --project-name $projectName --file $composeFile ps -q)
    Assert-NativeSuccess "inspect exact Phase 7 compose project"
    foreach ($containerId in $containerIds) {
        if ([string]::IsNullOrWhiteSpace($containerId)) {
            continue
        }
        $portJson = & docker inspect --format '{{json .NetworkSettings.Ports}}' $containerId
        Assert-NativeSuccess "inspect exact Phase 7 container ports"
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
        throw "Required Phase 7 port $Port is occupied outside compose project $projectName"
    }
}

Assert-CommandAvailable "docker"
Assert-CommandAvailable "uv"
Assert-CommandAvailable "corepack"
& docker info *> $null
Assert-NativeSuccess "Docker daemon check"

Assert-PortAvailableOrOwned 55437
Assert-PortAvailableOrOwned 55005

& powershell -ExecutionPolicy Bypass -File (Join-Path $projectRoot "scripts/verify.ps1")
Assert-NativeSuccess "root repository verification"

try {
    $cleanupProject = $true
    & docker compose --project-name $projectName --file $composeFile up -d --wait
    Assert-NativeSuccess "start isolated Phase 7 services"

    $env:DEEPAHA_DATABASE_URL = "postgresql+psycopg://deepaha:deepaha_phase7_local_only@127.0.0.1:55437/deepaha"
    $env:DEEPAHA_OBJECT_STORE_ENDPOINT = "http://127.0.0.1:55005"
    $env:DEEPAHA_OBJECT_STORE_REGION = "us-east-1"
    $env:DEEPAHA_OBJECT_STORE_BUCKET = "deepaha-raw"
    $env:DEEPAHA_OBJECT_STORE_ACCESS_KEY = "phase7-local"
    $env:DEEPAHA_OBJECT_STORE_SECRET_KEY = "phase7-local-secret"

    Push-Location (Join-Path $projectRoot "backend")
    try {
        uv run alembic upgrade head
        Assert-NativeSuccess "Phase 7 migration upgrade"
        uv run pytest `
            tests/contracts/test_phase1_contracts.py `
            tests/contracts/test_phase2_contracts.py `
            tests/contracts/test_phase3_contracts.py `
            tests/contracts/test_phase4_contracts.py `
            tests/contracts/test_phase6_contracts.py `
            tests/contracts/test_phase7_contracts.py `
            tests/feedback tests/review tests/validation `
            tests/api/test_feedback.py tests/api/test_review.py `
            tests/test_phase7_verifier_scope.py --strict-markers
        Assert-NativeSuccess "Phase 7 contracts, feedback, review, validation, API, fixtures, and scope tests"
        uv run pytest -m integration `
            tests/integration/test_phase7_feedback_submission.py `
            tests/integration/test_phase7_feedback_isolation.py `
            tests/integration/test_phase7_persistence.py `
            tests/integration/test_phase7_reviewer_authorization.py `
            tests/integration/test_phase7_review_workflow.py `
            tests/integration/test_phase7_validation_gate.py `
            tests/integration/test_phase7_vertical_slice.py `
            tests/integration/test_phase7_transaction_rollback.py `
            --strict-markers
        Assert-NativeSuccess "Phase 7 PostgreSQL feedback, authorization, review, validation, vertical, and rollback tests"
        uv run alembic downgrade 20260822_0006
        Assert-NativeSuccess "Phase 7 migration downgrade"
        uv run alembic upgrade head
        Assert-NativeSuccess "Phase 7 migration re-upgrade"
        uv run alembic check
        Assert-NativeSuccess "Phase 7 migration drift check"
    }
    finally {
        Pop-Location
    }

    Push-Location (Join-Path $projectRoot "web")
    try {
        corepack pnpm lint
        Assert-NativeSuccess "Phase 7 web lint"
        corepack pnpm typecheck
        Assert-NativeSuccess "Phase 7 web type check"
        corepack pnpm test
        Assert-NativeSuccess "Phase 7 web tests"
        corepack pnpm build
        Assert-NativeSuccess "Phase 7 web build"
    }
    finally {
        Pop-Location
    }

    Write-Host "SYNTHETIC_FEEDBACK_WORKFLOW_ONLY"
    Write-Host "real participants=0"
    Write-Host "human track=NOT_STARTED"
    Write-Host "Release Qualification=NOT_STARTED"
    Write-Host "release decision=HOLD_MISSING_HUMAN_EVIDENCE"
}
finally {
    if ($cleanupProject) {
        & docker compose --project-name $projectName --file $composeFile down --volumes --remove-orphans
        Assert-NativeSuccess "remove exact Phase 7 compose project"
    }
}
