#!/usr/bin/env bash
# scripts/run_shadow_smoke.sh
#
# P0-PG-03 fresh shadow smoke driver. Builds the shadow binary if
# needed, runs it under a bounded timeout (default 10m, overridable
# via SMOKE_DURATION_SECONDS) against the test config, captures
# stdout+stderr to a log file, then exits with the binary's exit
# code (or 124 on timeout, which the check_shadow_smoke_safety.sh
# script treats as a WARN smoke not a FAIL).
#
# CI first-run trigger (P0-PG-06): no logic change; comment only.
#
# Strict safety: refuses to start if any canary/live/paper env var
# is set or if the config file references canary/live DSN tokens.
# Does NOT source .env.canary or .env.live. The smoke is a read-mostly
# shadow test against a fresh local DB; it cannot broadcast, sign,
# or open positions in any meaningful way, but the env guard makes
# the intent explicit.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${SMOKE_CONFIG:-${ROOT_DIR}/configs/config.shadow.smoke.toml}"
LOG_DIR="${ROOT_DIR}/reports/p0_pg_03b_shadow_smoke_hardening"
DURATION_SECONDS="${SMOKE_DURATION_SECONDS:-600}"  # 10 minutes
BIN="${ROOT_DIR}/bin/lpbot-shadow"

usage() {
  cat <<EOF
usage: $0 [options]

  --config <path>          shadow config (default: \$SMOKE_CONFIG or
                           configs/config.shadow.smoke.toml)
  --duration <seconds>     bounded smoke duration (default: 600)
  --log-dir <path>         where to write SHADOW_SMOKE_RUN_LOG.txt
                           (default: reports/p0_pg_03_fresh_shadow_smoke)
  -h, --help               show this help

Environment overrides: SMOKE_CONFIG, SMOKE_DURATION_SECONDS, SMOKE_LOG_DIR,
LPBOT_SMOKE_NO_RPC (default: 1, set to 0 to disable no-RPC smoke mode).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)   CONFIG="$2"; shift 2 ;;
    --duration) DURATION_SECONDS="$2"; shift 2 ;;
    --log-dir)  LOG_DIR="$2"; shift 2 ;;
    -h|--help)  usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/SHADOW_SMOKE_RUN_LOG.txt"

# Safety guards: refuse to start if any canary/live/paper env var is
# set. The shadow binary itself does not read these, but the guard
# makes the smoke's intent obvious in CI logs.
for banned in LPBOT_CONFIRM_LIVE LPBOT_CANARY LPBOT_LIVE CANARY_DSN LIVE_DSN; do
  if [[ -n "${!banned:-}" ]]; then
    echo "error: ${banned} is set; smoke refuses to start." >&2
    exit 2
  fi
done

# Refuse to source canary / live env files even if present in CWD.
for banned_file in .env.canary .env.live; do
  if [[ -f "${ROOT_DIR}/${banned_file}" ]]; then
    echo "error: ${banned_file} present in repo root; smoke refuses to start." >&2
    echo "       (the smoke is shadow/test-only; canary/live env files belong in" >&2
    echo "        a separate canary/live stage with explicit operator approval.)" >&2
    exit 2
  fi
done

if [[ ! -x "${BIN}" ]]; then
  echo "info: ${BIN} not built yet; building now." >&2
  (cd "${ROOT_DIR}" && make build-shadow) >&2
fi

if [[ ! -f "${CONFIG}" ]]; then
  echo "error: config not found: ${CONFIG}" >&2
  echo "hint:  cp configs/config.shadow.smoke.example.toml ${CONFIG}" >&2
  echo "       then set POSTGRES_DSN and REDIS_URL appropriately." >&2
  exit 2
fi

echo "shadow_smoke: starting"                                            | tee "${LOG_FILE}"
echo "shadow_smoke: config=${CONFIG}"                                   | tee -a "${LOG_FILE}"
echo "shadow_smoke: duration=${DURATION_SECONDS}s"                       | tee -a "${LOG_FILE}"
echo "shadow_smoke: log=${LOG_FILE}"                                    | tee -a "${LOG_FILE}"
echo "shadow_smoke: cmd=${BIN} --config=${CONFIG}"                      | tee -a "${LOG_FILE}"
echo "shadow_smoke: started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"          | tee -a "${LOG_FILE}"
echo "shadow_smoke: LPBOT_SMOKE_NO_RPC=${LPBOT_SMOKE_NO_RPC:-<unset>}" | tee -a "${LOG_FILE}"

# P0-PG-03B: enable no-RPC mode by default. Operators can override to
# empty or 0 to fall back to the canonical (public-RPC-fallback)
# behavior, but the smoke's own safety check now requires the
# no-RPC lines to be present in the log.
export LPBOT_SMOKE_NO_RPC="${LPBOT_SMOKE_NO_RPC:-1}"

# Bounded run via timeout(1). 124 on timeout is captured but treated
# as a successful (planned) end by the safety check.
set +e
timeout --foreground "${DURATION_SECONDS}" \
  env LPBOT_SMOKE_NO_RPC="${LPBOT_SMOKE_NO_RPC}" \
  "${BIN}" --config="${CONFIG}" 2>&1 | tee -a "${LOG_FILE}"
EXIT=${PIPESTATUS[0]}
set -e

echo "shadow_smoke: ended_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"            | tee -a "${LOG_FILE}"
echo "shadow_smoke: exit_code=${EXIT}"                                  | tee -a "${LOG_FILE}"

# Normalize timeout exit to 0 for the smoke's purposes; the safety
# check distinguishes "ran the full window" from "exited early with
# an error" by reading the log timestamps, not the exit code alone.
if [[ "${EXIT}" -eq 124 ]]; then
  echo "shadow_smoke: timeout reached (planned end)"                     | tee -a "${LOG_FILE}"
  exit 0
fi
exit "${EXIT}"
