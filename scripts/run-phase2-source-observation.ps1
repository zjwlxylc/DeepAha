[CmdletBinding()]
param(
    [ValidateRange(1, 5)][int]$Rounds = 5,
    [ValidateRange(1, 2147483647)][int]$IntervalSeconds = 21600,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [string]$RegistryPath,
    [string]$CliPath,
    [switch]$RunDueRoundsOnly
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendRoot = Join-Path $projectRoot "backend"
if ([string]::IsNullOrWhiteSpace($RegistryPath)) {
    $RegistryPath = Join-Path $projectRoot "config/sources/phase2-official-endpoints.json"
}
$resolvedRegistryPath = (Resolve-Path -LiteralPath $RegistryPath).Path

if ($env:DEEPAHA_ALLOW_LIVE_SOURCE_CHECK -ne "true") {
    throw "DEEPAHA_ALLOW_LIVE_SOURCE_CHECK=true is required"
}

$registry = Get-Content -LiteralPath $resolvedRegistryPath -Raw | ConvertFrom-Json
$endpoints = @(
    foreach ($entry in $registry.sources) {
        foreach ($endpoint in $entry.endpoints) {
            if ($entry.source.active -and $endpoint.active) {
                [ordered]@{
                    endpoint_id = [string]$endpoint.endpoint_id
                    url = [string]$endpoint.url
                    minimum_interval_seconds = [int]$endpoint.minimum_interval_seconds
                }
            }
        }
    }
)
if ($endpoints.Count -eq 0) {
    throw "Registry has no active endpoints"
}
$minimumPolicy = [int](
    $endpoints.minimum_interval_seconds | Measure-Object -Maximum
).Maximum
if ($IntervalSeconds -lt $minimumPolicy) {
    throw "IntervalSeconds cannot be below active minimum_interval_seconds=$minimumPolicy"
}

$resolvedOutputPath = [System.IO.Path]::GetFullPath($OutputPath)
$projectPrefix = $projectRoot.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
if (
    $resolvedOutputPath.Equals($projectRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
    $resolvedOutputPath.StartsWith($projectPrefix, [System.StringComparison]::OrdinalIgnoreCase)
) {
    throw "OutputPath must be outside the repository"
}
$outputDirectory = Split-Path -Parent $resolvedOutputPath
if (-not (Test-Path -LiteralPath $outputDirectory)) {
    New-Item -ItemType Directory -Path $outputDirectory | Out-Null
}
$registrySha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedRegistryPath).Hash.ToLowerInvariant()

function Write-ObservationState {
    param([Parameter(Mandatory = $true)][object]$State)

    $json = $State | ConvertTo-Json -Depth 20
    $temporaryPath = "$resolvedOutputPath.tmp"
    [System.IO.File]::WriteAllText(
        $temporaryPath,
        $json + [Environment]::NewLine,
        [System.Text.UTF8Encoding]::new($false)
    )
    Move-Item -LiteralPath $temporaryPath -Destination $resolvedOutputPath -Force
}

function Invoke-SourceCli {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    Push-Location $backendRoot
    $previousPythonPath = $env:PYTHONPATH
    try {
        if ([string]::IsNullOrWhiteSpace($CliPath)) {
            $sourcePath = Join-Path $backendRoot "src"
            $env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
                $sourcePath
            }
            else {
                $sourcePath + [System.IO.Path]::PathSeparator + $previousPythonPath
            }
            $output = @(& uv run python -m deepaha.sources.cli @Arguments)
        }
        else {
            $output = @(& $CliPath @Arguments)
        }
        $exitCode = $LASTEXITCODE
        return [ordered]@{
            exit_code = $exitCode
            stdout = $output -join [Environment]::NewLine
        }
    }
    finally {
        $env:PYTHONPATH = $previousPythonPath
        Pop-Location
    }
}

function Convert-CliJson {
    param(
        [Parameter(Mandatory = $true)][object]$Invocation,
        [Parameter(Mandatory = $true)][string]$Operation
    )

    if ($Invocation.exit_code -ne 0) {
        throw "$Operation failed with exit code $($Invocation.exit_code)"
    }
    try {
        return $Invocation.stdout | ConvertFrom-Json
    }
    catch {
        throw "$Operation returned invalid JSON"
    }
}

function Update-ObservationCounts {
    param([Parameter(Mandatory = $true)][object]$State)

    $allResults = @(
        foreach ($round in @($State.rounds)) {
            foreach ($result in @($round.results)) {
                $result
            }
        }
    )
    $valid = @(
        $allResults | Where-Object {
            $_.final_outcome -in @("SUCCEEDED", "NOT_MODIFIED") -and
            -not [string]::IsNullOrWhiteSpace([string]$_.artifact_sha256) -and
            -not [string]::IsNullOrWhiteSpace([string]$_.object_key)
        }
    ).Count
    $State.counts = [ordered]@{
        results = $allResults.Count
        valid = $valid
        failed = $allResults.Count - $valid
    }
}

if (Test-Path -LiteralPath $resolvedOutputPath) {
    $state = Get-Content -LiteralPath $resolvedOutputPath -Raw | ConvertFrom-Json
    if (
        $state.schema_version -ne "0.2.0" -or
        [int]$state.requested_rounds -ne $Rounds -or
        [int]$state.interval_seconds -ne $IntervalSeconds -or
        $state.registry_sha256 -ne $registrySha256
    ) {
        throw "Existing observation state does not match requested configuration"
    }
}
else {
    $state = [ordered]@{
        schema_version = "0.2.0"
        status = "RUNNING"
        started_at = [DateTimeOffset]::UtcNow.ToString("o")
        completed_at = $null
        next_due_at = $null
        requested_rounds = $Rounds
        interval_seconds = $IntervalSeconds
        registry_sha256 = $registrySha256
        endpoint_count = $endpoints.Count
        endpoints = $endpoints
        rounds = @()
        counts = [ordered]@{ results = 0; valid = 0; failed = 0 }
    }
    Write-ObservationState -State $state
}

while (@($state.rounds | Where-Object { $null -ne $_.completed_at }).Count -lt $Rounds) {
    $currentRound = @(
        $state.rounds | Where-Object { $null -eq $_.completed_at } | Select-Object -First 1
    )
    if ($currentRound.Count -eq 0) {
        $completedRounds = @($state.rounds | Where-Object { $null -ne $_.completed_at })
        if ($completedRounds.Count -gt 0) {
            $previousCompletedAt = [DateTimeOffset]::Parse(
                [string]$completedRounds[-1].completed_at
            )
            $dueAt = $previousCompletedAt.AddSeconds($IntervalSeconds)
            $now = [DateTimeOffset]::UtcNow
            if ($now -lt $dueAt) {
                $state.status = "WAITING"
                $state.next_due_at = $dueAt.ToString("o")
                Write-ObservationState -State $state
                if ($RunDueRoundsOnly) {
                    break
                }
                $remainingSeconds = [int][Math]::Ceiling(($dueAt - $now).TotalSeconds)
                Start-Sleep -Seconds $remainingSeconds
            }
        }

        $currentRoundValue = [ordered]@{
            round_number = @($state.rounds).Count + 1
            started_at = [DateTimeOffset]::UtcNow.ToString("o")
            completed_at = $null
            results = @()
        }
        $state.rounds = @($state.rounds) + @($currentRoundValue)
        $currentRound = @($currentRoundValue)
        $state.status = "RUNNING"
        $state.next_due_at = $null
        Write-ObservationState -State $state
    }

    $roundValue = $currentRound[0]
    $importInvocation = Invoke-SourceCli -Arguments @(
        "import-registry", "--path", $resolvedRegistryPath
    )
    $null = Convert-CliJson -Invocation $importInvocation -Operation "registry import"
    $completedEndpointIds = @($roundValue.results | ForEach-Object { $_.endpoint_id })

    foreach ($endpoint in $endpoints) {
        if ($endpoint.endpoint_id -in $completedEndpointIds) {
            continue
        }
        $collectInvocation = Invoke-SourceCli -Arguments @(
            "collect", "--endpoint-id", $endpoint.endpoint_id
        )
        if ($collectInvocation.exit_code -ne 0) {
            $roundValue.results = @($roundValue.results) + @(
                [ordered]@{
                    endpoint_id = $endpoint.endpoint_id
                    url = $endpoint.url
                    collection_run_id = $null
                    attempts = @()
                    final_outcome = "FAILED"
                    final_error_code = "COLLECT_COMMAND_FAILED"
                    artifact_sha256 = $null
                    object_key = $null
                    evidence_error_code = "COLLECT_COMMAND_FAILED"
                }
            )
            Update-ObservationCounts -State $state
            Write-ObservationState -State $state
            throw "collection command failed for endpoint $($endpoint.endpoint_id)"
        }
        $collect = Convert-CliJson -Invocation $collectInvocation -Operation "collection"

        $healthInvocation = Invoke-SourceCli -Arguments @(
            "health", "--endpoint-id", $endpoint.endpoint_id
        )
        $health = $null
        $evidenceError = $null
        if ($healthInvocation.exit_code -eq 0) {
            $health = Convert-CliJson -Invocation $healthInvocation -Operation "health"
        }
        else {
            $evidenceError = "HEALTH_COMMAND_FAILED"
        }

        $attempts = @(
            foreach ($attempt in @($collect.attempts)) {
                [ordered]@{
                    attempt_number = $attempt.attempt_number
                    outcome = $attempt.outcome
                    http_status = $attempt.http_status
                    artifact_id = $attempt.artifact_id
                    error_code = $attempt.error_code
                    started_at = $attempt.started_at
                    completed_at = $attempt.completed_at
                }
            }
        )
        $finalAttempt = @($attempts | Select-Object -Last 1)
        $roundValue.results = @($roundValue.results) + @(
            [ordered]@{
                endpoint_id = $endpoint.endpoint_id
                url = $endpoint.url
                collection_run_id = $collect.collection_run_id
                attempts = $attempts
                final_outcome = if ($finalAttempt.Count -eq 1) {
                    $finalAttempt[0].outcome
                } else { $null }
                final_error_code = $collect.final_error_code
                artifact_sha256 = if ($null -ne $health) {
                    $health.latest_content_sha256
                } else { $null }
                object_key = if ($null -ne $health) {
                    $health.latest_object_key
                } else { $null }
                evidence_error_code = $evidenceError
            }
        )
        Update-ObservationCounts -State $state
        Write-ObservationState -State $state
    }

    $roundValue.completed_at = [DateTimeOffset]::UtcNow.ToString("o")
    $completedCount = @($state.rounds | Where-Object { $null -ne $_.completed_at }).Count
    if ($completedCount -eq $Rounds) {
        $state.status = "COMPLETE"
        $state.completed_at = $roundValue.completed_at
        $state.next_due_at = $null
    }
    else {
        $state.status = "WAITING"
        $state.next_due_at = ([DateTimeOffset]::Parse(
            [string]$roundValue.completed_at
        )).AddSeconds($IntervalSeconds).ToString("o")
    }
    Update-ObservationCounts -State $state
    Write-ObservationState -State $state
    if ($RunDueRoundsOnly) {
        break
    }
}

[ordered]@{
    status = $state.status
    completed_rounds = @($state.rounds | Where-Object { $null -ne $_.completed_at }).Count
    counts = $state.counts
    next_due_at = $state.next_due_at
} | ConvertTo-Json -Depth 5 -Compress
