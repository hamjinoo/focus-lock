# Uninstall focus-lock. Refuses while frozen sessions are still active.
# Run as Administrator.
. (Join-Path $PSScriptRoot "_common.ps1")

Assert-Admin

if (-not (Test-ServiceExists)) {
    Write-Host "service '$ServiceName' is not installed" -ForegroundColor Yellow
    exit 0
}

$frozen = Get-FrozenSessions
if ($frozen.Count -gt 0) {
    Write-Host "" -ForegroundColor Red
    Write-Host "REFUSED: $($frozen.Count) frozen session(s) still active." -ForegroundColor Red
    foreach ($s in $frozen) {
        $ends = (Get-Date 1970-01-01).AddSeconds([double]$s.ends_at).ToLocalTime()
        Write-Host "  * $($s.label)  ends: $ends" -ForegroundColor Red
    }
    Write-Host ""
    Write-Host "This is by design - frozen sessions cannot be bypassed by uninstalling." -ForegroundColor DarkGray
    Write-Host "Wait until they expire, then retry." -ForegroundColor DarkGray
    exit 1
}

# Watchdog must be removed first; otherwise it'd just reinstall the service.
$wdName = "focus-lock-watchdog"
if (Get-ScheduledTask -TaskName $wdName -ErrorAction SilentlyContinue) {
    Write-Host "removing watchdog scheduled task..." -ForegroundColor DarkGray
    Unregister-ScheduledTask -TaskName $wdName -Confirm:$false
}

Push-Location $ProjectRoot
try {
    Ensure-Nssm
    & $NssmExe stop $ServiceName confirm | Out-Null
    & $NssmExe remove $ServiceName confirm | Out-Null
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "service '$ServiceName' removed" -ForegroundColor Green
Write-Host "the hosts file managed block has NOT been cleared automatically." -ForegroundColor Yellow
Write-Host "  -> if you want it cleared, run scripts\clear-hosts.ps1" -ForegroundColor Yellow
