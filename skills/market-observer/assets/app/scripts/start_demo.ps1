$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path '.venv\Scripts\python.exe')) { throw '请先按 README 创建 .venv 并安装项目。' }
$env:MONITOR_DB = Join-Path (Get-Location) 'data\demo.sqlite3'
& .\.venv\Scripts\python.exe -m a_share_monitor collect --source demo --once
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .\.venv\Scripts\python.exe -m a_share_monitor serve
