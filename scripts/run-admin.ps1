# focus-lock launcher (Windows)
# Run from project root:  powershell -ExecutionPolicy Bypass -File scripts\run-admin.ps1
# Will re-launch itself elevated if needed (hosts file write requires admin).

$ErrorActionPreference = "Stop"

$current = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $current.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "elevating..." -ForegroundColor Yellow
    Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path ".venv")) {
    Write-Host "creating venv..." -ForegroundColor Cyan
    python -m venv .venv
}

& ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
& ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt

Write-Host ""
Write-Host "focus-lock running at http://127.0.0.1:8765" -ForegroundColor Green
Write-Host "press Ctrl+C to stop" -ForegroundColor DarkGray
Write-Host ""

& ".venv\Scripts\python.exe" -m uvicorn focus_lock.main:app --host 127.0.0.1 --port 8765
