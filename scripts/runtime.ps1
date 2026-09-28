# Repair Hermes + PC runtime and install Atlas modules that belong here.
# Does not edit mcp.json or live config.yaml.
# Does not start Mission Control, Paperclip, or a Gas Town town.
[CmdletBinding()]
param(
    [switch]$InstallMissingTools,
    [switch]$SkipSuperpowers,
    [switch]$SkipBeadsCli,
    [switch]$SkipHermesDoctor,
    [switch]$PaperclipAdapter,
    [switch]$MissionControl
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
$ErrorActionPreference = 'Continue'

$Repo = Get-RepoRoot
$Board = Get-NhoodBoard
$Hermes = Get-HermesHome
$fail = 0

function Note {
    param([string]$Name, [string]$Tone, [string]$Detail)
    Write-Host ("{0,-7} {1,-22} {2}" -f $Tone, $Name, $Detail)
    if ($Tone -eq 'FAIL') { $script:fail++ }
}

Write-NhoodLog "runtime repair  repo=$Repo"
Write-NhoodLog "board $Board"
Write-NhoodLog "hermes $Hermes"

New-Item -ItemType Directory -Path (Join-Path $Board 'catalog') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $Board 'runtime') -Force | Out-Null

$catalogSrc = Join-Path $Repo 'catalog\atlas.json'
$catalogDst = Join-Path $Board 'catalog\atlas.json'
if (Test-Path $catalogSrc) {
    Copy-NhoodFile $catalogSrc $catalogDst
    Note 'catalog' 'PASS' $catalogDst
} else {
    Note 'catalog' 'FAIL' 'missing catalog/atlas.json in product repo'
}

# --- PC tools ----------------------------------------------------------------
function Test-NhoodCmd {
    param([string]$Name)
    $c = Get-Command $Name -ErrorAction SilentlyContinue
    return [bool]$c
}

function Install-WingetId {
    param([string]$Id, [string]$Label)
    if (-not $InstallMissingTools) {
        Note $Label 'WARN' "missing; re-run Runtime.cmd or pass -InstallMissingTools"
        return
    }
    $wg = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $wg) {
        Note $Label 'WARN' 'winget not on PATH; install manually'
        return
    }
    Write-NhoodLog "winget install $Id"
    & $wg.Source install --id $Id -e --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -eq 0) {
        Note $Label 'PASS' "installed $Id"
    } else {
        Note $Label 'WARN' "winget $Id exit=$LASTEXITCODE (may need UAC)"
    }
}

try {
    $py = Get-NhoodPython
    Note 'python' 'PASS' $py.Ver
} catch {
    Note 'python' 'FAIL' $_.Exception.Message
    Install-WingetId 'Python.Python.3.12' 'python'
}

if (Test-NhoodCmd 'git') {
    $gv = (& git --version 2>&1 | Out-String).Trim()
    Note 'git' 'PASS' $gv
} else {
    Note 'git' 'WARN' 'not on PATH'
    Install-WingetId 'Git.Git' 'git'
}

if ((Test-NhoodCmd 'node') -or (Test-NhoodCmd 'node.exe')) {
    $nv = (& node --version 2>&1 | Out-String).Trim()
    Note 'node' 'PASS' $nv
} else {
    Note 'node' 'WARN' 'not on PATH'
    Install-WingetId 'OpenJS.NodeJS.LTS' 'node'
}

if (Test-NhoodCmd 'uv') {
    Note 'uv' 'PASS' 'on PATH'
} else {
    Note 'uv' 'WARN' 'optional; MCP uvx path'
    Install-WingetId 'astral-sh.uv' 'uv'
}

# --- Hermes CLI + doctor -----------------------------------------------------
$hermesCli = Get-HermesCli
if ($hermesCli) {
    Note 'hermes' 'PASS' $hermesCli
    if (-not $SkipHermesDoctor) {
        Write-NhoodLog 'hermes doctor'
        & $hermesCli doctor
        $docCode = $LASTEXITCODE
        if ($docCode -eq 0) {
            Note 'hermes-doctor' 'PASS' 'exit=0'
        } else {
            Note 'hermes-doctor' 'WARN' "exit=$docCode (warnings do not fail runtime)"
        }
    }
} else {
    Note 'hermes' 'FAIL' 'CLI not found. Official install: https://hermes-agent.nousresearch.com/docs/  (will not curl|bash over a live tree)'
}

$cfg = Join-Path $Hermes 'config.yaml'
$envFile = Join-Path $Hermes '.env'
Note 'config.yaml' $(if (Test-Path $cfg) { 'PASS' } else { 'FAIL' }) $cfg
Note '.env' $(if (Test-Path $envFile) { 'PASS' } else { 'WARN' }) 'secrets stay here; never in the board'

# --- Beads CLI ---------------------------------------------------------------
if (-not $SkipBeadsCli) {
    $bd = Get-Command bd -ErrorAction SilentlyContinue
    if (-not $bd) { $bd = Get-Command bd.cmd -ErrorAction SilentlyContinue }
    if ($bd) {
        Note 'bd' 'PASS' 'on PATH'
    } else {
        $npm = Get-Command npm -ErrorAction SilentlyContinue
        if (-not $npm) { $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue }
        if ($npm) {
            Write-NhoodLog 'npm i -g @beads/bd'
            & $npm.Source i -g '@beads/bd'
            if ($LASTEXITCODE -eq 0) {
                Note 'bd' 'PASS' 'npm i -g @beads/bd'
            } else {
                Note 'bd' 'WARN' "npm i -g @beads/bd exit=$LASTEXITCODE"
            }
        } else {
            Note 'bd' 'WARN' 'npm missing; board works without bd'
        }
    }
}

# --- Superpowers -------------------------------------------------------------
if (-not $SkipSuperpowers) {
    if (-not $hermesCli) {
        Note 'superpowers' 'WARN' 'no hermes CLI; skip plugin install'
    } elseif (Test-HermesPluginPresent -HermesCli $hermesCli -Name 'superpowers') {
        Note 'superpowers' 'PASS' 'already installed'
    } else {
        Write-NhoodLog 'hermes plugins install obra/superpowers --enable --force'
        Write-NhoodLog 'scanner flags docs/tests in the Superpowers repo (fake tokens, CLAUDE.md mentions). Official obra/superpowers; --force is required for 1-click.' 'WARN'
        & $hermesCli plugins install 'obra/superpowers' --enable --force
        $spCode = $LASTEXITCODE
        if ((Test-HermesPluginPresent -HermesCli $hermesCli -Name 'superpowers')) {
            Note 'superpowers' 'PASS' 'obra/superpowers enabled'
        } else {
            Note 'superpowers' 'WARN' "plugin install exit=$spCode (Neighbourhood still installs)"
        }
    }
}

# --- Optional Paperclip adapter (npm vendor, no server) ----------------------
if ($PaperclipAdapter) {
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) { $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue }
    $dest = Join-Path $Board 'runtime\paperclip-adapter'
    New-Item -ItemType Directory -Path $dest -Force | Out-Null
    if ($npm) {
        Write-NhoodLog "npm install hermes-paperclip-adapter -> $dest"
        & $npm.Source install 'hermes-paperclip-adapter' --prefix $dest
        if ($LASTEXITCODE -eq 0) {
            Note 'paperclip-adapter' 'PASS' $dest
            Write-NhoodLog 'Paperclip adapter is a bridge only. Needs a paperclip.ing company. Not started.' 'WARN'
        } else {
            Note 'paperclip-adapter' 'WARN' "npm exit=$LASTEXITCODE"
        }
    } else {
        Note 'paperclip-adapter' 'WARN' 'npm missing'
    }
}

# --- Optional Mission Control clone (never start) ----------------------------
if ($MissionControl) {
    $dest = Join-Path $Board 'runtime\mission-control'
    $git = Get-Command git -ErrorAction SilentlyContinue
    if (Test-Path (Join-Path $dest '.git')) {
        Note 'mission-control' 'PASS' "already cloned $dest (not started)"
    } elseif ($git) {
        Write-NhoodLog "git clone --depth 1 builderz-labs/mission-control -> $dest"
        & $git.Source clone --depth 1 'https://github.com/builderz-labs/mission-control.git' $dest
        if ($LASTEXITCODE -eq 0) {
            Note 'mission-control' 'PASS' "$dest cloned; NOT started (second orchestrator)"
            Write-NhoodLog 'Do not run install.ps1 -Mode local or docker compose unless the human says go.' 'WARN'
        } else {
            Note 'mission-control' 'WARN' "git clone exit=$LASTEXITCODE"
        }
    } else {
        Note 'mission-control' 'WARN' 'git missing; cannot clone'
    }
}

# --- Explicitly not done -----------------------------------------------------
Note 'mcp.json' 'PASS' 'untouched'
Note 'config.yaml-edit' 'PASS' 'untouched (plugin install is the official path)'
Note 'gt-town' 'PASS' 'gated'
Note 'mission-control-start' 'PASS' 'not started'

if ($fail -gt 0) {
    Write-NhoodLog "runtime FAIL ($fail check(s))" 'WARN'
    Write-Host "runtime FAIL ($fail check(s))"
    exit 1
}
Write-NhoodLog 'runtime OK'
Write-Host 'runtime OK'
Write-Host 'Gated: gt install, Mayor, polecats, beads-mcp, Mission Control start, Paperclip company, mcp.json'
exit 0
