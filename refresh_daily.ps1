# refresh_daily.ps1 - run the Brreg delta refresh and log the outcome.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
    Write-Host "No venv found. Run .\run.ps1 first." -ForegroundColor Red
    exit 1
}
. .\.venv\Scripts\Activate.ps1

New-Item -ItemType Directory -Path "logs" -Force | Out-Null
$log = "logs\refresh_$(Get-Date -Format 'yyyyMMdd').log"

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"
"[$stamp] Starting daily refresh" | Tee-Object -FilePath $log -Append

python -m agent.refresh --days 1 2>&1 | Tee-Object -FilePath $log -Append

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"
"[$stamp] Done" | Tee-Object -FilePath $log -Append

Write-Host "Log: $log" -ForegroundColor Green
