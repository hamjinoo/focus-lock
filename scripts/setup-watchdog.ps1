# Register a Scheduled Task that ensures focus-lock service is running.
# Covers the "user manually ran Stop-Service" gap that NSSM's restart-on-exit
# does not catch.
. (Join-Path $PSScriptRoot "_common.ps1")

Assert-Admin

$wdName = "focus-lock-watchdog"

if (-not (Test-ServiceExists)) {
    throw "service '$ServiceName' is not installed yet. Run install-service.ps1 first."
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -Command `"if ((Get-Service '$ServiceName' -EA 0).Status -ne 'Running') { Start-Service '$ServiceName' }`""

$trigger1 = New-ScheduledTaskTrigger -AtStartup
$trigger2 = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 1)

$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew

if (Get-ScheduledTask -TaskName $wdName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $wdName -Confirm:$false
}

Register-ScheduledTask -TaskName $wdName -Action $action -Trigger @($trigger1, $trigger2) `
    -Principal $principal -Settings $settings `
    -Description "Restarts focus-lock service if it is not running." | Out-Null

Write-Host "watchdog scheduled task '$wdName' registered (1-min interval + at startup)" -ForegroundColor Green
