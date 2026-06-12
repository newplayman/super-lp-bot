#!/usr/bin/env bash
# scripts/strategy_pivot_d1_delta_hedged_lp_feasibility.sh
#
# Run the D1 delta-hedged LP feasibility model.
# This is a read-only Python script that:
#   - reads R4C's corrected fee matrix (already on disk)
#   - reads R2's gas anchor (already on disk)
#   - queries public perp funding endpoints (Hyperliquid, Binance; OKX 403)
#   - computes a 11,250-cell delta-hedged EV matrix
#   - emits delta_hedged_ev_matrix.csv, delta_hedged_ev_matrix.jsonl
#
# No wallet, no signing, no broadcasting, no execution.

set -euo pipefail

REPORT_DIR="${1:-reports/strategy_pivot_d1_delta_hedged_lp_feasibility/20260612_120000}"

echo "strategy_pivot_d1: running delta-hedged LP feasibility model"
echo "strategy_pivot_d1: report dir: ${REPORT_DIR}"

# Verify R4C and R2 inputs exist
R4C_DIR="reports/strategy_evidence_r4c_independent_clmm_liquidity_replay/20260612_100000"
R2_DIR="reports/strategy_evidence_r2_gas_reward_reprice/20260611_064703"
for f in independent_clmm_fee_replay_matrix.csv; do
  if [[ ! -f "${R4C_DIR}/${f}" ]]; then
    echo "ERROR: ${R4C_DIR}/${f} not found"
    exit 1
  fi
done
if [[ ! -f "${R2_DIR}/gas_anchor_estimates.csv" ]]; then
  echo "ERROR: ${R2_DIR}/gas_anchor_estimates.csv not found"
  exit 1
fi

mkdir -p "${REPORT_DIR}"

# Run the Python model
python3 scripts/strategy_pivot_d1_delta_hedged_lp_feasibility.py

# Verify outputs
if [[ ! -f "${REPORT_DIR}/delta_hedged_ev_matrix.csv" ]]; then
  echo "ERROR: delta_hedged_ev_matrix.csv not generated"
  exit 1
fi
if [[ ! -f "${REPORT_DIR}/delta_hedged_ev_matrix.jsonl" ]]; then
  echo "ERROR: delta_hedged_ev_matrix.jsonl not generated"
  exit 1
fi

MATRIX_ROWS=$(wc -l < "${REPORT_DIR}/delta_hedged_ev_matrix.csv")
echo ""
echo "strategy_pivot_d1: delta_hedged_ev_matrix has ${MATRIX_ROWS} lines"
echo "  expected ~11251 = 1 header + 11250 cells (3 pools × 5 sizes × 5 ranges × 5 horizons × 2 hedge × 5 funding × 3 perp_fee)"

if [[ ${MATRIX_ROWS} -lt 11240 ]]; then
  echo "ERROR: too few cells in delta_hedged_ev_matrix (got ${MATRIX_ROWS}, expected ~11251)"
  exit 1
fi

echo "strategy_pivot_d1: this is a read-only Python pipeline."
echo "strategy_pivot_d1: it does NOT execute any on-chain probes, wallet actions, sign/broadcast."
echo "strategy_pivot_d1: it does NOT query any authenticated CEX/perp API."
echo "strategy_pivot_d1: completed successfully"
exit 0
