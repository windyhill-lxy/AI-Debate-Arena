param(
    [int[]]$Ports = @(9000, 5173),
    [switch]$IncludeElectron
)

function Stop-PortListeners {
    param([int]$Port)
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($conn in $conns) {
        $processId = $conn.OwningProcess
        if ($processId -and $processId -gt 0) {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
    }
}

foreach ($port in $Ports) {
    Stop-PortListeners -Port $port
}

if ($IncludeElectron) {
    Get-Process -Name "electron" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}

Write-Host "Released ports: $($Ports -join ', ')"
if ($IncludeElectron) {
    Write-Host "Stopped Electron processes (if any)"
}
