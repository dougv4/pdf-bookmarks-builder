param(
  [string]$PlatformDir = 'windows-x64'
)

$ErrorActionPreference = 'Stop'
$RootDir = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$DesktopDir = Join-Path $RootDir 'desktop'
$BinDir = Join-Path $DesktopDir "resources\binaries\$PlatformDir"
$GsResourceDir = Join-Path $DesktopDir "resources\ghostscript\$PlatformDir"

New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
New-Item -ItemType Directory -Force -Path $GsResourceDir | Out-Null

function Require-Path([string]$Value, [string]$Label) {
  if ([string]::IsNullOrWhiteSpace($Value) -or -not (Test-Path $Value)) {
    throw "Nao foi possivel localizar $Label."
  }
  return (Resolve-Path $Value).Path
}

$GsExe = $env:PDF_BUILDER_GS_PATH
if (-not $GsExe) {
  $candidate = Get-Command gswin64c.exe -ErrorAction SilentlyContinue
  if (-not $candidate) { $candidate = Get-Command gs.exe -ErrorAction SilentlyContinue }
  if ($candidate) { $GsExe = $candidate.Source }
}
$QpdfExe = $env:PDF_BUILDER_QPDF_PATH
if (-not $QpdfExe) {
  $candidate = Get-Command qpdf.exe -ErrorAction SilentlyContinue
  if ($candidate) { $QpdfExe = $candidate.Source }
}

$GsExe = Require-Path $GsExe 'o executavel do Ghostscript'
$QpdfExe = Require-Path $QpdfExe 'o executavel do qpdf'

Copy-Item $GsExe (Join-Path $BinDir 'gs.exe') -Force
Copy-Item $QpdfExe (Join-Path $BinDir 'qpdf.exe') -Force

$gsDir = Split-Path $GsExe -Parent
$qpdfDir = Split-Path $QpdfExe -Parent
Get-ChildItem $gsDir -Filter '*.dll' -ErrorAction SilentlyContinue | ForEach-Object {
  Copy-Item $_.FullName $BinDir -Force
}
Get-ChildItem $qpdfDir -Filter '*.dll' -ErrorAction SilentlyContinue | ForEach-Object {
  Copy-Item $_.FullName $BinDir -Force
}

$gsRoot = $env:PDF_BUILDER_GS_ROOT
if (-not $gsRoot) {
  $gsRoot = Split-Path $gsDir -Parent
}

foreach ($subdir in @('Resource', 'lib', 'fonts', 'iccprofiles')) {
  $source = Join-Path $gsRoot $subdir
  $target = Join-Path $GsResourceDir $subdir
  if (Test-Path $source) {
    if (Test-Path $target) {
      Remove-Item $target -Recurse -Force
    }
    Copy-Item $source $target -Recurse -Force
  }
}
if (-not (Test-Path (Join-Path $GsResourceDir 'Resource')) -and -not (Test-Path (Join-Path $GsResourceDir 'lib'))) {
  throw 'Nao foi possivel localizar os recursos do Ghostscript (Resource/lib).'
}

Write-Host "Recursos Windows staged em: $BinDir"
Write-Host "Ghostscript resources em: $GsResourceDir"
