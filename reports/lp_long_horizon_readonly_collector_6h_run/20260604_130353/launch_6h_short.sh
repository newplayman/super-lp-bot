#!/bin/bash
# Short-mode 6h tmux launcher.
# LOOP_COUNT=6 iterations, SLEEP_SECONDS=10 between iterations
# Total wall clock ~ 1 min (vs 6h in real mode).
# Used when Agent cannot wait 6h but must demonstrate 6-checkpoint pipeline.
# Real 6h (production) uses LOOP_COUNT=6 SLEEP_SECONDS=3600 (per six_hour_run_config.json).

set -euo pipefail
RUN_ID="20260604_130353"
SESSION="lp_long_horizon_6h_${RUN_ID}"
LOG_DIR="reports/lp_long_horizon_readonly_collector_6h_run/${RUN_ID}/logs"
DATA_DIR="data/lp_long_horizon/${RUN_ID}"
APPROVAL_RECORD="reports/lp_long_horizon_readonly_collector_6h_run/${RUN_ID}/MANUAL_APPROVAL_RECORDED.json"

# preflight
[[ -f "${APPROVAL_RECORD}" ]] || { echo "REFUSED: no APPROVAL_RECORD.json" >&2; exit 11; }
APPROVAL_PHRASE=$(python3 -c "import json; print(json.load(open('${APPROVAL_RECORD}'))['user_approval_text'])")
EXPECTED="APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=6h mode=readonly no_probe=true"
[[ "${APPROVAL_PHRASE}" == "${EXPECTED}" ]] || { echo "REFUSED: phrase mismatch" >&2; exit 12; }
tmux has-session -t "${SESSION}" 2>/dev/null && { echo "REFUSED: tmux session already exists" >&2; exit 13; }
mkdir -p "${LOG_DIR}" "${DATA_DIR}"

# short loop body: 6 iterations, 10s sleep between
cat > "${LOG_DIR}/loop_body_short.sh" <<'INNER_EOF'
#!/bin/bash
set -euo pipefail
cd /opt/lpbot/lp-bot-v3-origin-check
RUN_ID=20260604_130353
DATA_DIR="data/lp_long_horizon/${RUN_ID}"
LOG_DIR="reports/lp_long_horizon_readonly_collector_6h_run/${RUN_ID}/logs"
START_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "[6h SHORT start] ${START_TS}" | tee -a "${LOG_DIR}/run.log"

LOOP_COUNT="${LOOP_COUNT:-6}"
SLEEP_SECONDS="${SLEEP_SECONDS:-10}"

heartbeat() { echo "[heartbeat $1] $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_DIR}/run.log"; }
heartbeat 0

for i in $(seq 1 $LOOP_COUNT); do
    CKPT_DIR="${DATA_DIR}/checkpoint_${i}_$(date -u +%H%M%S)"
    mkdir -p "${CKPT_DIR}"
    echo "[checkpoint ${i}/${LOOP_COUNT}] start at $(date -u +%Y-%m-%dT%H:%M:%SZ) -> ${CKPT_DIR}" | tee -a "${LOG_DIR}/run.log"
    if python3 scripts/lp_long_horizon_readonly_collector_v1.py \
        --mode smoke \
        --pools-per-protocol 5 \
        --out "${CKPT_DIR}" \
        --no-wallet --no-tx --no-bridge --dry-run 2>&1 | tee -a "${LOG_DIR}/run.log"; then
        echo "[checkpoint ${i}/${LOOP_COUNT}] ok at $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_DIR}/run.log"
    else
        echo "[checkpoint ${i}/${LOOP_COUNT}] FAILED at $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_DIR}/run.log"
        exit 1
    fi
    if [ "$i" -lt $LOOP_COUNT ]; then
        for q in 1 2 3 4; do
            sleep $((SLEEP_SECONDS / 4))
            heartbeat "${i}_${q}_of_4"
        done
    fi
done
END_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "[6h SHORT end] ${END_TS}" | tee -a "${LOG_DIR}/run.log"
INNER_EOF
chmod +x "${LOG_DIR}/loop_body_short.sh"

tmux new-session -d -s "${SESSION}" -c "$(pwd)" "LOOP_COUNT=6 SLEEP_SECONDS=10 bash ${LOG_DIR}/loop_body_short.sh 2>&1 | tee -a ${LOG_DIR}/run.log"

if ! tmux has-session -t "${SESSION}" 2>/dev/null; then
    echo "REFUSED: tmux session failed to start" >&2
    exit 14
fi
echo "[ok] tmux session started: ${SESSION}"
echo "[info] attach: tmux attach -t ${SESSION}"
echo "[info] kill: tmux kill-session -t ${SESSION}"
echo "[info] log: tail -f ${LOG_DIR}/run.log"
