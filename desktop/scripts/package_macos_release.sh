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

platform_arch_suffix() {
  case "$1" in
    macos-arm64) echo "aarch64" ;;
    macos-x64) echo "x64" ;;
    *) echo "$1" ;;
  esac
}

require_bin() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Dependencia obrigatoria ausente: $1"
    exit 1
  }
}

has_notary_credentials() {
  if [[ -n "${APPLE_API_KEY_ID:-}" && -n "${APPLE_API_ISSUER:-}" && -n "${APPLE_API_KEY_BASE64:-}" ]]; then
    return 0
  fi
  if [[ -n "${APPLE_ID:-}" && -n "${APPLE_APP_PASSWORD:-}" && -n "${APPLE_TEAM_ID:-}" ]]; then
    return 0
  fi
  return 1
}

notarize_file() {
  local path="$1"
  if ! has_notary_credentials; then
    return 0
  fi

  require_bin xcrun
  if [[ -n "${APPLE_API_KEY_ID:-}" && -n "${APPLE_API_ISSUER:-}" && -n "${APPLE_API_KEY_BASE64:-}" ]]; then
    local key_path="${RUNNER_TEMP:-/tmp}/appstoreconnect_api_key.p8"
    printf '%s' "$APPLE_API_KEY_BASE64" | base64 --decode > "$key_path"
    xcrun notarytool submit "$path" \
      --key "$key_path" \
      --key-id "$APPLE_API_KEY_ID" \
      --issuer "$APPLE_API_ISSUER" \
      --wait
    rm -f "$key_path"
    return 0
  fi

  xcrun notarytool submit "$path" \
    --apple-id "$APPLE_ID" \
    --password "$APPLE_APP_PASSWORD" \
    --team-id "$APPLE_TEAM_ID" \
    --wait
}

sign_binary() {
  local path="$1"
  local identity="$2"
  codesign --force --timestamp --options runtime --sign "$identity" "$path"
}

sign_bundle_contents() {
  local app_path="$1"
  local identity="$2"

  while IFS= read -r candidate; do
    [[ -z "$candidate" ]] && continue
    sign_binary "$candidate" "$identity"
  done < <(
    find "$app_path" -type f \( \
      -path '*/Contents/MacOS/*' -o \
      -name '*.dylib' -o \
      -name '*.so' -o \
      -perm -111 \
    \) | awk '{ print length, $0 }' | sort -rn | cut -d' ' -f2-
  )

  codesign --force --timestamp --options runtime --sign "$identity" "$app_path"
}

PLATFORM_DIR="${1:-$(detect_platform_dir)}"
PRODUCT_NAME="PDF Bookmarks Builder"
BUNDLE_DIR="$DESKTOP_DIR/src-tauri/target/release/bundle"
ARCH_SUFFIX="$(platform_arch_suffix "$PLATFORM_DIR")"
APP_ARCHIVE="$(find "$BUNDLE_DIR/macos" -maxdepth 1 -name '*.app.tar.gz' | head -n 1 || true)"

if [[ -z "$APP_ARCHIVE" || ! -f "$APP_ARCHIVE" ]]; then
  echo "Nao foi encontrado nenhum bundle .app.tar.gz em $BUNDLE_DIR/macos."
  exit 1
fi

VERSION="$(DESKTOP_DIR="$DESKTOP_DIR" python3 - <<'PY'
import json
import os
from pathlib import Path
path = Path(os.environ["DESKTOP_DIR"]) / 'src-tauri' / 'tauri.conf.json'
print(json.loads(path.read_text())['version'])
PY
)"

WORK_DIR="$DESKTOP_DIR/.bundle-work/$PLATFORM_DIR"
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"
tar -xzf "$APP_ARCHIVE" -C "$WORK_DIR"

APP_PATH="$(find "$WORK_DIR" -maxdepth 2 -name '*.app' -type d | head -n 1 || true)"
if [[ -z "$APP_PATH" || ! -d "$APP_PATH" ]]; then
  echo "Nao foi possivel extrair o .app a partir de $APP_ARCHIVE."
  exit 1
fi

if [[ -n "${APPLE_SIGNING_IDENTITY:-}" ]]; then
  sign_bundle_contents "$APP_PATH" "$APPLE_SIGNING_IDENTITY"
  codesign --verify --deep --strict --verbose=2 "$APP_PATH"
else
  echo "APPLE_SIGNING_IDENTITY ausente. O build macOS sera gerado sem assinatura distribuivel."
fi

APP_ZIP="$BUNDLE_DIR/macos/${PRODUCT_NAME}.app.zip"
rm -f "$APP_ZIP"
ditto -c -k --keepParent "$APP_PATH" "$APP_ZIP"

if has_notary_credentials; then
  if [[ -z "${APPLE_SIGNING_IDENTITY:-}" ]]; then
    echo "Credenciais de notarizacao detectadas, mas APPLE_SIGNING_IDENTITY esta ausente."
    exit 1
  fi
  notarize_file "$APP_ZIP"
  xcrun stapler staple "$APP_PATH"
fi

DMG_PATH="$BUNDLE_DIR/dmg/${PRODUCT_NAME}_${VERSION}_${ARCH_SUFFIX}.dmg"
rm -f "$DMG_PATH"
hdiutil create -volname "$PRODUCT_NAME" -srcfolder "$APP_PATH" -ov -format UDZO "$DMG_PATH" >/dev/null

if has_notary_credentials; then
  notarize_file "$DMG_PATH"
  xcrun stapler staple "$DMG_PATH"
fi

echo "Bundle macOS preparado em: $APP_PATH"
echo "DMG final em: $DMG_PATH"
