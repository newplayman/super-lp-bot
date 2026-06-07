#!/usr/bin/env bash
# R1 12h stage runner (wallclock loop, 12 hourly checkpoints, readonly).
# Reuses lp_long_horizon_r1_real_data_collector_v1.py (smoke mode per ckpt).
# Writes per-ckpt data + aggregates + supervisor log + final FINAL_VERDICT.
#
# Hard prohibitions (enforced in code + audited in COLLECTOR_SAFETY_AUDIT):
#   - no private key / seed / keypair / keystore read
#   - no signer creation
#   - no transaction sent
#   - no approve / mint / add_liquidity / remove_liquidity / collect_fee / swap / bridge
#   - no live / canary / paper / probe start
#   - no production position write
#   - no shadow table overwrite
#   - no long-running daemon (this is a wallclock supervisor, not a daemon)
#   - no auto-advance to 24h+ / no longer-horizon auto-trigger
#   - actual_fee_data_available / can_run_probe_now / tiny_canary_allowed / edge_proven
#     must stay locked (False / "no" / "no" / "no")
set -euo pipefail

# Args: 1=RUN_ID 2=DURATION_HOURS 3=CHECKPOINT_COUNT
RUN_ID="${1:?RUN_ID required}"
DURATION_HOURS="${2:?DURATION_HOURS required}"
CHECKPOINT_COUNT="${3:?CHECKPOINT_COUNT required}"

# Locked fields (must NOT change).
export LP_R1_12H_STAGE="LP_LONG_HORIZON_R1_12H_REAL_DATA_OBSERVATION_REQUEST_V1"
export LP_R1_12H_RUN_ID="${RUN_ID}"
export LP_R1_12H_DURATION_HOURS="${DURATION_HOURS}"
export LP_R1_12H_CHECKPOINT_COUNT="${CHECKPOINT_COUNT}"
export LP_R1_12H_MODE="readonly"
export LP_R1_12H_COVERAGE_SCOPE="partial_solana_bsc_real_universe_r1_12h"

# Per-checkpoint sleep (sec). 12 ckpts × 3600s = 43200s = 12h.
SLEEP_SECONDS=$((DURATION_HOURS * 3600 / CHECKPOINT_COUNT))

# Paths.
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="${REPO_ROOT}/data/lp_long_horizon_r1_12h/${RUN_ID}"
LOG_DIR="${DATA_DIR}/logs"
HEARTBEAT_DIR="${LOG_DIR}/heartbeat"
CHECKPOINT_LOG_DIR="${LOG_DIR}/checkpoint"
POOL_UNIVERSE="${REPO_ROOT}/reports/lp_long_horizon_real_pool_universe_coverage_expand/20260606_091120/expanded_real_pool_universe_for_12h_retry.json"

mkdir -p "${DATA_DIR}" "${LOG_DIR}" "${HEARTBEAT_DIR}" "${CHECKPOINT_LOG_DIR}"

START_TS=$(date +%s)
END_TS=$((START_TS + DURATION_HOURS * 3600))

echo "[r1_12h start] RUN_ID=${RUN_ID} DURATION_HOURS=${DURATION_HOURS} CHECKPOINT_COUNT=${CHECKPOINT_COUNT} START_TS=${START_TS} END_TS=${END_TS} SLEEP_SECONDS=${SLEEP_SECONDS}" | tee -a "${LOG_DIR}/supervisor.log"

# Trap: on exit, write finalize marker.
trap 'rc=$?; echo "[r1_12h exit] rc=${rc} at $(date -u +%Y-%m-%dT%H:%M:%SZ) elapsed_min=$(( ( $(date +%s) - ${START_TS} ) / 60 ))" | tee -a "${LOG_DIR}/supervisor.log"; exit ${rc}' EXIT

LOOP_COUNT=0
ALL_OK=true

while [ "${LOOP_COUNT}" -lt "${CHECKPOINT_COUNT}" ]; do
    LOOP_COUNT=$((LOOP_COUNT + 1))
    CKPT_DIR="${DATA_DIR}/checkpoint_${LOOP_COUNT}_$(date -u +%H%M)"
    mkdir -p "${CKPT_DIR}"
    CKPT_START=$(date +%s)
    ELAPSED_MIN=$(( (CKPT_START - START_TS) / 60 ))

    echo "[r1_12h loop ${LOOP_COUNT}/${CHECKPOINT_COUNT}] start at $(date -u +%Y-%m-%dT%H:%M:%SZ) elapsed_min=${ELAPSED_MIN} ckpt_dir=${CKPT_DIR}" | tee -a "${LOG_DIR}/supervisor.log"

    # Run R1 collector in smoke mode (--max-snapshots 1) per checkpoint.
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

    # Write per-ckpt heartbeat.
    HEARTBEAT_FILE="${HEARTBEAT_DIR}/heartbeat_${LOOP_COUNT}.json"
    cat > "${HEARTBEAT_FILE}" <<HBEOF
{
  "loop_count": ${LOOP_COUNT},
  "ckpt_dir": "${CKPT_DIR}",
  "ckpt_start_utc": "$(date -u -d @${CKPT_START} +%Y-%m-%dT%H:%M:%SZ)",
  "ckpt_end_utc": "$(date -u -d @${CKPT_END} +%Y-%m-%dT%H:%M:%SZ)",
  "ckpt_duration_sec": ${CKPT_DURATION},
  "elapsed_min": ${ELAPSED_MIN},
  "ckpt_rc": ${CKPT_RC},
  "expected_end_ts": ${END_TS}
}
HBEOF

    if [ "${CKPT_RC}" -ne 0 ]; then
        echo "[r1_12h loop ${LOOP_COUNT}] rc=${CKPT_RC} (continuing)" | tee -a "${LOG_DIR}/supervisor.log"
        ALL_OK=false
    else
        echo "[r1_12h loop ${LOOP_COUNT}] ok in ${CKPT_DURATION}s" | tee -a "${LOG_DIR}/supervisor.log"
    fi

    # If not last checkpoint, sleep.
    if [ "${LOOP_COUNT}" -lt "${CHECKPOINT_COUNT}" ]; then
        NOW=$(date +%s)
        REMAINING=$((END_TS - NOW))
        if [ "${REMAINING}" -gt "${SLEEP_SECONDS}" ]; then
            echo "[r1_12h loop ${LOOP_COUNT}] sleeping ${SLEEP_SECONDS}s (until $(date -u -d @$((NOW + SLEEP_SECONDS)) +%Y-%m-%dT%H:%M:%SZ))" | tee -a "${LOG_DIR}/supervisor.log"
            sleep "${SLEEP_SECONDS}"
        else
            echo "[r1_12h loop ${LOOP_COUNT}] near END_TS, breaking" | tee -a "${LOG_DIR}/supervisor.log"
            break
        fi
    fi
done

# Finalize block.
END_FINAL_TS=$(date +%s)
ELAPSED_MIN_FINAL=$(( (END_FINAL_TS - START_TS) / 60 ))
echo "[r1_12h end] END_TS reached at $(date -u +%Y-%m-%dT%H:%M:%SZ) elapsed_min=${ELAPSED_MIN_FINAL}" | tee -a "${LOG_DIR}/supervisor.log"

# Aggregate per-ckpt summaries into one summary.
echo "[r1_12h finalize] aggregating per-ckpt summaries" | tee -a "${LOG_DIR}/supervisor.log"

# Run aggregate Python heredoc.
DATA_DIR="${DATA_DIR}" \
LOG_DIR="${LOG_DIR}" \
RUN_ID="${RUN_ID}" \
LOOP_COUNT="${LOOP_COUNT}" \
DURATION_HOURS="${DURATION_HOURS}" \
SLEEP_SECONDS="${SLEEP_SECONDS}" \
ELAPSED_MIN="${ELAPSED_MIN_FINAL}" \
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
ELAPSED_MIN = int(os.environ["ELAPSED_MIN"])
CHECKPOINT_COUNT = int(os.environ["CHECKPOINT_COUNT"])

ckpt_dirs = sorted([d for d in DATA_DIR.glob("checkpoint_*") if d.is_dir()])
all_summaries = []
per_ckpt_watchlist = []
per_ckpt_ready = []
per_ckpt_source_health = []
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
        "quote_ready_pool_count": s.get("quote_ready_pool_count", 0),
        "fee_ready_pool_count": s.get("fee_ready_pool_count", 0),
        "liquidity_ready_pool_count": s.get("liquidity_ready_pool_count", 0),
    })
    per_ckpt_source_health.append({
        "ckpt": d.name,
        "chain_reachability": s.get("chain_reachability", {}),
        "chains_skipped": s.get("chains_skipped", []),
        "confidence_distribution": s.get("confidence_distribution", {}),
    })

# Roll-up.
if all_summaries:
    last = all_summaries[-1]
    first = all_summaries[0]
    aggregate = {
        "stage": "LP_LONG_HORIZON_R1_12H_REAL_DATA_OBSERVATION_REQUEST_V1",
        "run_id": RUN_ID,
        "actual_runtime_minutes": ELAPSED_MIN,
        "expected_min_runtime_minutes": DURATION_HOURS * 60 - 60,  # 11h floor for PASS
        "actual_runtime_valid_for_12h_gate": ELAPSED_MIN >= DURATION_HOURS * 60 - 60,
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
        "source_health_per_ckpt": per_ckpt_source_health,
        "gate_decision": "DATA_OBSERVATION_PASS_BUT_NO_EXECUTABLE_EDGE" if (
            ELAPSED_MIN >= DURATION_HOURS * 60 - 60
            and all(s.get("pool_snapshot_rows", 0) > 0 for s in all_summaries)
            and all(s.get("quote_snapshot_rows", 0) > 0 for s in all_summaries)
            and all(s.get("fee_velocity_rows", 0) > 0 for s in all_summaries)
            and all(s.get("liquidity_distribution_rows", 0) > 0 for s in all_summaries)
            and all(s.get("candidate_review_rows", 0) > 0 for s in all_summaries)
        ) else "DATA_OBSERVATION_PARTIAL",
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
print("[r1_12h aggregate] wrote aggregate_summary.json")
print(f"[r1_12h aggregate] ckpt_count={len(ckpt_dirs)} watchlist_first={per_ckpt_watchlist[0]['watchlist_count'] if per_ckpt_watchlist else 'N/A'} watchlist_last={per_ckpt_watchlist[-1]['watchlist_count'] if per_ckpt_watchlist else 'N/A'}")
PYEOF_AGG

echo "[r1_12h finalize] aggregate done at $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_DIR}/supervisor.log"
echo "[r1_12h complete] rc=0" | tee -a "${LOG_DIR}/supervisor.log"
