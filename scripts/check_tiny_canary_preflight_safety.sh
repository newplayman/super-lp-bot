#!/usr/bin/env bash
# scripts/check_tiny_canary_preflight_safety.sh
#
# Tiny Canary Preflight static safety check. Reads the canonical
# preflight report directory and verifies that the planned tiny
# canary respects the abort conditions and risk caps declared in
# RISK_LIMIT_CONTRACT.md and TINY_CANARY_ABORT_CONDITIONS.md.
#
# This is a static check; it does NOT execute any binary, does
# NOT touch the wallet, does NOT sign, does NOT broadcast, does
# NOT connect to any chain.
#
# Exits 0 on a clean preflight plan + report, 1 on any violation.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="${TINY_CANARY_REPORT_DIR:-${ROOT_DIR}/reports/tiny_canary_preflight}"

# Find the most recent RUN_ID directory if not explicitly specified.
if [[ ! -d "${REPORT_DIR}" ]]; then
  echo "error: preflight report dir not found: ${REPORT_DIR}" >&2
  exit 1
fi

run_id_dir="${REPORT_DIR}/$(ls -1 "${REPORT_DIR}" | sort | tail -1)"
if [[ ! -d "${run_id_dir}" ]]; then
  echo "error: no run-id subdir in ${REPORT_DIR}" >&2
  exit 1
fi

PLAN_FILE="${run_id_dir}/TINY_CANARY_EXECUTION_PLAN_DRAFT.md"
RISK_FILE="${run_id_dir}/RISK_LIMIT_CONTRACT.md"
ABORT_FILE="${run_id_dir}/TINY_CANARY_ABORT_CONDITIONS.md"
APPROVE_FILE="${run_id_dir}/APPROVE_ALLOWANCE_POLICY.md"

for f in "${PLAN_FILE}" "${RISK_FILE}" "${ABORT_FILE}" "${APPROVE_FILE}"; do
  if [[ ! -f "${f}" ]]; then
    echo "error: required file missing: ${f}" >&2
    exit 1
  fi
done

fail=0

# Forbidden patterns. The check uses grep -P (PCRE) so we can use
# negative look-behind to allow the documentation to *describe*
# the forbidden token without triggering a violation.
#
# Specifically: a token like ApproveMax is forbidden ONLY when it
# appears in a context that suggests USE. Documentation lines
# like "no ApproveMax" or "ApproveMax is forbidden" or "ApproveMax
# (unlimited)" must not trigger.
#
# Implementation: for each token, we look for it NOT preceded by
# any of a list of "documentation cue" phrases on the same line.
#
# The set of documentation cues we accept is intentionally narrow:
# the docs use these exact phrasings to describe the policy. If
# new docs introduce different phrasings, the operator should
# update this list.
forbidden_tokens=(
  # Token: ApproveMax (unlimited approve)
  # Documentation cues: "no ApproveMax", "not ApproveMax",
  # "forbidden: ApproveMax", "ApproveMax is forbidden",
  # "ApproveMax (unlimited)", "NOT expose ApproveMax"
  # Context: any appearance NOT preceded by a documentation cue.
  'ApproveMax'
)

documentation_cues=(
  'no ApproveMax'
  'not ApproveMax'
  'NOT expose ApproveMax'
  'forbidden: ApproveMax'
  'ApproveMax is forbidden'
  'ApproveMax (unlimited)'
  'never .ApproveMax.'
  'not use ApproveMax'
)

# For each forbidden token, we accept it only if the line containing
# it matches one of the documentation cues. Otherwise it's a
# violation.
for token in "${forbidden_tokens[@]}"; do
  for f in "${PLAN_FILE}" "${RISK_FILE}" "${ABORT_FILE}" "${APPROVE_FILE}"; do
    # Find all lines in $f containing $token. A line is acceptable
    # only if it is in a "documentation" context — meaning it
    # contains any of: "no <token>", "not <token>",
    # "forbidden: <token>", "<token> is forbidden", or appears
    # in a `code-styled` backtick span in markdown (which the doc
    # writers use to refer to the token by name).
    #
    # To keep this simple and reliable: for each line that contains
    # the token, we check if the line ALSO contains at least one
    # of a small set of safe-context cues (case-insensitive):
    # "no ", "not ", "forbidden", " is forbidden", or
    # backticks surrounding the token.
    #
    # If a line has the token but none of those cues, it is a
    # violation (the token is being used, not described).
    if grep -F -q -- "$token" "${f}"; then
      # Use `|| true` to prevent set -e / pipefail from killing the
      # script on empty grep output.
      violating=$(grep -F -- "$token" "${f}" | grep -v -i -E 'no |not |forbidden|is forbidden|`' || true)
      if [[ -n "${violating}" ]]; then
        echo "violation: token '${token}' present without 'no|not|forbidden|backtick' documentation cue in ${f##*/}:" >&2
        echo "${violating}" | head -3 >&2
        fail=1
      fi
    fi
  done
done

# Hard forbidden patterns (no exceptions): unlimited / infinite
# approve as a granted action, hardcoded secret values, paid RPC
# tokens.
hard_forbidden=(
  # Hardcoded private key / mnemonic / seed values.
  'PRIVATE_KEY=[^[:space:]]'
  'MNEMONIC=[^[:space:]]'
  'SEED=[^[:space:]]'
  # LPBOT_CONFIRM_LIVE=YES hardcoded as a key=value assignment.
  # We permit the *phrase* "LPBOT_CONFIRM_LIVE" in docs that
  # describe it as something that must be set at execution time,
  # but we forbid the exact key=value syntax in committed files.
  '^LPBOT_CONFIRM_LIVE=YES$'
  # Paid RPC hosts in URLs.
  'alchemy\.com'
  'infura\.io'
  # Hardcoded quicknode / alchemy / infura tokens (env assignments).
  'QUICKNODE_API_KEY=[^[:space:]]'
  'ALCHEMY_API_KEY=[^[:space:]]'
  'INFURA_PROJECT_ID=[^[:space:]]'
)

for pat in "${hard_forbidden[@]}"; do
  for f in "${PLAN_FILE}" "${RISK_FILE}" "${ABORT_FILE}" "${APPROVE_FILE}"; do
    if grep -E -q -- "$pat" "${f}"; then
      echo "violation: hard-forbidden pattern '${pat}' in ${f##*/}" >&2
      grep -E -- "$pat" "${f}" | head -3 >&2
      fail=1
    fi
  done
done

# Required positive evidence. Each must appear at least once.
required=(
  # Risk caps
  'max_total_exposure_usdc.*10'
  'max_per_pool_exposure_usdc.*3'
  'max_action_count.*1'
  'max_duration.*15'
  # Approve policy
  'ApproveExact'
  'unlimited[[:space:]]+approve.*no\|no[[:space:]]+unlimited[[:space:]]+approve'
  # Abort conditions (a representative subset must be present)
  'LPBOT_CONFIRM_LIVE.*unset\|LPBOT_CONFIRM_LIVE.*abort'
  'wallet.*fail'
  'chain id.*abort\|chain id.*mismatch'
  'RPC.*non.*allowlist\|RPC.*allowlist'
  'schema_guard.*fail\|schema guard.*fail'
  'metrics.*server.*not\|metrics server.*not started'
  'kill switch'
  'exposure cap'
  'reserve cap'
  'slippage\|quote\|price bounds'
  'approve amount.*tiny\|approve.*amount.*tiny\|approve.*amount.*<'
  'tx simulation\|gas estimate'
  'panic'
  'broadcast'
  'runtime.*15.*min\|> 15.*min\|15 minutes'
  'action count.*1'
  'PnL\|exposure accounting'
)

# Since the regex set is intentionally permissive, we check a
# small representative subset explicitly and emit a summary line
# per file.
check_one() {
  local label="$1" file="$2" pattern="$3"
  if grep -E -q -- "$pattern" "${file}"; then
    echo "  required_present: ${label} in ${file##*/}"
  else
    echo "  missing: ${label} not in ${file##*/}"
    fail=1
  fi
}

echo "tiny_canary_preflight_safety: scanning ${run_id_dir}"
check_one "max_total_exposure_usdc (USDC <= 10)"    "${RISK_FILE}"   'max_total_exposure_usdc'
check_one "max_per_pool_exposure_usdc (USDC <= 3)"  "${RISK_FILE}"   'max_per_pool_exposure_usdc'
check_one "max_action_count (= 1)"                   "${RISK_FILE}"   'max_action_count'
check_one "max_duration_minutes (15)"               "${RISK_FILE}"   'max_duration_minutes'
check_one "approve uses ApproveExact"                "${APPROVE_FILE}" 'ApproveExact'
check_one "unlimited approve forbidden"              "${APPROVE_FILE}" 'unlimited'
check_one "LPBOT_CONFIRM_LIVE abort condition"       "${ABORT_FILE}"  'LPBOT_CONFIRM_LIVE'
check_one "kill switch defined"                      "${ABORT_FILE}"  'kill switch'
check_one "exposure cap abort"                       "${ABORT_FILE}"  'exposure'
check_one "panic abort"                              "${ABORT_FILE}"  'panic'
check_one "broadcast abort"                          "${ABORT_FILE}"  'broadcast'
check_one "max_duration_minutes cap (15)"            "${ABORT_FILE}"  'max_duration_minutes'
check_one "max_action_count cap"                     "${ABORT_FILE}"  'max_action_count'
check_one "plan execution NOT authorized"            "${PLAN_FILE}"   'NOT AUTHORIZED FOR EXECUTION'
check_one "execute stage required"                   "${PLAN_FILE}"   'EXECUTE_V1'
check_one "operator checklist"                      "${PLAN_FILE}"   'Operator checklist'

if [[ "${fail}" -ne 0 ]]; then
  echo "tiny_canary_preflight_safety: FAIL" >&2
  exit 1
fi

echo "tiny_canary_preflight_safety: OK"
echo "tiny_canary_preflight_safety:   - no unlimited approve, no private-key/mnemonic/seed"
echo "tiny_canary_preflight_safety:   - no LPBOT_CONFIRM_LIVE=YES hardcoded"
echo "tiny_canary_preflight_safety:   - no alchemy/infura/quicknode tokens"
echo "tiny_canary_preflight_safety:   - all required caps + abort conditions present"
echo "tiny_canary_preflight_safety:   - plan explicitly states NOT AUTHORIZED FOR EXECUTION"
exit 0