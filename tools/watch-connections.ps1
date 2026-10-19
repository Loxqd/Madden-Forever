# Prints every new network connection Madden20.exe opens (address + port), so we
# learn which ports the game really uses. Read-only; run while starting the game.
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\watch-connections.ps1
param([string]$ProcessName = 'Madden20', [int]$Seconds = 600)

$seen = @{}
$end = (Get-Date).AddSeconds($Seconds)
Write-Host "Watching $ProcessName.exe connections for $Seconds s (Ctrl+C to stop)..."
while ((Get-Date) -lt $end) {
    $procs = Get-Process -Name $ProcessName -ErrorAction SilentlyContinue
    foreach ($p in $procs) {
        $tcp = Get-NetTCPConnection -OwningProcess $p.Id -ErrorAction SilentlyContinue
        foreach ($c in $tcp) {
            $key = "TCP $($c.RemoteAddress):$($c.RemotePort)"
            if ($c.RemotePort -ne 0 -and -not $seen.ContainsKey($key)) {
                $seen[$key] = $true
                Write-Host ("{0:HH:mm:ss}  {1,-28} state={2}" -f (Get-Date), $key, $c.State)
            }
        }
        $udp = Get-NetUDPEndpoint -OwningProcess $p.Id -ErrorAction SilentlyContinue
        foreach ($u in $udp) {
            $key = "UDP local :$($u.LocalPort)"
            if (-not $seen.ContainsKey($key)) {
                $seen[$key] = $true
                Write-Host ("{0:HH:mm:ss}  {1,-28}" -f (Get-Date), $key)
            }
        }
    }
    Start-Sleep -Milliseconds 250
}
