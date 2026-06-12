#!/usr/bin/env bash
# scripts/strategy_pivot_d2_dynamic_delta_funding_history.sh
#
# Run the D2 dynamic-delta LP replay with funding history.
# This is a read-only Python script that:
#   - reads R4C's corrected fee matrix (already on disk)
#   - reads R4's per-event swap data (already on disk)
#   - reads Binance's 90d funding history (already pulled in funding_history.csv)
#   - runs a dynamic-delta replay with rebalance rules
#   - emits dynamic_delta_replay_matrix.csv / .jsonl
#
# No wallet, no signing, no broadcasting, no execution.

set -euo pipefail

REPORT_DIR="${1:-reports/strategy_pivot_d2_dynamic_delta_funding_history/20260612_140000}"

echo "strategy_pivot_d2: running dynamic-delta LP replay"
echo "strategy_pivot_d2: report dir: ${REPORT_DIR}"

# Verify inputs exist
R4C_DIR="reports/strategy_evidence_r4c_independent_clmm_liquidity_replay/20260612_100000"
R4_DIR="reports/strategy_evidence_r4_swap_event_fee_replay/20260611_080000"
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
if [[ ! -f "${REPORT_DIR}/funding_history.csv" ]]; then
  echo "ERROR: ${REPORT_DIR}/funding_history.csv not found (D2 requires pre-pulled funding history)"
  exit 1
fi

mkdir -p "${REPORT_DIR}"

# Run the Python model
python3 scripts/strategy_pivot_d2_dynamic_delta_funding_history.py

# Verify outputs
if [[ ! -f "${REPORT_DIR}/dynamic_delta_replay_matrix.csv" ]]; then
  echo "ERROR: dynamic_delta_replay_matrix.csv not generated"
  exit 1
fi

MATRIX_ROWS=$(wc -l < "${REPORT_DIR}/dynamic_delta_replay_matrix.csv")
echo ""
echo "strategy_pivot_d2: dynamic_delta_replay_matrix has ${MATRIX_ROWS} lines"
echo "  expected ~271 = 1 header + 270 cells (2 pools × 3 sizes × 3 ranges × 5 rebal × 3 hedge)"

if [[ ${MATRIX_ROWS} -lt 260 ]]; then
  echo "ERROR: too few cells in dynamic_delta_replay_matrix (got ${MATRIX_ROWS}, expected ~271)"
  exit 1
fi

echo "strategy_pivot_d2: this is a read-only Python pipeline."
echo "strategy_pivot_d2: it does NOT execute any on-chain probes, wallet actions, sign/broadcast."
echo "strategy_pivot_d2: it does NOT use any CEX/perp API key. Funding history was pre-pulled in 15m checkpoint."
echo "strategy_pivot_d2: completed successfully"
exit 0
