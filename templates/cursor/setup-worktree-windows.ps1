#Requires -Version 5.1
# Copied by /adopt to .cursor/setup-worktree-windows.ps1.
# Cursor runs this when creating a worktree (Agents Window / /worktree).
$ErrorActionPreference = 'Stop'

$root = $env:ROOT_WORKTREE_PATH
if ($root -and (Test-Path (Join-Path $root '.env'))) {
    Copy-Item (Join-Path $root '.env') .env -Force
}

if (Test-Path package-lock.json) {
    npm ci
} elseif (Test-Path pnpm-lock.yaml) {
    pnpm install --frozen-lockfile
} elseif (Test-Path yarn.lock) {
    yarn install --frozen-lockfile
}

if (Get-ChildItem -Filter *.sln -File -ErrorAction SilentlyContinue) {
    dotnet restore
}
