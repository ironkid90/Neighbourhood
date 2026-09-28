# Rebuild the snapshot and open the HTML dashboard.
[CmdletBinding()]
param(
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

$Board = Get-NhoodBoard
$build = Join-Path $Board 'dashboard\build.py'
if (-not (Test-Path $build)) {
    throw "Board not installed at $Board. Run Install.cmd first."
}

$env:NHOOD_HOME = $Board
$code = Invoke-NhoodPython -PythonArgs @($build)
if ($code -ne 0) { throw "dashboard build failed ($code)" }

$html = Join-Path $Board 'dashboard\index.html'
if (-not (Test-Path $html)) { throw "missing $html" }
Write-NhoodLog "wrote $html"

# Sync the fresh snapshot to the desktop plugin dir (the plugin reads it as
# its last-resort source; build.py also writes it, but only when the dir
# already exists — make sure).
$pluginDir = Join-Path (Get-HermesHome) 'desktop-plugins\neighbourhood'
if (Test-Path $pluginDir) {
    Copy-Item (Join-Path $Board 'dashboard\snapshot.json') (Join-Path $pluginDir 'snapshot.json') -Force
    Write-NhoodLog "snapshot -> $pluginDir"
}

# Bring up the LIVE dashboard server (dashboard/serve.mjs in the
# context-orchestrator repo) detached, so it survives this script and any
# Hermes session. The desktop plugin probes http://localhost:7700 first.
$serve = Join-Path (Get-RepoRoot) '..\context-orchestrator\dashboard\serve.mjs'
$serve = (Resolve-Path $serve -ErrorAction SilentlyContinue).Path
if ($serve) {
    $portInUse = Get-NetTCPConnection -LocalPort 7700 -State Listen -ErrorAction SilentlyContinue
    if (-not $portInUse) {
        $node = (Get-Command node -ErrorAction SilentlyContinue).Source
        if ($node) {
            Start-Process -FilePath $node -ArgumentList @($serve, '--port', '7700') -WindowStyle Hidden
            # serve.mjs takes a few seconds to bind (node cold start + board read).
            # Poll for up to 10s before declaring failure.
            $up = $false
            foreach ($i in 1..10) {
                Start-Sleep -Seconds 1
                if (Get-NetTCPConnection -LocalPort 7700 -State Listen -ErrorAction SilentlyContinue) { $up = $true; break }
            }
            if ($up) { Write-NhoodLog 'live dashboard on http://localhost:7700' }
            else { Write-NhoodLog 'WARN: live dashboard did not bind :7700 within 10s (static snapshot still available)' }
        } else {
            Write-NhoodLog 'WARN: node not found; live dashboard skipped (static snapshot still available)'
        }
    } else {
        Write-NhoodLog 'live dashboard already on :7700'
    }
} else {
    Write-NhoodLog 'WARN: serve.mjs not found next to this repo (context-orchestrator); static only'
}

if (-not $NoBrowser) {
    # Prefer the live dashboard when it's up; fall back to the static file.
    $liveUp = Get-NetTCPConnection -LocalPort 7700 -State Listen -ErrorAction SilentlyContinue
    if ($liveUp) {
        Start-Process 'http://localhost:7700/'
        Write-NhoodLog 'opened live dashboard'
    } else {
        Start-Process $html
        Write-NhoodLog 'opened static dashboard in default browser'
    }
}
