#!/usr/bin/env bash
# Collect overnight fee-velocity artifacts into the repo's report dir.
#
# Dual mode:
#   1. If /tmp/lp_bsc_fee_velocity_overnight_<RUN_ID> exists locally, rsync
#      from there (no SSH). This is the right mode when you ARE the VPS.
#   2. Otherwise, fall back to SSH from a remote host (LPBOT_VPS_HOST or --ssh-host).
#
# Safety:
#   - --delete is NOT used. The runner may still be alive; clobbering the
#     repo report dir would (a) lose phase audit reports already written
#     and (b) race the next checkpoint write.
#   - The script NEVER overwrites a final/FINAL_VERDICT.json that the source
#     does not contain. If a stale final is detected (final mtime older than
#     checkpoint mtime), a WARNING is printed but no file is rewritten.
#   - No overnight re-run is triggered.
set -euo pipefail

usage() {
  cat <<EOF >&2
usage: $0 [--local-only] [--ssh-host HOST] [--run-id RUN_ID] [RUN_ID]

Modes:
  --local-only          Only sync from /tmp on this host; do not attempt SSH.
  --ssh-host HOST       Force SSH mode with HOST (default: \$LPBOT_VPS_HOST or 'vps').
                        If /tmp/lp_bsc_fee_velocity_overnight_<RUN_ID> exists locally,
                        local mode takes precedence unless --ssh-host is set explicitly.

Positional/--run-id RUN_ID is required.
EOF
}

LOCAL_ONLY=0
FORCE_SSH=0
SSH_HOST_OVERRIDE=""
RUN_ID=""

while [ $# -gt 0 ]; do
  case "$1" in
    --local-only)
      LOCAL_ONLY=1; shift ;;
    --ssh-host)
      FORCE_SSH=1; SSH_HOST_OVERRIDE="$2"; shift 2 ;;
    --run-id)
      RUN_ID="$2"; shift 2 ;;
    -h|--help)
      usage; exit 0 ;;
    --)
      shift; break ;;
    -*)
      echo "unknown option: $1" >&2; usage; exit 2 ;;
    *)
      if [ -z "$RUN_ID" ]; then RUN_ID="$1"; shift; else
        echo "extra positional arg: $1" >&2; usage; exit 2
      fi ;;
  esac
done

if [ -z "$RUN_ID" ]; then
  usage; exit 2
fi

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL_REPORT_DIR="${ROOT_DIR}/reports/lp_bsc_fee_velocity_overnight/${RUN_ID}"
LOCAL_RUN_DIR="/tmp/lp_bsc_fee_velocity_overnight_${RUN_ID}"

mkdir -p "$LOCAL_REPORT_DIR"

# Rsync excludes — protect phase audit reports and finalize outputs already
# in the repo from being deleted or overwritten with stale snapshots.
RSYNC_EXCLUDES=(
  --exclude='VPS_LOCAL_*' --exclude='vps_local_*'
  --exclude='LOCAL_VPS_*' --exclude='local_vps_*'
  --exclude='RUN_LOG_*'   --exclude='run_log_*'
  --exclude='CHECKPOINT_PROGRESS_*' --exclude='checkpoint_progress_*'
  --exclude='FINAL_AUTHORITY_*'      --exclude='final_authority_*'
  --exclude='RUNNING_STATUS*'        --exclude='running_status*'
  --exclude='PARTIAL_FINAL_*'
  --exclude='FINAL_VERDICT_REBUILT*' --exclude='FINAL_AUTHORITY_REBUILT*'
  --exclude='LOCAL_SYNC_FINAL_VERDICT_V2*'
  --exclude='ONEPAGE_STATUS_*'
)

do_local_sync() {
  if [ ! -d "$LOCAL_RUN_DIR" ]; then
    return 1
  fi
  echo "synced_from=local:${LOCAL_RUN_DIR}"
  rsync -av "${RSYNC_EXCLUDES[@]}" "$LOCAL_RUN_DIR/" "$LOCAL_REPORT_DIR/"
  echo "local_report_dir=${LOCAL_REPORT_DIR}"
  return 0
}

do_ssh_sync() {
  local ssh_host="${1:-${LPBOT_VPS_HOST:-vps}}"
  local remote_repo="${LPBOT_VPS_REPO:-/opt/lpbot/lp-bot-v3-origin-check}"
  local remote_fallback="/tmp/lp_bsc_fee_velocity_overnight_${RUN_ID}"
  local remote_run_dir="${LPBOT_VPS_RUN_DIR:-${remote_repo}/reports/lp_bsc_fee_velocity_overnight/${RUN_ID}}"
  local ssh_opts=( -A -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10 )

  local remote_path
  remote_path="$(
    ssh "${ssh_opts[@]}" "$ssh_host" "bash -lc '
      if [ -d \"${remote_run_dir}\" ]; then
        printf \"%s\" \"${remote_run_dir}\"
      elif [ -d \"${remote_fallback}\" ]; then
        printf \"%s\" \"${remote_fallback}\"
      else
        exit 3
      fi
    '"
  )"
  if [ -z "$remote_path" ]; then
    echo "remote run dir not found at ${ssh_host}" >&2
    return 3
  fi
  echo "synced_from=${ssh_host}:${remote_path}"
  rsync -az -e "ssh ${ssh_opts[*]}" "${RSYNC_EXCLUDES[@]}" \
    "${ssh_host}:${remote_path}/" "${LOCAL_REPORT_DIR}/"
  echo "local_report_dir=${LOCAL_REPORT_DIR}"
  return 0
}

# Mode selection ----------------------------------------------------------
if [ "$FORCE_SSH" = "1" ]; then
  do_ssh_sync "$SSH_HOST_OVERRIDE"
elif [ "$LOCAL_ONLY" = "1" ]; then
  if ! do_local_sync; then
    echo "local /tmp run dir not present: $LOCAL_RUN_DIR" >&2
    exit 3
  fi
elif [ -d "$LOCAL_RUN_DIR" ]; then
  do_local_sync
else
  do_ssh_sync ""
fi

# Post-sync sanity --------------------------------------------------------
if [ ! -f "${LOCAL_REPORT_DIR}/final/FINAL_VERDICT.json" ] && [ ! -f "${LOCAL_REPORT_DIR}/FINAL_VERDICT.json" ]; then
  echo "FINAL_VERDICT.json missing after sync" >&2
  exit 4
fi

# Stale-final detection ---------------------------------------------------
final_path=""
if [ -f "${LOCAL_REPORT_DIR}/final/FINAL_VERDICT.json" ]; then
  final_path="${LOCAL_REPORT_DIR}/final/FINAL_VERDICT.json"
elif [ -f "${LOCAL_REPORT_DIR}/FINAL_VERDICT.json" ]; then
  final_path="${LOCAL_REPORT_DIR}/FINAL_VERDICT.json"
fi
state_path="${LOCAL_REPORT_DIR}/checkpoint/state.json"
log_path="${LOCAL_REPORT_DIR}/logs/run.log"

stale_warned=0
if [ -n "$final_path" ] && [ -f "$state_path" ]; then
  final_mtime=$(stat -c '%Y' "$final_path" 2>/dev/null || stat -f '%m' "$final_path" 2>/dev/null || echo 0)
  state_mtime=$(stat -c '%Y' "$state_path" 2>/dev/null || stat -f '%m' "$state_path" 2>/dev/null || echo 0)
  if [ "$final_mtime" -lt "$state_mtime" ]; then
    echo "WARNING: final exists but may be stale; checkpoint/log should be audited."
    echo "  final_mtime=${final_mtime} state_mtime=${state_mtime}"
    echo "  checkpoint/state.json is more recent than final/FINAL_VERDICT.json by $((state_mtime - final_mtime)) seconds."
    stale_warned=1
  fi
fi

if [ -f "$log_path" ] && [ -n "$final_path" ]; then
  log_mtime=$(stat -c '%Y' "$log_path" 2>/dev/null || stat -f '%m' "$log_path" 2>/dev/null || echo 0)
  final_mtime=$(stat -c '%Y' "$final_path" 2>/dev/null || stat -f '%m' "$final_path" 2>/dev/null || echo 0)
  if [ "$log_mtime" -gt "$final_mtime" ] && [ "$stale_warned" = "0" ]; then
    echo "WARNING: final exists but may be stale; checkpoint/log should be audited."
    echo "  logs/run.log is more recent than final/FINAL_VERDICT.json by $((log_mtime - final_mtime)) seconds."
  fi
fi

echo "sync_done=ok run_id=${RUN_ID}"
