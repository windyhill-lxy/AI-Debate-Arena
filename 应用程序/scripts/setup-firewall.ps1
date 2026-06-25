# Delegate to project-root firewall script (when run from 应用程序 folder)
$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$rootScript = Join-Path $projectRoot "scripts\setup-firewall.ps1"
if (-not (Test-Path $rootScript)) {
    Write-Host "[ERROR] Not found: $rootScript" -ForegroundColor Red
    exit 1
}
& $rootScript @args
