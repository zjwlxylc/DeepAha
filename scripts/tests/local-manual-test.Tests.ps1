$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
. (Join-Path $repositoryRoot "scripts/local-manual-test.ps1")

function Assert-Equal {
    param($Actual, $Expected, [string]$Message)
    if ($Actual -ne $Expected) {
        throw "$Message (actual=$Actual expected=$Expected)"
    }
}

function Assert-Throws {
    param([scriptblock]$Operation, [string]$Pattern)
    try {
        & $Operation
    }
    catch {
        if ($_.Exception.Message -notmatch $Pattern) {
            throw "Unexpected error: $($_.Exception.Message)"
        }
        return
    }
    throw "Expected an error matching $Pattern"
}

$first = Get-LocalManualProjectInfo -ProjectRoot "C:\work\DeepAha"
$second = Get-LocalManualProjectInfo -ProjectRoot "C:\work\DeepAha"
$other = Get-LocalManualProjectInfo -ProjectRoot "C:\work\Other"
if ($first.ProjectName -cnotmatch '^deepaha-local-manual-[a-f0-9]{12}$') {
    throw "Project name is not bounded to the expected prefix and lowercase hash"
}
Assert-Equal $first.ProjectName $second.ProjectName "Project name must be deterministic"
if ($first.ProjectName -eq $other.ProjectName) {
    throw "Different roots must not share a project name"
}

$state = [pscustomobject]@{
    schema_version = "1.0"
    project_root = $first.ProjectRoot
    project_hash = $first.ProjectHash
    compose_project = $first.ProjectName
    compose_file = $first.ComposeFile
}
Assert-RuntimeStateOwnership -State $state -ProjectInfo $first
Assert-Throws {
    Assert-RuntimeStateOwnership -State $state -ProjectInfo $other
} "不属于当前工作树"
$foreignState = $state.PSObject.Copy()
$foreignState.compose_file = "C:\foreign\compose.yaml"
Assert-Throws {
    Assert-RuntimeStateOwnership -State $foreignState -ProjectInfo $first
} "不属于当前工作树"

$record = [pscustomobject]@{
    pid = 123
    created_at = "2026-08-23T01:02:03.0000000Z"
    role = "api"
    command_marker = "deepaha.main:app"
}
$owned = [pscustomobject]@{
    ProcessId = 123
    CreationDate = "2026-08-23T01:02:03.0000000Z"
    CommandLine = "uv run uvicorn --app-dir C:\work\DeepAha\backend\src deepaha.main:app"
}
if (-not (Test-RecordedProcessOwnership -Record $record -Process $owned -ProjectRoot "C:\work\DeepAha")) {
    throw "Exact recorded process should be recognized"
}
$nativeTime = [DateTime]::Parse(
    "2026-08-23T01:02:03.1234567Z",
    [Globalization.CultureInfo]::InvariantCulture,
    [Globalization.DateTimeStyles]::RoundtripKind
)
$nativeRecord = $record.PSObject.Copy()
$nativeRecord.created_at = ([DateTimeOffset]$nativeTime).ToString("o")
$nativeProcess = $owned.PSObject.Copy()
$nativeProcess.CreationDate = $nativeTime
if (-not (Test-RecordedProcessOwnership -Record $nativeRecord -Process $nativeProcess `
    -ProjectRoot "C:\work\DeepAha")) {
    throw "Native CIM DateTime must retain sub-second ownership precision"
}
$reused = $owned.PSObject.Copy()
$reused.CreationDate = "2026-08-23T01:02:04.0000000Z"
if (Test-RecordedProcessOwnership -Record $record -Process $reused -ProjectRoot "C:\work\DeepAha") {
    throw "Reused PID with another creation time must be rejected"
}
$foreign = $owned.PSObject.Copy()
$foreign.CommandLine = "uv run uvicorn foreign.main:app"
if (Test-RecordedProcessOwnership -Record $record -Process $foreign -ProjectRoot "C:\work\DeepAha") {
    throw "Foreign command line must be rejected"
}
$forgedRecord = $record.PSObject.Copy()
$forgedRecord.command_marker = "foreign.main:app"
$forgedProcess = $owned.PSObject.Copy()
$forgedProcess.CommandLine = "uv run --directory C:\work\DeepAha foreign.main:app"
if (Test-RecordedProcessOwnership -Record $forgedRecord -Process $forgedProcess `
    -ProjectRoot "C:\work\DeepAha") {
    throw "A state file cannot redefine the fixed command marker for a role"
}

$tree = @(
    [pscustomobject]@{ ProcessId = 10; ParentProcessId = 0 },
    [pscustomobject]@{ ProcessId = 11; ParentProcessId = 10 },
    [pscustomobject]@{ ProcessId = 12; ParentProcessId = 11 },
    [pscustomobject]@{ ProcessId = 99; ParentProcessId = 0 }
)
$order = @(Get-OwnedProcessStopOrder -RootProcessId 10 -Processes $tree)
Assert-Equal ($order -join ",") "12,11,10" "Children must stop before their recorded parent"

$composeLabels = [pscustomobject]@{
    'com.docker.compose.project' = $first.ProjectName
    'com.docker.compose.project.working_dir' = 'C:\work\DeepAha\infra'
    'com.docker.compose.project.config_files' = 'C:\work\DeepAha\infra\compose.local-manual.yaml'
}
if (-not (Test-ComposeLabelsOwnership -Labels $composeLabels `
    -ProjectName $first.ProjectName `
    -ComposeFile 'C:\work\DeepAha\infra\compose.local-manual.yaml')) {
    throw "Compose working directory must be derived from the exact compose file"
}
$foreignLabels = $composeLabels.PSObject.Copy()
$foreignLabels.'com.docker.compose.project.config_files' = 'C:\foreign\compose.yaml'
if (Test-ComposeLabelsOwnership -Labels $foreignLabels `
    -ProjectName $first.ProjectName `
    -ComposeFile 'C:\work\DeepAha\infra\compose.local-manual.yaml') {
    throw "Foreign compose config must be rejected"
}

$missingPath = Join-Path ([IO.Path]::GetTempPath()) "deepaha-missing-state-$PID.json"
$missing = Get-LocalManualRuntimeState -StatePath $missingPath
if ($null -ne $missing) {
    throw "Missing state must be an idempotent no-op"
}

$readyMarker = Join-Path ([IO.Path]::GetTempPath()) "deepaha-ready-$PID.json"
'{"status":"ready"}' | Set-Content -LiteralPath $readyMarker -Encoding UTF8
try {
    Wait-LocalManualBrowserReady -MarkerPath $readyMarker -HostProcessId $PID `
        -TimeoutMilliseconds 100
}
finally {
    Remove-Item -LiteralPath $readyMarker -Force -ErrorAction SilentlyContinue
}
Assert-Throws {
    Wait-LocalManualBrowserReady -MarkerPath $readyMarker -HostProcessId $PID `
        -TimeoutMilliseconds 50
} "浏览器未完成页面检查"

& node --check (Join-Path $repositoryRoot "web/scripts/open-local-manual-browser.mjs")
if ($LASTEXITCODE -ne 0) {
    throw "Browser host must be executable JavaScript"
}

Write-Host "本地人工测试启动器单元测试：PASS"
