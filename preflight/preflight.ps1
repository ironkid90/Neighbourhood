# Neighbourhood preflight - environment and path health gate
# Read-only: reports PASS/WARN/FAIL, never mutates config.
# Usage: pwsh -File preflight.ps1 [-Json] [-BoardDir <path>]
# Exit code: 0 = no FAIL, 1 = at least one FAIL (WARN never blocks).

[CmdletBinding()]
param(
    [switch]$Json,
    [string]$BoardDir = $(
        if ($env:NHOOD_HOME) { $env:NHOOD_HOME }
        elseif ($env:NEIGHBOURHOOD_BOARD_DIR) { $env:NEIGHBOURHOOD_BOARD_DIR }
        else { "$HOME/.neighbourhood" }
    )
)

$ErrorActionPreference = 'Continue'
$results = [System.Collections.Generic.List[object]]::new()

function Add-Check {
    param([string]$Name, [ValidateSet('PASS','WARN','FAIL')][string]$Status, [string]$Detail)
    $results.Add([pscustomobject]@{
        name   = $Name
        status = $Status
        detail = $Detail
        ts     = (Get-Date).ToUniversalTime().ToString('o')
    })
}

# --- 1. node/npm presence and version --------------------------------------
$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if (-not $nodeCmd) {
    Add-Check 'node-present' 'FAIL' 'node not on PATH'
} else {
    $nodeVer = (& node --version 2>$null)
    Add-Check 'node-present' 'PASS' "node $nodeVer at $($nodeCmd.Source)"
    # nopt-lib poison: stray package in the *global* node_modules breaks npx arg parsing
    $npmRoot = (& npm root -g 2>$null)
    if ($npmRoot -and (Test-Path (Join-Path $npmRoot.Trim() 'nopt-lib'))) {
        Add-Check 'npx-nopt-lib' 'FAIL' "nopt-lib found in global node_modules ($npmRoot); breaks npx arg parsing; remove it"
    } else {
        Add-Check 'npx-nopt-lib' 'PASS' 'no nopt-lib in global node_modules'
    }
}

# --- 2. Python env drift ----------------------------------------------------
$py = Get-Command python -ErrorAction SilentlyContinue
$py3 = Get-Command python3 -ErrorAction SilentlyContinue
if ($py -and $py3) {
    $vPy = (& python --version 2>&1) -replace '\D+(\d+\.\d+\.\d+).*','$1'
    $vPy3 = (& python3 --version 2>&1) -replace '\D+(\d+\.\d+\.\d+).*','$1'
    if ($vPy -ne $vPy3) {
        Add-Check 'python-drift' 'WARN' "python=$vPy python3=$vPy3; pip maps to python3.11 here; use 'python -m pip' explicitly"
    } else {
        Add-Check 'python-drift' 'PASS' "python==python3 ($vPy)"
    }
} elseif ($py -or $py3) {
    Add-Check 'python-drift' 'PASS' 'single python interpreter on PATH'
} else {
    Add-Check 'python-drift' 'FAIL' 'no python on PATH'
}

# --- 3. MCP hub drift: referenced commands/args resolve ----------------------
$hubFile = "$HOME/.mcp-hub/mcp.json"
if (-not (Test-Path $hubFile)) {
    Add-Check 'mcp-hub-drift' 'WARN' "hub file not found: $hubFile"
} else {
    try {
        $hub = Get-Content $hubFile -Raw | ConvertFrom-Json
        $servers = if ($hub.mcpServers) { $hub.mcpServers } else { $hub.servers }
        $missing = @()
        foreach ($prop in $servers.PSObject.Properties) {
            $s = $prop.Value
            # expand ${USERPROFILE} the way the hub's sync does
            $expandedArgs = @()
            foreach ($a in @($s.args)) { $expandedArgs += ($a -replace '\$\{USERPROFILE\}', $env:USERPROFILE) }
            $cmd = ($s.command -replace '\$\{USERPROFILE\}', $env:USERPROFILE)
            if ($cmd -match '\.cmd$|\.bat$|\.exe$|\.py$' -and $cmd -match '[\\/]') {
                if (-not (Test-Path $cmd)) { $missing += "$($prop.Name): command $cmd" }
            }
            foreach ($a in $expandedArgs) {
                # filesystem path heuristic: drive-letter or UNC/home paths only -
                # npm specifiers (@scope/pkg), cmd flags (/c) and bare flags are not paths
                $looksLikePath = ($a -match '^[A-Za-z]:[\\/]') -or ($a -match '^[\\/][\\/]') -or ($a -like "$env:USERPROFILE*") -or ($a -like "$HOME*")
                if ($looksLikePath -and -not (Test-Path $a)) { $missing += "$($prop.Name): arg $a" }
            }
        }
        if ($missing.Count) {
            Add-Check 'mcp-hub-drift' 'FAIL' ("missing paths: " + ($missing -join '; '))
        } else {
            Add-Check 'mcp-hub-drift' 'PASS' "all hub server commands/args resolve ($(@($servers.PSObject.Properties).Count) servers)"
        }
    } catch {
        Add-Check 'mcp-hub-drift' 'FAIL' "hub JSON unparseable: $($_.Exception.Message)"
    }
}

# --- 4. Port 5051 (Lucky5 dev server) ---------------------------------------
$conn = Get-NetTCPConnection -LocalPort 5051 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) {
    $owner = (Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue).ProcessName
    Add-Check 'port-5051' 'WARN' "5051 already LISTENING (pid $($conn.OwningProcess) $owner); fine if dev.ps1 is running, conflict otherwise"
} else {
    Add-Check 'port-5051' 'PASS' '5051 free'
}

# --- 5. Board writability ----------------------------------------------------
try {
    if (-not (Test-Path $BoardDir)) { New-Item -ItemType Directory -Path $BoardDir -Force | Out-Null }
    $probe = Join-Path $BoardDir ".preflight-probe-$PID"
    Set-Content -Path $probe -Value 'ok' -ErrorAction Stop
    Remove-Item $probe -Force
    Add-Check 'board-writable' 'PASS' "$BoardDir writable"
} catch {
    Add-Check 'board-writable' 'FAIL' "$BoardDir not writable: $($_.Exception.Message)"
}

# --- Emit -------------------------------------------------------------------
$summary = [pscustomobject]@{
    ts      = (Get-Date).ToUniversalTime().ToString('o')
    overall = if ($results.status -contains 'FAIL') { 'FAIL' } elseif ($results.status -contains 'WARN') { 'WARN' } else { 'PASS' }
    checks  = $results
}

$outDir = Join-Path $BoardDir 'preflight'
New-Item -ItemType Directory -Path $outDir -Force | Out-Null
$jsonPath = Join-Path $outDir 'health.json'
$logPath  = Join-Path $outDir 'health-latest.log'
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($jsonPath, ($summary | ConvertTo-Json -Depth 5), $utf8NoBom)

$lines = foreach ($c in $results) { "{0,-7} {1,-16} {2}" -f $c.status, $c.name, $c.detail }
$logText = (@("preflight $($summary.ts) overall=$($summary.overall)") + $lines) -join [char]10
Set-Content -Path $logPath -Value $logText -Encoding UTF8

if ($Json) {
    $summary | ConvertTo-Json -Depth 5
} else {
    Write-Host $logText
}
if ($summary.overall -eq 'FAIL') { exit 1 } else { exit 0 }
