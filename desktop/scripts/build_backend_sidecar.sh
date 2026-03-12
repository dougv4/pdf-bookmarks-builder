#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
DESKTOP_DIR="$ROOT_DIR/desktop"
PLATFORM_DIR="${1:-macos-arm64}"
OUTPUT_DIR="$DESKTOP_DIR/resources/binaries/$PLATFORM_DIR"
ENTRYPOINT="$DESKTOP_DIR/backend_entrypoint.py"

mkdir -p "$OUTPUT_DIR"

if ! command -v pyinstaller >/dev/null 2>&1; then
  echo "pyinstaller nao encontrado. Instale com: python3 -m pip install pyinstaller"
  exit 1
fi

pyinstaller \
  --noconfirm \
  --clean \
  --onefile \
  --name pdf-bookmarks-backend \
  --distpath "$OUTPUT_DIR" \
  --workpath "$DESKTOP_DIR/.pyinstaller-work" \
  --specpath "$DESKTOP_DIR/.pyinstaller-spec" \
  --paths "$ROOT_DIR" \
  "$ENTRYPOINT"

echo "Backend sidecar gerado em: $OUTPUT_DIR/pdf-bookmarks-backend"
