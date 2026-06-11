#!/usr/bin/env bash
# scripts/strategy_evidence_r3_real_fee_exit_readiness.sh
#
# Read-only verification that the R3 report exists and contains the expected files.
# This script does NOT execute any on-chain probes, wallet actions, or sign/broadcast.
# It is a sanity check that the R3 deliverables were generated and pushed.
#
# Usage: bash scripts/strategy_evidence_r3_real_fee_exit_readiness.sh [REPORT_DIR]
#        defaults to reports/strategy_evidence_r3_real_fee_exit_readiness/20260611_073000

set -euo pipefail

REPORT_DIR="${1:-reports/strategy_evidence_r3_real_fee_exit_readiness/20260611_073000}"

echo "strategy_evidence_r3: verifying ${REPORT_DIR}"

EXPECTED=(
  "FINAL_VERDICT.json"
  "EXECUTIVE_SUMMARY.md"
  "R2_BASELINE_REVIEW.md"
  "FEE_ACCRUAL_CALIBRATION_REPORT.md"
  "real_position_fee_samples.csv"
  "real_position_fee_samples.jsonl"
  "hypothetical_position_fee_calibration.csv"
  "EXIT_READINESS_AUDIT.md"
  "exit_path_matrix.csv"
  "TINY_LIVE_RECLASSIFICATION.md"
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
  echo "strategy_evidence_r3: ${MISSING} expected files missing in ${REPORT_DIR}"
  exit 1
fi

echo ""
echo "strategy_evidence_r3: all 14 expected files present in ${REPORT_DIR}"
echo "strategy_evidence_r3: this is a read-only verification script. It does not"
echo "strategy_evidence_r3: execute any on-chain probes, wallet actions, or sign/broadcast."
exit 0
