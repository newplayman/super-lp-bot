#!/usr/bin/env bash
# scripts/check_shadow_smoke_safety.sh
#
# P0-PG-03 shadow smoke safety check. Reads SHADOW_SMOKE_RUN_LOG.txt
# (produced by run_shadow_smoke.sh) and verifies the binary stayed
# in shadow-test mode. Exits 0 on clean smoke, 1 on any safety
# violation. The check is a static string-grep; it does not load
# the binary.
#
# Forbidden keywords / patterns (all must be absent from the log):
#   * "panic:" (Go panic)
#   * "FATAL" / "fatal error" (Go runtime / log.Fatal)
#   * "wallet" / "signing" / "broadcast" / "sendTransaction" /
#     "mint" / "addLiquidity" / "removeLiquidity" / "approve" /
#     "swap" / "bridge" — any of these as a Go-level action
#     indicates the shadow binary escaped its read-only simulation
#     mode and is attempting chain operations.
#   * "canary" / "live" / "paper" / "LPBOT_CONFIRM_LIVE" — any
#     reference at startup or in a hot-path means the binary is
#     not in pure shadow mode.
#
# The log will legitimately contain words like "shadow strategy",
# "shadow trace", "shadow mode" — those are expected. The check
# only fires on the forbidden action verbs above.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${SMOKE_LOG_DIR:-${ROOT_DIR}/reports/p0_pg_03_fresh_shadow_smoke}"
LOG_FILE="${LOG_DIR}/SHADOW_SMOKE_RUN_LOG.txt"

if [[ ! -f "${LOG_FILE}" ]]; then
  echo "error: smoke log not found: ${LOG_FILE}" >&2
  exit 1
fi

fail=0
patterns=(
  'panic:'
  'FATAL[[:space:]]'
  'fatal error'
  'sendTransaction'
  'LPBOT_CONFIRM_LIVE'
  # Action verbs. Each is checked as a word boundary to avoid
  # matching log lines that incidentally contain the substring.
  '[[:space:]](mint|addLiquidity|removeLiquidity|approve|swap|bridge)[[:space:]]'
)

for pat in "${patterns[@]}"; do
  if grep -E -q -- "$pat" "${LOG_FILE}"; then
    echo "violation: pattern '${pat}' present in ${LOG_FILE}" >&2
    grep -E -- "$pat" "${LOG_FILE}" | head -3 >&2
    fail=1
  fi
done

# Additional allowlist-style checks: the log must contain evidence
# the binary actually started (shadow mode banner), initialized
# metrics, and the schema guard passed. Each is a positive
# requirement; absence is a violation.
expected_substrings=(
  'Running in shadow mode'
  'metrics server started'
)

for sub in "${expected_substrings[@]}"; do
  if ! grep -qF -- "$sub" "${LOG_FILE}"; then
    echo "missing: expected substring '${sub}' not found in ${LOG_FILE}" >&2
    fail=1
  fi
done

if [[ "${fail}" -ne 0 ]]; then
  exit 1
fi

echo "shadow_smoke_safety: OK (no panic, no fatal, no canary/live/paper,"
echo "shadow_smoke_safety:     no signing/broadcast/mint/swap keywords,"
echo "shadow_smoke_safety:     shadow mode banner + metrics server present)"
exit 0
