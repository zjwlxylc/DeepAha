param(
    [string]$ComposeProjectName = $env:COMPOSE_PROJECT_NAME
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$composeRelativePath = "infra/compose.phase6.yaml"
$composeFile = Join-Path $projectRoot $composeRelativePath
$projectName = $ComposeProjectName
$cleanupProject = $false

if ([string]::IsNullOrWhiteSpace($projectName)) {
    $projectName = "deepaha-phase6-$PID"
}
if ($projectName -cnotmatch '^deepaha-phase6-[a-z0-9][a-z0-9-]*$') {
    throw "COMPOSE_PROJECT_NAME must begin with deepaha-phase6- and use lowercase letters, digits, or hyphens"
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
        throw "$Name is required for Phase 6 verification"
    }
}

function Get-ExactProjectHostPorts {
    $ports = [System.Collections.Generic.HashSet[int]]::new()
    $containerIds = @(& docker compose --project-name $projectName --file $composeFile ps -q)
    Assert-NativeSuccess "inspect exact Phase 6 compose project"
    foreach ($containerId in $containerIds) {
        if ([string]::IsNullOrWhiteSpace($containerId)) {
            continue
        }
        $portJson = & docker inspect --format '{{json .NetworkSettings.Ports}}' $containerId
        Assert-NativeSuccess "inspect exact Phase 6 container ports"
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
        throw "Required Phase 6 port $Port is occupied outside compose project $projectName"
    }
}

Assert-CommandAvailable "docker"
Assert-CommandAvailable "uv"
Assert-CommandAvailable "corepack"
& docker info *> $null
Assert-NativeSuccess "Docker daemon check"

Assert-PortAvailableOrOwned 55436
Assert-PortAvailableOrOwned 55004

& powershell -ExecutionPolicy Bypass -File (Join-Path $projectRoot "scripts/verify.ps1")
Assert-NativeSuccess "root repository verification"

try {
    $cleanupProject = $true
    & docker compose --project-name $projectName --file $composeFile up -d --wait
    Assert-NativeSuccess "start isolated Phase 6 services"

    $env:DEEPAHA_DATABASE_URL = "postgresql+psycopg://deepaha:deepaha_phase6_local_only@127.0.0.1:55436/deepaha"
    $env:DEEPAHA_OBJECT_STORE_ENDPOINT = "http://127.0.0.1:55004"
    $env:DEEPAHA_OBJECT_STORE_REGION = "us-east-1"
    $env:DEEPAHA_OBJECT_STORE_BUCKET = "deepaha-raw"
    $env:DEEPAHA_OBJECT_STORE_ACCESS_KEY = "phase6-local"
    $env:DEEPAHA_OBJECT_STORE_SECRET_KEY = "phase6-local-secret"

    Push-Location (Join-Path $projectRoot "backend")
    try {
        uv run alembic upgrade head
        Assert-NativeSuccess "Phase 6 migration upgrade"
        uv run pytest tests/contracts/test_phase6_contracts.py tests/personal tests/api/test_personal.py tests/test_phase6_verifier_scope.py --strict-markers
        Assert-NativeSuccess "Phase 6 offline contract, personal, API, and scope tests"
        uv run pytest -m integration tests/integration/test_phase6_profile_persistence.py tests/integration/test_phase6_personal_match_replay.py tests/integration/test_phase6_personal_api.py tests/integration/test_phase6_vertical_slice.py tests/integration/test_phase6_user_isolation.py --strict-markers
        Assert-NativeSuccess "Phase 6 profile, match, action, and isolation integration tests"
        uv run alembic downgrade 20260822_0005
        Assert-NativeSuccess "Phase 6 migration downgrade"
        uv run alembic upgrade head
        Assert-NativeSuccess "Phase 6 migration re-upgrade"
        uv run alembic check
        Assert-NativeSuccess "Phase 6 migration drift check"
    }
    finally {
        Pop-Location
    }

    Push-Location (Join-Path $projectRoot "web")
    try {
        corepack pnpm lint
        Assert-NativeSuccess "Phase 6 web lint"
        corepack pnpm typecheck
        Assert-NativeSuccess "Phase 6 web type check"
        corepack pnpm test
        Assert-NativeSuccess "Phase 6 web tests"
        corepack pnpm build
        Assert-NativeSuccess "Phase 6 web build"
    }
    finally {
        Pop-Location
    }

    Write-Host "SYNTHETIC_FIXTURE_ONLY: profiles=2; public opportunities=3; real users=0; real Gold records=0"
    Write-Host "Implementation: IMPLEMENTED"
    Write-Host "Engineering verification: PASS"
    Write-Host "Release Qualification: NOT_STARTED"
    Write-Host "Phase 6 v0.5 Contract Maturity: IMPLEMENTED"
}
finally {
    if ($cleanupProject) {
        & docker compose --project-name $projectName --file $composeFile down --volumes --remove-orphans
        Assert-NativeSuccess "remove exact Phase 6 compose project"
    }
}
