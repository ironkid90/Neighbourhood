# Sync this product repo onto the local Neighbourhood board + Hermes desktop pane.
# Does not overwrite live status.json / handoffs. Does not edit mcp.json or config.yaml.
[CmdletBinding()]
param(
    [switch]$SkipBeads,
    [switch]$SkipSnapshot,
    [switch]$NoDesktopPlugin
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

$Repo = Get-RepoRoot
$Board = Get-NhoodBoard
$Hermes = Get-HermesHome

Write-NhoodLog "repo  $Repo"
Write-NhoodLog "board $Board"
Write-NhoodLog "hermes $Hermes"

$py = Get-NhoodPython
Write-NhoodLog "python $($py.Ver) ($($py.Cmd))"

# --- board skeleton ----------------------------------------------------------
New-Item -ItemType Directory -Path $Board -Force | Out-Null
foreach ($d in @('dashboard', 'tools', 'preflight', 'handoffs', 'courier', '.beads\formulas')) {
    New-Item -ItemType Directory -Path (Join-Path $Board $d) -Force | Out-Null
}

$seed = @{
    (Join-Path $Repo 'templates\RULES.md')           = (Join-Path $Board 'RULES.md')
    (Join-Path $Repo 'templates\status.json')        = (Join-Path $Board 'status.json')
    (Join-Path $Repo 'templates\board.gitignore')    = (Join-Path $Board '.gitignore')
}
foreach ($from in $seed.Keys) {
    $to = $seed[$from]
    if (-not (Test-Path $to)) {
        Copy-NhoodFile $from $to
        Write-NhoodLog "seeded $to"
    } else {
        Write-NhoodLog "keep existing $to"
    }
}

# --- app code (always refresh from product) ---------------------------------
$sync = @(
    @{ From = 'dashboard\build.py'; To = 'dashboard\build.py' }
    @{ From = 'dashboard\STEAL.md'; To = 'dashboard\STEAL.md' }
    @{ From = 'tools\nhood.py'; To = 'tools\nhood.py' }
    @{ From = 'tools\README.md'; To = 'tools\README.md' }
    @{ From = 'preflight\preflight.ps1'; To = 'preflight\preflight.ps1' }
    @{ From = 'courier\neighbourhood_courier.py'; To = 'courier\neighbourhood_courier.py' }
    @{ From = 'courier\courier-config.example.json'; To = 'courier\courier-config.example.json' }
    @{ From = 'formulas\nhood-feature.formula.toml'; To = '.beads\formulas\nhood-feature.formula.toml' }
)
foreach ($item in $sync) {
    $from = Join-Path $Repo $item.From
    $to = Join-Path $Board $item.To
    if (-not (Test-Path $from)) { throw "missing product file: $from" }
    Copy-NhoodFile $from $to
    Write-NhoodLog "synced $($item.To)"
}

# --- desktop plugin (standalone, loads by default) --------------------------
if (-not $NoDesktopPlugin) {
    $pluginDir = Join-Path $Hermes 'desktop-plugins\neighbourhood'
    New-Item -ItemType Directory -Path $pluginDir -Force | Out-Null
    Copy-NhoodFile (Join-Path $Repo 'desktop-plugin\plugin.js') (Join-Path $pluginDir 'plugin.js')
    Write-NhoodLog "desktop plugin -> $pluginDir"
}

# --- hermes python plugin (opt-in; do not enable in config.yaml) ------------
$pkg = Join-Path $Hermes 'plugins\neighbourhood'
New-Item -ItemType Directory -Path (Join-Path $pkg 'dashboard') -Force | Out-Null
Copy-NhoodFile (Join-Path $Repo 'hermes-plugin\plugin.yaml') (Join-Path $pkg 'plugin.yaml')
Copy-NhoodFile (Join-Path $Repo 'hermes-plugin\dashboard\plugin_api.py') (Join-Path $pkg 'dashboard\plugin_api.py')
Copy-NhoodFile (Join-Path $Repo 'hermes-plugin\dashboard\manifest.json') (Join-Path $pkg 'dashboard\manifest.json')
Write-NhoodLog "hermes plugin copied (not enabled; leave plugins.enabled alone)"

# --- git repo on the board (beads wants this) -------------------------------
$git = Get-Command git -ErrorAction SilentlyContinue
if ($git) {
    if (-not (Test-Path (Join-Path $Board '.git'))) {
        & git -C $Board init -b main | Out-Host
        Write-NhoodLog 'git init -b main on board'
    } else {
        Write-NhoodLog 'board already a git repo'
    }
} else {
    Write-NhoodLog 'git not on PATH; skip board git init' 'WARN'
}

# --- beads ------------------------------------------------------------------
if (-not $SkipBeads) {
    $bd = Get-Command bd -ErrorAction SilentlyContinue
    if (-not $bd) { $bd = Get-Command bd.cmd -ErrorAction SilentlyContinue }
    $beadsMeta = Join-Path $Board '.beads\metadata.json'
    if ($bd -and -not (Test-Path $beadsMeta)) {
        Push-Location $Board
        try {
            & $bd.Source init --non-interactive --role maintainer -p nhood --skip-agents
            if ($LASTEXITCODE -ne 0) { throw "bd init failed ($LASTEXITCODE)" }
            Write-NhoodLog 'bd init prefix=nhood'
        } finally { Pop-Location }
    } elseif (-not $bd) {
        Write-NhoodLog 'bd CLI not on PATH; board works without it. Install: npm i -g @beads/bd' 'WARN'
    } else {
        Write-NhoodLog 'beads already initialized'
    }
}

# --- smoke + snapshot -------------------------------------------------------
$code = Invoke-NhoodPython -PythonArgs @((Join-Path $Repo 'tests\test_smoke.py'))
if ($code -ne 0) { throw "smoke tests failed ($code)" }
Write-NhoodLog 'smoke tests OK'

if (-not $SkipSnapshot) {
    $env:NHOOD_HOME = $Board
    $code = Invoke-NhoodPython -PythonArgs @((Join-Path $Board 'dashboard\build.py'))
    if ($code -ne 0) { throw "dashboard build failed ($code)" }
    Write-NhoodLog "snapshot -> $(Join-Path $Board 'dashboard\index.html')"
}

Write-NhoodLog 'install complete'
Write-Host ''
Write-Host 'Next:'
Write-Host "  double-click Start.cmd    (rebuild snapshot + open HTML)"
Write-Host "  double-click Doctor.cmd   (health gate)"
Write-Host "  Hermes: Reload desktop plugins  (sidebar Neighbourhood)"
Write-Host "Gated (do not run unless asked): gt install, Mayor, polecats, beads-mcp, plugins.enabled"
