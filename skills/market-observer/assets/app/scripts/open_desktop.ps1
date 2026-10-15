$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
& (Join-Path $PSScriptRoot 'local_service.ps1') -Action Start
if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) { throw 'Unable to start local services.' }
$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $result = Invoke-RestMethod 'http://127.0.0.1:8000/healthz' -TimeoutSec 2
        if ($result.status -eq 'ok') { $ready = $true; break }
    } catch {}
    Start-Sleep -Milliseconds 500
}
if (-not $ready) { throw 'Local API did not become ready. See data/local-service logs.' }
$edgeCandidates = @(
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
)
$edge = $edgeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ($edge) {
    Start-Process -FilePath $edge -ArgumentList '--app=http://127.0.0.1:8000/', '--window-size=1440,960'
} else {
    Start-Process 'http://127.0.0.1:8000/'
}
