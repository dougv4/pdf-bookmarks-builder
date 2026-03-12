#!/usr/bin/env bash
set -euo pipefail

CERT_BASE64="${APPLE_CERTIFICATE_BASE64:-}"
CERT_PASSWORD="${APPLE_CERTIFICATE_PASSWORD:-}"

if [[ -z "$CERT_BASE64" || -z "$CERT_PASSWORD" ]]; then
  echo "APPLE_CERTIFICATE_BASE64 e APPLE_CERTIFICATE_PASSWORD sao obrigatorios para importar o certificado."
  exit 1
fi

KEYCHAIN_PASSWORD="${APPLE_KEYCHAIN_PASSWORD:-$(uuidgen)}"
RUNNER_TEMP_DIR="${RUNNER_TEMP:-/tmp}"
KEYCHAIN_PATH="${APPLE_KEYCHAIN_PATH:-$RUNNER_TEMP_DIR/pdf-bookmarks-builder-signing.keychain-db}"
CERT_PATH="$RUNNER_TEMP_DIR/pdf-bookmarks-builder-signing-cert.p12"

rm -f "$CERT_PATH"
printf '%s' "$CERT_BASE64" | base64 --decode > "$CERT_PATH"

security create-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN_PATH"
security set-keychain-settings -lut 21600 "$KEYCHAIN_PATH"
security unlock-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN_PATH"
security import "$CERT_PATH" -k "$KEYCHAIN_PATH" -P "$CERT_PASSWORD" -T /usr/bin/codesign -T /usr/bin/security -A
security set-key-partition-list -S apple-tool:,apple: -s -k "$KEYCHAIN_PASSWORD" "$KEYCHAIN_PATH"
security list-keychains -d user -s "$KEYCHAIN_PATH" login.keychain-db

if [[ -n "${GITHUB_ENV:-}" ]]; then
  {
    echo "APPLE_KEYCHAIN_PASSWORD=$KEYCHAIN_PASSWORD"
    echo "APPLE_KEYCHAIN_PATH=$KEYCHAIN_PATH"
  } >> "$GITHUB_ENV"
fi

echo "Certificado Apple importado em: $KEYCHAIN_PATH"
