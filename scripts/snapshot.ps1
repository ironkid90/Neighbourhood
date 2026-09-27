# Rebuild snapshot.json + index.html without opening a browser.
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

$Board = Get-NhoodBoard
$build = Join-Path $Board 'dashboard\build.py'
if (-not (Test-Path $build)) { throw "Board not installed at $Board. Run Install.cmd first." }
$env:NHOOD_HOME = $Board
$code = Invoke-NhoodPython -PythonArgs @($build)
if ($code -ne 0) { throw "dashboard build failed ($code)" }
Write-NhoodLog "wrote $(Join-Path $Board 'dashboard\index.html')"
