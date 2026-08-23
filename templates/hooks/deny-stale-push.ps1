# beforeShellExecution: deny git push / az repos pr while .gate-stamp is stale.
# Cursor stdout: {"permission":"deny"|"allow", ...}. failClosed: true in hooks.json.
# Non-matching commands (the matcher should already filter) are allowed.

$ErrorActionPreference = 'SilentlyContinue'
$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent

function Write-Allow { '{"permission":"allow"}'; exit 0 }
function Write-Deny([string]$AgentMessage) {
    @{
        permission     = 'deny'
        user_message   = $AgentMessage
        agent_message  = $AgentMessage
    } | ConvertTo-Json -Compress
    exit 0
}

$payload = $null
try { $payload = [Console]::In.ReadToEnd() | ConvertFrom-Json } catch { Write-Allow }

$command = ''
if ($payload.command) { $command = [string]$payload.command }
elseif ($payload.tool_input -and $payload.tool_input.command) { $command = [string]$payload.tool_input.command }

if ($command -notmatch '(?i)git(\s+|.*\|.*\s)push' -and $command -notmatch '(?i)az\s+repos\s+pr') {
    Write-Allow
}

# Read-only PR inspection is fine.
if ($command -match '(?i)az\s+repos\s+pr\s+(list|show|status)') { Write-Allow }

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

$stampPath = Join-Path $repoRoot '.gate-stamp'
if (-not (Test-Path $stampPath)) {
    Write-Deny "Quality gate stamp missing (.gate-stamp). Run ./gate.ps1 until it is green before git push or az repos pr."
}

$stamp = (Get-Content $stampPath -TotalCount 1 2>$null)
$current = Get-WorkingTreeHash $repoRoot
if (-not $stamp -or -not $current -or ("$stamp".Trim() -ne $current)) {
    Write-Deny "Quality gate stamp is stale. Run ./gate.ps1 until it is green before git push or az repos pr."
}

Write-Allow
