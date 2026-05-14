# Strip the focus-lock managed block from the system hosts file.
# Only safe to run when service is not installed (or stopped + no frozen).
. (Join-Path $PSScriptRoot "_common.ps1")

Assert-Admin

$frozen = Get-FrozenSessions
if ($frozen.Count -gt 0) {
    Write-Host "REFUSED: $($frozen.Count) frozen session(s) still active." -ForegroundColor Red
    exit 1
}

$hosts = "$env:SystemRoot\System32\drivers\etc\hosts"
$content = Get-Content $hosts -Raw -Encoding UTF8
$pattern = '(?s)\r?\n?# >>> focus-lock managed block >>>.*?# <<< focus-lock managed block <<<\r?\n?'
$stripped = [regex]::Replace($content, $pattern, "`n")
Set-Content -Path $hosts -Value $stripped -Encoding UTF8 -NoNewline
Write-Host "hosts file cleared" -ForegroundColor Green
