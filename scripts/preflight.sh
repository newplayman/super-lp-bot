#!/bin/bash
# preflight.sh - Run lint, tests, and build all tags before commit
set -e

echo "=== Preflight Check ==="
echo "Running full CI checklist locally..."
echo ""

FAILED=0

# 1. Lint
echo "[1/4] Running lint..."
if make lint; then
    echo "[PASS] Lint"
else
    echo "[FAIL] Lint"
    FAILED=1
fi
echo ""

# 2. Unit tests
echo "[2/4] Running unit tests..."
if make test; then
    echo "[PASS] Unit tests"
else
    echo "[FAIL] Unit tests"
    FAILED=1
fi
echo ""

# 3. Property tests
echo "[3/4] Running property tests..."
if make test-property; then
    echo "[PASS] Property tests"
else
    echo "[FAIL] Property tests"
    FAILED=1
fi
echo ""

# 4. Build all tags
echo "[4/4] Building all tags..."
if make build-dryrun && make build-shadow && make build-live && make backtest; then
    echo "[PASS] Build all tags"
else
    echo "[FAIL] Build all tags"
    FAILED=1
fi
echo ""

# 5. Dependency audit
echo "[5/5] Running dependency audit..."
echo "=== Checking for dependency updates ==="
if go list -m -u all 2>&1 | grep -v "^$" | grep -v "^[#]" | grep -q "."; then
    echo "NOTE: Updates available:"
    go list -m -u all 2>&1 | grep "\]"
fi
echo ""
echo "=== Running govulncheck ==="
if command -v govulncheck &> /dev/null; then
    if govulncheck ./...; then
        echo "[PASS] No known vulnerabilities found"
    else
        echo "[WARN] Vulnerabilities found - review output above"
    fi
else
    echo "[SKIP] govulncheck not installed"
fi
echo ""

# Summary
echo "==================================="
if [ $FAILED -eq 0 ]; then
    echo "PREFLIGHT PASSED - Ready to commit!"
    exit 0
else
    echo "PREFLIGHT FAILED - Fix issues before committing"
    exit 1
fi