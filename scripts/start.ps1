# Starts the Madden Forever server in the background. Used by start.bat.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$RunDir = Join-Path $Root 'run'
$LogDir = Join-Path $Root 'logs'
$PidFile = Join-Path $RunDir 'server.pid'
$Config = Join-Path $Root 'config\server.json'
New-Item -ItemType Directory -Force $RunDir, $LogDir | Out-Null

if (Test-Path $PidFile) {
    $old = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($old -and (Get-Process -Id $old -ErrorAction SilentlyContinue)) {
        Write-Host "Server is already running (PID $old). Use stop.bat first." -ForegroundColor Yellow
        exit 0
    }
    Remove-Item $PidFile -Force
}

if (-not (Test-Path $Config)) {
    Copy-Item (Join-Path $Root 'config\server.example.json') $Config
    Write-Host "Created config\server.json from the example."
}
$cfg = Get-Content $Config -Raw | ConvertFrom-Json

# Find a real Python 3 (skip the Microsoft Store "python" alias).
$python = $null
$pyArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) { $python = (Get-Command py).Source; $pyArgs = @('-3') }
else {
    foreach ($c in Get-Command python -All -ErrorAction SilentlyContinue) {
        if ($c.Source -notlike '*WindowsApps*') { $python = $c.Source; break }
    }
}
if (-not $python) {
    Write-Host 'Python 3 was not found. Install it from https://www.python.org/downloads/ and try again.' -ForegroundColor Red
    exit 1
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$outLog = Join-Path $LogDir "server-$stamp.log"
$errLog = Join-Path $LogDir "server-$stamp.err.log"
$proc = Start-Process -FilePath $python -ArgumentList ($pyArgs + @('-u', '-m', 'server', '--config', "`"$Config`"")) `
    -WorkingDirectory $Root -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $outLog -RedirectStandardError $errLog
# py.exe launches python.exe as a child; record the real server PID if we can see it.
Start-Sleep -Milliseconds 700
$child = Get-CimInstance Win32_Process -Filter "ParentProcessId=$($proc.Id) AND Name='python.exe'" -ErrorAction SilentlyContinue | Select-Object -First 1
$serverPid = if ($child) { $child.ProcessId } else { $proc.Id }
Set-Content -Path $PidFile -Value $serverPid -Encoding ascii

# Wait for both ports to accept connections.
$ports = @($cfg.redirector.port, $cfg.blaze.port)
$deadline = (Get-Date).AddSeconds(10)
$up = $false
while ((Get-Date) -lt $deadline) {
    if ($proc.HasExited -and -not (Get-Process -Id $serverPid -ErrorAction SilentlyContinue)) { break }
    $open = $ports | Where-Object {
        $t = New-Object Net.Sockets.TcpClient
        try { $t.Connect($cfg.bind, $_); $true } catch { $false } finally { $t.Close() }
    }
    if (@($open).Count -eq $ports.Count) { $up = $true; break }
    Start-Sleep -Milliseconds 300
}

if ($up) {
    Write-Host "Madden Forever server is running (PID $serverPid)." -ForegroundColor Green
    Write-Host "  Redirector : $($cfg.bind):$($cfg.redirector.port)"
    Write-Host "  Blaze      : $($cfg.bind):$($cfg.blaze.port)"
    Write-Host "  Log        : $outLog"
    exit 0
}
Write-Host 'Server did not start. Last lines of the error log:' -ForegroundColor Red
Get-Content $errLog -Tail 20 -ErrorAction SilentlyContinue
Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
exit 1
