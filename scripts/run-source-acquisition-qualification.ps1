param(
    [Parameter(Mandatory = $true)]
    [string]$RecipeId,
    [Parameter(Mandatory = $true)]
    [string]$EndpointId,
    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 25)]
    [int]$MaximumRequests,
    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 86400)]
    [int]$MinimumIntervalSeconds,
    [string]$RecipePath,
    [switch]$Live
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $RecipePath) {
    $RecipePath = Join-Path $projectRoot "config/acquisition/recipes.v1.json"
}
if (-not $Live) {
    Write-Output '{"error_code":"LIVE_QUALIFICATION_NOT_ALLOWED"}'
    exit 2
}

$priorPermission = $env:DEEPAHA_ALLOW_LIVE_SOURCE_CHECK
try {
    $env:DEEPAHA_ALLOW_LIVE_SOURCE_CHECK = "true"
    Push-Location (Join-Path $projectRoot "backend")
    try {
        uv run python -m deepaha.acquisition.cli qualify `
            --recipe-id $RecipeId `
            --endpoint-id $EndpointId `
            --recipe-path $RecipePath `
            --maximum-requests $MaximumRequests `
            --minimum-interval-seconds $MinimumIntervalSeconds `
            --live
        exit $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
}
finally {
    if ($null -eq $priorPermission) {
        Remove-Item Env:DEEPAHA_ALLOW_LIVE_SOURCE_CHECK -ErrorAction SilentlyContinue
    }
    else {
        $env:DEEPAHA_ALLOW_LIVE_SOURCE_CHECK = $priorPermission
    }
}
