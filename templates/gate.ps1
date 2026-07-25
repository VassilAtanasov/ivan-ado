# gate.ps1 — the single quality gate for Mills.
# Run by: developers, Ivan (Claude Code), the Stop hook, and GitHub Actions CI.
# Auto-detects project state: passes trivially until application code exists.
# Server and client legs run in PARALLEL (background jobs) — total time is max(leg), not the sum.
# On success, writes .gate-stamp (a hash of the working tree) so the Stop hook can skip
# re-running the gate when nothing changed since the last green run.
# Compatible with Windows PowerShell 5.1 and PowerShell Core (pwsh, incl. Linux CI).

$ErrorActionPreference = 'Continue'
$repoRoot = $PSScriptRoot

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

# .slnx (the XML solution format) is what `dotnet new sln` produces on the .NET 10 SDK; .sln is the
# classic format. Match both, or a fresh .NET 10 repo looks like "no application code" forever.
# (-Include needs a wildcard path to match without -Recurse; .sln sorts before .slnx if both exist.)
$solution = Get-ChildItem -Path (Join-Path (Join-Path $repoRoot 'server') '*') -Include '*.sln', '*.slnx' -File -ErrorAction SilentlyContinue |
    Sort-Object Extension | Select-Object -First 1
$clientPkg = Test-Path (Join-Path (Join-Path $repoRoot 'client') 'package.json')

if (-not $solution -and -not $clientPkg) {
    Write-Host "GATE: no application code yet (no server/*.sln[x], no client/package.json) - gate passes trivially." -ForegroundColor Green
    exit 0
}

$legs = @()

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
    $serverDir = Join-Path $repoRoot 'server'
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

    $legs += @{ Name = 'server'; Steps = $serverSteps }
}

if ($clientPkg) {
    $clientDir = Join-Path $repoRoot 'client'
    $clientSteps = @()
    if (-not (Test-Path (Join-Path $clientDir 'node_modules'))) {
        $clientSteps += @{ Name = 'npm ci'; WorkDir = $clientDir; Command = 'npm ci' }
    }
    $clientSteps += @{ Name = 'npm run typecheck'; WorkDir = $clientDir; Command = 'npm run typecheck' }
    $clientSteps += @{ Name = 'npm run lint';      WorkDir = $clientDir; Command = 'npm run lint' }
    $clientSteps += @{ Name = 'npm test';          WorkDir = $clientDir; Command = 'npm test -- --run' }
    $legs += @{ Name = 'client'; Steps = $clientSteps }
}

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
