#!/usr/bin/env bash
# scripts/strategy_evidence_r4b_active_liquidity_replay.sh
#
# Run the R4B corrected active-liquidity fee replay.
# This is a read-only Python script that re-uses the R4 Swap event JSONL files
# and recomputes the 81-cell matrix with the corrected fee share formula.
#
# Usage: bash scripts/strategy_evidence_r4b_active_liquidity_replay.sh
#        defaults report_dir to reports/strategy_evidence_r4b_active_liquidity_corrected_replay/20260612_090000

set -euo pipefail

REPORT_DIR="${1:-reports/strategy_evidence_r4b_active_liquidity_corrected_replay/20260612_090000}"

echo "strategy_evidence_r4b: running corrected active-liquidity replay"
echo "strategy_evidence_r4b: report dir: ${REPORT_DIR}"

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
python3 scripts/strategy_evidence_r4b_active_liquidity_replay.py

# Verify the matrix CSV was generated
if [[ ! -f "${REPORT_DIR}/active_liquidity_corrected_replay_matrix.csv" ]]; then
  echo "ERROR: corrected matrix not generated"
  exit 1
fi

MATRIX_ROWS=$(wc -l < "${REPORT_DIR}/active_liquidity_corrected_replay_matrix.csv")
echo ""
echo "strategy_evidence_r4b: corrected matrix has ${MATRIX_ROWS} lines (expected ~82 = 1 header + 81 cells)"

if [[ ${MATRIX_ROWS} -lt 80 ]]; then
  echo "ERROR: too few cells in corrected matrix"
  exit 1
fi

echo "strategy_evidence_r4b: this is a read-only Python replay. It does not"
echo "strategy_evidence_r4b: execute any on-chain probes, wallet actions, or sign/broadcast."
echo "strategy_evidence_r4b: completed successfully"
exit 0
