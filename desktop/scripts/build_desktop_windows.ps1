param(
  [string]$PlatformDir = 'windows-x64'
)

$ErrorActionPreference = 'Stop'
$RootDir = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$DesktopDir = Join-Path $RootDir 'desktop'

Set-Location $RootDir
py -m pip install -r requirements.txt pyinstaller | Out-Host
Set-Location $DesktopDir
npm ci | Out-Host
& (Join-Path $DesktopDir 'scripts\build_backend_sidecar.ps1') -PlatformDir $PlatformDir
& (Join-Path $DesktopDir 'scripts\stage_windows_resources.ps1') -PlatformDir $PlatformDir
npm run tauri:build | Out-Host
