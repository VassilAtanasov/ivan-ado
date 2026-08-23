# Stop hook: Ivan may not end a working turn while the quality gate fails.
#
# Dual payload:
#   Claude Code — skip when stop_hook_active; on failure write the gate tail to stderr and exit 2.
#   Cursor      — skip when loop_count is already looping on a non-source change; on failure write
#                 {"followup_message": "..."} to stdout and exit 0 (Cursor re-prompts from that).
#
# Shared skip rules:
#   - turns that changed nothing but prose (docs, markdown, .claude/, .cursor/)
#   - .gate-stamp matches the current working tree (gate.ps1 already ran green on this exact code)

$ErrorActionPreference = 'SilentlyContinue'
$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent

$raw = ''
$payload = $null
try {
    $raw = [Console]::In.ReadToEnd()
    if ($raw) { $payload = $raw | ConvertFrom-Json }
} catch { }

$isClaude = $false
$isCursor = $false
if ($payload) {
    $names = @($payload.PSObject.Properties.Name)
    if ($names -contains 'stop_hook_active') { $isClaude = $true }
    if ($names -contains 'loop_count' -or $names -contains 'conversation_id') { $isCursor = $true }
    if ($payload.stop_hook_active) { exit 0 }
}

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
        $env:GIT_INDEX_FILE = $prev
        Remove-Item $tmpIndex -Force -ErrorAction SilentlyContinue
    }
}

function Test-SourceChanged {
    param([string]$Root)
    $changes = @(git -C $Root status --porcelain 2>$null)
    $sourceChanged = $changes | Where-Object {
        $path = ($_ -replace '^..\s+', '')
        $path = ($path -split ' -> ')[-1]
        $path = $path -replace '^"|"$', ''
        $path -notmatch '(?i)^(docs/|\.claude/|\.cursor/)' -and $path -notmatch '(?i)\.md$'
    }
    return [bool]$sourceChanged
}

$sourceChanged = Test-SourceChanged $repoRoot
if (-not $sourceChanged) { exit 0 }

if ($isCursor -and -not $sourceChanged) { exit 0 }

$stampPath = Join-Path $repoRoot '.gate-stamp'
if (Test-Path $stampPath) {
    $stamp = (Get-Content $stampPath -TotalCount 1 2>$null)
    $current = Get-WorkingTreeHash $repoRoot
    if ($stamp -and $current -and ("$stamp".Trim() -eq $current)) { exit 0 }
}

$gateScript = Join-Path $repoRoot 'gate.ps1'
$gateOutput = & $gateScript 2>&1
if ($LASTEXITCODE -eq 0) { exit 0 }

$tail = ($gateOutput | Select-Object -Last 40) -join "`n"
$message = "Quality gate FAILED - you cannot finish this turn until gate.ps1 passes. Fix the failures below, re-run ./gate.ps1, and only stop when it is green.`n$tail"

if ($isCursor -or -not $isClaude) {
    @{ followup_message = $message } | ConvertTo-Json -Compress
    if ($isCursor -and -not $isClaude) { exit 0 }
}
if ($isClaude -or -not $isCursor) {
    [Console]::Error.WriteLine($message)
    exit 2
}
exit 0
