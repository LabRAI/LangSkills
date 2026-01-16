param()

$ErrorActionPreference = "Stop"

Write-Host "Running self-check..." -ForegroundColor Cyan
node scripts/self-check.js @args
