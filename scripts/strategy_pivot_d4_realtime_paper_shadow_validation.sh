#!/usr/bin/env bash
# scripts/strategy_pivot_d4_realtime_paper_shadow_validation.sh
#
# LP_BOT_STRATEGY_PIVOT_D4_REALTIME_PAPER_SHADOW_VALIDATION_V1
#
# Read-only paper / shadow validation runner. No secrets. No wallet. No execution.
# Polls Base public RPC, DefiLlama, Binance, Hyperliquid. All public, no-auth.
#
# Subcommands:
#   start    — launch the validator in the background; writes PID file
#   status   — print uptime, last heartbeat, last block
#   stop     — gracefully shut down (SIGTERM)
#   finalize — write FINAL_VERDICT.json and shut down (called by stage supervisor)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="${STRATEGY_D4_RUN_ID:-$(date -u +%Y%m%d_%H%M%S)}"
REPORT_DIR="${ROOT_DIR}/reports/strategy_pivot_d4_realtime_paper_shadow_validation/${RUN_ID}"
LOG_DIR="${REPORT_DIR}/_logs"
PID_FILE="${REPORT_DIR}/d4_runner.pid"
LOG_FILE="${LOG_DIR}/runner.log"
mkdir -p "${LOG_DIR}"

cd "${ROOT_DIR}"

ACTION="${1:-start}"

case "${ACTION}" in
  start)
    if [ -f "${PID_FILE}" ] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
      echo "D4 already running (PID $(cat "${PID_FILE}")) at ${REPORT_DIR}"
      exit 0
    fi
    : > "${LOG_FILE}"
    nohup python3 -u scripts/strategy_pivot_d4_realtime_paper_shadow_validation.py "${REPORT_DIR}" \
      >"${LOG_FILE}" 2>&1 &
    echo $! > "${PID_FILE}"
    echo "D4 started: PID $(cat "${PID_FILE}"), report_dir=${REPORT_DIR}, log=${LOG_FILE}"
    ;;
  status)
    if [ -f "${PID_FILE}" ] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
      PID="$(cat "${PID_FILE}")"
      echo "D4 RUNNING (PID ${PID}) at ${REPORT_DIR}"
      if [ -f "${REPORT_DIR}/heartbeat.jsonl" ]; then
        echo "  last heartbeat: $(tail -1 "${REPORT_DIR}/heartbeat.jsonl")"
      fi
      if [ -f "${REPORT_DIR}/paper_position_state_hourly.jsonl" ]; then
        echo "  hourly state lines: $(wc -l < "${REPORT_DIR}/paper_position_state_hourly.jsonl")"
      fi
    else
      echo "D4 NOT RUNNING (stale pidfile at ${PID_FILE})"
    fi
    ;;
  stop)
    if [ -f "${PID_FILE}" ] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
      PID="$(cat "${PID_FILE}")"
      kill -TERM "${PID}" 2>/dev/null || true
      for i in 1 2 3 4 5 6 7 8 9 10; do
        kill -0 "${PID}" 2>/dev/null || break
        sleep 1
      done
      kill -KILL "${PID}" 2>/dev/null || true
      rm -f "${PID_FILE}"
      echo "D4 stopped"
    else
      echo "D4 not running"
    fi
    ;;
  finalize)
    if [ -f "${PID_FILE}" ] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
      PID="$(cat "${PID_FILE}")"
      kill -TERM "${PID}" 2>/dev/null || true
      for i in 1 2 3 4 5 6 7 8 9 10; do
        kill -0 "${PID}" 2>/dev/null || break
        sleep 1
      done
      kill -KILL "${PID}" 2>/dev/null || true
      rm -f "${PID_FILE}"
    fi
    echo "D4 finalized at ${REPORT_DIR}"
    ;;
  *)
    echo "usage: $0 {start|status|stop|finalize}" >&2
    exit 1
    ;;
esac
