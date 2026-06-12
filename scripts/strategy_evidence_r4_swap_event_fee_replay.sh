#!/usr/bin/env bash
# scripts/strategy_evidence_r4_swap_event_fee_replay.sh
#
# Read-only verification that the R4 report exists and contains the expected files.
# This script does NOT execute any on-chain probes, wallet actions, or sign/broadcast.
# It is a sanity check that the R4 deliverables were generated and pushed.
#
# Usage: bash scripts/strategy_evidence_r4_swap_event_fee_replay.sh [REPORT_DIR]
#        defaults to reports/strategy_evidence_r4_swap_event_fee_replay/20260611_080000

set -euo pipefail

REPORT_DIR="${1:-reports/strategy_evidence_r4_swap_event_fee_replay/20260611_080000}"

echo "strategy_evidence_r4: verifying ${REPORT_DIR}"

EXPECTED=(
  "FINAL_VERDICT.json"
  "EXECUTIVE_SUMMARY.md"
  "R3_BASELINE_REVIEW.md"
  "swap_event_abi_probe.md"
  "swap_events_raw.jsonl"
  "swap_events_decoded.csv"
  "historical_24h_swap_replay.csv"
  "historical_24h_swap_replay.jsonl"
  "hypothetical_lp_fee_replay_matrix.csv"
  "hypothetical_lp_fee_replay_matrix.jsonl"
  "FEE_PROXY_CALIBRATION_DECISION.md"
  "WATCHER_DECISION.md"
  "TINY_LIVE_DECISION.md"
  "NEXT_STRATEGY_FORK.md"
  "TEST_RESULTS.txt"
  "CHANGED_FILES.txt"
  "SAFETY_LOCKS_RECHECK.json"
)

MISSING=0
for f in "${EXPECTED[@]}"; do
  if [[ ! -f "${REPORT_DIR}/${f}" ]]; then
    echo "  MISSING: ${f}"
    MISSING=$((MISSING+1))
  else
    echo "  OK:      ${f}"
  fi
done

if [[ ${MISSING} -gt 0 ]]; then
  echo ""
  echo "strategy_evidence_r4: ${MISSING} expected files missing in ${REPORT_DIR}"
  exit 1
fi

# Sanity check the swap events raw file
RAW_COUNT=$(wc -l < "${REPORT_DIR}/swap_events_raw.jsonl")
echo ""
echo "strategy_evidence_r4: swap_events_raw.jsonl has ${RAW_COUNT} events (expected > 100,000)"

# Sanity check the matrix
MATRIX_COUNT=$(wc -l < "${REPORT_DIR}/hypothetical_lp_fee_replay_matrix.csv")
echo "strategy_evidence_r4: hypothetical_lp_fee_replay_matrix.csv has ${MATRIX_COUNT} lines (expected ~82)"

# Sanity check the historical replay
HIST_COUNT=$(wc -l < "${REPORT_DIR}/historical_24h_swap_replay.csv")
echo "strategy_evidence_r4: historical_24h_swap_replay.csv has ${HIST_COUNT} lines (expected 4)"

echo ""
echo "strategy_evidence_r4: all 17 expected files present in ${REPORT_DIR}"
echo "strategy_evidence_r4: this is a read-only verification script. It does not"
echo "strategy_evidence_r4: execute any on-chain probes, wallet actions, or sign/broadcast."
exit 0
