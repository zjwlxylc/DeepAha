$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$DataDir = if ($env:DEEPAHA_DATA_DIR) { $env:DEEPAHA_DATA_DIR } else { Join-Path $env:USERPROFILE 'deepaha-data' }
$Python = Join-Path $Root '.venv-product\Scripts\python.exe'
if (-not (Test-Path $Python)) { throw '未找到 .venv-product。请先正常运行一次机会星图。' }
# Stop only the processes owned by this launcher; it will not kill unrelated services.
& $Python (Join-Path $Root 'scripts\launch_product.py') --stop
if ($LASTEXITCODE -ne 0) { throw '停止本地服务失败，请先检查。' }
$env:PYTHONPATH = Join-Path $Root 'backend\src'
$env:DEEPAHA_DATA_DIR = $DataDir
$Stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$OutDir = Join-Path $Root 'sg8a-export'
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$Backup = Join-Path $OutDir "DeepAha-local-$Stamp.zip"
Push-Location (Join-Path $Root 'backend')
try {
  & $Python -m deepaha.product.cli backup $Backup
  if ($LASTEXITCODE -ne 0) { throw '创建备份失败。' }
  & $Python -m deepaha.product.cli verify-backup $Backup
  if ($LASTEXITCODE -ne 0) { throw '备份校验失败。' }
} finally { Pop-Location }
Write-Host "SG8A_PORTABLE_BACKUP=$Backup"
Write-Host '说明：该文件包含账号密码哈希和用户数据，但不包含WMA API Key。请按敏感数据保管。'
