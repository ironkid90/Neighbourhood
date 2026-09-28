# Shared helpers for Neighbourhood 1-click scripts.
$ErrorActionPreference = 'Stop'

function Get-RepoRoot {
    if ($PSScriptRoot) {
        return (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
    }
    return (Resolve-Path (Join-Path $PSCommandPath '..\..')).Path
}

function Get-NhoodBoard {
    if ($env:NHOOD_HOME) { return $env:NHOOD_HOME }
    if ($env:NEIGHBOURHOOD_BOARD_DIR) { return $env:NEIGHBOURHOOD_BOARD_DIR }
    return (Join-Path $HOME '.neighbourhood')
}

function Get-HermesHome {
    # App root, not a profile dir: HERMES_HOME may point at <root>\profiles\<name>.
    # Walk up from any candidate until we find the root (owns desktop-plugins\).
    $candidates = @()
    if ($env:HERMES_HOME) { $candidates += $env:HERMES_HOME }
    if ($env:LOCALAPPDATA) { $candidates += (Join-Path $env:LOCALAPPDATA 'hermes') }
    $candidates += (Join-Path $HOME '.hermes')
    foreach ($c in $candidates) {
        $p = $c
        while ($p) {
            if (Test-Path (Join-Path $p 'desktop-plugins')) { return $p }
            $parent = Split-Path $p -Parent
            if ($parent -eq $p) { break }
            $p = $parent
        }
    }
    return $candidates[0]
}

function Get-NhoodPython {
    $candidates = @(
        @{ Cmd = 'py'; Args = @('-3') },
        @{ Cmd = 'python'; Args = @() },
        @{ Cmd = 'python3'; Args = @() }
    )
    foreach ($c in $candidates) {
        $found = Get-Command $c.Cmd -ErrorAction SilentlyContinue
        if (-not $found) { continue }
        try {
            $ver = & $c.Cmd @($c.Args) '--version' 2>&1 | Out-String
            if ($ver -match 'Python 3\.(\d+)') {
                $minor = [int]$Matches[1]
                if ($minor -ge 11) {
                    return [pscustomobject]@{
                        Cmd  = $found.Source
                        Args = $c.Args
                        Ver  = $ver.Trim()
                    }
                }
            }
        } catch {
            continue
        }
    }
    throw 'Python 3.11+ not found on PATH (need tomllib). Install Python 3.11+ and retry.'
}

function Invoke-NhoodPython {
    param(
        [Parameter(Mandatory = $true)][string[]]$PythonArgs,
        [string]$Cwd
    )
    $py = Get-NhoodPython
    $argList = @()
    if ($py.Args) { $argList += @($py.Args) }
    $argList += $PythonArgs
    $work = if ($Cwd) { $Cwd } else { (Get-Location).Path }
    $p = Start-Process -FilePath $py.Cmd -ArgumentList $argList -WorkingDirectory $work -Wait -PassThru -NoNewWindow
    return [int]$p.ExitCode
}

function Copy-NhoodFile {
    param([string]$From, [string]$To)
    $destDir = Split-Path -Parent $To
    if (-not (Test-Path $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }
    Copy-Item -LiteralPath $From -Destination $To -Force
}

function Write-NhoodLog {
    param([string]$Message, [string]$Level = 'INFO')
    $stamp = (Get-Date).ToUniversalTime().ToString('s') + 'Z'
    Write-Host "[$stamp] [$Level] $Message"
}

function Get-HermesCli {
    $found = Get-Command hermes -ErrorAction SilentlyContinue
    if ($found) { return $found.Source }
    $hermesHome = Get-HermesHome
    $candidates = @(
        (Join-Path $hermesHome 'hermes-agent\venv\Scripts\hermes.exe'),
        (Join-Path $hermesHome 'bin\hermes.exe'),
        (Join-Path $hermesHome 'hermes.exe')
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }
    return $null
}

function Test-HermesPluginPresent {
    param(
        [Parameter(Mandatory = $true)][string]$HermesCli,
        [Parameter(Mandatory = $true)][string]$Name
    )
    $out = & $HermesCli plugins list 2>&1 | Out-String
    if ($out -match [regex]::Escape($Name)) { return $true }
    $hermesHome = Get-HermesHome
    $pluginRoot = Join-Path $hermesHome 'plugins'
    if (-not (Test-Path $pluginRoot)) { return $false }
    $hit = Get-ChildItem -LiteralPath $pluginRoot -Recurse -Filter 'plugin.yaml' -ErrorAction SilentlyContinue |
        Select-String -Pattern ("name:\s*" + [regex]::Escape($Name)) -List
    return [bool]$hit
}
