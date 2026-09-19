param([ValidateSet("Start","Stop","Status","Library")][string]$Action="Start")
$ErrorActionPreference="Stop"
$Root=Split-Path $PSScriptRoot -Parent
switch($Action){
 "Start" { & py -3 (Join-Path $PSScriptRoot "launch_product.py") --install }
 "Stop" { & py -3 (Join-Path $PSScriptRoot "launch_product.py") --stop }
 "Status" { & py -3 (Join-Path $PSScriptRoot "launch_product.py") --status }
 default { Write-Output "旧手工测试控制台已退役；当前入口为 launch_product.py。" }
}
exit $LASTEXITCODE
