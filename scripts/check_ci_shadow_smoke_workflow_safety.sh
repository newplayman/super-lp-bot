#!/usr/bin/env bash
# scripts/check_ci_shadow_smoke_workflow_safety.sh
#
# P0-PG-04 static safety check for .github/workflows/shadow-smoke-gate.yml.
# Reads the workflow file and verifies:
#   - forbidden tokens are absent (secrets., LPBOT_CONFIRM_LIVE=YES,
#     PRIVATE_KEY, MNEMONIC, SEED, KMS, CANARY_DSN, LIVE_DSN,
#     BASE_RPC_PRIMARY, SOL_RPC_PRIMARY, run-live, bin/lpbot-live,
#     run-dryrun, bin/lpbot-dryrun)
#   - required tokens are present (postgres:16-alpine, redis:7-alpine,
#     LPBOT_SMOKE_NO_RPC, make build-migrate-postgres, make migrate-postgres,
#     make migrate-postgres-status, make build-shadow,
#     run_shadow_smoke.sh, check_shadow_smoke_safety.sh)
# Exits 0 on a clean workflow, 1 on any violation. The check is a
# static string-grep; it does not execute the workflow.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKFLOW="${ROOT_DIR}/.github/workflows/shadow-smoke-gate.yml"

if [[ ! -f "${WORKFLOW}" ]]; then
  echo "error: workflow file not found: ${WORKFLOW}" >&2
  exit 1
fi

# Strip YAML comments so tokens documented in comments do not match.
# This keeps the workflow file's safety doc next to the actual config
# without polluting the check. We use a temp file rather than a pipe
# so grep can scan line-by-line.
TMP_CHECK="$(mktemp)"
trap 'rm -f "${TMP_CHECK}"' EXIT
awk '
  {
    # Strip whole-line comments.
    if ($0 ~ /^[[:space:]]*#/) next
    # Strip inline comments after a value (preserving "quoted #" tokens).
    line = ""
    in_quote = 0
    for (i = 1; i <= length($0); i++) {
      ch = substr($0, i, 1)
      if (ch == "\"") in_quote = !in_quote
      if (!in_quote && ch == "#" && (i == 1 || substr($0, i-1, 1) == " ")) {
        break
      }
      line = line ch
    }
    print line
  }
' "${WORKFLOW}" > "${TMP_CHECK}"

fail=0
forbidden=(
  'secrets\.'
  'LPBOT_CONFIRM_LIVE=YES'
  'PRIVATE_KEY'
  'MNEMONIC'
  'SEED'
  'KMS'
  'CANARY_DSN'
  'LIVE_DSN'
  'BASE_RPC_PRIMARY'
  'SOL_RPC_PRIMARY'
  'run-live'
  'bin/lpbot-live'
  'run-dryrun'
  'bin/lpbot-dryrun'
)

for token in "${forbidden[@]}"; do
  if grep -E -q -- "$token" "${TMP_CHECK}"; then
    echo "violation: forbidden token '${token}' present in ${WORKFLOW}" >&2
    grep -E -- "$token" "${TMP_CHECK}" | head -3 >&2
    fail=1
  fi
done

required=(
  'postgres:16-alpine'
  'redis:7-alpine'
  'LPBOT_SMOKE_NO_RPC'
  'make build-migrate-postgres'
  'make migrate-postgres'
  'make migrate-postgres-status'
  'make build-shadow'
  'run_shadow_smoke.sh'
  'check_shadow_smoke_safety.sh'
)

for token in "${required[@]}"; do
  if ! grep -qF -- "$token" "${TMP_CHECK}"; then
    echo "missing: required token '${token}' not found in ${WORKFLOW}" >&2
    fail=1
  fi
done

echo "ci_workflow_safety: workflow=${WORKFLOW}"
if [[ "${fail}" -ne 0 ]]; then
  echo "ci_workflow_safety: FAIL" >&2
  exit 1
fi
echo "ci_workflow_safety: OK"
echo "ci_workflow_safety:   - no forbidden tokens (secrets, wallet keys, canary/live paths)"
echo "ci_workflow_safety:   - all required tokens present (services, no-RPC mode, migrator + smoke steps)"
exit 0