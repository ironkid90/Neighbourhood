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

if (-not $NoBrowser) {
    Start-Process $html
    Write-NhoodLog 'opened dashboard in default browser'
}
