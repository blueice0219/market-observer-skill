param(
    [ValidateSet('Start', 'Stop', 'Status')][string]$Action = 'Status',
    [switch]$UseProxy
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$runtimePath = Join-Path $projectRoot 'data\local-service'
New-Item -ItemType Directory -Path $runtimePath -Force | Out-Null

function Get-OwnedProcess([string]$Role) {
    $pidFile = Join-Path $runtimePath "$Role.pid"
    if (-not (Test-Path -LiteralPath $pidFile)) { return $null }
    $savedId = 0
    if (-not [int]::TryParse((Get-Content -LiteralPath $pidFile -Raw).Trim(), [ref]$savedId)) { return $null }
    $running = Get-CimInstance Win32_Process -Filter "ProcessId=$savedId" -ErrorAction SilentlyContinue
    if ($running -and $running.ExecutablePath -eq $pythonPath -and $running.CommandLine -match "a_share_monitor $Role") {
        return $running
    }
    return $null
}

if ($Action -eq 'Start') {
    if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Project virtual environment is missing.' }
    $env:MONITOR_DB = Join-Path $projectRoot 'data\live.sqlite3'
    $env:MONITOR_STALE_SECONDS = '900'
    $env:MONITOR_API_KEY = ''
    $env:MONITOR_CORS_ORIGINS = ''
    $env:PYTHONUTF8 = '1'
    # Only these child processes use direct connections; system proxy is unchanged.
    if (-not $UseProxy) {
        Remove-Item Env:HTTP_PROXY,Env:HTTPS_PROXY,Env:ALL_PROXY -ErrorAction SilentlyContinue
    }
    foreach ($role in @('serve', 'collect')) {
        if (Get-OwnedProcess $role) { Write-Host "$role already running"; continue }
        if ($role -eq 'serve') {
            if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
                throw 'Port 8000 is occupied by another process.'
            }
            $arguments = '-m a_share_monitor serve --host 127.0.0.1 --port 8000'
        } else {
            $arguments = '-m a_share_monitor collect --source auto --interval 300 --timeout 90'
        }
        $child = Start-Process -FilePath $pythonPath -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimePath "$role.stdout.log") -RedirectStandardError (Join-Path $runtimePath "$role.stderr.log")
        Set-Content -LiteralPath (Join-Path $runtimePath "$role.pid") -Value $child.Id
        Write-Host "$role started (PID $($child.Id))"
    }
    Write-Host 'API docs: http://127.0.0.1:8000/docs'
    Write-Host 'Status:   http://127.0.0.1:8000/api/v1/status'
} elseif ($Action -eq 'Stop') {
    foreach ($role in @('collect', 'serve')) {
        $owned = Get-OwnedProcess $role
        if ($owned) {
            # Kill only the verified project's process tree, including an active worker.
            & taskkill.exe /PID $owned.ProcessId /T /F
            if ($LASTEXITCODE -ne 0) { throw "Unable to stop $role" }
            Remove-Item -LiteralPath (Join-Path $runtimePath "$role.pid") -ErrorAction SilentlyContinue
        } else { Write-Host "$role is not running" }
    }
} else {
    foreach ($role in @('serve', 'collect')) {
        $owned = Get-OwnedProcess $role
        if ($owned) { Write-Host "$role running (PID $($owned.ProcessId))" }
        else { Write-Host "$role is not running" }
    }
    try { Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/status' -TimeoutSec 5 | ConvertTo-Json -Depth 5 }
    catch { Write-Host 'API is not responding.' }
}
