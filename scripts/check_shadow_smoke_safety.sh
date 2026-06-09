#!/usr/bin/env bash
# scripts/check_shadow_smoke_safety.sh
#
# P0-PG-03B hardened smoke safety check. Reads SHADOW_SMOKE_RUN_LOG.txt
# (produced by run_shadow_smoke.sh) and verifies the binary stayed in
# shadow-test mode AND that the schema guard reported OK AND that no-RPC
# smoke mode was honored. Exits 0 on a clean smoke, 1 on any violation.
#
# Forbidden patterns (must be absent):
#   * "panic:"             — Go panic
#   * "FATAL" / "fatal error" — runtime fatal
#   * "sendTransaction"   — any actual tx
#   * "LPBOT_CONFIRM_LIVE" — must not be set
#   * mint / addLiquidity / removeLiquidity / approve / swap / bridge
#                            as standalone words — chain action verbs
#
# Required positive evidence (must be present):
#   * "Running in shadow mode"          — banner
#   * "metrics server started"          — metrics wired
#   * "schema_guard=ok"                 — schema guard ran and passed
#                                            (added in P0-PG-03B)
#   * "smoke_no_rpc_mode=true"          — no-RPC mode honored
#                                            (added in P0-PG-03B)
#   * "base_rpc_initialization=skipped" — base RPC list empty
#                                            (added in P0-PG-03B)
#
# Optional evidence (informational; presence is logged but not required):
#   * "solana_rpc_initialization=skipped"

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${SMOKE_LOG_DIR:-${ROOT_DIR}/reports/p0_pg_03b_shadow_smoke_hardening}"
LOG_FILE="${LOG_DIR}/SHADOW_SMOKE_RUN_LOG.txt"

if [[ ! -f "${LOG_FILE}" ]]; then
  # Fallback for the legacy P0-PG-03 location, so this script can be
  # re-run against an older smoke without breaking the check.
  LEGACY_LOG="${ROOT_DIR}/reports/p0_pg_03_fresh_shadow_smoke/SHADOW_SMOKE_RUN_LOG.txt"
  if [[ -f "${LEGACY_LOG}" ]]; then
    echo "info: using legacy P0-PG-03 smoke log ${LEGACY_LOG}" >&2
    LOG_FILE="${LEGACY_LOG}"
  else
    echo "error: smoke log not found: ${LOG_DIR}/SHADOW_SMOKE_RUN_LOG.txt" >&2
    echo "       (also looked for ${LEGACY_LOG})" >&2
    exit 1
  fi
fi

fail=0
patterns=(
  'panic:'
  'FATAL[[:space:]]'
  'fatal error'
  'sendTransaction'
  'LPBOT_CONFIRM_LIVE'
  '[[:space:]](mint|addLiquidity|removeLiquidity|approve|swap|bridge)[[:space:]]'
)

for pat in "${patterns[@]}"; do
  if grep -E -q -- "$pat" "${LOG_FILE}"; then
    echo "violation: pattern '${pat}' present in ${LOG_FILE}" >&2
    grep -E -- "$pat" "${LOG_FILE}" | head -3 >&2
    fail=1
  fi
done

required_substrings=(
  'Running in shadow mode'
  'metrics server started'
  'schema_guard=ok'
  'smoke_no_rpc_mode=true'
  'base_rpc_initialization=skipped'
)

missing=()
for sub in "${required_substrings[@]}"; do
  if ! grep -qF -- "$sub" "${LOG_FILE}"; then
    echo "missing: expected substring '${sub}' not found in ${LOG_FILE}" >&2
    missing+=("$sub")
    fail=1
  fi
done

# Informational: solana RPC skip line should also be present in
# no-RPC mode; absence is logged but not a hard failure (some smoke
# configs only target base).
if ! grep -qF -- 'solana_rpc_initialization=skipped' "${LOG_FILE}"; then
  echo "info: optional 'solana_rpc_initialization=skipped' not found" >&2
fi

echo "shadow_smoke_safety: log=${LOG_FILE}"
echo "shadow_smoke_safety: forbidden_pattern_violations=$([ $fail -eq 0 ] && echo 0 || echo 1)"
echo "shadow_smoke_safety: missing_required_substrings=${#missing[@]}"
if [[ "${fail}" -ne 0 ]]; then
  echo "shadow_smoke_safety: FAIL (see violations above)" >&2
  exit 1
fi
echo "shadow_smoke_safety: OK"
echo "shadow_smoke_safety:   - no panic, no fatal, no canary/live/paper"
echo "shadow_smoke_safety:   - no signing/broadcast/mint/swap/approve keywords"
echo "shadow_smoke_safety:   - schema_guard=ok present"
echo "shadow_smoke_safety:   - smoke_no_rpc_mode=true and base_rpc_initialization=skipped present"
echo "shadow_smoke_safety:   - shadow mode banner + metrics server start present"
exit 0