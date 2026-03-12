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

cd "$ROOT_DIR"
python3 -m pip install -r requirements.txt pyinstaller
cd "$DESKTOP_DIR"
npm ci
./scripts/build_backend_sidecar.sh "$PLATFORM_DIR"
./scripts/stage_macos_resources.sh "$PLATFORM_DIR"
npm run tauri:build
