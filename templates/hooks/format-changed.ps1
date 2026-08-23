# PostToolUse / afterFileEdit: auto-format the file that was just changed.
# Dual payload: Claude `tool_input.file_path` or Cursor `file_path` / `path`.
# Always exits 0 (formatting must never block work).
# /adopt extends the switch below with one arm per language in the project's stack profile.

$ErrorActionPreference = 'SilentlyContinue'
try {
    $payload = [Console]::In.ReadToEnd() | ConvertFrom-Json
    $file = $null
    if ($payload.tool_input -and $payload.tool_input.file_path) {
        $file = $payload.tool_input.file_path
    }
    if (-not $file -and $payload.file_path) { $file = $payload.file_path }
    if (-not $file -and $payload.path) { $file = $payload.path }
    if (-not $file -or -not (Test-Path $file)) { exit 0 }

    $repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
    $ext = [System.IO.Path]::GetExtension($file).ToLowerInvariant()

    switch ($ext) {
        '.cs' {
            $sln = Get-ChildItem -Path (Join-Path (Join-Path $repoRoot 'server') '*') -Include '*.sln', '*.slnx' -File |
                Sort-Object Extension | Select-Object -First 1
            if ($sln) { dotnet format $sln.FullName --include $file --verbosity quiet | Out-Null }
        }
        '.py' {
            if (Get-Command ruff -ErrorAction SilentlyContinue) { ruff format $file | Out-Null }
        }
        { $_ -in '.ts', '.tsx', '.css', '.json' } {
            $clientDir = Join-Path $repoRoot 'client'
            if ((Test-Path (Join-Path $clientDir 'node_modules\.bin\prettier.cmd')) -or
                (Test-Path (Join-Path $clientDir 'node_modules\.bin\prettier'))) {
                Push-Location $clientDir
                npx --no-install prettier --write $file | Out-Null
                Pop-Location
            }
        }
    }
} catch { }
exit 0
