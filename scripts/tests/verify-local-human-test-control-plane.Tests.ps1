$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$verifierPath = Join-Path $repositoryRoot "scripts/verify-local-human-test-control-plane.ps1"

if (-not (Test-Path -LiteralPath $verifierPath -PathType Leaf)) {
    throw "Local human-test verifier is missing"
}
$content = Get-Content -LiteralPath $verifierPath -Raw -Encoding UTF8
foreach ($required in @(
    "local-manual-test.Tests.ps1",
    "verify-p9b-with-legacy-ports-occupied.ps1",
    "DEEPAHA_ALLOW_LIVE_SOURCE_CHECK",
    "GatewayExecutor",
    "Independent Acceptance=NOT_RUN",
    "Release Qualification=NOT_STARTED"
)) {
    if ($content -notmatch [Regex]::Escape($required)) {
        throw "Verifier does not contain required offline control: $required"
    }
}
foreach ($forbidden in @(
    "LLM-API.txt",
    "load_for_invocation",
    "LIVE_OFFICIAL",
    "api_key"
)) {
    if ($content -match [Regex]::Escape($forbidden)) {
        throw "Verifier contains forbidden credential or live-call behavior: $forbidden"
    }
}

Write-Host "Local human-test verifier scope test: PASS"
