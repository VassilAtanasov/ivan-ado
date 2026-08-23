#Requires -Version 5.1
<#
.SYNOPSIS
  Dev-install Ivan into Cursor as a local plugin (no GitHub marketplace).

.DESCRIPTION
  Copies this checkout to %USERPROFILE%\.cursor\plugins\local\ivan.
  After it finishes: Command Palette → "Developer: Reload Window", then open a new chat.
  Skills, agents, and the manifest do not hot-reload while a session is running.
#>
$ErrorActionPreference = 'Stop'

$src = Split-Path $PSScriptRoot -Parent
$dest = Join-Path $env:USERPROFILE '.cursor\plugins\local\ivan'

if (-not (Test-Path (Join-Path $src '.cursor-plugin\plugin.json'))) {
    throw "No .cursor-plugin/plugin.json next to scripts/. Run this from the ivan-ado checkout."
}

New-Item -ItemType Directory -Force -Path (Split-Path $dest -Parent) | Out-Null
if (Test-Path $dest) {
    Remove-Item -LiteralPath $dest -Recurse -Force
}

$exclude = @('.git', '.cursor\plans', 'node_modules', '__pycache__')
$roboArgs = @($src, $dest, '/E', '/NFL', '/NDL', '/NJH', '/NJS', '/nc', '/ns', '/np')
foreach ($e in $exclude) { $roboArgs += @('/XD', (Join-Path $src $e)) }
& robocopy @roboArgs | Out-Null
$rc = $LASTEXITCODE
# robocopy: 0-7 are success (bit flags); 8+ are failures
if ($rc -ge 8) { throw "robocopy failed with exit $rc" }

$manifest = Join-Path $dest '.cursor-plugin\plugin.json'
if (-not (Test-Path $manifest)) { throw "Copy did not produce $manifest" }

Write-Host "Ivan copied to $dest"
Write-Host "Next: Command Palette → Developer: Reload Window, then start a new chat."
Write-Host "You should see /adopt /discover /kickoff /implement /autopilot /retrospective"
Write-Host "and Task types code-reviewer / qa-verifier."
