$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$suffix = [guid]::NewGuid().ToString("N").Substring(0, 8)
$composeProject = "deepaha-p9b-replacement-local-human-$PID-$suffix"

function Assert-NativeSuccess {
    param([Parameter(Mandatory = $true)][string]$Operation)
    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE"
    }
}

# The verifier owns no real-source or Provider authority. Remove inherited switches before
# invoking repository tests; test transports and the verifier-owned Compose project remain local.
Remove-Item Env:DEEPAHA_ALLOW_LIVE_SOURCE_CHECK -ErrorAction SilentlyContinue
Remove-Item Env:DEEPAHA_LOCAL_HUMAN_TEST_ENABLED -ErrorAction SilentlyContinue
Remove-Item Env:DEEPAHA_LOCAL_HUMAN_TEST_ROOT -ErrorAction SilentlyContinue

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (
    Join-Path $projectRoot "scripts/tests/verify-local-human-test-control-plane.Tests.ps1"
)
Assert-NativeSuccess "local human-test verifier scope tests"

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (
    Join-Path $projectRoot "scripts/tests/local-manual-test.Tests.ps1"
)
Assert-NativeSuccess "local human-test launcher tests"

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (
    Join-Path $projectRoot "scripts/verify-p9b-with-legacy-ports-occupied.ps1"
) -ComposeProjectName $composeProject
Assert-NativeSuccess "offline backend, migration, integration and Web verification"

$gatewayPath = Join-Path $projectRoot "backend/src/deepaha/p9b/gateway.py"
$gatewayCalls = @(
    Select-String -LiteralPath $gatewayPath -SimpleMatch "self._adapter.invoke(invocation)"
)
if ($gatewayCalls.Count -ne 1) {
    throw "Provider adapter dispatch is not uniquely owned by GatewayExecutor"
}
$otherDispatches = @(
    Get-ChildItem -LiteralPath (Join-Path $projectRoot "backend/src/deepaha") `
        -Filter "*.py" -Recurse |
        Select-String -SimpleMatch "_adapter.invoke(invocation)" |
        Where-Object { $_.Path -ne $gatewayPath }
)
if ($otherDispatches.Count -ne 0) {
    throw "Provider adapter dispatch exists outside GatewayExecutor"
}

Write-Host "LOCAL HUMAN TEST CONTROL PLANE VERIFIER=PASS"
Write-Host "external official calls=0; real Provider calls=0; credential=NOT_READ"
Write-Host "Engineering implementation only"
Write-Host "Independent Acceptance=NOT_RUN"
Write-Host "Release Qualification=NOT_STARTED"
