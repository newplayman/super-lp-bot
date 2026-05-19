#!/bin/bash
# check-test-files.sh - Verify no *_test.go files deleted or modified
set -e

echo "=== Checking test files unmodified ==="

# Get the base commit (merge-base with origin/main or main)
BASE=$(git merge-base origin/main HEAD 2>/dev/null || echo "main")
echo "Base commit: $BASE"

# Check for deleted lines in *_test.go files
DIFF=$(git diff "$BASE" -- '*_test.go')

if echo "$DIFF" | grep -E '^-[^-]' | grep -v '^---' > /dev/null; then
    echo "ERROR: Cannot delete or modify *_test.go files"
    echo "Modified/deleted test files detected:"
    echo "$DIFF" | grep -E '^-[^-]' | grep -v '^---'
    exit 1
fi

echo "PASS: No *_test.go files deleted or modified"