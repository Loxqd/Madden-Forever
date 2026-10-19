# Stops the Madden Forever server started by start.ps1. Used by stop.bat.
$Root = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $Root 'run\server.pid'
$stopped = @()

if (Test-Path $PidFile) {
    $id = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($id -and (Get-Process -Id $id -ErrorAction SilentlyContinue)) {
        Stop-Process -Id $id -Force -Confirm:$false
        $stopped += $id
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

# Safety net: any python still running "-m server" from this folder.
$rootPattern = [regex]::Escape($Root)
Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='py.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match '-m server' -and $_.CommandLine -match $rootPattern } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -Confirm:$false -ErrorAction SilentlyContinue
        $stopped += $_.ProcessId
    }

if ($stopped.Count) { Write-Host "Server stopped (PID $($stopped -join ', '))." -ForegroundColor Green }
else { Write-Host 'Server was not running.' }
