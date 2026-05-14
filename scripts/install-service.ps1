# Install focus-lock as a Windows service via NSSM.
# Run as Administrator.
. (Join-Path $PSScriptRoot "_common.ps1")

Assert-Admin
Ensure-Dirs

Push-Location $ProjectRoot
try {
    Ensure-Venv
    Ensure-Nssm

    if (Test-ServiceExists) {
        Write-Host "service already exists — reconfiguring" -ForegroundColor Yellow
        & $NssmExe stop $ServiceName confirm | Out-Null
    } else {
        & $NssmExe install $ServiceName $VenvPython "-m" "uvicorn" "focus_lock.main:app" "--host" "127.0.0.1" "--port" "8765"
    }

    & $NssmExe set $ServiceName AppDirectory   $ProjectRoot
    & $NssmExe set $ServiceName DisplayName    $DisplayName
    & $NssmExe set $ServiceName Description    "Website blocker with Frozen sessions and schedules."
    & $NssmExe set $ServiceName Start          SERVICE_AUTO_START
    & $NssmExe set $ServiceName ObjectName     "LocalSystem"
    & $NssmExe set $ServiceName AppStdout      (Join-Path $LogDir "service.out.log")
    & $NssmExe set $ServiceName AppStderr      (Join-Path $LogDir "service.err.log")
    & $NssmExe set $ServiceName AppRotateFiles 1
    & $NssmExe set $ServiceName AppRotateBytes 1048576
    & $NssmExe set $ServiceName AppExit        Default Restart
    & $NssmExe set $ServiceName AppRestartDelay 2000

    # SCM-level recovery (covers NSSM-bypass scenarios)
    & sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/5000/restart/15000 | Out-Null

    & $NssmExe start $ServiceName | Out-Null
    Start-Sleep -Seconds 2

    $svc = Get-Service -Name $ServiceName
    Write-Host ""
    Write-Host "service '$ServiceName' is $($svc.Status)" -ForegroundColor Green
    Write-Host "open    : http://127.0.0.1:8765" -ForegroundColor Green
    Write-Host "logs    : $LogDir" -ForegroundColor DarkGray
    Write-Host "uninstall (frozen-guard): scripts\uninstall-service.ps1" -ForegroundColor DarkGray
} finally {
    Pop-Location
}
