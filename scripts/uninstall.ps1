# Remove installed plugin copies. Board data is kept unless -WipeBoard.
[CmdletBinding()]
param(
    [switch]$WipeBoard
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

$Board = Get-NhoodBoard
$Hermes = Get-HermesHome

$plugin = Join-Path $Hermes 'desktop-plugins\neighbourhood'
if (Test-Path $plugin) {
    Remove-Item -LiteralPath $plugin -Recurse -Force
    Write-NhoodLog "removed $plugin"
}

$pkg = Join-Path $Hermes 'plugins\neighbourhood'
if (Test-Path $pkg) {
    Remove-Item -LiteralPath $pkg -Recurse -Force
    Write-NhoodLog "removed $pkg"
}

if ($WipeBoard) {
    if (-not (Test-Path $Board)) {
        Write-NhoodLog "board already absent: $Board"
    } else {
        Remove-Item -LiteralPath $Board -Recurse -Force
        Write-NhoodLog "wiped board $Board"
    }
} else {
    Write-NhoodLog "board data kept at $Board (pass -WipeBoard to delete)"
}
