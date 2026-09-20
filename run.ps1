# run.ps1 - one command to build all profiles from scratch.
$ErrorActionPreference = "Stop"

Write-Host "== Norwegian Company Agent ==" -ForegroundColor Cyan

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
}
. .\.venv\Scripts\Activate.ps1

pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

if (-not (Test-Path "data\seed_orgnrs.txt")) {
    if (-not (Test-Path "data\enheter.json.gz")) {
        Write-Host "Downloading bulk Enhetsregisteret dump..." -ForegroundColor Yellow
        curl.exe -L -o data\enheter.json.gz "https://data.brreg.no/enhetsregisteret/api/enheter/lastned"
    }
    Write-Host "Extracting seed orgnrs..." -ForegroundColor Yellow
    python data\extract_seed.py
}

Write-Host "Building profiles..." -ForegroundColor Yellow
python -m agent.build --orgnrs data\seed_orgnrs.txt --output profiles --concurrency 8

Write-Host "Validating profiles..." -ForegroundColor Yellow
python tests\validate_profiles.py

Write-Host "== Done. Profiles are in .\profiles ==" -ForegroundColor Green
