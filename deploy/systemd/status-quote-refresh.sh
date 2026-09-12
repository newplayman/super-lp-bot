#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
POOL_META="${REPO_ROOT}/reports/lp_rh/pool_meta.json"
FAIL_LOG="${REPO_ROOT}/reports/quote_refresh/cron_failures.jsonl"

svc_inst=false; [[ -f "/etc/systemd/system/lpbot-quote-refresh.service" ]] && svc_inst=true
tmr_inst=false; [[ -f "/etc/systemd/system/lpbot-quote-refresh.timer" ]] && tmr_inst=true
echo "Systemd files installed: service=${svc_inst} timer=${tmr_inst}"

tmr_status="$(systemctl is-enabled lpbot-quote-refresh.timer 2>&1 || true)"
tmr_status="$(echo "${tmr_status}" | tr -d '\r\n')"
[[ -z "${tmr_status}" ]] && tmr_status="disabled"
echo "Timer enabled status: ${tmr_status}"

if [[ -f "${POOL_META}" ]]; then
  mtime_s="$(stat -c %Y "${POOL_META}")"
  now_s="$(date +%s)"
  age_s=$((now_s - mtime_s))
  pretty_mtime="$(stat -c %y "${POOL_META}")"
  if [[ ${age_s} -lt 1800 ]]; then
    echo "Last refresh: FRESH (${age_s}s old, ${pretty_mtime})"
  else
    echo "Last refresh: STALE (${age_s}s old >= 1800s, ${pretty_mtime})"
  fi
else
  echo "Last refresh: NOT FOUND (${POOL_META} does not exist)"
fi

if [[ -f "${FAIL_LOG}" ]]; then
  fail_lines="$(wc -l < "${FAIL_LOG}")"
  echo "Cron failure log entries: ${fail_lines} (${FAIL_LOG})"
else
  echo "Cron failure log entries: 0 (no log file at ${FAIL_LOG})"
fi

if [[ "${tmr_status}" != "enabled" ]]; then
  echo "[BLOCKED_BY_OWNER_FREEZE] lpbot-quote-refresh.timer is NOT enabled (current: ${tmr_status})."
fi
exit 0
