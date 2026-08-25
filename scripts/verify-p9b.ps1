param(
    [string]$ComposeProjectName,
    [string]$ExpectedCandidate
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $projectRoot "infra/compose.p9b.yaml"
$projectName = $ComposeProjectName
$mainProjectStarted = $false

if ([string]::IsNullOrWhiteSpace($projectName)) {
    $suffix = [guid]::NewGuid().ToString("N").Substring(0, 8)
    $projectName = "deepaha-p9b-replacement-$PID-$suffix"
}
if ($projectName -cnotmatch '^deepaha-p9b-replacement-[a-z0-9][a-z0-9-]*$') {
    throw "COMPOSE_PROJECT_NAME must use the deepaha-p9b-replacement- prefix"
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
        throw "$Name is required for P9-B replacement verification"
    }
}

function Get-ProjectContainerIds {
    param([Parameter(Mandatory = $true)][string]$Name)

    $ids = @(& docker compose --project-name $Name --file $composeFile ps -aq)
    Assert-NativeSuccess "inspect exact compose project $Name"
    return @($ids | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}

function Assert-ProjectAbsent {
    param([Parameter(Mandatory = $true)][string]$Name)

    if ((Get-ProjectContainerIds $Name).Count -ne 0) {
        throw "refusing to reuse non-empty compose project $Name"
    }
}

function Start-ExactProject {
    param([Parameter(Mandatory = $true)][string]$Name)

    Assert-ProjectAbsent $Name
    & docker compose --project-name $Name --file $composeFile up -d --wait
    Assert-NativeSuccess "start exact compose project $Name"
    if ((Get-ProjectContainerIds $Name).Count -ne 2) {
        throw "compose project $Name did not start exactly two services"
    }
}

function Remove-ExactProject {
    param([Parameter(Mandatory = $true)][string]$Name)

    & docker compose --project-name $Name --file $composeFile down --volumes --remove-orphans
    Assert-NativeSuccess "remove exact compose project $Name"
    if ((Get-ProjectContainerIds $Name).Count -ne 0) {
        throw "compose project $Name cleanup was incomplete"
    }
}

function Get-DynamicHostPort {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Service,
        [Parameter(Mandatory = $true)][int]$ContainerPort
    )

    [string]$binding = @(& docker compose --project-name $Name --file $composeFile `
        port $Service $ContainerPort) | Select-Object -First 1
    Assert-NativeSuccess "read dynamic port for $Name/$Service"
    $binding = $binding.Trim()
    if ($binding -notmatch ':(?<port>[0-9]+)$') {
        throw "unexpected dynamic port binding for $Name/${Service}: $binding"
    }
    return [int]$Matches.port
}

function Test-ConcurrentComposeIsolation {
    $first = "$projectName-smoke-a"
    $second = "$projectName-smoke-b"
    $firstStarted = $false
    $secondStarted = $false
    try {
        Start-ExactProject $first
        $firstStarted = $true
        Start-ExactProject $second
        $secondStarted = $true
        $ports = @(
            Get-DynamicHostPort $first "postgres" 5432
            Get-DynamicHostPort $first "s3" 5000
            Get-DynamicHostPort $second "postgres" 5432
            Get-DynamicHostPort $second "s3" 5000
        )
        if (($ports | Sort-Object -Unique).Count -ne 4) {
            throw "concurrent compose projects did not receive four isolated dynamic ports"
        }
        Write-Host "P9-B concurrent Compose isolation smoke=PASS"
    }
    finally {
        if ($secondStarted) { Remove-ExactProject $second }
        if ($firstStarted) { Remove-ExactProject $first }
    }
}

Assert-CommandAvailable "docker"
Assert-CommandAvailable "uv"
Assert-CommandAvailable "corepack"
& docker info *> $null
Assert-NativeSuccess "Docker daemon check"

Push-Location $projectRoot
try {
    $head = (& git rev-parse HEAD).Trim()
    Assert-NativeSuccess "read verifier candidate HEAD"
    if (-not [string]::IsNullOrWhiteSpace($ExpectedCandidate) -and $head -ne $ExpectedCandidate) {
        throw "candidate HEAD $head does not match expected $ExpectedCandidate"
    }
    & git diff --check
    Assert-NativeSuccess "initial diff check"
}
finally { Pop-Location }

Test-ConcurrentComposeIsolation

Push-Location (Join-Path $projectRoot "backend")
try {
    & uv sync --locked --group dev
    Assert-NativeSuccess "locked backend dependency sync"
    & uv run ruff format --check .
    Assert-NativeSuccess "backend format check"
    & uv run ruff check .
    Assert-NativeSuccess "backend lint"
    & uv run mypy src tests
    Assert-NativeSuccess "backend type check"
    & uv run pytest --strict-markers
    Assert-NativeSuccess "backend non-integration tests"
}
finally { Pop-Location }

Push-Location (Join-Path $projectRoot "web")
try {
    & corepack pnpm install --frozen-lockfile
    Assert-NativeSuccess "web dependency install"
    & corepack pnpm lint
    Assert-NativeSuccess "web lint"
    & corepack pnpm typecheck
    Assert-NativeSuccess "web type check"
    & corepack pnpm test
    Assert-NativeSuccess "web tests"
    & corepack pnpm build
    Assert-NativeSuccess "web build"
}
finally { Pop-Location }

try {
    Start-ExactProject $projectName
    $mainProjectStarted = $true
    $postgresPort = Get-DynamicHostPort $projectName "postgres" 5432
    $s3Port = Get-DynamicHostPort $projectName "s3" 5000
    $env:DEEPAHA_DATABASE_URL = `
        "postgresql+psycopg://deepaha:deepaha_p9b_verifier_local_only@127.0.0.1:$postgresPort/deepaha"
    $env:DEEPAHA_OBJECT_STORE_ENDPOINT = "http://127.0.0.1:$s3Port"
    $env:DEEPAHA_OBJECT_STORE_REGION = "us-east-1"
    $env:DEEPAHA_OBJECT_STORE_BUCKET = "deepaha-raw"
    $env:DEEPAHA_OBJECT_STORE_ACCESS_KEY = "p9b-verifier-local"
    $env:DEEPAHA_OBJECT_STORE_SECRET_KEY = "p9b-verifier-local-secret"
    $env:DEEPAHA_ENVIRONMENT = "test"

    Push-Location (Join-Path $projectRoot "backend")
    try {
        & uv run alembic upgrade head
        Assert-NativeSuccess "fresh P9-B migration upgrade"
        & uv run pytest -m integration --strict-markers
        Assert-NativeSuccess "full PostgreSQL and S3 integration tests"
        & uv run alembic check
        Assert-NativeSuccess "P9-B migration drift check"
        & uv run alembic downgrade 20260825_0028
        Assert-NativeSuccess "P9-B value-contract downgrade"
        & uv run alembic upgrade head
        Assert-NativeSuccess "P9-B value-contract re-upgrade"
        & uv run alembic check
        Assert-NativeSuccess "P9-B re-upgrade drift check"
    }
    finally { Pop-Location }

    Push-Location $projectRoot
    try {
        & git diff --check
        Assert-NativeSuccess "final diff check"
    }
    finally { Pop-Location }

    Write-Host "P9-B INTERNAL VERIFIER=PASS"
    Write-Host "Independent Acceptance=NOT_RUN"
    Write-Host "Real Gold=0 / NOT_OBSERVED; Locked Acceptance=NOT_RUN"
    Write-Host "Qualification Gold pairs=0 / NOT_OBSERVED"
    Write-Host "Live Provider=NOT_RUN; token/cost=0; credential=NOT_READ"
    Write-Host "P9-B Engineering Gate=OPEN"
    Write-Host "P9-B Release Qualification=NOT_STARTED"
    Write-Host "P9-B Contract=IMPLEMENTED, not STABLE"
}
finally {
    try {
        if ($mainProjectStarted) { Remove-ExactProject $projectName }
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
