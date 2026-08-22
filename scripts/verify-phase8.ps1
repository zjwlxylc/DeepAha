param(
    [string]$ComposeProjectName = $env:COMPOSE_PROJECT_NAME
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$composeRelativePath = "infra/compose.phase8.yaml"
$composeFile = Join-Path $projectRoot $composeRelativePath
$projectName = $ComposeProjectName
$cleanupProject = $false

if ([string]::IsNullOrWhiteSpace($projectName)) {
    $projectName = "deepaha-phase8-$PID"
}
if ($projectName -cnotmatch '^deepaha-phase8-[a-z0-9][a-z0-9-]*$') {
    throw "COMPOSE_PROJECT_NAME must begin with deepaha-phase8- and use lowercase letters, digits, or hyphens"
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
        throw "$Name is required for Phase 8 verification"
    }
}

function Get-ExactProjectHostPorts {
    $ports = [System.Collections.Generic.HashSet[int]]::new()
    $containerIds = @(& docker compose --project-name $projectName --file $composeFile ps -q)
    Assert-NativeSuccess "inspect exact Phase 8 compose project"
    foreach ($containerId in $containerIds) {
        if ([string]::IsNullOrWhiteSpace($containerId)) {
            continue
        }
        $portJson = & docker inspect --format '{{json .NetworkSettings.Ports}}' $containerId
        Assert-NativeSuccess "inspect exact Phase 8 container ports"
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
        throw "Required Phase 8 port $Port is occupied outside compose project $projectName"
    }
}

Assert-CommandAvailable "docker"
Assert-CommandAvailable "uv"
Assert-CommandAvailable "corepack"
& docker info *> $null
Assert-NativeSuccess "Docker daemon check"

Assert-PortAvailableOrOwned 55438
Assert-PortAvailableOrOwned 55006

& powershell -ExecutionPolicy Bypass -File (Join-Path $projectRoot "scripts/verify.ps1")
Assert-NativeSuccess "root repository verification"

try {
    $cleanupProject = $true
    & docker compose --project-name $projectName --file $composeFile up -d --wait
    Assert-NativeSuccess "start isolated Phase 8 services"

    $env:DEEPAHA_DATABASE_URL = "postgresql+psycopg://deepaha:deepaha_phase8_local_only@127.0.0.1:55438/deepaha"
    $env:DEEPAHA_OBJECT_STORE_ENDPOINT = "http://127.0.0.1:55006"
    $env:DEEPAHA_OBJECT_STORE_REGION = "us-east-1"
    $env:DEEPAHA_OBJECT_STORE_BUCKET = "deepaha-raw"
    $env:DEEPAHA_OBJECT_STORE_ACCESS_KEY = "phase8-local"
    $env:DEEPAHA_OBJECT_STORE_SECRET_KEY = "phase8-local-secret"
    $env:DEEPAHA_ENVIRONMENT = "test"
    $env:DEEPAHA_PERSONAL_AUTH_MODE = "fixture"

    Push-Location (Join-Path $projectRoot "backend")
    try {
        uv run alembic upgrade head
        Assert-NativeSuccess "Phase 8 migration upgrade"
        uv run pytest `
            tests/contracts/test_phase8_contracts.py `
            tests/notifications `
            tests/api/test_reminders.py `
            tests/test_phase8_verifier_scope.py --strict-markers
        Assert-NativeSuccess "Phase 8 contracts, notifications, reminder API, fixtures, and scope tests"
        uv run pytest -m integration `
            tests/integration/test_phase8_candidate_transaction.py `
            tests/integration/test_phase8_inbox_isolation.py `
            tests/integration/test_phase8_persistence.py `
            tests/integration/test_phase8_preference_api.py `
            tests/integration/test_phase8_public_governance.py `
            tests/integration/test_phase8_transaction_rollback.py `
            tests/integration/test_phase8_vertical_slice.py `
            tests/integration/test_phase8_worker_recovery.py `
            --strict-markers
        Assert-NativeSuccess "Phase 8 PostgreSQL transaction, isolation, governance, recovery, and vertical tests"
        uv run alembic downgrade 20260822_0007
        Assert-NativeSuccess "Phase 8 empty migration downgrade"
        uv run alembic upgrade head
        Assert-NativeSuccess "Phase 8 migration re-upgrade"
        uv run alembic check
        Assert-NativeSuccess "Phase 8 migration drift check"
        $priorPythonPath = $env:PYTHONPATH
        try {
            $env:PYTHONPATH = "src"
            uv run python -m tests.notifications.seed_phase8_browser
            Assert-NativeSuccess "Phase 8 seeded browser fixture smoke"
        }
        finally {
            if ($null -eq $priorPythonPath) {
                Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
            }
            else {
                $env:PYTHONPATH = $priorPythonPath
            }
        }
    }
    finally {
        Pop-Location
    }

    Push-Location (Join-Path $projectRoot "web")
    try {
        corepack pnpm lint
        Assert-NativeSuccess "Phase 8 web lint"
        corepack pnpm typecheck
        Assert-NativeSuccess "Phase 8 web type check"
        corepack pnpm test
        Assert-NativeSuccess "Phase 8 web tests"
        corepack pnpm build
        Assert-NativeSuccess "Phase 8 web build"
    }
    finally {
        Pop-Location
    }

    Write-Host "SYNTHETIC_REMINDER_DELIVERY_ONLY"
    Write-Host "real participants=0"
    Write-Host "human track=NOT_STARTED"
    Write-Host "Release Qualification=NOT_STARTED"
    Write-Host "release decision=HOLD_MISSING_HUMAN_EVIDENCE"
    Write-Host "delivery target=TEST_INBOX"
}
finally {
    try {
        if ($cleanupProject) {
            & docker compose --project-name $projectName --file $composeFile down --volumes --remove-orphans
            Assert-NativeSuccess "remove exact Phase 8 compose project"
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
        Remove-Item Env:DEEPAHA_PERSONAL_AUTH_MODE -ErrorAction SilentlyContinue
    }
}
