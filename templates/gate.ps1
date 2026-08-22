# gate.ps1 — the single quality gate for this repository.
# Run by: developers, Ivan (Claude Code), the Stop hook, and the Azure Pipelines build.
# Auto-detects project state: passes trivially until application code exists.
# Legs (.NET / Node / Python) run in PARALLEL (background jobs) — total time is max(leg), not the sum.
# Every leg ends with a SUPPLY-CHAIN step: an unattended agent adds dependencies, so a known
# vulnerable package has to fail the gate rather than wait for a human to notice it.
# On success, writes .gate-stamp (a hash of the working tree) so the Stop hook can skip
# re-running the gate when nothing changed since the last green run.
# Compatible with Windows PowerShell 5.1 and PowerShell Core (pwsh, incl. Linux CI).
#
# /adopt writes this file to match the project's stack profile: delete the legs the project does
# not have, and correct the detection roots below to the real layout rather than leaving them to
# guess. The profile is recorded in CLAUDE.md's `## Ivan project config`.
#
# Environment:
#   GATE_COVERAGE_MIN=<n>       minimum line coverage % for the .NET leg (default 0 = report only)
#   GATE_SKIP_SUPPLY_CHAIN=1    skip the advisory checks (they need network — offline work only,
#                               never in CI, and never as a way to turn a red gate green)

$ErrorActionPreference = 'Continue'
$repoRoot = $PSScriptRoot
$skipSupplyChain = [bool]$env:GATE_SKIP_SUPPLY_CHAIN

# Hash the exact working-tree content (tracked + untracked, staged + unstaged) without touching
# the real index. Returns '' if git is unavailable. Must match the copy in stop-gate.ps1.
function Get-WorkingTreeHash {
    param([string]$Root)
    $tmpIndex = Join-Path ([IO.Path]::GetTempPath()) ("gate-index-" + [Guid]::NewGuid().ToString('N'))
    $prev = $env:GIT_INDEX_FILE
    try {
        $env:GIT_INDEX_FILE = $tmpIndex
        git -C $Root read-tree HEAD 2>$null
        git -C $Root add -A 2>$null
        $tree = git -C $Root write-tree 2>$null
        if ($tree) { return "$tree".Trim() } else { return '' }
    } catch {
        return ''
    } finally {
        $env:GIT_INDEX_FILE = $prev   # $null assignment removes the variable
        Remove-Item $tmpIndex -Force -ErrorAction SilentlyContinue
    }
}

# First existing candidate path, or $null. Keeps layout detection in one place.
function Find-FirstPath {
    param([string[]]$Candidates)
    foreach ($c in $Candidates) { if (Test-Path $c) { return (Resolve-Path $c).Path } }
    return $null
}

# Runs one leg's steps sequentially; executed inline (single leg) or inside a Start-Job (parallel).
$legRunner = {
    param($LegName, $Steps)
    $failures = @()
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($step in $Steps) {
        $lines.Add("")
        $lines.Add("=== $($step.Name) ===")
        Push-Location $step.WorkDir
        try {
            try {
                $out = @(Invoke-Expression $step.Command 2>&1 | ForEach-Object { "$_" })
                $exit = $LASTEXITCODE
            } catch {
                $out = @("$_")
                $exit = 1
            }
            foreach ($line in $out) { $lines.Add($line) }
            if ($exit -ne 0) {
                $failures += $step.Name
                $lines.Add("--- FAILED: $($step.Name) (exit $exit)")
            } else {
                $lines.Add("--- OK: $($step.Name)")
            }
        } finally {
            Pop-Location
        }
    }
    [PSCustomObject]@{ Leg = $LegName; Failures = $failures; Transcript = ($lines -join "`n") }
}

# ---- Detection ------------------------------------------------------------------------------
# .slnx (the XML solution format) is what `dotnet new sln` produces on the .NET 10 SDK; .sln is the
# classic format. Match both, or a fresh .NET 10 repo looks like "no application code" forever.
# (-Include needs a wildcard path to match without -Recurse; .sln sorts before .slnx if both exist.)
$solution = $null
foreach ($sub in @('server', 'src', '.')) {
    $solution = Get-ChildItem -Path (Join-Path (Join-Path $repoRoot $sub) '*') -Include '*.sln', '*.slnx' -File -ErrorAction SilentlyContinue |
        Sort-Object Extension | Select-Object -First 1
    if ($solution) { break }
}

$clientPkg = Find-FirstPath @(
    (Join-Path $repoRoot 'client\package.json'),
    (Join-Path $repoRoot 'web\package.json'),
    (Join-Path $repoRoot 'frontend\package.json'),
    (Join-Path $repoRoot 'package.json')
)

$pyProject = Find-FirstPath @(
    (Join-Path $repoRoot 'pyproject.toml'),
    (Join-Path $repoRoot 'server\pyproject.toml'),
    (Join-Path $repoRoot 'api\pyproject.toml'),
    (Join-Path $repoRoot 'src\pyproject.toml')
)

if (-not $solution -and -not $clientPkg -and -not $pyProject) {
    Write-Host "GATE: no application code yet (no solution, package.json or pyproject.toml) - gate passes trivially." -ForegroundColor Green
    exit 0
}

$legs = @()

# ---- .NET leg -------------------------------------------------------------------------------
if ($solution) {
    $sln = $solution.FullName
    $serverSteps = @(
        # Formatting drift fails here rather than depending on the PostToolUse hook having fired.
        # Style/analyzer rules themselves are enforced by the build: .editorconfig severities are
        # promoted to build diagnostics by EnforceCodeStyleInBuild in Directory.Build.props.
        @{ Name = 'dotnet format (verify)'; WorkDir = $repoRoot; Command = "dotnet format `"$sln`" --verify-no-changes --verbosity minimal" },
        @{ Name = 'dotnet build (warnings as errors)'; WorkDir = $repoRoot; Command = "dotnet build `"$sln`" -warnaserror --nologo" }
    )

    # Coverage runs only when the test projects actually reference coverlet.collector, so this
    # degrades to a plain `dotnet test` in projects that have not opted in.
    $serverDir = Split-Path $sln -Parent
    $hasCoverlet = $false
    $projFiles = @(Get-ChildItem -Path $serverDir -Filter '*.csproj' -Recurse -ErrorAction SilentlyContinue)
    if ($projFiles.Count -gt 0) {
        $hasCoverlet = [bool](Select-String -Path $projFiles.FullName -Pattern 'coverlet\.collector' -SimpleMatch:$false -Quiet -ErrorAction SilentlyContinue)
    }

    # Minimum line coverage percentage. 0 = report only. Raise it via the environment (CI or shell)
    # once the suite is established; the gate then fails when coverage drops below it.
    $coverageMin = 0
    if ($env:GATE_COVERAGE_MIN) { $coverageMin = [double]$env:GATE_COVERAGE_MIN }

    if ($hasCoverlet) {
        $coverageDir = Join-Path $repoRoot '.coverage'
        # Note: the leg runner discards a step's collected output if the step throws, so the test
        # transcript is carried in the exception message rather than written to the pipeline.
        $coverageCmd = @'
Remove-Item -Recurse -Force "__DIR__" -ErrorAction SilentlyContinue
$testOut = @(dotnet test "__SLN__" --nologo --no-build --results-directory "__DIR__" --collect "XPlat Code Coverage" 2>&1 | ForEach-Object { "$_" })
$testExit = $LASTEXITCODE
function Fail([string]$Reason) { throw (($testOut + $Reason) -join "`n") }
if ($testExit -ne 0) { Fail "dotnet test failed (exit $testExit)" }
$reports = @(Get-ChildItem -Path "__DIR__" -Recurse -Filter 'coverage.cobertura.xml' -ErrorAction SilentlyContinue)
if ($reports.Count -eq 0) { Fail "coverage: no cobertura report was produced" }
$covered = 0; $total = 0
foreach ($r in $reports) {
    $xml = [xml](Get-Content $r.FullName -Raw)
    $covered += [int]$xml.coverage.GetAttribute('lines-covered')
    $total   += [int]$xml.coverage.GetAttribute('lines-valid')
}
$pct = if ($total -gt 0) { [math]::Round(100.0 * $covered / $total, 2) } else { 0 }
$summary = "coverage: $pct% ($covered/$total lines, minimum __MIN__%)"
if ($pct -lt __MIN__) { Fail $summary }
$testOut + $summary
'@
        $coverageCmd = $coverageCmd.Replace('__DIR__', $coverageDir).Replace('__SLN__', $sln).Replace('__MIN__', "$coverageMin")
        $serverSteps += @{ Name = "dotnet test (coverage, min ${coverageMin}%)"; WorkDir = $repoRoot; Command = $coverageCmd }
    } else {
        $serverSteps += @{ Name = 'dotnet test'; WorkDir = $repoRoot; Command = "dotnet test `"$sln`" --nologo --no-build" }
    }

    if (-not $skipSupplyChain) {
        # `dotnet list package --vulnerable` exits 0 even when it finds advisories, so its output
        # has to be parsed. Transitive included — a vulnerable dependency of a dependency still
        # ships. Moderate/Low are printed but do not fail the gate.
        $nugetAuditCmd = @'
$out = @(dotnet list "__SLN__" package --vulnerable --include-transitive 2>&1 | ForEach-Object { "$_" })
$hits = @($out | Where-Object { $_ -match '^\s*>\s' -and $_ -match '\b(High|Critical)\b' })
if ($hits.Count -gt 0) { throw (($out + "supply chain: $($hits.Count) High/Critical advisory line(s) - upgrade the package, or pin a patched version and say why in the PR description") -join "`n") }
$out + "supply chain: no High/Critical NuGet advisories"
'@
        $nugetAuditCmd = $nugetAuditCmd.Replace('__SLN__', $sln)
        $serverSteps += @{ Name = 'supply chain (NuGet advisories)'; WorkDir = $repoRoot; Command = $nugetAuditCmd }
    }

    $legs += @{ Name = 'server'; Steps = $serverSteps }
}

# ---- Node leg -------------------------------------------------------------------------------
if ($clientPkg) {
    $clientDir = Split-Path $clientPkg -Parent
    $clientSteps = @()
    if (-not (Test-Path (Join-Path $clientDir 'node_modules'))) {
        $clientSteps += @{ Name = 'npm ci'; WorkDir = $clientDir; Command = 'npm ci' }
    }
    $clientSteps += @{ Name = 'npm run typecheck'; WorkDir = $clientDir; Command = 'npm run typecheck' }
    $clientSteps += @{ Name = 'npm run lint';      WorkDir = $clientDir; Command = 'npm run lint' }
    $clientSteps += @{ Name = 'npm test';          WorkDir = $clientDir; Command = 'npm test -- --run' }
    if (-not $skipSupplyChain) {
        # `npm audit` exits non-zero when it finds an advisory at or above the level — exactly the
        # semantics the leg runner wants. It needs a lockfile, and a missing one is a real defect
        # (unpinned dependencies, unreproducible builds), not a reason to skip the check.
        $npmAuditCmd = @'
if (-not (Test-Path 'package-lock.json')) { throw "supply chain: no package-lock.json - dependencies are unpinned and cannot be audited. Commit the lockfile." }
npm audit --audit-level=high
'@
        $clientSteps += @{ Name = 'supply chain (npm audit, high+)'; WorkDir = $clientDir; Command = $npmAuditCmd }
    }
    $legs += @{ Name = 'client'; Steps = $clientSteps }
}

# ---- Python leg -----------------------------------------------------------------------------
if ($pyProject) {
    $pyDir = Split-Path $pyProject -Parent
    $pyConfig = Get-Content $pyProject -Raw -ErrorAction SilentlyContinue
    $typeCheck = if ($pyConfig -match '\[tool\.pyright\]') { 'pyright' } else { 'mypy .' }
    $pySteps = @(
        @{ Name = 'ruff format (verify)';    WorkDir = $pyDir; Command = 'ruff format --check .' },
        @{ Name = 'ruff check';              WorkDir = $pyDir; Command = 'ruff check .' },
        @{ Name = "type check ($typeCheck)"; WorkDir = $pyDir; Command = $typeCheck },
        @{ Name = 'pytest';                  WorkDir = $pyDir; Command = 'pytest -q' }
    )
    if (-not $skipSupplyChain) {
        # pip-audit resolves the installed environment against the PyPI/OSV advisory database and
        # exits non-zero on any finding. A missing tool fails the gate: /adopt adds it to the dev
        # dependencies, so its absence means this is not the environment the project committed to.
        $pipAuditCmd = @'
if (-not (Get-Command pip-audit -ErrorAction SilentlyContinue)) { throw "supply chain: pip-audit is not installed - it belongs to this project's dev dependencies (pip install pip-audit)." }
pip-audit --strict
'@
        $pySteps += @{ Name = 'supply chain (pip-audit)'; WorkDir = $pyDir; Command = $pipAuditCmd }
    }
    $legs += @{ Name = 'python'; Steps = $pySteps }
}

# ---- Run ------------------------------------------------------------------------------------
if ($legs.Count -eq 1) {
    $results = @(& $legRunner $legs[0].Name $legs[0].Steps)
} else {
    $jobs = foreach ($leg in $legs) {
        Start-Job -ScriptBlock $legRunner -ArgumentList $leg.Name, $leg.Steps
    }
    $results = @($jobs | Wait-Job | Receive-Job)
    $jobs | Remove-Job -Force
}

$failures = @()
foreach ($result in $results) {
    Write-Host ""
    Write-Host "===== LEG: $($result.Leg) =====" -ForegroundColor Cyan
    Write-Host $result.Transcript
    $failures += @($result.Failures)
}

Write-Host ""
if ($skipSupplyChain) {
    Write-Host "GATE: supply-chain checks SKIPPED (GATE_SKIP_SUPPLY_CHAIN set) - not a valid state for CI or a PR." -ForegroundColor Yellow
}
if ($failures.Count -gt 0) {
    Write-Host "GATE FAILED - $($failures.Count) step(s):" -ForegroundColor Red
    $failures | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}

$treeHash = Get-WorkingTreeHash $repoRoot
if ($treeHash) {
    Set-Content -Path (Join-Path $repoRoot '.gate-stamp') -Value $treeHash -Encoding Ascii
}
Write-Host "GATE PASSED - all steps green." -ForegroundColor Green
exit 0
