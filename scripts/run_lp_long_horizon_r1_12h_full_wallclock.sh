#!/usr/bin/env bash
# R1 12h FULL WALLCLOCK wrapper (12 ckpt × 3600s = 43200s).
# Hard requirements (per user acceptance):
#   - duration_wallclock_seconds >= 43200
#   - checkpoint_count = 12
#   - checkpoint_interval_seconds = 3600
#   - compressed = false
#   - short_supervisor_used = false
#   - full_supervisor_used = true
#   - coverage_scope = partial_solana_bsc_real_universe_r1_12h_full_wallclock
# Uses env var LP_R1_12H_DATA_DIR to redirect supervisor output; does NOT
# sed-rewrite the supervisor path (which previously broke REPO_ROOT).
set -euo pipefail

RUN_ID="${1:?RUN_ID required}"
DURATION_HOURS="${2:-12}"
CHECKPOINT_COUNT="${3:-12}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

export LP_R1_12H_RUN_ID="${RUN_ID}"
export LP_R1_12H_DURATION_HOURS="${DURATION_HOURS}"
export LP_R1_12H_CHECKPOINT_COUNT="${CHECKPOINT_COUNT}"
export LP_R1_12H_MODE="readonly"
export LP_R1_12H_COVERAGE_SCOPE="partial_solana_bsc_real_universe_r1_12h_full_wallclock"
export LP_R1_12H_STAGE="LP_LONG_HORIZON_R1_12H_FULL_WALLCLOCK_REPEAT_V1"
export LP_R1_12H_FULL_WALLCLOCK="true"
export LP_R1_12H_DATA_DIR="${REPO_ROOT}/data/lp_long_horizon_r1_12h_full_wallclock/${RUN_ID}"
export LP_R1_12H_REPORT_DIR="${REPO_ROOT}/reports/lp_long_horizon_r1_12h_full_wallclock_observation/${RUN_ID}"
export LP_R1_12H_LOG_PREFIX="full_wallclock"

mkdir -p "${LP_R1_12H_DATA_DIR}" "${LP_R1_12H_REPORT_DIR}"

echo "[r1_12h_full_wallclock wrapper] RUN_ID=${RUN_ID} DURATION_HOURS=${DURATION_HOURS} DATA_DIR=${LP_R1_12H_DATA_DIR} REPORT_DIR=${LP_R1_12H_REPORT_DIR} START=$(date -u +%Y-%m-%dT%H:%M:%SZ)"

bash "${REPO_ROOT}/scripts/run_lp_long_horizon_r1_12h_stage_once.sh" "${RUN_ID}" "${DURATION_HOURS}" "${CHECKPOINT_COUNT}" \
  > "${LP_R1_12H_REPORT_DIR}/supervisor_nohup.log" 2>&1
RC=$?

echo "[r1_12h_full_wallclock wrapper] supervisor exited rc=${RC} at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
exit ${RC}
