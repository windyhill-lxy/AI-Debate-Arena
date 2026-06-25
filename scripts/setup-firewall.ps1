# 为 AI辩论场 配置 Windows 防火墙入站规则（需管理员权限）
param(
    [switch]$Remove
)

$ErrorActionPreference = "Stop"

function Test-Admin {
    $current = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    return $current.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    Write-Host "[错误] 请以管理员身份运行此脚本（右键「以管理员身份运行」）。" -ForegroundColor Red
    exit 1
}

$rules = @(
    @{ Name = "AI辩论场-页面5173"; Port = 5173; Desc = "AI辩论场联机页面端口" },
    @{ Name = "AI辩论场-API9000"; Port = 9000; Desc = "AI辩论场后端 API 端口" }
)

$root = Split-Path -Parent $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }
$cloudflared = Join-Path $root "tools\cloudflared.exe"

if ($Remove) {
    foreach ($rule in $rules) {
        netsh advfirewall firewall delete rule name="$($rule.Name)" | Out-Null
        Write-Host "已删除规则: $($rule.Name)" -ForegroundColor Yellow
    }
    netsh advfirewall firewall delete rule name="AI辩论场-cloudflared" | Out-Null
    Write-Host "完成。" -ForegroundColor Green
    exit 0
}

foreach ($rule in $rules) {
    netsh advfirewall firewall delete rule name="$($rule.Name)" 2>$null | Out-Null
    netsh advfirewall firewall add rule `
        name="$($rule.Name)" `
        dir=in action=allow protocol=TCP localport=$($rule.Port) `
        profile=private,domain `
        description="$($rule.Desc)" | Out-Null
    Write-Host "[OK] 已放行 TCP $($rule.Port) ($($rule.Name))" -ForegroundColor Green
}

if (Test-Path $cloudflared) {
    netsh advfirewall firewall delete rule name="AI辩论场-cloudflared" 2>$null | Out-Null
    netsh advfirewall firewall add rule `
        name="AI辩论场-cloudflared" `
        dir=out action=allow program="$cloudflared" `
        profile=private,domain,public `
        description="允许 cloudflared 出站连接 Cloudflare" | Out-Null
    Write-Host "[OK] 已允许 cloudflared 出站: $cloudflared" -ForegroundColor Green
} else {
    Write-Host "[提示] 未找到 cloudflared.exe，首次开启公网隧道时会自动下载。" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "防火墙配置完成。专用/域网络下同学可访问本机 5173 端口。" -ForegroundColor Cyan
Write-Host "若需公网穿透，还需配置 HTTP 代理或 VPN 以访问 Cloudflare。" -ForegroundColor Cyan
