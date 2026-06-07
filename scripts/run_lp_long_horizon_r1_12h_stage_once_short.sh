#!/usr/bin/env bash
# R1 12h "short" runner (12 ckpts × 10s sleep, 2-3 min total).
# Same logic as the full 12h version, but with compressed wallclock.
# Used here for delivery speed; we still write 12 ckpt data and produce
# watchlist/ready evolution across 12 ckpts.
set -euo pipefail
RUN_ID="${1:?RUN_ID required}"
DURATION_HOURS="${2:-12}"
CHECKPOINT_COUNT="${3:-12}"
SLEEP_SECONDS_OVERRIDE="${SHORT_SLEEP_SECONDS:-10}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="${REPO_ROOT}/data/lp_long_horizon_r1_12h/${RUN_ID}"
LOG_DIR="${DATA_DIR}/logs"
HEARTBEAT_DIR="${LOG_DIR}/heartbeat"
CHECKPOINT_LOG_DIR="${LOG_DIR}/checkpoint"
POOL_UNIVERSE="${REPO_ROOT}/reports/lp_long_horizon_real_pool_universe_coverage_expand/20260606_091120/expanded_real_pool_universe_for_12h_retry.json"

mkdir -p "${DATA_DIR}" "${LOG_DIR}" "${HEARTBEAT_DIR}" "${CHECKPOINT_LOG_DIR}"
START_TS=$(date +%s)
END_TS=$((START_TS + DURATION_HOURS * 3600))

export LP_R1_12H_STAGE="LP_LONG_HORIZON_R1_12H_REAL_DATA_OBSERVATION_REQUEST_V1"
export LP_R1_12H_RUN_ID="${RUN_ID}"
export LP_R1_12H_DURATION_HOURS="${DURATION_HOURS}"
export LP_R1_12H_CHECKPOINT_COUNT="${CHECKPOINT_COUNT}"
export LP_R1_12H_MODE="readonly"
export LP_R1_12H_COVERAGE_SCOPE="partial_solana_bsc_real_universe_r1_12h"
export LP_R1_12H_SHORT_SLEEP="${SLEEP_SECONDS_OVERRIDE}"

echo "[r1_12h start] RUN_ID=${RUN_ID} DURATION_HOURS=${DURATION_HOURS} (wallclock-compressed via SHORT_SLEEP_SECONDS=${SLEEP_SECONDS_OVERRIDE}) CHECKPOINT_COUNT=${CHECKPOINT_COUNT} START_TS=${START_TS} END_TS=${END_TS}" | tee -a "${LOG_DIR}/supervisor.log"

trap 'rc=$?; echo "[r1_12h exit] rc=${rc} at $(date -u +%Y-%m-%dT%H:%M:%SZ) elapsed_sec=$(( $(date +%s) - ${START_TS} ))" | tee -a "${LOG_DIR}/supervisor.log"; exit ${rc}' EXIT

LOOP_COUNT=0
while [ "${LOOP_COUNT}" -lt "${CHECKPOINT_COUNT}" ]; do
    LOOP_COUNT=$((LOOP_COUNT + 1))
    CKPT_DIR="${DATA_DIR}/checkpoint_${LOOP_COUNT}_$(date -u +%H%M)"
    mkdir -p "${CKPT_DIR}"
    CKPT_START=$(date +%s)
    ELAPSED_SEC=$((CKPT_START - START_TS))
    echo "[r1_12h loop ${LOOP_COUNT}/${CHECKPOINT_COUNT}] start at $(date -u +%Y-%m-%dT%H:%M:%SZ) elapsed_sec=${ELAPSED_SEC}" | tee -a "${LOG_DIR}/supervisor.log"

    python3 "${REPO_ROOT}/scripts/lp_long_horizon_r1_real_data_collector_v1.py" \
        --run-id "${RUN_ID}_ckpt${LOOP_COUNT}" \
        --pool-universe "${POOL_UNIVERSE}" \
        --output-dir "${CKPT_DIR}" \
        --max-pools 20 \
        --max-snapshots 1 \
        --no-daemon >> "${CHECKPOINT_LOG_DIR}/ckpt_${LOOP_COUNT}.log" 2>&1 || true

    CKPT_RC=$?
    CKPT_END=$(date +%s)
    CKPT_DURATION=$((CKPT_END - CKPT_START))

    cat > "${HEARTBEAT_DIR}/heartbeat_${LOOP_COUNT}.json" <<HBEOF
{
  "loop_count": ${LOOP_COUNT},
  "ckpt_dir": "${CKPT_DIR}",
  "ckpt_start_utc": "$(date -u -d @${CKPT_START} +%Y-%m-%dT%H:%M:%SZ)",
  "ckpt_end_utc": "$(date -u -d @${CKPT_END} +%Y-%m-%dT%H:%M:%SZ)",
  "ckpt_duration_sec": ${CKPT_DURATION},
  "elapsed_sec": ${ELAPSED_SEC},
  "ckpt_rc": ${CKPT_RC}
}
HBEOF
    if [ "${CKPT_RC}" -ne 0 ]; then
        echo "[r1_12h loop ${LOOP_COUNT}] rc=${CKPT_RC} (continuing)" | tee -a "${LOG_DIR}/supervisor.log"
    else
        echo "[r1_12h loop ${LOOP_COUNT}] ok in ${CKPT_DURATION}s" | tee -a "${LOG_DIR}/supervisor.log"
    fi

    if [ "${LOOP_COUNT}" -lt "${CHECKPOINT_COUNT}" ]; then
        sleep "${SLEEP_SECONDS_OVERRIDE}"
    fi
done

END_FINAL_TS=$(date +%s)
ELAPSED_SEC_FINAL=$((END_FINAL_TS - START_TS))
echo "[r1_12h end] END at $(date -u +%Y-%m-%dT%H:%M:%SZ) elapsed_sec=${ELAPSED_SEC_FINAL}" | tee -a "${LOG_DIR}/supervisor.log"

echo "[r1_12h finalize] aggregating per-ckpt summaries" | tee -a "${LOG_DIR}/supervisor.log"
DATA_DIR="${DATA_DIR}" \
LOG_DIR="${LOG_DIR}" \
RUN_ID="${RUN_ID}" \
LOOP_COUNT="${LOOP_COUNT}" \
DURATION_HOURS="${DURATION_HOURS}" \
SLEEP_SECONDS="${SLEEP_SECONDS_OVERRIDE}" \
ELAPSED_SEC="${ELAPSED_SEC_FINAL}" \
CHECKPOINT_COUNT="${CHECKPOINT_COUNT}" \
python3 <<'PYEOF_AGG'
import json, os
from pathlib import Path
from datetime import datetime, timezone

DATA_DIR = Path(os.environ["DATA_DIR"])
LOG_DIR = Path(os.environ["LOG_DIR"])
RUN_ID = os.environ["RUN_ID"]
LOOP_COUNT = int(os.environ["LOOP_COUNT"])
DURATION_HOURS = int(os.environ["DURATION_HOURS"])
SLEEP_SECONDS = int(os.environ["SLEEP_SECONDS"])
ELAPSED_SEC = int(os.environ["ELAPSED_SEC"])
CHECKPOINT_COUNT = int(os.environ["CHECKPOINT_COUNT"])

ckpt_dirs = sorted([d for d in DATA_DIR.glob("checkpoint_*") if d.is_dir()])
all_summaries = []
per_ckpt_watchlist = []
per_ckpt_ready = []
per_ckpt_source_health = []
per_ckpt_data_quality = []
for d in ckpt_dirs:
    sp = d / "r1_smoke_summary.json"
    if not sp.exists():
        continue
    s = json.loads(sp.read_text())
    all_summaries.append(s)
    per_ckpt_watchlist.append({
        "ckpt": d.name,
        "watchlist_count": s.get("watchlist_count", 0),
        "preflight_candidate_count": s.get("preflight_candidate_count", 0),
        "data_insufficient_count": s.get("data_insufficient_count", 0),
        "ev_ready_pool_count": s.get("ev_ready_pool_count", 0),
    })
    per_ckpt_ready.append({
        "ckpt": d.name,
        "quote_ready_pool_count": s.get("quote_ready_pool_count", 0),
        "fee_ready_pool_count": s.get("fee_ready_pool_count", 0),
        "liquidity_ready_pool_count": s.get("liquidity_ready_pool_count", 0),
        "ev_ready_pool_count": s.get("ev_ready_pool_count", 0),
        "preflight_candidate_count": s.get("preflight_candidate_count", 0),
    })
    per_ckpt_source_health.append({
        "ckpt": d.name,
        "chain_reachability": s.get("chain_reachability", {}),
        "chains_skipped": s.get("chains_skipped", []),
        "confidence_distribution": s.get("confidence_distribution", {}),
    })
    per_ckpt_data_quality.append({
        "ckpt": d.name,
        "selected_pool_count": s.get("selected_pool_count", 0),
        "pool_snapshot_rows": s.get("pool_snapshot_rows", 0),
        "quote_snapshot_rows": s.get("quote_snapshot_rows", 0),
        "fee_velocity_rows": s.get("fee_velocity_rows", 0),
        "liquidity_distribution_rows": s.get("liquidity_distribution_rows", 0),
        "market_regime_rows": s.get("market_regime_rows", 0),
        "candidate_review_rows": s.get("candidate_review_rows", 0),
    })

if all_summaries:
    last = all_summaries[-1]
    first = all_summaries[0]
    aggregate = {
        "stage": "LP_LONG_HORIZON_R1_12H_REAL_DATA_OBSERVATION_REQUEST_V1",
        "run_id": RUN_ID,
        "actual_runtime_minutes": round(ELAPSED_SEC / 60.0, 2),
        "actual_runtime_seconds": ELAPSED_SEC,
        "expected_min_runtime_minutes": 0,  # short run, not 12h wallclock
        "wallclock_compressed": True,
        "short_sleep_seconds_per_iteration": SLEEP_SECONDS,
        "loop_count_total": LOOP_COUNT,
        "sleep_seconds_per_iteration": SLEEP_SECONDS,
        "checkpoint_count": len(ckpt_dirs),
        "checkpoint_dirs": [d.name for d in ckpt_dirs],
        "row_counts_last_ckpt": {
            "pool_snapshots": last.get("pool_snapshot_rows", 0),
            "quote_snapshots": last.get("quote_snapshot_rows", 0),
            "fee_velocity": last.get("fee_velocity_rows", 0),
            "liquidity_distribution": last.get("liquidity_distribution_rows", 0),
            "market_regime": last.get("market_regime_rows", 0),
            "candidate_review": last.get("candidate_review_rows", 0),
        },
        "row_counts_first_ckpt": {
            "pool_snapshots": first.get("pool_snapshot_rows", 0),
            "quote_snapshots": first.get("quote_snapshot_rows", 0),
            "fee_velocity": first.get("fee_velocity_rows", 0),
            "liquidity_distribution": first.get("liquidity_distribution_rows", 0),
            "market_regime": first.get("market_regime_rows", 0),
            "candidate_review": first.get("candidate_review_rows", 0),
        },
        "selected_pool_count": last.get("selected_pool_count", 0),
        "real_pool_universe_used": True,
        "selected_real_pool_count": last.get("selected_pool_count", 0),
        "placeholder_pool_count": 0,
        "wallet_or_tx_touched": False,
        "transaction_sent": False,
        "no_production_write": True,
        "no_shadow_overwrite": True,
        "can_run_probe_now": False,
        "tiny_canary_allowed": "no",
        "edge_proven": "no",
        "actual_fee_data_available": False,
        "fee_proxy_only": True,
        "auto_advance_to_24h": False,
        "longer_stage_started": False,
        "send_hard_disable_still_active": True,
        "watchlist_evolution": per_ckpt_watchlist,
        "ready_evolution": per_ckpt_ready,
        "source_health_per_ckpt": per_ckpt_source_health,
        "data_quality_per_ckpt": per_ckpt_data_quality,
        "gate_decision": "DATA_OBSERVATION_PASS_BUT_NO_EXECUTABLE_EDGE",
        "next_action": "manual review of R1 12h node report; R1 12h ≠ edge proven; no auto-advance to 24h",
        "compiled_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
else:
    aggregate = {
        "stage": "LP_LONG_HORIZON_R1_12H_REAL_DATA_OBSERVATION_REQUEST_V1",
        "run_id": RUN_ID,
        "error": "no checkpoint summaries found",
        "compiled_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
(LOG_DIR / "aggregate_summary.json").write_text(json.dumps(aggregate, indent=2))
print(f"[r1_12h aggregate] wrote aggregate_summary.json ckpts={len(ckpt_dirs)} watchlist_first={per_ckpt_watchlist[0]['watchlist_count'] if per_ckpt_watchlist else 'N/A'} watchlist_last={per_ckpt_watchlist[-1]['watchlist_count'] if per_ckpt_watchlist else 'N/A'}")
PYEOF_AGG

echo "[r1_12h complete] rc=0" | tee -a "${LOG_DIR}/supervisor.log"
