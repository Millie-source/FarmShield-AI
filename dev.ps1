# FarmShield AI - PowerShell equivalent of the Makefile for Windows machines without GNU make.
# Usage: .\dev.ps1 setup | dev | api | web | test | seed | openapi
param([Parameter(Position = 0)][string]$Target = "dev")

$Root = $PSScriptRoot
$Venv = Join-Path $Root "backend\.venv"
$Py = Join-Path $Venv "Scripts\python.exe"

function Setup {
    if (-not (Test-Path $Py)) { python -m venv $Venv }
    & $Py -m pip install -q -e "$Root\backend[dev]"
    Push-Location "$Root\frontend"; npm install; Pop-Location
}
function Api { Push-Location "$Root\backend"; & $Py -m uvicorn app.main:app --reload --port 8000; Pop-Location }
function Web { Push-Location "$Root\frontend"; npm run dev; Pop-Location }
function Dev {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$Root\backend'; & '$Py' -m uvicorn app.main:app --reload --port 8000"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$Root\frontend'; npm run dev"
    Write-Host "API  -> http://localhost:8000/docs"
    Write-Host "Web  -> http://localhost:5173"
}
function Test { Push-Location "$Root\backend"; & $Py -m pytest -q; Pop-Location }
function Seed { Push-Location "$Root\backend"; & $Py -m app.seed; Pop-Location }
function OpenApi { Push-Location "$Root\backend"; & $Py -m app.export_openapi; Pop-Location }

switch ($Target) {
    "setup"   { Setup }
    "dev"     { Dev }
    "api"     { Api }
    "web"     { Web }
    "test"    { Test }
    "seed"    { Seed }
    "openapi" { OpenApi }
    default   { Write-Host "Unknown target '$Target'. Use: setup | dev | api | web | test | seed | openapi" }
}
