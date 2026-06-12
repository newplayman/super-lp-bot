#!/usr/bin/env bash
# scripts/strategy_pivot_d3_aerodrome_reward_edge.sh
#
# Run the D3 reward-adjusted delta-hedged LP model.
# This is a read-only Python script that:
#   - reads D2's funding history (already on disk)
#   - reads R4C's corrected fee matrix (already on disk)
#   - reads R4's per-event swap data (already on disk)
#   - reads DefiLlama's reward APR (queried at 45m checkpoint, embedded in script)
#   - computes a 2,700-cell reward-adjusted matrix
#   - emits reward_adjusted_delta_matrix.csv / .jsonl
#
# No wallet, no signing, no broadcasting, no execution.

set -euo pipefail

REPORT_DIR="${1:-reports/strategy_pivot_d3_aerodrome_reward_edge/20260612_160000}"

echo "strategy_pivot_d3: running reward-adjusted delta-hedged LP model"
echo "strategy_pivot_d3: report dir: ${REPORT_DIR}"

# Verify D2, R4C, R4 inputs exist
D2_DIR="reports/strategy_pivot_d2_dynamic_delta_funding_history/20260612_140000"
R4C_DIR="reports/strategy_evidence_r4c_independent_clmm_liquidity_replay/20260612_100000"
R4_DIR="reports/strategy_evidence_r4_swap_event_fee_replay/20260611_080000"
for f in funding_history.csv; do
  if [[ ! -f "${D2_DIR}/${f}" ]]; then
    echo "ERROR: ${D2_DIR}/${f} not found"
    exit 1
  fi
done
for f in independent_clmm_fee_replay_matrix.csv; do
  if [[ ! -f "${R4C_DIR}/${f}" ]]; then
    echo "ERROR: ${R4C_DIR}/${f} not found"
    exit 1
  fi
done
for f in swap_events_0xb2cc22.jsonl swap_events_0x72ab38.jsonl; do
  if [[ ! -f "${R4_DIR}/${f}" ]]; then
    echo "ERROR: ${R4_DIR}/${f} not found"
    exit 1
  fi
done

mkdir -p "${REPORT_DIR}"

# Run the Python model
python3 scripts/strategy_pivot_d3_aerodrome_reward_edge.py

# Verify outputs
if [[ ! -f "${REPORT_DIR}/reward_adjusted_delta_matrix.csv" ]]; then
  echo "ERROR: reward_adjusted_delta_matrix.csv not generated"
  exit 1
fi

MATRIX_ROWS=$(wc -l < "${REPORT_DIR}/reward_adjusted_delta_matrix.csv")
echo ""
echo "strategy_pivot_d3: reward_adjusted_delta_matrix has ${MATRIX_ROWS} lines"
echo "  expected ~2701 = 1 header + 2700 cells (2 pools × 3 sizes × 3 ranges × 3 horizons × 2 hedge × 5 funding × 5 reward)"

if [[ ${MATRIX_ROWS} -lt 2690 ]]; then
  echo "ERROR: too few cells (got ${MATRIX_ROWS}, expected ~2701)"
  exit 1
fi

echo "strategy_pivot_d3: this is a read-only Python pipeline."
echo "strategy_pivot_d3: it does NOT execute any on-chain probes, wallet actions, sign/broadcast."
echo "strategy_pivot_d3: it does NOT use any CEX/perp API key."
echo "strategy_pivot_d3: completed successfully"
exit 0
