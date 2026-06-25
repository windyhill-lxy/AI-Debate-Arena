param(
    [string]$FrontendUrl = "http://127.0.0.1:5173",
    [string]$BackendUrl = "",
    [int]$TimeoutSec = 180,
    [int]$IntervalSec = 2
)

function Test-ServiceReady {
    param([string]$Url)
    if (-not $Url) { return $true }
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 4 -Method GET
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500)
    }
    catch {
        return $false
    }
}

$deadline = (Get-Date).AddSeconds($TimeoutSec)
$opened = $false

while ((Get-Date) -lt $deadline) {
    $frontendReady = Test-ServiceReady -Url $FrontendUrl
    $backendReady = Test-ServiceReady -Url $BackendUrl
    if ($frontendReady -and $backendReady) {
        Start-Process $FrontendUrl
        $opened = $true
        exit 0
    }
    Start-Sleep -Seconds $IntervalSec
}

# 超时后仍尝试打开前端，避免用户完全无响应
if (-not $opened) {
    Start-Process $FrontendUrl
}
exit 1
