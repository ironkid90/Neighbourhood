# Health gate: Python, board files, nhood self-check, compile, optional preflight.
[CmdletBinding()]
param(
    [switch]$SkipPreflight
)

$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'common.ps1')

$Repo = Get-RepoRoot
$Board = Get-NhoodBoard
$Hermes = Get-HermesHome
$fail = 0

function Check {
    param([string]$Name, [bool]$Ok, [string]$Detail)
    $tone = if ($Ok) { 'PASS' } else { 'FAIL' }
    if (-not $Ok) { $script:fail++ }
    Write-Host ("{0,-7} {1,-22} {2}" -f $tone, $Name, $Detail)
}

try {
    $py = Get-NhoodPython
    Check 'python' $true $py.Ver
} catch {
    Check 'python' $false $_.Exception.Message
}

Check 'board' (Test-Path $Board) $Board
Check 'nhood.py' (Test-Path (Join-Path $Board 'tools\nhood.py')) (Join-Path $Board 'tools\nhood.py')
Check 'build.py' (Test-Path (Join-Path $Board 'dashboard\build.py')) (Join-Path $Board 'dashboard\build.py')
Check 'status.json' (Test-Path (Join-Path $Board 'status.json')) 'coordination SoT'
$pluginOk = (Test-Path (Join-Path $Hermes 'desktop-plugins\neighbourhood\plugin.js')) -or
            (Test-Path (Join-Path $Hermes 'plugins\neighbourhood\desktop\plugin.js'))
Check 'plugin.js' $pluginOk 'standalone desktop pane'

$prodPlugin = Join-Path $Repo 'desktop-plugin\plugin.js'
$instPlugin = Join-Path $Hermes 'desktop-plugins\neighbourhood\plugin.js'
if ((Test-Path $prodPlugin) -and (Test-Path $instPlugin)) {
    $h1 = (Get-FileHash -LiteralPath $prodPlugin -Algorithm SHA256).Hash
    $h2 = (Get-FileHash -LiteralPath $instPlugin -Algorithm SHA256).Hash
    Check 'plugin-drift' ($h1 -eq $h2) $(if ($h1 -eq $h2) { 'product == installed' } else { 'run Install.cmd' })
}
$paneSnap = Join-Path $Hermes 'desktop-plugins\neighbourhood\snapshot.json'
Check 'plugin-snapshot' (Test-Path $paneSnap) $paneSnap

$bd = Get-Command bd -ErrorAction SilentlyContinue
if (-not $bd) { $bd = Get-Command bd.cmd -ErrorAction SilentlyContinue }
Check 'bd' ([bool]$bd) $(if ($bd) { 'on PATH' } else { 'optional; npm i -g @beads/bd' })

$ErrorActionPreference = 'Stop'
$code = Invoke-NhoodPython -PythonArgs @((Join-Path $Repo 'tests\test_smoke.py'))
Check 'smoke' ($code -eq 0) "tests/test_smoke.py exit=$code"

if (Test-Path (Join-Path $Board 'tools\nhood.py')) {
    $env:NHOOD_HOME = $Board
    $code = Invoke-NhoodPython -PythonArgs @((Join-Path $Board 'tools\nhood.py'), 'self-check')
    Check 'nhood-self-check' ($code -eq 0) "exit=$code"
}

if (-not $SkipPreflight -and (Test-Path (Join-Path $Board 'preflight\preflight.ps1'))) {
    $pre = Join-Path $Board 'preflight\preflight.ps1'
    $env:NHOOD_HOME = $Board
    $p = Start-Process -FilePath 'powershell' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$pre,'-BoardDir',$Board) -Wait -PassThru -NoNewWindow
    Check 'preflight' ($p.ExitCode -eq 0) "exit=$($p.ExitCode) (WARN does not fail)"
}

if ($fail -gt 0) {
    Write-Host "doctor FAIL ($fail check(s))"
    exit 1
}
Write-Host 'doctor PASS'
exit 0
