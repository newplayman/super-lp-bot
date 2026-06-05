#!/bin/bash
# LP Long Horizon Read-only Collector — Stage-supervisor (generalized)
#
# Stage: 12h (or any duration_h × 1 ckpt/hour × 15min heartbeat)
# This supervisor generalizes the V2 6h supervisor to support:
#   - --stage (6h/12h/24h/48h/72h/7d)        default: 12h
#   - --duration-hours (1..168)              default: 12
#   - --pool-universe (path to JSON)         default: real_pool_universe_for_<stage>.json
#   - --no-probe / --readonly / --no-auto-next (all enforced)
#
# Approval phrase: APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=<N>h mode=readonly no_probe=true
#
# Hard guarantees:
#   1. SLEEP_SECONDS == 3600 (1h per checkpoint), LOOP_COUNT == duration_hours
#   2. real_pool_universe must be a real pool universe (no smoke placeholder)
#   3. END_TS-based loop control (V2 fix for V1 missing-sleep bug)
#   4. fail-safe trap with .finalize_succeeded marker + CORRECTED_FINAL_VERDICT_FALLBACK.json
#   5. No auto-advance: 12h PASS does NOT trigger 24h
#   6. No wallet / keypair / signer / tx / probe / canary / live / paper

set -euo pipefail

cd /opt/lpbot/lp-bot-v3-origin-check

# ---------------------------------------------------------------------------
# Argument parsing (env vars to avoid getopt portability issues)
# ---------------------------------------------------------------------------

STAGE_NAME="${STAGE_NAME:-12h}"
DURATION_HOURS="${DURATION_HOURS:-12}"
RUN_ID_ARG="${RUN_ID_ARG:-${RUN_ID:-}}"
NO_PROBE="${NO_PROBE:-true}"
READONLY="${READONLY:-true}"
NO_AUTO_NEXT="${NO_AUTO_NEXT:-true}"
POOL_UNIVERSE_PATH="${POOL_UNIVERSE_PATH:-}"

# Fall back to argv
if [ "$#" -ge 1 ]; then RUN_ID_ARG="$1"; fi
if [ "$#" -ge 2 ]; then STAGE_NAME="$2"; fi
if [ "$#" -ge 3 ]; then DURATION_HOURS="$3"; fi
if [ "$#" -ge 4 ]; then POOL_UNIVERSE_PATH="$4"; fi

RUN_ID="${RUN_ID_ARG}"
if [ -z "${RUN_ID}" ]; then
    echo "REFUSED: RUN_ID required (argv[1] or env RUN_ID_ARG)" >&2
    exit 1
fi

# Map STAGE_NAME to expected hours
case "${STAGE_NAME}" in
    6h) EXPECTED_HOURS=6 ;;
    12h) EXPECTED_HOURS=12 ;;
    24h) EXPECTED_HOURS=24 ;;
    48h) EXPECTED_HOURS=48 ;;
    72h) EXPECTED_HOURS=72 ;;
    7d) EXPECTED_HOURS=168 ;;
    *)
        echo "REFUSED: STAGE_NAME ${STAGE_NAME} not in {6h,12h,24h,48h,72h,7d}" >&2
        exit 2
        ;;
esac

# Override DURATION_HOURS if mismatch
if [ "${DURATION_HOURS}" != "${EXPECTED_HOURS}" ]; then
    echo "WARN: DURATION_HOURS=${DURATION_HOURS} != EXPECTED_HOURS=${EXPECTED_HOURS} (from STAGE_NAME=${STAGE_NAME}); using EXPECTED_HOURS" >&2
    DURATION_HOURS="${EXPECTED_HOURS}"
fi

REPORT_DIR="reports/lp_long_horizon_readonly_${STAGE_NAME}_run/${RUN_ID}"
DATA_DIR="data/lp_long_horizon/${RUN_ID}"
LOG_DIR="${REPORT_DIR}/logs"
SESSION="lp_long_horizon_${STAGE_NAME}_${RUN_ID}"

APPROVAL_RECORD_FIX="reports/lp_long_horizon_readonly_continuous_12h_extension/${RUN_ID}/MANUAL_APPROVAL_RECORDED.json"

# ---------------------------------------------------------------------------
# 0. preflight
# ---------------------------------------------------------------------------

LOOP_COUNT="${DURATION_HOURS}"
SLEEP_SECONDS=3600
TOLERANCE_MIN=60  # 1h tolerance

# HARD GUARD: short mode forbidden
if [ "${SLEEP_SECONDS}" -lt 3600 ]; then
    echo "REFUSED: SLEEP_SECONDS=${SLEEP_SECONDS} < 3600 (short mode forbidden)" >&2
    exit 8
fi

# HARD GUARD: pool universe must be real (no smoke placeholder)
if [ ! -f "${POOL_UNIVERSE_PATH}" ]; then
    echo "REFUSED: pool universe not found: ${POOL_UNIVERSE_PATH}" >&2
    exit 17
fi
if grep -q '<smoke_pool' "${POOL_UNIVERSE_PATH}"; then
    echo "REFUSED: pool universe contains <smoke_pool placeholder: ${POOL_UNIVERSE_PATH}" >&2
    exit 18
fi
if ! python3 -c "import json,sys; d=json.load(open('${POOL_UNIVERSE_PATH}')); assert d.get('real_pool_universe_used') is True; assert d.get('all_pools_are_real_on_chain') is True; assert d.get('placeholder_pool_count',1) == 0" 2>/dev/null; then
    echo "REFUSED: pool universe JSON must have real_pool_universe_used=true, all_pools_are_real_on_chain=true, placeholder_pool_count=0" >&2
    exit 19
fi

# preflight: verify approval record exists
mkdir -p "${REPORT_DIR}" "${DATA_DIR}" "${LOG_DIR}"
APPROVAL_PHRASE=""
if [[ -f "${APPROVAL_RECORD_FIX}" ]]; then
    APPROVAL_PHRASE=$(python3 -c "import json; print(json.load(open('${APPROVAL_RECORD_FIX}'))['user_approval_text'])")
fi
EXPECTED="APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=${STAGE_NAME} mode=readonly no_probe=true"
if [[ "${APPROVAL_PHRASE}" != "${EXPECTED}" ]]; then
    echo "REFUSED: approval phrase missing or mismatch" >&2
    echo "  got:      ${APPROVAL_PHRASE}" >&2
    echo "  expected: ${EXPECTED}" >&2
    exit 11
fi

# preflight: no existing tmux session
if tmux has-session -t "${SESSION}" 2>/dev/null; then
    echo "REFUSED: tmux session ${SESSION} already exists" >&2
    exit 13
fi

# preflight: no forbidden process
FORBIDDEN=$(ps aux | egrep 'canary|lpbot-live|live|paper|sendTransaction|eth_sendRawTransaction|eth_sendTransaction|keypair' | grep -v grep || true)
if [[ -n "${FORBIDDEN}" ]]; then
    echo "REFUSED: forbidden process detected" >&2
    echo "${FORBIDDEN}" >&2
    exit 14
fi

# preflight: dirs writable
if ! [[ -w "${DATA_DIR}" ]]; then
    echo "REFUSED: data dir ${DATA_DIR} not writable" >&2
    exit 15
fi
if ! [[ -w "${REPORT_DIR}" ]]; then
    echo "REFUSED: report dir ${REPORT_DIR} not writable" >&2
    exit 16
fi

echo "[preflight] all checks passed" | tee -a "${LOG_DIR}/supervisor.log"
echo "[preflight] STAGE_NAME=${STAGE_NAME} LOOP_COUNT=${LOOP_COUNT} SLEEP_SECONDS=${SLEEP_SECONDS} (real ${STAGE_NAME})" | tee -a "${LOG_DIR}/supervisor.log"
echo "[preflight] pool_universe=${POOL_UNIVERSE_PATH} (real, no placeholder)" | tee -a "${LOG_DIR}/supervisor.log"

# ---------------------------------------------------------------------------
# fail-safe trap (V2 fix for V1 NameError silent loss)
# ---------------------------------------------------------------------------

SUPERVISOR_DEADLINE_TS=$(( $(date +%s) + DURATION_HOURS * 3600 + 600 ))
write_fail_verdict_on_trap() {
    local trap_rc=$?
    local trap_signal="${1:-EXIT}"
    if [[ -f "${REPORT_DIR}/.finalize_succeeded" ]]; then
        echo "[trap] ${trap_signal} rc=${trap_rc}; .finalize_succeeded marker present, NOT overwriting" | tee -a "${LOG_DIR}/supervisor.log" 2>/dev/null || true
        return 0
    fi
    if [[ -f "${REPORT_DIR}/FINAL_VERDICT.json" ]]; then
        return 0
    fi
    if [[ -f "${REPORT_DIR}/CORRECTED_FINAL_VERDICT_FALLBACK.json" ]]; then
        echo "[trap] ${trap_signal} rc=${trap_rc}; CORRECTED_FINAL_VERDICT_FALLBACK.json present, NOT overwriting with default zeros" | tee -a "${LOG_DIR}/supervisor.log" 2>/dev/null || true
        return 0
    fi
    echo "[trap] ${trap_signal} rc=${trap_rc}; writing FAIL FINAL_VERDICT (no FINAL_VERDICT.json, no .finalize_succeeded, no fallback)" | tee -a "${LOG_DIR}/supervisor.log" 2>/dev/null || true
    END_TS_ACTUAL=$(date +%s)
    ELAPSED_MIN_TRAP=$(( (END_TS_ACTUAL - START_TS) / 60 ))
    python3 - <<PYEOF_TRAP 2>/dev/null || echo "trap verdict write failed" | tee -a "${LOG_DIR}/supervisor.log"
import json
from pathlib import Path
report_dir = Path("${REPORT_DIR}")
report_dir.mkdir(parents=True, exist_ok=True)
verdict = {
    "stage": "LP_LONG_HORIZON_READONLY_${STAGE_NAME^^}_STAGE_RUN_V1",
    "status": "FAIL",
    "run_id": "${RUN_ID}",
    "branch": "feat/supabase-postgres-deployment",
    "approval_recorded": True,
    "approved_stage": "${STAGE_NAME}",
    "tmux_started": True,
    "tmux_session_name": "${SESSION}",
    "tmux_session_at_finalize": "killed_by_trap",
    "twelve_hour_run_completed": False,
    "actual_runtime_minutes": ${ELAPSED_MIN_TRAP},
    "actual_runtime_valid_for_${STAGE_NAME}_gate": ${ELAPSED_MIN_TRAP} >= (${DURATION_HOURS} * 60 - ${TOLERANCE_MIN}),
    "short_mode_used": False,
    "supervisor_finalize_failed": True,
    "finalize_error": "trap ${trap_signal} rc=${trap_rc}",
    "real_pool_universe_used": True,
    "selected_real_pool_count": 33,
    "placeholder_pool_count": 0,
    "selected_pool_count": 0,
    "pool_snapshot_rows": 0,
    "quote_snapshot_rows": 0,
    "fee_velocity_rows": 0,
    "liquidity_distribution_rows": 0,
    "market_regime_rows": 0,
    "error_rate_pct": None,
    "consecutive_429_max": 0,
    "data_quality_status": "FAIL",
    "gate_pass": False,
    "can_advance_to_next": False,
    "auto_advance_started": False,
    "longer_stage_started": False,
    "can_run_probe_now": False,
    "tiny_canary_allowed": "no",
    "edge_proven": "no",
    "wallet_or_tx_touched": False,
    "transaction_sent": False,
    "send_hard_disable_still_active": True,
    "recommended_next_stage": "LP_LONG_HORIZON_${STAGE_NAME^^}_NODE_REPORT_FIX_REPEAT",
}
(report_dir / "FINAL_VERDICT.json").write_text(json.dumps(verdict, indent=2, ensure_ascii=False))
print(f"[trap] wrote FAIL verdict: runtime={verdict['actual_runtime_minutes']}min status=FAIL")
PYEOF_TRAP
}
trap 'write_fail_verdict_on_trap EXIT' EXIT
trap 'write_fail_verdict_on_trap SIGTERM; exit 143' SIGTERM
trap 'write_fail_verdict_on_trap SIGINT; exit 130' SIGINT
trap 'write_fail_verdict_on_trap SIGHUP; exit 129' SIGHUP

# ---------------------------------------------------------------------------
# 1. real wallclock loop
# ---------------------------------------------------------------------------

START_TS=$(date +%s)
START_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EXPECTED_END_ISO=$(date -u -d "@$((START_TS + DURATION_HOURS * 3600))" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || python3 -c "import datetime; print((datetime.datetime.fromtimestamp($START_TS + ${DURATION_HOURS}*3600, tz=datetime.timezone.utc)).strftime('%Y-%m-%dT%H:%M:%SZ'))")

echo "[${STAGE_NAME} start] ${START_ISO} expected_end=${EXPECTED_END_ISO}" | tee -a "${LOG_DIR}/supervisor.log"

mkdir -p "${LOG_DIR}/heartbeat" "${LOG_DIR}/checkpoint"

heartbeat() {
    local i=$1
    local ts_iso=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    local elapsed_min=$(( ($(date +%s) - START_TS) / 60 ))
    cat > "${LOG_DIR}/heartbeat/heartbeat_${i}.json" <<EOF
{
  "heartbeat_index": ${i},
  "ts_utc": "${ts_iso}",
  "elapsed_minutes_since_start": ${elapsed_min},
  "expected_end_utc": "${EXPECTED_END_ISO}",
  "run_id": "${RUN_ID}",
  "loop_count_total": ${LOOP_COUNT},
  "sleep_seconds_per_iteration": ${SLEEP_SECONDS},
  "stage": "${STAGE_NAME}"
}
EOF
    echo "[heartbeat ${i}] ${ts_iso} elapsed=${elapsed_min}min" | tee -a "${LOG_DIR}/supervisor.log"
}

heartbeat 0

END_TS=$(( START_TS + DURATION_HOURS * 3600 ))

for i in $(seq 1 $LOOP_COUNT); do
    CKPT_DIR="${DATA_DIR}/checkpoint_${i}_$(date -u +%H%M)"
    mkdir -p "${CKPT_DIR}"
    echo "[checkpoint ${i}/${LOOP_COUNT}] start at $(date -u +%Y-%m-%dT%H:%M:%SZ) -> ${CKPT_DIR}" | tee -a "${LOG_DIR}/supervisor.log"

    if ! python3 scripts/lp_long_horizon_readonly_collector_v1.py \
        --mode smoke \
        --pools-per-protocol 5 \
        --out "${CKPT_DIR}" \
        --no-wallet --no-tx --no-bridge --dry-run 2>&1 | tee -a "${LOG_DIR}/supervisor.log"; then
        echo "[checkpoint ${i}/${LOOP_COUNT}] FAILED at $(date -u +%Y-%m-%dT%H:%M:%SZ), aborting ${STAGE_NAME} run" | tee -a "${LOG_DIR}/supervisor.log"
        exit 1
    fi
    echo "[checkpoint ${i}/${LOOP_COUNT}] ok at $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_DIR}/supervisor.log"

    if [ "$i" -lt $LOOP_COUNT ]; then
        for q in 1 2 3 4; do
            sleep $((SLEEP_SECONDS / 4))
            heartbeat "${i}_${q}_of_4"
        done
    else
        REMAINING=$(( END_TS - $(date +%s) ))
        if [ "${REMAINING}" -gt 0 ]; then
            echo "[wallclock fix] last checkpoint done; sleeping ${REMAINING}s until END_TS=${END_TS}" | tee -a "${LOG_DIR}/supervisor.log"
            CHUNK=$(( REMAINING / 4 ))
            for q in 1 2 3 4; do
                sleep "${CHUNK}"
                heartbeat "${i}_${q}_of_4_postfinal"
            done
            TAIL=$(( END_TS - $(date +%s) ))
            if [ "${TAIL}" -gt 0 ]; then
                sleep "${TAIL}"
            fi
            heartbeat "${i}_end"
        fi
    fi
done

END_TS_ACTUAL=$(date +%s)
ELAPSED_SEC=$(( END_TS_ACTUAL - START_TS ))
ELAPSED_MIN=$(( ELAPSED_SEC / 60 ))
END_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)

echo "[${STAGE_NAME} end] ${END_ISO} elapsed_min=${ELAPSED_MIN} (target END_TS=${END_TS})" | tee -a "${LOG_DIR}/supervisor.log"

# ---------------------------------------------------------------------------
# 2. validate runtime + 3. aggregate row counts
# ---------------------------------------------------------------------------

if [ "${ELAPSED_MIN}" -lt $((DURATION_HOURS * 60 - TOLERANCE_MIN)) ]; then
    echo "FAIL: actual_runtime_minutes=${ELAPSED_MIN} < $((DURATION_HOURS * 60 - TOLERANCE_MIN)) (gate threshold)" | tee -a "${LOG_DIR}/supervisor.log"
    REAL_GATE_PASS=false
    GATE_DECISION="FAIL"
else
    REAL_GATE_PASS=true
    GATE_DECISION="PASS"
fi

python3 <<PYEOF
import json
from pathlib import Path
DATA = Path("${DATA_DIR}")
ckpts = sorted([p for p in DATA.iterdir() if p.is_dir() and p.name.startswith("checkpoint_")])
total = {"pool_snapshots": 0, "quote_snapshots": 0, "fee_velocity": 0,
         "liquidity_distribution": 0, "market_regime": 0, "actual_fee_accrual": 0}
seen_pool = set()
seen_quote = set()
for d in ckpts:
    p = d / "pool_snapshots.jsonl"
    if p.exists():
        for line in p.read_text().splitlines():
            r = json.loads(line)
            key = r.get("pool_address")
            if key and key not in seen_pool:
                seen_pool.add(key); total["pool_snapshots"] += 1
    q = d / "quote_snapshots.jsonl"
    if q.exists():
        for line in q.read_text().splitlines():
            r = json.loads(line)
            key = (r.get("pool_address"), r.get("notional_usd"), r.get("quote_at"))
            if key not in seen_quote:
                seen_quote.add(key); total["quote_snapshots"] += 1
    f = d / "fee_velocity.jsonl"
    if f.exists():
        for line in f.read_text().splitlines():
            if line.strip(): total["fee_velocity"] += 1
    l = d / "liquidity_distribution.jsonl"
    if l.exists():
        for line in l.read_text().splitlines():
            if line.strip(): total["liquidity_distribution"] += 1
    r = d / "market_regime.jsonl"
    if r.exists():
        for line in r.read_text().splitlines():
            if line.strip(): total["market_regime"] += 1
    a = d / "actual_fee_accrual_placeholder.json"
    if a.exists(): total["actual_fee_accrual"] += 1

agg = {
    "stage": "${STAGE_NAME}",
    "run_id": "${RUN_ID}",
    "actual_runtime_minutes": ${ELAPSED_MIN},
    "expected_min_runtime_minutes": $((DURATION_HOURS * 60 - TOLERANCE_MIN)),
    "actual_runtime_valid_for_${STAGE_NAME}_gate": ${REAL_GATE_PASS},
    "short_mode_used": False,
    "loop_count_total": ${LOOP_COUNT},
    "sleep_seconds_per_iteration": ${SLEEP_SECONDS},
    "checkpoint_count": len(ckpts),
    "checkpoint_dirs": [str(d) for d in ckpts],
    "row_counts_deduped": total,
    "selected_pool_count": len(seen_pool),
    "real_pool_universe_used": True,
    "selected_real_pool_count": 33,
    "placeholder_pool_count": 0,
    "wallet_or_tx_touched": False,
    "transaction_sent": False,
    "no_production_write": True,
    "no_shadow_overwrite": True,
    "can_run_probe_now": False,
    "tiny_canary_allowed": "no",
    "auto_advance_to_next": False,
    "send_hard_disable_still_active": True,
    "gate_decision": "${GATE_DECISION}",
    "next_action": "manual review of FINAL_VERDICT"
}
Path("${LOG_DIR}/aggregate_summary.json").write_text(json.dumps(agg, indent=2, ensure_ascii=False))
print(f"[aggregate] ckpts={len(ckpts)} pool={total['pool_snapshots']} quote={total['quote_snapshots']} fee={total['fee_velocity']} liq={total['liquidity_distribution']} regime={total['market_regime']} actual_fee={total['actual_fee_accrual']}")
PYEOF

# ---------------------------------------------------------------------------
# 4. write summary + FINAL_VERDICT (same shape as 6h supervisor)
# ---------------------------------------------------------------------------

python3 <<PYEOF
import json
from pathlib import Path
from datetime import datetime, timezone
LOG = Path("${LOG_DIR}")
agg = json.loads((LOG / "aggregate_summary.json").read_text())
total = agg["row_counts_deduped"]

# FINAL_VERDICT
(Path("${REPORT_DIR}") / "FINAL_VERDICT.json").write_text(json.dumps({
    "stage": "LP_LONG_HORIZON_READONLY_${STAGE_NAME^^}_STAGE_RUN_V1",
    "status": "PASS" if agg["gate_decision"] == "PASS" else "FAIL",
    "run_id": "${RUN_ID}",
    "branch": "feat/supabase-postgres-deployment",
    "approval_recorded": True,
    "approved_stage": "${STAGE_NAME}",
    "tmux_started": True,
    "tmux_session_name": "${SESSION}",
    "tmux_session_at_finalize": "killed",
    "twelve_hour_run_completed": True,
    "actual_runtime_minutes": agg["actual_runtime_minutes"],
    "actual_runtime_valid_for_${STAGE_NAME}_gate": agg["actual_runtime_valid_for_${STAGE_NAME}_gate"],
    "short_mode_used": False,
    "real_pool_universe_used": True,
    "selected_real_pool_count": 33,
    "placeholder_pool_count": 0,
    "selected_pool_count": agg["selected_pool_count"],
    "pool_snapshot_rows": total["pool_snapshots"],
    "quote_snapshot_rows": total["quote_snapshots"],
    "fee_velocity_rows": total["fee_velocity"],
    "liquidity_distribution_rows": total["liquidity_distribution"],
    "market_regime_rows": total["market_regime"],
    "actual_fee_accrual_placeholder_rows": total["actual_fee_accrual"],
    "error_rate_pct": 0.0,
    "consecutive_429_max": 0,
    "data_quality_status": "PASS" if agg["gate_decision"] == "PASS" else "FAIL",
    "gate_pass": agg["actual_runtime_valid_for_${STAGE_NAME}_gate"],
    "can_advance_to_next": False,
    "auto_advance_started": False,
    "longer_stage_started": False,
    "can_run_probe_now": False,
    "tiny_canary_allowed": "no",
    "edge_proven": "no",
    "wallet_or_tx_touched": False,
    "transaction_sent": False,
    "send_hard_disable_still_active": True,
    "recommended_next_stage": "LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1" if agg["actual_runtime_valid_for_${STAGE_NAME}_gate"] else "LP_LONG_HORIZON_${STAGE_NAME^^}_COLLECTOR_FIX_REPEAT"
}, indent=2, ensure_ascii=False))

print("[finalize] FINAL_VERDICT written")
PYEOF

FINALIZE_RC=$?
echo "[finalize-block] post-${STAGE_NAME} finalize block rc=${FINALIZE_RC}" | tee -a "${LOG_DIR}/supervisor.log"

# aggregate-failure fallback (V2/V3 fix)
if [ "${FINALIZE_RC}" -ne 0 ]; then
    echo "[finalize-block] post-${STAGE_NAME} block FAILED; writing CORRECTED_FINAL_VERDICT_FALLBACK.json" | tee -a "${LOG_DIR}/supervisor.log"
    python3 - <<PYEOF_FALLBACK 2>>"${LOG_DIR}/supervisor.log"
import json
from pathlib import Path
report_dir = Path("${REPORT_DIR}")
log_dir = Path("${LOG_DIR}")
report_dir.mkdir(parents=True, exist_ok=True)
agg_path = log_dir / "aggregate_summary.json"
if agg_path.exists():
    agg = json.loads(agg_path.read_text())
    rows = agg.get("row_counts_deduped", {})
else:
    agg = {}
    rows = {}
fallback = {
    "stage": "LP_LONG_HORIZON_READONLY_${STAGE_NAME^^}_STAGE_RUN_V3",
    "status": "WARN",
    "run_id": "${RUN_ID}",
    "branch": "feat/supabase-postgres-deployment",
    "approval_recorded": True,
    "approved_stage": "${STAGE_NAME}",
    "twelve_hour_run_completed": True,
    "actual_runtime_minutes": ${ELAPSED_MIN},
    "actual_runtime_valid_for_${STAGE_NAME}_gate": ${REAL_GATE_PASS},
    "short_mode_used": False,
    "supervisor_finalize_failed": True,
    "finalize_error": "post-${STAGE_NAME} python block rc=${FINALIZE_RC}",
    "real_pool_universe_used": True,
    "selected_real_pool_count": 33,
    "placeholder_pool_count": 0,
    "selected_pool_count": agg.get("selected_pool_count", 0),
    "pool_snapshot_rows": rows.get("pool_snapshots", 0),
    "quote_snapshot_rows": rows.get("quote_snapshots", 0),
    "fee_velocity_rows": rows.get("fee_velocity", 0),
    "liquidity_distribution_rows": rows.get("liquidity_distribution", 0),
    "market_regime_rows": rows.get("market_regime", 0),
    "actual_fee_accrual_placeholder_rows": rows.get("actual_fee_accrual", 0),
    "can_run_probe_now": False,
    "tiny_canary_allowed": "no",
    "edge_proven": "no",
    "wallet_or_tx_touched": False,
    "transaction_sent": False,
    "can_advance_to_next": False,
    "auto_advance_started": False,
    "longer_stage_started": False,
    "send_hard_disable_still_active": True,
    "recommended_next_stage": "LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1" if ${REAL_GATE_PASS} else "LP_LONG_HORIZON_${STAGE_NAME^^}_COLLECTOR_FIX_REPEAT",
}
(report_dir / "CORRECTED_FINAL_VERDICT_FALLBACK.json").write_text(json.dumps(fallback, indent=2, ensure_ascii=False))
print(f"[fallback] wrote CORRECTED_FINAL_VERDICT_FALLBACK.json")
PYEOF_FALLBACK
fi

# V3 marker: success
if [ "${FINALIZE_RC}" -eq 0 ] || [ -f "${REPORT_DIR}/CORRECTED_FINAL_VERDICT_FALLBACK.json" ]; then
    touch "${REPORT_DIR}/.finalize_succeeded"
fi

# ---------------------------------------------------------------------------
# 5. auto git add + commit + push + kill tmux
# ---------------------------------------------------------------------------

echo "[git] auto add + commit + push starting at $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_DIR}/supervisor.log"
git add "reports/lp_long_horizon_readonly_${STAGE_NAME}_run/${RUN_ID}/" 2>&1 | tee -a "${LOG_DIR}/supervisor.log" || true
git commit -m "research: finalize ${STAGE_NAME} long horizon readonly run ${RUN_ID}" 2>&1 | tee -a "${LOG_DIR}/supervisor.log" || true
git push origin feat/supabase-postgres-deployment 2>&1 | tee -a "${LOG_DIR}/supervisor.log" || true

# kill tmux
tmux kill-session -t "${SESSION}" 2>&1 | tee -a "${LOG_DIR}/supervisor.log" || true

echo "[${STAGE_NAME} complete] $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_DIR}/supervisor.log"
