#Requires -Version 5.1
# Local proofs for the Cursor port. Does not talk to Azure Boards except whoami.
$ErrorActionPreference = 'Stop'
$plugin = Split-Path $PSScriptRoot -Parent
$failed = @()
$utf8 = New-Object System.Text.UTF8Encoding $false

function Assert-True([bool]$Cond, [string]$Name) {
    if ($Cond) { Write-Host "PASS  $Name" }
    else { Write-Host "FAIL  $Name"; $script:failed += $Name }
}

Write-Host '=== 1. Manifests ==='
$cursorPlugin = Join-Path $plugin '.cursor-plugin\plugin.json'
$cursorMarket = Join-Path $plugin '.cursor-plugin\marketplace.json'
$claudePlugin = Join-Path $plugin '.claude-plugin\plugin.json'
Assert-True (Test-Path $cursorPlugin) '.cursor-plugin/plugin.json exists'
Assert-True (Test-Path $cursorMarket) '.cursor-plugin/marketplace.json exists'
Assert-True (Test-Path $claudePlugin) '.claude-plugin/plugin.json exists'
$pv = (Get-Content $cursorPlugin -Raw | ConvertFrom-Json).version
$cv = (Get-Content $claudePlugin -Raw | ConvertFrom-Json).version
Assert-True ($pv -eq '2.2.0' -and $cv -eq '2.2.0') "plugin version 2.2.0 (cursor=$pv claude=$cv)"

$skills = @('adopt','discover','kickoff','implement','autopilot','retrospective')
foreach ($s in $skills) {
    Assert-True (Test-Path (Join-Path $plugin "skills\$s\SKILL.md")) "skill $s"
}
Assert-True (Test-Path (Join-Path $plugin 'agents\code-reviewer.md')) 'agent code-reviewer'
Assert-True (Test-Path (Join-Path $plugin 'agents\qa-verifier.md')) 'agent qa-verifier'
Assert-True (Test-Path (Join-Path $plugin 'rules\ivan.mdc')) 'rules/ivan.mdc'
Assert-True (Test-Path (Join-Path $plugin 'templates\AGENTS-ivan.md')) 'templates/AGENTS-ivan.md'
Assert-True (-not (Test-Path (Join-Path $plugin 'templates\CLAUDE-ivan.md'))) 'no leftover CLAUDE-ivan.md'
Assert-True (Test-Path (Join-Path $plugin 'templates\cursor\setup-worktree-windows.ps1')) 'windows worktree setup script'
Assert-True (-not (Test-Path (Join-Path $plugin 'hooks\hooks.json'))) 'no plugin-level gate hooks'

Write-Host ''
Write-Host '=== 2. Scratch adopt layout + hook proofs ==='
$scratch = Join-Path $env:TEMP ("ivan-adopt-proof-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $scratch | Out-Null
Push-Location $scratch
try {
    git init -q
    git config user.email 'ivan@test.local'
    git config user.name 'Ivan'
    Set-Content -Path (Join-Path $scratch 'gate.ps1') -Value 'Write-Error "deliberate fail"; exit 1'
    New-Item -ItemType Directory -Path (Join-Path $scratch '.claude\hooks') | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $scratch '.cursor') | Out-Null
    Copy-Item (Join-Path $plugin 'templates\hooks\format-changed.ps1') (Join-Path $scratch '.claude\hooks\format-changed.ps1')
    Copy-Item (Join-Path $plugin 'templates\hooks\stop-gate.ps1') (Join-Path $scratch '.claude\hooks\stop-gate.ps1')
    Copy-Item (Join-Path $plugin 'templates\hooks\deny-stale-push.ps1') (Join-Path $scratch '.claude\hooks\deny-stale-push.ps1')
    Copy-Item (Join-Path $plugin 'templates\cursor\hooks.json') (Join-Path $scratch '.cursor\hooks.json')
    Copy-Item (Join-Path $plugin 'templates\cursor\worktrees.json') (Join-Path $scratch '.cursor\worktrees.json')
    Copy-Item (Join-Path $plugin 'templates\cursor\setup-worktree-windows.ps1') (Join-Path $scratch '.cursor\setup-worktree-windows.ps1')
    Copy-Item (Join-Path $plugin 'templates\AGENTS-ivan.md') (Join-Path $scratch 'AGENTS.md')
    [System.IO.File]::WriteAllText((Join-Path $scratch 'CLAUDE.md'), '@AGENTS.md', $utf8)
    Set-Content -Path (Join-Path $scratch 'broken.cs') -Value 'class X { public void M() { var x = 1; } }'
    git add -A
    git commit -q -m 'scratch adopt'
    Set-Content -Path (Join-Path $scratch 'broken.cs') -Value 'class X { public void M() { var x = 2; } }'

    $stop = Join-Path $scratch '.claude\hooks\stop-gate.ps1'
    $deny = Join-Path $scratch '.claude\hooks\deny-stale-push.ps1'

    function Invoke-Hook([string]$Script, [string]$Json, [string]$StdErrPath) {
        $inPath = Join-Path $scratch 'hook-stdin.json'
        [System.IO.File]::WriteAllText($inPath, $Json, $utf8)
        $stdoutPath = Join-Path $scratch 'hook-stdout.txt'
        if (Test-Path $stdoutPath) { Remove-Item $stdoutPath -Force }
        if (Test-Path $StdErrPath) { Remove-Item $StdErrPath -Force }
        $p = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-File', $Script) -RedirectStandardInput $inPath -RedirectStandardOutput $stdoutPath -RedirectStandardError $StdErrPath -Wait -PassThru -NoNewWindow
        $out = ''
        if (Test-Path $stdoutPath) { $out = [System.IO.File]::ReadAllText($stdoutPath) }
        return @{ ExitCode = $p.ExitCode; StdOut = $out }
    }

    $claude = Invoke-Hook $stop '{"stop_hook_active": false}' (Join-Path $scratch 'claude.err')
    $claudeErr = ''
    if (Test-Path (Join-Path $scratch 'claude.err')) { $claudeErr = [System.IO.File]::ReadAllText((Join-Path $scratch 'claude.err')) }
    Assert-True ($claude.ExitCode -eq 2) "Claude stop-gate exit 2 (got $($claude.ExitCode))"
    Assert-True ($claudeErr -match 'Quality gate FAILED') 'Claude stop-gate stderr has gate tail'

    $cursor = Invoke-Hook $stop '{"loop_count": 0, "conversation_id": "adopt-probe", "status": "completed"}' (Join-Path $scratch 'cursor.err')
    Assert-True ($cursor.ExitCode -eq 0) "Cursor stop-gate exit 0 (got $($cursor.ExitCode))"
    Assert-True ($cursor.StdOut -match 'followup_message') 'Cursor stop-gate prints followup_message'

    $denyR = Invoke-Hook $deny '{"command":"git push origin HEAD"}' (Join-Path $scratch 'deny.err')
    Assert-True ($denyR.StdOut -match '"permission"\s*:\s*"deny"') 'deny-stale-push denies git push without stamp'

    $allowR = Invoke-Hook $deny '{"command":"az repos pr list"}' (Join-Path $scratch 'allow.err')
    Assert-True ($allowR.StdOut -match '"permission"\s*:\s*"allow"') 'deny-stale-push allows az repos pr list'

    Write-Host ''
    Write-Host '=== 3. Worktree isolation ==='
    git add broken.cs
    git commit -q -m 'dirty source'
    $wt = Join-Path $env:TEMP ("ivan-wt-" + [Guid]::NewGuid().ToString('N'))
    cmd /c "git worktree add -b feature/scratch-1 `"$wt`"" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "git worktree add failed with $LASTEXITCODE" }
    Set-Content -Path (Join-Path $wt 'only-in-worktree.txt') -Value 'isolated'
    Assert-True (Test-Path (Join-Path $wt 'only-in-worktree.txt')) 'file exists in worktree'
    Assert-True (-not (Test-Path (Join-Path $scratch 'only-in-worktree.txt'))) 'file absent from main checkout'
    cmd /c "git worktree remove --force `"$wt`"" | Out-Null
} finally {
    Pop-Location
    Remove-Item $scratch -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ''
Write-Host '=== 4. ado_cli.py whoami ==='
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
if ($python) {
    Push-Location $plugin
    try {
        & $python.Source (Join-Path $plugin 'scripts\ado_cli.py') whoami
        Assert-True ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq 1) "ado_cli.py whoami ran (exit $LASTEXITCODE)"
    } catch {
        Write-Host "WARN  ado_cli.py whoami: $_"
    } finally { Pop-Location }
} else {
    Write-Host 'WARN  python not on PATH; skipped whoami'
}

Write-Host ''
Write-Host '=== 5. Local Cursor copy-install ==='
& powershell.exe -NoProfile -File (Join-Path $plugin 'scripts\install-cursor.ps1')
Assert-True ($LASTEXITCODE -eq 0) 'install-cursor.ps1 exit 0'
$dest = Join-Path $env:USERPROFILE '.cursor\plugins\local\ivan'
Assert-True (Test-Path (Join-Path $dest '.cursor-plugin\plugin.json')) 'copied plugin.json'
Assert-True (Test-Path (Join-Path $dest 'skills\adopt\SKILL.md')) 'copied /adopt'
Assert-True (Test-Path (Join-Path $dest 'agents\code-reviewer.md')) 'copied code-reviewer'
Assert-True (Test-Path (Join-Path $dest 'agents\qa-verifier.md')) 'copied qa-verifier'

Write-Host ''
if ($failed.Count -eq 0) {
    Write-Host 'ALL CHECKS PASSED'
    exit 0
} else {
    Write-Host ("FAILED: " + ($failed -join '; '))
    exit 1
}
