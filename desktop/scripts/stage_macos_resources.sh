#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
DESKTOP_DIR="$ROOT_DIR/desktop"
detect_platform_dir() {
  local machine
  machine="$(uname -m)"
  case "$machine" in
    arm64|aarch64) echo "macos-arm64" ;;
    x86_64) echo "macos-x64" ;;
    *) echo "macos-$machine" ;;
  esac
}

PLATFORM_DIR="${1:-$(detect_platform_dir)}"
BIN_DIR="$DESKTOP_DIR/resources/binaries/$PLATFORM_DIR"
GS_RESOURCE_DIR="$DESKTOP_DIR/resources/ghostscript/$PLATFORM_DIR"

mkdir -p "$BIN_DIR" "$GS_RESOURCE_DIR"

require_bin() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Dependencia obrigatoria ausente: $1"
    exit 1
  }
}

require_bin brew
require_bin otool
require_bin install_name_tool
require_bin rsync

GS_BIN="${PDF_BUILDER_GS_PATH:-$(command -v gs || true)}"
QPDF_BIN="${PDF_BUILDER_QPDF_PATH:-$(command -v qpdf || true)}"
GS_PREFIX="${PDF_BUILDER_GS_PREFIX:-$(brew --prefix ghostscript 2>/dev/null || true)}"
QPDF_PREFIX="${PDF_BUILDER_QPDF_PREFIX:-$(brew --prefix qpdf 2>/dev/null || true)}"

if [[ -z "$GS_BIN" || -z "$QPDF_BIN" ]]; then
  echo "gs e qpdf precisam estar instalados antes do staging."
  exit 1
fi

copy_binary_with_deps() {
  local src="$1"
  local dst_name="$2"
  local dst="$BIN_DIR/$dst_name"
  if [[ -e "$dst" ]]; then
    chmod u+w "$dst" 2>/dev/null || true
    rm -f "$dst"
  fi
  cp "$src" "$dst"
  chmod +x "$dst"

  while IFS= read -r dep; do
    [[ -z "$dep" ]] && continue
    local base
    base="$(basename "$dep")"
    if [[ ! -f "$BIN_DIR/$base" ]]; then
      if [[ -e "$BIN_DIR/$base" ]]; then
        chmod u+w "$BIN_DIR/$base" 2>/dev/null || true
        rm -f "$BIN_DIR/$base"
      fi
      cp "$dep" "$BIN_DIR/$base"
      chmod +x "$BIN_DIR/$base"
      if [[ "$dep" == /opt/homebrew/* || "$dep" == /usr/local/* ]]; then
        copy_nested_deps "$BIN_DIR/$base"
      fi
    fi
    install_name_tool -change "$dep" "@loader_path/$base" "$dst" 2>/dev/null || true
  done < <(otool -L "$src" | tail -n +2 | awk '{print $1}' | grep -E '^(/opt/homebrew|/usr/local)')

  install_name_tool -id "@loader_path/$dst_name" "$dst" 2>/dev/null || true
}

copy_nested_deps() {
  local target="$1"
  while IFS= read -r dep; do
    [[ -z "$dep" ]] && continue
    local base
    base="$(basename "$dep")"
    if [[ ! -f "$BIN_DIR/$base" ]]; then
      if [[ -e "$BIN_DIR/$base" ]]; then
        chmod u+w "$BIN_DIR/$base" 2>/dev/null || true
        rm -f "$BIN_DIR/$base"
      fi
      cp "$dep" "$BIN_DIR/$base"
      chmod +x "$BIN_DIR/$base"
      copy_nested_deps "$BIN_DIR/$base"
    fi
    install_name_tool -change "$dep" "@loader_path/$base" "$target" 2>/dev/null || true
  done < <(otool -L "$target" | tail -n +2 | awk '{print $1}' | grep -E '^(/opt/homebrew|/usr/local)')

  install_name_tool -id "@loader_path/$(basename "$target")" "$target" 2>/dev/null || true
}

copy_binary_with_deps "$GS_BIN" gs
copy_binary_with_deps "$QPDF_BIN" qpdf

if [[ -z "$GS_PREFIX" || ! -d "$GS_PREFIX" ]]; then
  echo "Nao foi possivel localizar o prefixo do Ghostscript via Homebrew."
  exit 1
fi

GS_SHARE_ROOT="$GS_PREFIX/share/ghostscript"
if [[ ! -d "$GS_SHARE_ROOT" ]]; then
  echo "Nao foi possivel localizar os recursos share/ghostscript do Ghostscript."
  exit 1
fi

for subdir in Resource lib fonts iccprofiles; do
  if [[ -d "$GS_SHARE_ROOT/$subdir" ]]; then
    rsync -a --delete "$GS_SHARE_ROOT/$subdir/" "$GS_RESOURCE_DIR/$subdir/"
  fi
done

for notice in COPYING LICENSE; do
  if [[ -f "$GS_PREFIX/$notice" ]]; then
    cp "$GS_PREFIX/$notice" "$GS_RESOURCE_DIR/ghostscript-$notice"
  fi
  if [[ -n "$QPDF_PREFIX" && -f "$QPDF_PREFIX/$notice" ]]; then
    cp "$QPDF_PREFIX/$notice" "$GS_RESOURCE_DIR/qpdf-$notice"
  fi
done

echo "Recursos macOS staged em: $BIN_DIR"
echo "Ghostscript resources em: $GS_RESOURCE_DIR"
