#!/usr/bin/env bash
# scripts/strategy_evidence_r4c_independent_clmm_liquidity_replay.sh
#
# Run the R4C independent CLMM liquidity replay.
# This is a read-only Python script that re-uses the R4 Swap event JSONL files
# and recomputes the 81-cell matrix with INDEPENDENT V3 L_position math
# (LiquidityAmounts.sol formulas, not size/TVL × l_factor).
#
# Usage: bash scripts/strategy_evidence_r4c_independent_clmm_liquidity_replay.sh
#        defaults report_dir to reports/strategy_evidence_r4c_independent_clmm_liquidity_replay/20260612_100000

set -euo pipefail

REPORT_DIR="${1:-reports/strategy_evidence_r4c_independent_clmm_liquidity_replay/20260612_100000}"

echo "strategy_evidence_r4c: running independent CLMM liquidity replay"
echo "strategy_evidence_r4c: report dir: ${REPORT_DIR}"

# Verify R4 inputs exist
R4_DIR="reports/strategy_evidence_r4_swap_event_fee_replay/20260611_080000"
for f in swap_events_0xb2cc22.jsonl swap_events_0x72ab38.jsonl swap_events_0xb77527.jsonl; do
  if [[ ! -f "${R4_DIR}/${f}" ]]; then
    echo "ERROR: ${R4_DIR}/${f} not found"
    exit 1
  fi
done

mkdir -p "${REPORT_DIR}"

# Run the Python replay script
python3 scripts/strategy_evidence_r4c_independent_clmm_liquidity_replay.py

# Verify the matrix CSV was generated
if [[ ! -f "${REPORT_DIR}/independent_clmm_fee_replay_matrix.csv" ]]; then
  echo "ERROR: independent replay matrix not generated"
  exit 1
fi
if [[ ! -f "${REPORT_DIR}/independent_liquidity_position_validation.csv" ]]; then
  echo "ERROR: validation table not generated"
  exit 1
fi

MATRIX_ROWS=$(wc -l < "${REPORT_DIR}/independent_clmm_fee_replay_matrix.csv")
VALIDATION_ROWS=$(wc -l < "${REPORT_DIR}/independent_liquidity_position_validation.csv")
echo ""
echo "strategy_evidence_r4c: independent replay matrix has ${MATRIX_ROWS} lines (expected ~82 = 1 header + 81 cells)"
echo "strategy_evidence_r4c: validation table has ${VALIDATION_ROWS} lines (expected ~82 = 1 header + 81 cells)"

if [[ ${MATRIX_ROWS} -lt 80 ]]; then
  echo "ERROR: too few cells in independent replay matrix"
  exit 1
fi
if [[ ${VALIDATION_ROWS} -lt 80 ]]; then
  echo "ERROR: too few cells in validation table"
  exit 1
fi

echo "strategy_evidence_r4c: this is a read-only Python replay. It does not"
echo "strategy_evidence_r4c: execute any on-chain probes, wallet actions, or sign/broadcast."
echo "strategy_evidence_r4c: completed successfully"
exit 0
