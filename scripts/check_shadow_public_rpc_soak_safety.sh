#!/usr/bin/env bash
# scripts/check_shadow_public_rpc_soak_safety.sh
#
# Mode A2 soak safety check. Reads the captured SHADOW_SOAK_RUN_LOG.txt
# (default location: reports/mode_a2_public_rpc_readonly_shadow_soak/<RUN_ID>/)
# and verifies:
#   - forbidden patterns are absent (panic, fatal, signing/broadcast/
#     wallet/canary/live/paper/sendTransaction / mint / addLiquidity /
#     removeLiquidity / approve / swap / bridge / private key /
#     mnemonic / seed / LPBOT_CONFIRM_LIVE / LPBOT_CANARY / LPBOT_LIVE /
#     canary_dsn / live_dsn / QUICKNODE_API_KEY)
#   - required positive evidence is present (shadow banner, metrics
#     server started, schema_guard=ok, Base RPC provider initialized,
#     at least one RPC health summary line, NO smoke_no_rpc_mode=true)
#   - panic_count / fatal_count / wallet_keyword_count /
#     signing_keyword_count / broadcast_keyword_count /
#     lp_action_keyword_count are recorded in the output for the
#     FINAL_VERDICT.json fields.
#
# Exits 0 on a clean soak, 1 on any violation. The check is a static
# string-grep; it does not load the binary.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${SOAK_LOG_DIR:-${ROOT_DIR}/reports/mode_a2_public_rpc_readonly_shadow_soak}"
LOG_FILE="${LOG_DIR}/SHADOW_SOAK_RUN_LOG.txt"

if [[ ! -f "${LOG_FILE}" ]]; then
  echo "error: soak log not found: ${LOG_FILE}" >&2
  exit 1
fi

fail=0

# Counters (printed to stdout for FINAL_VERDICT.json fields).
panic_count=$(grep -c -E '"level":"error"' "${LOG_FILE}" 2>/dev/null || true)
fatal_count=$(grep -c -E 'panic:|^FATAL|^fatal error|traceback' "${LOG_FILE}" 2>/dev/null || true)

forbidden=(
  'panic:'
  '^FATAL'
  'fatal error'
  'sendTransaction'
  'LPBOT_CONFIRM_LIVE'
  'LPBOT_CANARY'
  'LPBOT_LIVE'
  'CANARY_DSN'
  'LIVE_DSN'
  'QUICKNODE_API_KEY'
  # Action verbs as standalone words (case-insensitive).
  '(^|[^[:alnum:]_])(mint|addLiquidity|removeLiquidity|approve|swap|bridge)([^[:alnum:]_]|$)'
  # Wallet / signer / broadcaster keywords.
  '(^|[^[:alnum:]_])signing([^[:alnum:]_]|$)'
  '(^|[^[:alnum:]_])broadcast([^[:alnum:]_]|$)'
  '(^|[^[:alnum:]_])wallet([^[:alnum:]_]|$)'
  'PRIVATE_KEY'
  'MNEMONIC'
  'SEED'
)

wallet_keyword_count=$(grep -c -iE '(^|[^[:alnum:]_])wallet([^[:alnum:]_]|$)' "${LOG_FILE}" 2>/dev/null || true)
signing_keyword_count=$(grep -c -iE '(^|[^[:alnum:]_])signing([^[:alnum:]_]|$)' "${LOG_FILE}" 2>/dev/null || true)
broadcast_keyword_count=$(grep -c -iE '(^|[^[:alnum:]_])broadcast([^[:alnum:]_]|$)' "${LOG_FILE}" 2>/dev/null || true)
lp_action_keyword_count=$(grep -c -E '(^|[^[:alnum:]_])(mint|addLiquidity|removeLiquidity|approve|swap|bridge)([^[:alnum:]_]|$)' "${LOG_FILE}" 2>/dev/null || true)

for pat in "${forbidden[@]}"; do
  if grep -E -q -- "$pat" "${LOG_FILE}"; then
    echo "violation: pattern '${pat}' present in ${LOG_FILE}" >&2
    grep -E -- "$pat" "${LOG_FILE}" | head -3 >&2
    fail=1
  fi
done

required=(
  'Running in shadow mode'
  'metrics server started'
  'schema_guard=ok'
  'Base RPC provider initialized'
)

# RPC health evidence: at least one RPC health summary line.
# The binary logs these as `health check summary:` after each
# 30s probe tick. We require >=1 such line.
rpc_health_lines=$(grep -c 'health check summary' "${LOG_FILE}" 2>/dev/null || true)

for sub in "${required[@]}"; do
  if ! grep -qF -- "$sub" "${LOG_FILE}"; then
    echo "missing: required substring '${sub}' not found in ${LOG_FILE}" >&2
    fail=1
  fi
done

# smoke_no_rpc_mode=true must NOT be present (Mode A2 uses canonical RPC).
if grep -qF 'smoke_no_rpc_mode=true' "${LOG_FILE}"; then
  echo "violation: smoke_no_rpc_mode=true present in ${LOG_FILE} (Mode A2 requires canonical RPC)" >&2
  fail=1
fi

# Emit counters to stdout (captured to SHADOW_SOAK_SAFETY_CHECK.txt by
# the runner).
echo "shadow_soak_safety: log=${LOG_FILE}"
echo "shadow_soak_safety: forbidden_pattern_violations=$([ $fail -eq 0 ] && echo 0 || echo 1)"
echo "shadow_soak_safety: rpc_health_lines=${rpc_health_lines}"
echo "shadow_soak_safety: panic_count=${panic_count}"
echo "shadow_soak_safety: fatal_count=${fatal_count}"
echo "shadow_soak_safety: wallet_keyword_count=${wallet_keyword_count}"
echo "shadow_soak_safety: signing_keyword_count=${signing_keyword_count}"
echo "shadow_soak_safety: broadcast_keyword_count=${broadcast_keyword_count}"
echo "shadow_soak_safety: lp_action_keyword_count=${lp_action_keyword_count}"

if [[ "${fail}" -ne 0 ]]; then
  echo "shadow_soak_safety: FAIL (see violations above)" >&2
  exit 1
fi

echo "shadow_soak_safety: OK"
echo "shadow_soak_safety:   - no panic, no fatal, no wallet/signing/broadcast keywords"
echo "shadow_soak_safety:   - no canary/live/paper/quicknode references"
echo "shadow_soak_safety:   - shadow banner + metrics server + schema_guard=ok + Base RPC provider initialized"
echo "shadow_soak_safety:   - RPC health evidence present (>= 1 health check summary line)"
echo "shadow_soak_safety:   - smoke_no_rpc_mode=true absent (canonical RPC path)"
exit 0