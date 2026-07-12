# Stop hook: Ivan may not end a working turn while the quality gate fails.
# - Skips when this stop was already triggered by a previous Stop-hook block (stop_hook_active),
#   letting Ivan report an unfixable failure instead of looping forever.
# - Skips chat-only turns (no changes under server/ or client/).
# - Exit 2 + stderr feeds the gate failure back to Ivan, forcing him to keep fixing.

$ErrorActionPreference = 'SilentlyContinue'
$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent

try {
    $payload = [Console]::In.ReadToEnd() | ConvertFrom-Json
    if ($payload.stop_hook_active) { exit 0 }
} catch { }

$changes = git -C $repoRoot status --porcelain 2>$null
$sourceChanged = $changes | Where-Object { $_ -match '^\s*\S+\s+"?(server|client)/' }
if (-not $sourceChanged) { exit 0 }

$gateOutput = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repoRoot 'gate.ps1') 2>&1
if ($LASTEXITCODE -ne 0) {
    $tail = ($gateOutput | Select-Object -Last 40) -join "`n"
    [Console]::Error.WriteLine("Quality gate FAILED - you cannot finish this turn until gate.ps1 passes. Fix the failures below, re-run ./gate.ps1, and only stop when it is green.`n$tail")
    exit 2
}
exit 0
