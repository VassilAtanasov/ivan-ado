# PostToolUse hook (Edit|Write): auto-format the file that was just changed.
# Reads the hook payload from stdin; always exits 0 (formatting must never block work).

$ErrorActionPreference = 'SilentlyContinue'
try {
    $payload = [Console]::In.ReadToEnd() | ConvertFrom-Json
    $file = $payload.tool_input.file_path
    if (-not $file -or -not (Test-Path $file)) { exit 0 }

    $repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
    $ext = [System.IO.Path]::GetExtension($file).ToLowerInvariant()

    switch ($ext) {
        '.cs' {
            # -Include needs the trailing \* to match without -Recurse. .slnx is the .NET 10 format.
            $sln = Get-ChildItem -Path (Join-Path (Join-Path $repoRoot 'server') '*') -Include '*.sln', '*.slnx' -File |
                Sort-Object Extension | Select-Object -First 1
            if ($sln) { dotnet format $sln.FullName --include $file --verbosity quiet | Out-Null }
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
