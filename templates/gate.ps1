# gate.ps1 — the single quality gate for Mills.
# Run by: developers, Ivan (Claude Code), the Stop hook, and GitHub Actions CI.
# Auto-detects project state: passes trivially until application code exists.
# Compatible with Windows PowerShell 5.1 and PowerShell Core (pwsh, incl. Linux CI).

$ErrorActionPreference = 'Continue'
$repoRoot = $PSScriptRoot
$failures = @()

function Invoke-Step {
    param([string]$Name, [string]$WorkDir, [scriptblock]$Action)
    Write-Host ""
    Write-Host "=== $Name ===" -ForegroundColor Cyan
    Push-Location $WorkDir
    try {
        & $Action
        if ($LASTEXITCODE -ne 0) {
            $script:failures += $Name
            Write-Host "--- FAILED: $Name (exit $LASTEXITCODE)" -ForegroundColor Red
        } else {
            Write-Host "--- OK: $Name" -ForegroundColor Green
        }
    } finally {
        Pop-Location
    }
}

$solution = Get-ChildItem -Path (Join-Path $repoRoot 'server') -Filter '*.sln' -ErrorAction SilentlyContinue | Select-Object -First 1
$clientPkg = Test-Path (Join-Path $repoRoot 'client\package.json')

if (-not $solution -and -not $clientPkg) {
    Write-Host "GATE: no application code yet (no server/*.sln, no client/package.json) - gate passes trivially." -ForegroundColor Green
    exit 0
}

if ($solution) {
    Invoke-Step -Name 'dotnet build (warnings as errors)' -WorkDir $repoRoot -Action {
        dotnet build $solution.FullName -warnaserror --nologo
    }.GetNewClosure()
    Invoke-Step -Name 'dotnet test' -WorkDir $repoRoot -Action {
        dotnet test $solution.FullName --nologo --no-build
    }.GetNewClosure()
}

if ($clientPkg) {
    $clientDir = Join-Path $repoRoot 'client'
    if (-not (Test-Path (Join-Path $clientDir 'node_modules'))) {
        Invoke-Step -Name 'npm ci' -WorkDir $clientDir -Action { npm ci }
    }
    Invoke-Step -Name 'npm run typecheck' -WorkDir $clientDir -Action { npm run typecheck }
    Invoke-Step -Name 'npm run lint'      -WorkDir $clientDir -Action { npm run lint }
    Invoke-Step -Name 'npm test'          -WorkDir $clientDir -Action { npm test -- --run }
}

Write-Host ""
if ($failures.Count -gt 0) {
    Write-Host "GATE FAILED - $($failures.Count) step(s):" -ForegroundColor Red
    $failures | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}
Write-Host "GATE PASSED - all steps green." -ForegroundColor Green
exit 0
