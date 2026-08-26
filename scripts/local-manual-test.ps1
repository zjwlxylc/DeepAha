param(
    [ValidateSet("Library", "Start", "Stop", "Status")]
    [string]$Action = "Library"
)

$ErrorActionPreference = "Stop"
$script:LocalManualPorts = @(55439, 8009, 3089)

function Get-LocalManualProjectInfo {
    param([Parameter(Mandatory = $true)][string]$ProjectRoot)

    $normalized = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\', '/')
    $hashInput = $normalized.ToLowerInvariant()
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($hashInput)
        $hash = ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
    [pscustomobject]@{
        ProjectRoot = $normalized
        ProjectHash = $hash
        ProjectName = "deepaha-local-manual-$($hash.Substring(0, 12))"
        DataRoot = [IO.Path]::GetFullPath(
            (Join-Path $env:LOCALAPPDATA "DeepAha\manual-test")
        )
        ComposeFile = [IO.Path]::GetFullPath(
            (Join-Path $normalized "infra\compose.local-manual.yaml")
        )
    }
}

function Get-LocalManualRuntimeState {
    param([Parameter(Mandatory = $true)][string]$StatePath)

    if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) {
        return $null
    }
    Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Assert-RuntimeStateOwnership {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)]$ProjectInfo
    )

    $schemaVersion = [string]$State.schema_version
    $dataRootMatches = (
        $schemaVersion -eq "1.0" -or
        [IO.Path]::GetFullPath([string]$State.data_root) -eq $ProjectInfo.DataRoot
    )
    if (
        $schemaVersion -notin @("1.0", "1.1") -or
        $State.project_root -ne $ProjectInfo.ProjectRoot -or
        $State.project_hash -ne $ProjectInfo.ProjectHash -or
        $State.compose_project -ne $ProjectInfo.ProjectName -or
        [IO.Path]::GetFullPath([string]$State.compose_file) -ne $ProjectInfo.ComposeFile -or
        -not $dataRootMatches
    ) {
        throw "现有运行清单不属于当前工作树，已拒绝操作。"
    }
}

function Test-RecordedProcessOwnership {
    param(
        [Parameter(Mandatory = $true)]$Record,
        [Parameter(Mandatory = $true)]$Process,
        [Parameter(Mandatory = $true)][string]$ProjectRoot
    )

    if ([int]$Process.ProcessId -ne [int]$Record.pid) {
        return $false
    }
    $fixedMarkers = @{
        api = "deepaha.main:app"
        worker = "deepaha.local_human_test.runtime"
        web = "pnpm start"
        browser = "open-local-manual-browser.mjs"
    }
    if (
        -not $fixedMarkers.ContainsKey([string]$Record.role) -or
        [string]$Record.command_marker -cne $fixedMarkers[[string]$Record.role]
    ) {
        return $false
    }
    try {
        if ($Record.created_at -is [DateTime]) {
            $recordedTime = ([DateTimeOffset]$Record.created_at).UtcDateTime
        }
        else {
            $recordedTime = [DateTimeOffset]::Parse([string]$Record.created_at).UtcDateTime
        }
        if ($Process.CreationDate -is [DateTime]) {
            $actualTime = ([DateTimeOffset]$Process.CreationDate).UtcDateTime
        }
        else {
            $actualTime = [DateTimeOffset]::Parse([string]$Process.CreationDate).UtcDateTime
        }
    }
    catch {
        return $false
    }
    if ($recordedTime.Ticks -ne $actualTime.Ticks) {
        return $false
    }
    $commandLine = [string]$Process.CommandLine
    return (
        $commandLine.IndexOf($ProjectRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $commandLine.IndexOf(
            [string]$Record.command_marker,
            [StringComparison]::OrdinalIgnoreCase
        ) -ge 0
    )
}

function Get-OwnedProcessStopOrder {
    param(
        [Parameter(Mandatory = $true)][int]$RootProcessId,
        [Parameter(Mandatory = $true)][array]$Processes
    )

    $children = @{}
    foreach ($process in $Processes) {
        $parent = [int]$process.ParentProcessId
        if (-not $children.ContainsKey($parent)) {
            $children[$parent] = [Collections.Generic.List[int]]::new()
        }
        $children[$parent].Add([int]$process.ProcessId)
    }
    $order = [Collections.Generic.List[int]]::new()
    function Add-Descendants([int]$ProcessId) {
        if ($children.ContainsKey($ProcessId)) {
            foreach ($childId in $children[$ProcessId]) {
                Add-Descendants $childId
            }
        }
        $order.Add($ProcessId)
    }
    Add-Descendants $RootProcessId
    return $order
}

function Assert-CommandAvailable {
    param([Parameter(Mandatory = $true)][string]$Name, [string]$Help)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "缺少必需组件 $Name。$Help"
    }
}

function Invoke-NativeChecked {
    param(
        [Parameter(Mandatory = $true)][string]$Description,
        [Parameter(Mandatory = $true)][scriptblock]$Operation
    )
    & $Operation
    if ($LASTEXITCODE -ne 0) {
        throw "$Description 失败（退出码 $LASTEXITCODE）。请查看上方信息。"
    }
}

function Assert-LocalManualPortsFree {
    foreach ($port in $script:LocalManualPorts) {
        $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
        if ($listeners.Count -gt 0) {
            throw "本地测试所需资源被其他程序占用。请关闭占用程序后重试。"
        }
    }
}

function Write-LocalManualState {
    param([Parameter(Mandatory = $true)][string]$StatePath, [Parameter(Mandatory = $true)]$State)
    $temporary = "$StatePath.tmp"
    $State | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $StatePath -Force
}

function Start-LocalManualProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Role,
        [Parameter(Mandatory = $true)][string]$CommandMarker,
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$LogDirectory
    )
    $stdout = Join-Path $LogDirectory "$Role.out.log"
    $stderr = Join-Path $LogDirectory "$Role.err.log"
    $process = Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $Command
    ) -WorkingDirectory $WorkingDirectory -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr -PassThru -WindowStyle Hidden
    $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $($process.Id)"
    if ($null -eq $cim) {
        throw "无法记录 $Role 进程所有权。"
    }
    [pscustomobject]@{
        pid = $process.Id
        created_at = ([DateTimeOffset]$cim.CreationDate).ToUniversalTime().ToString("o")
        role = $Role
        command_marker = $CommandMarker
    }
}

function Wait-LocalManualReady {
    param([Parameter(Mandatory = $true)][string]$Url, [string]$Name)
    $lastError = $null
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                return
            }
        }
        catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Milliseconds 500
    }
    throw "$Name 未在预期时间内就绪。$lastError"
}

function Wait-LocalManualBrowserReady {
    param(
        [Parameter(Mandatory = $true)][string]$MarkerPath,
        [Parameter(Mandatory = $true)][int]$HostProcessId,
        [int]$TimeoutMilliseconds = 30000
    )
    $watch = [Diagnostics.Stopwatch]::StartNew()
    while ($watch.ElapsedMilliseconds -lt $TimeoutMilliseconds) {
        if (Test-Path -LiteralPath $MarkerPath -PathType Leaf) {
            $marker = Get-Content -LiteralPath $MarkerPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($marker.status -eq "ready") {
                return
            }
        }
        if ($null -eq (Get-Process -Id $HostProcessId -ErrorAction SilentlyContinue)) {
            throw "测试浏览器在完成页面检查前退出。请查看 browser.err.log。"
        }
        Start-Sleep -Milliseconds 50
    }
    throw "浏览器未完成页面检查。请查看 browser.err.log。"
}

function Test-ExactComposeOwnership {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectName,
        [Parameter(Mandatory = $true)][string]$ComposeFile,
        [Parameter(Mandatory = $true)][string]$ProjectRoot
    )
    $containerIds = @(& docker compose --project-name $ProjectName --file $ComposeFile ps -q)
    if ($LASTEXITCODE -ne 0) {
        return $false
    }
    foreach ($containerId in $containerIds) {
        if ([string]::IsNullOrWhiteSpace($containerId)) { continue }
        $labelsJson = & docker inspect --format '{{json .Config.Labels}}' $containerId
        if ($LASTEXITCODE -ne 0) { return $false }
        $labels = $labelsJson | ConvertFrom-Json
        if (-not (Test-ComposeLabelsOwnership -Labels $labels -ProjectName $ProjectName `
            -ComposeFile $ComposeFile)) {
            return $false
        }
    }
    return $true
}

function Test-ComposeLabelsOwnership {
    param(
        [Parameter(Mandatory = $true)]$Labels,
        [Parameter(Mandatory = $true)][string]$ProjectName,
        [Parameter(Mandatory = $true)][string]$ComposeFile
    )
    $exactComposeFile = [IO.Path]::GetFullPath($ComposeFile)
    $expectedWorkingDirectory = Split-Path -Parent $exactComposeFile
    return (
        $Labels.'com.docker.compose.project' -ceq $ProjectName -and
        $Labels.'com.docker.compose.project.working_dir' -eq $expectedWorkingDirectory -and
        $Labels.'com.docker.compose.project.config_files' -eq $exactComposeFile
    )
}

function Stop-RecordedLocalManualProcess {
    param([Parameter(Mandatory = $true)]$Record, [string]$ProjectRoot)
    $rootProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$Record.pid)" `
        -ErrorAction SilentlyContinue
    if ($null -eq $rootProcess) {
        return $true
    }
    if (-not (Test-RecordedProcessOwnership -Record $Record -Process $rootProcess -ProjectRoot $ProjectRoot)) {
        Write-Warning "进程 $($Record.pid) 的身份已变化，未停止该进程。"
        return $false
    }
    $allProcesses = @(Get-CimInstance Win32_Process)
    $ownedProcessIds = @(
        Get-OwnedProcessStopOrder -RootProcessId $Record.pid -Processes $allProcesses
    )
    foreach ($processId in $ownedProcessIds) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
    for ($attempt = 1; $attempt -le 50; $attempt++) {
        $remaining = @($ownedProcessIds | Where-Object {
            $null -ne (Get-Process -Id $_ -ErrorAction SilentlyContinue)
        })
        if ($remaining.Count -eq 0) {
            return $true
        }
        Start-Sleep -Milliseconds 100
    }
    Write-Warning "进程 $($Record.pid) 未在预期时间内退出。"
    return $false
}

function Assert-PathWithinRuntime {
    param([string]$Path, [string]$RuntimeDirectory)
    $expectedRoot = [IO.Path]::GetFullPath($RuntimeDirectory).TrimEnd('\') + '\'
    $resolved = [IO.Path]::GetFullPath($Path)
    if (-not $resolved.StartsWith($expectedRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "拒绝清理运行目录之外的路径：$resolved"
    }
}

function Remove-LocalManualRuntimeSecrets {
    param([string]$RuntimeDirectory)
    foreach ($name in @(
        "identity.json",
        "browser-ready.json"
    )) {
        $target = Join-Path $RuntimeDirectory $name
        Assert-PathWithinRuntime -Path $target -RuntimeDirectory $RuntimeDirectory
        if (Test-Path -LiteralPath $target) {
            Remove-Item -LiteralPath $target -Recurse -Force
        }
    }
}

function Invoke-LocalManualStop {
    param([Parameter(Mandatory = $true)][string]$ProjectRoot)
    $projectInfo = Get-LocalManualProjectInfo -ProjectRoot $ProjectRoot
    $runtimeDirectory = Join-Path $projectInfo.ProjectRoot ".deepaha-local-manual"
    $statePath = Join-Path $runtimeDirectory "runtime.json"
    $state = Get-LocalManualRuntimeState -StatePath $statePath
    if ($null -eq $state) {
        Write-Host "DeepAha 本地人工测试当前未运行，无需停止。"
        return
    }
    Assert-RuntimeStateOwnership -State $state -ProjectInfo $projectInfo
    $allProcessesOwnedAndStopped = $true
    foreach ($record in @($state.processes)) {
        if (-not (Stop-RecordedLocalManualProcess -Record $record `
            -ProjectRoot $projectInfo.ProjectRoot)) {
            $allProcessesOwnedAndStopped = $false
        }
    }
    if (-not $allProcessesOwnedAndStopped) {
        throw "至少一个已记录进程无法验证或停止；已保留运行清单和数据供人工核对。"
    }
    $composeFile = [IO.Path]::GetFullPath([string]$state.compose_file)
    if (Test-ExactComposeOwnership -ProjectName $projectInfo.ProjectName `
        -ComposeFile $composeFile -ProjectRoot $projectInfo.ProjectRoot) {
        Invoke-NativeChecked "停止隔离数据库" {
            docker compose --project-name $projectInfo.ProjectName --file $composeFile `
                down --remove-orphans
        }
    }
    else {
        Write-Warning "Compose 资源标签与本轮清单不一致，未清理这些容器。"
    }
    Remove-LocalManualRuntimeSecrets -RuntimeDirectory $runtimeDirectory
    Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
    Write-Host "DeepAha 本地人工测试已安全停止。"
}

function Invoke-LocalManualStart {
    param([Parameter(Mandatory = $true)][string]$ProjectRoot)
    $projectInfo = Get-LocalManualProjectInfo -ProjectRoot $ProjectRoot
    $runtimeDirectory = Join-Path $projectInfo.ProjectRoot ".deepaha-local-manual"
    $statePath = Join-Path $runtimeDirectory "runtime.json"
    $composeFile = $projectInfo.ComposeFile
    $existing = Get-LocalManualRuntimeState -StatePath $statePath
    if ($null -ne $existing) {
        Assert-RuntimeStateOwnership -State $existing -ProjectInfo $projectInfo
        if ([string]$existing.schema_version -eq "1.0") {
            Write-Host "检测到旧版本地测试运行，正在安全停止后升级……"
            Invoke-LocalManualStop -ProjectRoot $projectInfo.ProjectRoot
        }
        else {
            Write-Host "DeepAha 本地人工测试已经启动，请使用现有浏览器窗口。"
            return
        }
    }

    Write-Host "[1/8] 正在检查本机环境……"
    Assert-CommandAvailable "docker" "请安装并启动 Docker Desktop。"
    Assert-CommandAvailable "uv" "请安装 uv。"
    Assert-CommandAvailable "node" "请安装 Node.js 24 LTS。"
    Assert-CommandAvailable "corepack" "请启用 Node.js 自带的 Corepack。"
    Invoke-NativeChecked "Docker Desktop 检查" { docker info *> $null }
    $nodeMajor = [int]((& node --version).TrimStart('v').Split('.')[0])
    if ($nodeMajor -ne 24) { throw "需要 Node.js 24 LTS，当前版本不符合要求。" }
    Assert-LocalManualPortsFree

    New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null
    $logDirectory = Join-Path $runtimeDirectory "logs"
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $identityPath = Join-Path $runtimeDirectory "identity.json"
    $browserReadyPath = Join-Path $runtimeDirectory "browser-ready.json"
    $processes = [Collections.Generic.List[object]]::new()
    $composeStarted = $false
    try {
        Write-Host "[2/8] 正在准备本地依赖（首次可能需要几分钟）……"
        Push-Location (Join-Path $projectInfo.ProjectRoot "backend")
        try { Invoke-NativeChecked "后端依赖准备" { uv sync --locked --group dev } }
        finally { Pop-Location }
        Push-Location (Join-Path $projectInfo.ProjectRoot "web")
        try { Invoke-NativeChecked "Web 依赖准备" { corepack pnpm install --frozen-lockfile } }
        finally { Pop-Location }

        Write-Host "[3/8] 正在启动持久化隔离数据库……"
        Invoke-NativeChecked "隔离服务启动" {
            docker compose --project-name $projectInfo.ProjectName --file $composeFile up -d --wait
        }
        $composeStarted = $true

        $env:DEEPAHA_DATABASE_URL = "postgresql+psycopg://deepaha:deepaha_local_manual_only@127.0.0.1:55439/deepaha"
        $env:DEEPAHA_ENVIRONMENT = "development"
        $env:DEEPAHA_REVIEWER_AUTH_MODE = "fixture"
        $env:DEEPAHA_LOCAL_HUMAN_TEST_ENABLED = "true"
        $env:DEEPAHA_LOCAL_HUMAN_TEST_ROOT = $projectInfo.DataRoot
        $env:DEEPAHA_LOCAL_HUMAN_TEST_BIND_HOST = "127.0.0.1"
        $env:DEEPAHA_LOCAL_HUMAN_TEST_WORKER_ID = "local-human-test-worker"

        Write-Host "[4/8] 正在迁移数据库并准备本地审核身份……"
        Push-Location (Join-Path $projectInfo.ProjectRoot "backend")
        try {
            Invoke-NativeChecked "数据库迁移" { uv run alembic upgrade head }
            $env:PYTHONPATH = "src"
            Invoke-NativeChecked "本地审核身份与来源注册表准备" {
                uv run python -m tests.manual.seed_local_manual --identity-file $identityPath
            }
        }
        finally { Pop-Location }

        Write-Host "[5/8] 正在构建 Web 页面……"
        Push-Location (Join-Path $projectInfo.ProjectRoot "web")
        try {
            $env:DEEPAHA_API_BASE_URL = "http://127.0.0.1:8009"
            Invoke-NativeChecked "Web 构建" { corepack pnpm build }
            Invoke-NativeChecked "Chromium 准备" { corepack pnpm exec playwright install chromium }
        }
        finally { Pop-Location }

        Write-Host "[6/8] 正在启动 API、Worker 与 Web……"
        $escapedRoot = $projectInfo.ProjectRoot.Replace("'", "''")
        $escapedDataRoot = $projectInfo.DataRoot.Replace("'", "''")
        $serviceEnvironment = "`$env:DEEPAHA_DATABASE_URL='postgresql+psycopg://deepaha:deepaha_local_manual_only@127.0.0.1:55439/deepaha'; " +
            "`$env:DEEPAHA_ENVIRONMENT='development'; " +
            "`$env:DEEPAHA_REVIEWER_AUTH_MODE='fixture'; " +
            "`$env:DEEPAHA_LOCAL_HUMAN_TEST_ENABLED='true'; " +
            "`$env:DEEPAHA_LOCAL_HUMAN_TEST_ROOT='$escapedDataRoot'; " +
            "`$env:DEEPAHA_LOCAL_HUMAN_TEST_BIND_HOST='127.0.0.1'; " +
            "`$env:DEEPAHA_LOCAL_HUMAN_TEST_WORKER_ID='local-human-test-worker'; "
        $apiCommand = $serviceEnvironment + "Set-Location -LiteralPath '$escapedRoot\backend'; " +
            "uv run uvicorn --app-dir '$escapedRoot\backend\src' deepaha.main:app " +
            "--host 127.0.0.1 --port 8009"
        $workerCommand = $serviceEnvironment + "Set-Location -LiteralPath '$escapedRoot\backend'; " +
            "uv run python -m deepaha.local_human_test.runtime --poll-seconds 0.5"
        $webCommand = "Set-Location -LiteralPath '$escapedRoot\web'; " +
            "`$env:DEEPAHA_API_BASE_URL='http://127.0.0.1:8009'; " +
            "corepack pnpm start --hostname 127.0.0.1 --port 3089"
        $processes.Add((Start-LocalManualProcess -Role "api" -CommandMarker "deepaha.main:app" `
            -Command $apiCommand -WorkingDirectory $projectInfo.ProjectRoot -LogDirectory $logDirectory))
        $processes.Add((Start-LocalManualProcess -Role "worker" `
            -CommandMarker "deepaha.local_human_test.runtime" -Command $workerCommand `
            -WorkingDirectory $projectInfo.ProjectRoot -LogDirectory $logDirectory))
        $processes.Add((Start-LocalManualProcess -Role "web" -CommandMarker "pnpm start" `
            -Command $webCommand -WorkingDirectory $projectInfo.ProjectRoot -LogDirectory $logDirectory))

        Write-Host "[7/8] 正在确认服务可用……"
        Wait-LocalManualReady -Url "http://127.0.0.1:8009/api/v1/health/ready" -Name "API"
        Wait-LocalManualReady -Url "http://127.0.0.1:3089/review/human-test" -Name "Web"

        Write-Host "[8/8] 正在打开已准备身份的测试浏览器……"
        Remove-Item -LiteralPath $browserReadyPath -Force -ErrorAction SilentlyContinue
        $browserCommand = "Set-Location -LiteralPath '$escapedRoot\web'; " +
            "node '$escapedRoot\web\scripts\open-local-manual-browser.mjs' " +
            "--origin http://127.0.0.1:3089 " +
            "--profile '$escapedDataRoot\browser-profile' " +
            "--identity '$escapedRoot\.deepaha-local-manual\identity.json' " +
            "--ready '$escapedRoot\.deepaha-local-manual\browser-ready.json'"
        $browserRecord = Start-LocalManualProcess -Role "browser" `
            -CommandMarker "open-local-manual-browser.mjs" -Command $browserCommand `
            -WorkingDirectory $projectInfo.ProjectRoot -LogDirectory $logDirectory
        $processes.Add($browserRecord)
        Wait-LocalManualBrowserReady -MarkerPath $browserReadyPath `
            -HostProcessId $browserRecord.pid

        $state = [ordered]@{
            schema_version = "1.1"
            project_root = $projectInfo.ProjectRoot
            project_hash = $projectInfo.ProjectHash
            compose_project = $projectInfo.ProjectName
            compose_file = [IO.Path]::GetFullPath($composeFile)
            data_root = $projectInfo.DataRoot
            started_at = [DateTimeOffset]::UtcNow.ToString("o")
            processes = @($processes)
        }
        Write-LocalManualState -StatePath $statePath -State $state
        Write-Host ""
        Write-Host "DeepAha 本地人工测试已启动。浏览器已打开受控人工体验控制台。"
        Write-Host "启动本身外部调用为 0；仅在页面确认真实运行后采集官网并调用已配置模型。"
        Write-Host "数据库、人工决定、审计证据和加密 Provider 配置会在正常停止后保留。"
        Write-Host "使用“停止 DeepAha 本地人工测试”入口结束本轮环境。"
    }
    catch {
        foreach ($record in $processes) {
            [void](Stop-RecordedLocalManualProcess -Record $record `
                -ProjectRoot $projectInfo.ProjectRoot)
        }
        if ($composeStarted -and (Test-ExactComposeOwnership -ProjectName $projectInfo.ProjectName `
            -ComposeFile $composeFile -ProjectRoot $projectInfo.ProjectRoot)) {
            & docker compose --project-name $projectInfo.ProjectName --file $composeFile `
                down --remove-orphans *> $null
        }
        Remove-LocalManualRuntimeSecrets -RuntimeDirectory $runtimeDirectory
        throw
    }
}

function Invoke-LocalManualStatus {
    param([Parameter(Mandatory = $true)][string]$ProjectRoot)
    $info = Get-LocalManualProjectInfo -ProjectRoot $ProjectRoot
    $state = Get-LocalManualRuntimeState -StatePath (
        Join-Path $info.ProjectRoot ".deepaha-local-manual\runtime.json"
    )
    if ($null -eq $state) { Write-Host "STOPPED"; return }
    Assert-RuntimeStateOwnership -State $state -ProjectInfo $info
    Write-Host "RUNNING"
}

if ($MyInvocation.InvocationName -ne '.') {
    $root = Split-Path -Parent $PSScriptRoot
    try {
        switch ($Action) {
            "Start" { Invoke-LocalManualStart -ProjectRoot $root }
            "Stop" { Invoke-LocalManualStop -ProjectRoot $root }
            "Status" { Invoke-LocalManualStatus -ProjectRoot $root }
            default { throw "必须指定 Start、Stop 或 Status。" }
        }
    }
    catch {
        Write-Host ""
        Write-Host "操作失败：$($_.Exception.Message)" -ForegroundColor Red
        Write-Host "日志保存在 .deepaha-local-manual\logs（如果已创建）。"
        exit 1
    }
}
