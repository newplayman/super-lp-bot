#!/bin/bash
# T-231: Batch backtest script for Phase 0 validation
# Runs backtest on 10 pools and aggregates results

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POOLS_CSV="${SCRIPT_DIR}/../docs/tasks/phase-0/T-230-pools.csv"
OUTPUT_DIR="${SCRIPT_DIR}/../verdict-phase0"
BIN="${SCRIPT_DIR}/../bin/lpbot-backtest"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Create output directory
mkdir -p "${OUTPUT_DIR}"

echo "=========================================="
echo "LP-Bot Phase 0 Backtest Validation"
echo "=========================================="
echo ""
echo "Pools CSV: ${POOLS_CSV}"
echo "Output: ${OUTPUT_DIR}"
echo ""

# Check if binary exists
if [ ! -f "${BIN}" ]; then
    echo -e "${RED}Error: ${BIN} not found${NC}"
    echo "Run: make backtest"
    exit 1
fi

# Counter for results
total=0
passed=0
warned=0
failed=0

# Read CSV and run backtests
while IFS=, read -r chain pool from to; do
    # Skip header
    if [ "${chain}" = "chain" ]; then
        continue
    fi

    total=$((total + 1))
    pool_output="${OUTPUT_DIR}/${chain}-${pool}"
    pool_name=$(basename "${pool}")

    echo "----------------------------------------"
    echo "[${total}/10] ${chain}: ${pool_name}"
    echo "Period: ${from} -> ${to}"
    echo ""

    # Run backtest
    if "${BIN}" \
        --pool="${pool}" \
        --chain="${chain}" \
        --from="${from}" \
        --to="${to}" \
        --range-mode="symmetric" \
        --range-k-sigma=1.5 \
        --tier="A" \
        --output="${pool_output}" \
        2>&1 | tee "${pool_output}/backtest.log"; then

        # Check verdict
        verdict_file="${pool_output}/verdict.md"
        if [ -f "${verdict_file}" ]; then
            verdict=$(grep -E "^Verdict:" "${verdict_file}" | head -1 | cut -d: -f2 | tr -d ' ')
            case "${verdict}" in
                PASS)
                    echo -e "${GREEN}Verdict: PASS${NC}"
                    passed=$((passed + 1))
                    ;;
                WARN)
                    echo -e "${YELLOW}Verdict: WARN${NC}"
                    warned=$((warned + 1))
                    ;;
                FAIL)
                    echo -e "${RED}Verdict: FAIL${NC}"
                    failed=$((failed + 1))
                    ;;
                *)
                    echo -e "${YELLOW}Verdict: UNKNOWN${NC}"
                    warned=$((warned + 1))
                    ;;
            esac
        else
            echo -e "${YELLOW}Warning: No verdict.md found${NC}"
            warned=$((warned + 1))
        fi
    else
        echo -e "${RED}Backtest failed for ${chain}:${pool}${NC}"
        failed=$((failed + 1))
    fi

    echo ""

done < "${POOLS_CSV}"

echo "=========================================="
echo "Phase 0 Batch Summary"
echo "=========================================="
echo "Total pools: ${total}"
echo -e "Passed: ${GREEN}${passed}${NC}"
echo -e "Warnings: ${YELLOW}${warned}${NC}"
echo -e "Failed: ${RED}${failed}${NC}"
echo ""

if [ ${failed} -gt 0 ]; then
    echo -e "${RED}Phase 0 FAILED: ${failed} pools with errors >= 10%${NC}"
    exit 1
elif [ ${warned} -gt 0 ]; then
    echo -e "${YELLOW}Phase 0 PASSED WITH WARNINGS${NC}"
    exit 0
else
    echo -e "${GREEN}Phase 0 PASSED: All pools within 5% error${NC}"
    exit 0
fi