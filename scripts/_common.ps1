# Shared helpers for focus-lock service scripts.

$ErrorActionPreference = "Stop"

$script:ServiceName  = "focus-lock"
$script:DisplayName  = "focus-lock website blocker"
$script:ProjectRoot  = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$script:ToolsDir     = Join-Path $ProjectRoot "tools"
$script:VenvDir      = Join-Path $ProjectRoot ".venv"
$script:VenvPython   = Join-Path $VenvDir "Scripts\python.exe"
$script:NssmExe      = Join-Path $ToolsDir "nssm.exe"
$script:DataDir      = Join-Path $env:ProgramData "focus-lock"
$script:LogDir       = Join-Path $DataDir "logs"

function Assert-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $pr = New-Object Security.Principal.WindowsPrincipal($id)
    if (-not $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "This script requires Administrator. Right-click PowerShell and 'Run as administrator'."
    }
}

function Ensure-Venv {
    if (-not (Test-Path $VenvPython)) {
        Write-Host "creating venv at $VenvDir ..." -ForegroundColor Cyan
        python -m venv $VenvDir
    }
    & $VenvPython -m pip install --quiet --upgrade pip
    & $VenvPython -m pip install --quiet -r (Join-Path $ProjectRoot "requirements.txt")
}

function Ensure-Dirs {
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    New-Item -ItemType Directory -Force -Path $LogDir  | Out-Null
    New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null
}

function Ensure-Nssm {
    if (Test-Path $NssmExe) { return }
    Write-Host "downloading NSSM ..." -ForegroundColor Cyan
    $zip = Join-Path $env:TEMP "nssm-2.24.zip"
    $ext = Join-Path $env:TEMP "nssm-extract"
    Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile $zip -UseBasicParsing
    if (Test-Path $ext) { Remove-Item -Recurse -Force $ext }
    Expand-Archive -Path $zip -DestinationPath $ext -Force
    $arch = if ([Environment]::Is64BitOperatingSystem) { "win64" } else { "win32" }
    $src = Get-ChildItem -Recurse -Path $ext -Filter "nssm.exe" | Where-Object { $_.FullName -match "\\$arch\\" } | Select-Object -First 1
    if ($null -eq $src) { throw "could not locate nssm.exe in archive" }
    Copy-Item $src.FullName $NssmExe -Force
    Remove-Item $zip -Force
    Remove-Item -Recurse -Force $ext
    Write-Host "nssm.exe installed at $NssmExe" -ForegroundColor Green
}

function Test-ServiceExists {
    return ($null -ne (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue))
}

function Get-ApiBase {
    return "http://127.0.0.1:8765"
}

function Get-FrozenSessions {
    # Returns @() if API unreachable or no frozen sessions active.
    try {
        $resp = Invoke-RestMethod -Uri "$(Get-ApiBase)/api/sessions" -TimeoutSec 2
        return @($resp.sessions | Where-Object { $_.frozen -eq $true })
    } catch {
        return @()
    }
}
