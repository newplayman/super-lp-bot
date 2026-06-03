#!/usr/bin/env bash
# LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1_READONLY wrapper
# Usage: bash lp_meteora_dlmm_known_pool_feed_expansion_overnight_v1_readonly.sh \
#         --run-id <id> --output-dir <dir> [--max-hours N] [--max-pools N]
#
# This wrapper:
#   1. Sets up the Meteora SDK in an isolated /tmp install
#   2. Launches the Node.js runner
#   3. Reports status
set -uo pipefail

# Parse args
RUN_ID=""
OUTPUT_DIR=""
MAX_HOURS=10
CHECKPOINT_MINUTES=60
MAX_POOLS=50
MIN_POOLS=20
MODE="all"
TMUX_SESSION=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id)        RUN_ID="$2"; shift 2 ;;
    --output-dir)    OUTPUT_DIR="$2"; shift 2 ;;
    --max-hours)     MAX_HOURS="$2"; shift 2 ;;
    --checkpoint-minutes) CHECKPOINT_MINUTES="$2"; shift 2 ;;
    --max-pools)     MAX_POOLS="$2"; shift 2 ;;
    --min-pools)     MIN_POOLS="$2"; shift 2 ;;
    --tmux-session)  TMUX_SESSION="$2"; shift 2 ;;
    --mode)          MODE="$2"; shift 2 ;;
    *)               echo "Unknown arg: $1"; exit 2 ;;
  esac
done

if [[ -z "$RUN_ID" || -z "$OUTPUT_DIR" ]]; then
  echo "FATAL: --run-id and --output-dir required"
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$SCRIPT_DIR/lp_meteora_dlmm_known_pool_feed_expansion_overnight_v1_readonly.js"
SDK_DIR="/tmp/lpbot_meteora_dlmm_sdk_overnight_${RUN_ID}"
mkdir -p "$OUTPUT_DIR/logs" "$OUTPUT_DIR/checkpoint" "$OUTPUT_DIR/data"

# Set up isolated SDK install (if not already there)
if [[ ! -d "$SDK_DIR/node_modules/@meteora-ag/dlmm" ]]; then
  echo "[wrapper] Setting up SDK in $SDK_DIR"
  mkdir -p "$SDK_DIR"
  cat > "$SDK_DIR/package.json" <<EOF
{
  "name": "lpbot-meteora-dlmm-overnight",
  "version": "1.0.0",
  "private": true,
  "dependencies": {
    "@meteora-ag/dlmm": "1.9.10",
    "@solana/web3.js": "1.95.0"
  }
}
EOF
  (cd "$SDK_DIR" && npm install --no-audit --no-fund --silent 2>&1 | tail -20)
fi

echo "[wrapper] RUN_ID=$RUN_ID"
echo "[wrapper] OUTPUT_DIR=$OUTPUT_DIR"
echo "[wrapper] SDK_DIR=$SDK_DIR"
echo "[wrapper] RUNNER=$RUNNER"

# Run the JS pipeline directly (it handles its own tmux checkpointing)
cd "$SCRIPT_DIR"
NODE_PATH="$SDK_DIR/node_modules" node "$RUNNER" \
  --run-id "$RUN_ID" \
  --output-dir "$OUTPUT_DIR" \
  --max-hours "$MAX_HOURS" \
  --checkpoint-minutes "$CHECKPOINT_MINUTES" \
  --max-pools "$MAX_POOLS" \
  --min-pools "$MIN_POOLS" \
  --mode "$MODE" 2>&1 | tee -a "$OUTPUT_DIR/logs/wrapper.log"
RC=$?
echo "[wrapper] exit_code=$RC"
exit $RC
