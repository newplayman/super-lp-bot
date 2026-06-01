#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: $0 RUN_ID" >&2
  exit 2
fi

RUN_ID="$1"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL_REPORT_DIR="${ROOT_DIR}/reports/lp_bsc_fee_velocity_overnight/${RUN_ID}"
REMOTE_HOST="${LPBOT_VPS_HOST:-vps}"
REMOTE_REPO="${LPBOT_VPS_REPO:-/opt/lpbot/lp-bot-v3-origin-check}"
REMOTE_FALLBACK="/tmp/lp_bsc_fee_velocity_overnight_${RUN_ID}"
REMOTE_RUN_DIR="${LPBOT_VPS_RUN_DIR:-${REMOTE_REPO}/reports/lp_bsc_fee_velocity_overnight/${RUN_ID}}"
SSH_OPTS=( -A -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10 )

mkdir -p "$LOCAL_REPORT_DIR"

remote_path="$(
  ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" "bash -lc '
    if [ -d \"${REMOTE_RUN_DIR}\" ]; then
      printf \"%s\" \"${REMOTE_RUN_DIR}\"
    elif [ -d \"${REMOTE_FALLBACK}\" ]; then
      printf \"%s\" \"${REMOTE_FALLBACK}\"
    else
      exit 3
    fi
  '"
)"

if [ -z "$remote_path" ]; then
  echo "remote run dir not found" >&2
  exit 3
fi

rsync -az --delete -e "ssh ${SSH_OPTS[*]}" \
  "$REMOTE_HOST:$remote_path/" \
  "$LOCAL_REPORT_DIR/"

if [ ! -f "${LOCAL_REPORT_DIR}/final/FINAL_VERDICT.json" ] && [ -f "${LOCAL_REPORT_DIR}/FINAL_VERDICT.json" ]; then
  :
fi

if [ ! -f "${LOCAL_REPORT_DIR}/final/FINAL_VERDICT.json" ] && [ ! -f "${LOCAL_REPORT_DIR}/FINAL_VERDICT.json" ]; then
  echo "FINAL_VERDICT.json missing after sync" >&2
  exit 4
fi

echo "synced_from=${REMOTE_HOST}:${remote_path}"
echo "local_report_dir=${LOCAL_REPORT_DIR}"
