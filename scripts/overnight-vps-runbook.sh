#!/usr/bin/env bash
# overnight-vps-runbook.sh
# Long-running unattended progression loop for VPS lp-bot deployment.
#
# Default behavior is read-only observability and reporting.
# - no auto-restart by default
# - no automatic code edits
# - no automatic schema changes
#
# Usage example:
#   LPBOT_HOST=lpbot@157.173.123.24 LPBOT_KEY=~/.ssh/lpbot_ed25519 \
#   ./scripts/overnight-vps-runbook.sh 8

set -euo pipefail

DURATION_HOURS="${1:-8}"
HOST="${LPBOT_HOST:-lpbot@157.173.123.24}"
KEY="${LPBOT_KEY:-$HOME/.ssh/lpbot_ed25519}"
LPBOT_ROOT="${LPBOT_ROOT:-/opt/lpbot/lp-bot-v3}"
SERVICE_NAME="${LPBOT_SERVICE:-lpbot-shadow}"
CYCLE_MIN="${LPBOT_CYCLE_MIN:-15}"
AUDIT_WINDOW_SEC="${LPBOT_AUDIT_WINDOW_SEC:-180}"
AUGMENT_RESTART="${LPBOT_AUTO_RESTART:-0}"
AUTO_INSTALL_TOOLS="${LPBOT_AUTOINSTALL_TOOLS:-0}"

TS="$(date +%Y%m%d-%H%M%S)"
RUN_DIR="${LPBOT_RUN_DIR:-$HOME/.lpbot-ops}"
mkdir -p "$RUN_DIR"
SUMMARY_FILE="$RUN_DIR/overnight-${TS}.md"
STATE_FILE="$RUN_DIR/overnight-${TS}.state"

SSH_OPTS=( -i "$KEY" -o StrictHostKeyChecking=no )

log() {
  printf '%s %s\n' "$(date -u +'%Y-%m-%d %H:%M:%S UTC')" "$*"
}

run_ssh() {
  ssh "${SSH_OPTS[@]}" "$HOST" "$@"
}

run_remote_cycle() {
  run_ssh "
    set -euo pipefail
    cd '$LPBOT_ROOT'
    /usr/bin/printf '%s\\n' \"===== cycle snapshot =====\"
    /usr/bin/date -u +%Y-%m-%dT%H:%M:%SZ
    /usr/bin/systemctl is-active '$SERVICE_NAME' || true
    /usr/bin/systemctl show -p LoadState,ActiveState,SubState,MainPID '$SERVICE_NAME' --no-pager || true
    /usr/bin/git rev-parse --abbrev-ref HEAD || true
    /usr/bin/git rev-parse --short HEAD || true
    /usr/bin/git status --short || true
    /usr/bin/pgrep -af '${SERVICE_NAME}' | /usr/bin/head -n 20 || true
  "
}

run_audit() {
  run_ssh "
    set -euo pipefail
    LPBOT_AUTOINSTALL_TOOLS=\"${AUTO_INSTALL_TOOLS}\" /opt/lpbot/lp-bot-v3/scripts/audit_shadow_vps.sh '$AUDIT_WINDOW_SEC' 15 > '/tmp/lpbot-overnight-audit.tmp' 2>&1 || true
    /usr/bin/cat /tmp/lpbot-overnight-audit.tmp
    /usr/bin/rm -f /tmp/lpbot-overnight-audit.tmp
  "
}

run_journal_delta() {
  local since="$1"
  run_ssh "
    set -euo pipefail
    /usr/bin/journalctl -u '$SERVICE_NAME' --since '$since' --no-pager | /usr/bin/grep -Ei 'panic|INVARIANT|failed|fatal|error' || true
  "
}

now_utc() {
  date -u +%Y-%m-%dT%H:%M:%SZ
}

{
  cat <<EOF
# LP-Bot Overnight Runbook Report

Start: $(now_utc)
Duration (hours): $DURATION_HOURS
Host: $HOST
Cycle (minutes): $CYCLE_MIN
Service: $SERVICE_NAME
Audit window sec: $AUDIT_WINDOW_SEC
Auto-restart: $AUGMENT_RESTART
Auto-install tools: $AUTO_INSTALL_TOOLS
EOF
} > "$SUMMARY_FILE"

START_TS=$(date +%s)
END_TS=$(( START_TS + DURATION_HOURS * 3600 ))
ALERTS=0
CYCLES=0
LAST_ALERT_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
START_DATE="$(now_utc)"
echo "$START_TS" > "$STATE_FILE"

echo "overnight-start: $(now_utc)" >> "$SUMMARY_FILE"
log "Starting overnight runbook. Summary: $SUMMARY_FILE"

while [ "$(date +%s)" -lt "$END_TS" ]; do
  CYCLES=$((CYCLES + 1))
  CYCLE_TS=$(date +%s)
  cycle_tag="$(now_utc)"

  {
    echo
    echo "## Cycle ${CYCLES} @ ${cycle_tag}"
    echo
    echo "### 1) Snapshot"
  } >> "$SUMMARY_FILE"

  if snapshot="$(run_remote_cycle)"; then
    echo "$snapshot" >> "$SUMMARY_FILE"
  else
    ALERTS=$((ALERTS + 1))
    echo "- ALERT: snapshot failed in cycle ${CYCLES}" >> "$SUMMARY_FILE"
    snapshot=""
  fi

  echo "### 2) Audit (window=${AUDIT_WINDOW_SEC}s)" >> "$SUMMARY_FILE"
  if audit="$(run_audit)"; then
    echo "$audit" >> "$SUMMARY_FILE"
  else
    ALERTS=$((ALERTS + 1))
    echo "- ALERT: audit failed in cycle ${CYCLES}" >> "$SUMMARY_FILE"
    audit=""
  fi

  if echo "$audit" | grep -Eq 'AUDIT_VERDICT=FAIL|^FAIL:'; then
    ALERTS=$((ALERTS + 1))
    echo "- ALERT: audit fail in cycle ${CYCLES}" >> "$SUMMARY_FILE"
  fi

  echo "### 3) New critical logs since last cycle" >> "$SUMMARY_FILE"
  if delta="$(run_journal_delta "$LAST_ALERT_TS")"; then
    :
  else
    delta=""
  fi
  if [ -n "$delta" ]; then
    ALERTS=$((ALERTS + 1))
    echo "$delta" >> "$SUMMARY_FILE"
    echo "LAST_ALERT_TS=$cycle_tag" >> "$STATE_FILE"
    LAST_ALERT_TS="$cycle_tag"
  else
    echo "(none)" >> "$SUMMARY_FILE"
  fi

  if [ "$AUGMENT_RESTART" = "1" ]; then
    if echo "$snapshot" | /usr/bin/grep -q "inactive" ; then
      {
        echo "### 4) Auto-restart (enabled)"
        run_ssh "sudo systemctl restart '$SERVICE_NAME' && sudo systemctl is-active '$SERVICE_NAME'"
      } >> "$SUMMARY_FILE"
    fi
  fi

  echo "Cycle ${CYCLES} complete. next at +${CYCLE_MIN}m" >> "$SUMMARY_FILE"
  sleep "$((CYCLE_MIN * 60))"
done

END_DATE="$(now_utc)"
{
  echo
  echo "## Done"
  echo "End: $END_DATE"
  echo "Cycles: $CYCLES"
  echo "Alerts: $ALERTS"
  echo "Summary file: $SUMMARY_FILE"
} >> "$SUMMARY_FILE"

log "Overnight runbook finished. Alerts=$ALERTS, cycles=$CYCLES. report=$SUMMARY_FILE"
