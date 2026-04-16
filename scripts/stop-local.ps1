$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$runDir = Join-Path $root ".run"
$pidFile = Join-Path $runDir "bot.pid"

if (-not (Test-Path $pidFile)) {
    Write-Host "PID file not found – nothing to stop"
    exit 0
}

$pidText = Get-Content $pidFile -Raw
$targetPid = 0
if (-not [int]::TryParse($pidText.Trim(), [ref]$targetPid)) {
    Write-Host "PID file is invalid"
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    exit 0
}

$proc = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
if ($null -eq $proc) {
    Write-Host "Process already stopped ($targetPid)"
} else {
    Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue
    Write-Host "BreakoutBolt stopped ($targetPid)"
}

Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
