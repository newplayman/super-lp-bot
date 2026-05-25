#!/usr/bin/env bash
# validate-shadow-binary.sh
# Validates that the lpbot-shadow binary is built in shadow mode before starting service.

set -euo pipefail

ROOT_DIR="${1:-${LPBOT_ROOT:-/opt/lpbot/lp-bot-v3}}"
BIN_PATH="${ROOT_DIR}/bin/lpbot-shadow"
CFG_PATH="${2:-${LPBOT_SHADOW_CONFIG:-${ROOT_DIR}/configs/config.shadow.toml}}"

if [ ! -x "$BIN_PATH" ]; then
  echo "validate-shadow-binary: missing executable $BIN_PATH" >&2
  exit 1
fi

if [ ! -f "$CFG_PATH" ]; then
  echo "validate-shadow-binary: missing config file $CFG_PATH" >&2
  exit 1
fi

version_line="$("$BIN_PATH" --version)"
if ! printf '%s\n' "$version_line" | grep -Fq "mode: shadow"; then
  echo "validate-shadow-binary: binary mode check failed: $version_line" >&2
  exit 1
fi

if ! awk '
  BEGIN { in_mode = 0; found_expected = 0 }
  /^\[mode\]/ { in_mode = 1; next }
  /^\[[^ ]+\]/ {
    if (in_mode) {
      exit 1
    }
  }
  in_mode && $0 ~ /^[[:space:]]*expected[[:space:]]*=[[:space:]]*"/ {
    split($0, a, "=")
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", a[2])
    gsub(/^"|"$/, "", a[2])
    if (a[2] == "shadow") {
      found_expected = 1
      exit 0
    }
    exit 1
  }
  END { exit (found_expected ? 0 : 1) }
' "$CFG_PATH"; then
  echo "validate-shadow-binary: config mode expected value is not shadow in $CFG_PATH" >&2
  exit 1
fi

exit 0
