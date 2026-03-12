param(
  [string]$PlatformDir = 'windows-x64'
)

$ErrorActionPreference = 'Stop'
$RootDir = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$DesktopDir = Join-Path $RootDir 'desktop'
$OutputDir = Join-Path $DesktopDir "resources\binaries\$PlatformDir"
$Entrypoint = Join-Path $DesktopDir 'backend_entrypoint.py'

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
  throw 'pyinstaller nao encontrado. Instale com: py -m pip install pyinstaller'
}

pyinstaller `
  --noconfirm `
  --clean `
  --onefile `
  --name pdf-bookmarks-backend `
  --distpath $OutputDir `
  --workpath (Join-Path $DesktopDir '.pyinstaller-work') `
  --specpath (Join-Path $DesktopDir '.pyinstaller-spec') `
  --paths $RootDir `
  $Entrypoint | Out-Host

Write-Host "Backend sidecar gerado em: $OutputDir\pdf-bookmarks-backend.exe"
