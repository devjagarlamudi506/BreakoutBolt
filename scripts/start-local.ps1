$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Error ".venv not found. Create it first with: py -3.11 -m venv .venv"
}

$envFile = Join-Path $root ".env"
$envExample = Join-Path $root ".env.example"
if (-not (Test-Path $envFile) -and (Test-Path $envExample)) {
    Copy-Item $envExample $envFile
    Write-Host "Created .env from .env.example"
}

$runDir = Join-Path $root ".run"
if (-not (Test-Path $runDir)) {
    New-Item -Path $runDir -ItemType Directory | Out-Null
}

$outLog = Join-Path $runDir "bot.out.log"
$errLog = Join-Path $runDir "bot.err.log"

$proc = Start-Process -FilePath $venvPython -ArgumentList "main.py" -WorkingDirectory $root -PassThru -RedirectStandardOutput $outLog -RedirectStandardError $errLog

Set-Content -Path (Join-Path $runDir "bot.pid") -Value $proc.Id

# Brief pause to confirm process did not crash immediately
Start-Sleep -Seconds 2
$running = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
if ($null -eq $running -or $running.HasExited) {
    Write-Host "BreakoutBolt failed to start. Last error lines:"
    if (Test-Path $errLog) {
        Get-Content $errLog -Tail 30
    }
    exit 1
}

Write-Host "BreakoutBolt started (single process)"
Write-Host "PID: $($proc.Id)"
Write-Host "Logs: .run/bot.out.log and .run/bot.err.log"
Write-Host "To stop: Stop-Process -Id $($proc.Id)"
