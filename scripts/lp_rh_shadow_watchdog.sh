#!/usr/bin/env bash
# RH shadow daemon watchdog. Cron every 5 minutes; token-free, no agent.
# Liveness is judged by ROW GROWTH, not merely by the process existing: a recorder
# that is alive but wedged (RPC black hole, stuck socket) must also be restarted.
set -u
ROOT=/opt/lpbot/lp-bot-v3-origin-check
PY=/root/lp-bot/.venv/bin/python
DB="$ROOT/reports/lp_rh/shadow.db"
PIDF="$ROOT/reports/lp_rh/shadow_daemon.pid"
LOG="$ROOT/reports/lp_rh/shadow_daemon.log"
WLOG="$ROOT/reports/lp_rh/shadow_watchdog.log"
STATE="$ROOT/reports/lp_rh/shadow_watchdog_state.json"
MAX_RESTARTS=50
# Period is 180s and the REST source rate-limits, so allow three missed cycles
# before calling it wedged.
STALL_SECS=2400
ts() { date -u +%FT%TZ; }
say() { echo "$(ts) $*" >> "$WLOG"; }
cd "$ROOT" || { say "FATAL cannot cd $ROOT"; exit 1; }

read -r rows last <<<"$("$PY" -c "
import sqlite3, datetime
rows, age = -1, -1
try:
    c = sqlite3.connect('file:$DB?mode=ro', uri=True)
    rows = c.execute('select count(*) from rh_shadow_episodes').fetchone()[0]
    t = c.execute('select max(started_at) from rh_shadow_episodes').fetchone()[0]
    d = datetime.datetime.fromisoformat(t.replace('Z', '+00:00'))
    age = int((datetime.datetime.now(datetime.timezone.utc) - d).total_seconds())
except Exception:
    pass
print(rows, age)" 2>/dev/null)"
[ -z "${rows:-}" ] && rows=-1
[ -z "${last:-}" ] && last=-1

pid=$(cat "$PIDF" 2>/dev/null || echo "")
alive=0; [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && alive=1
restarts=$("$PY" -c "
import json
try: print(json.load(open('$STATE')).get('restarts', 0))
except Exception: print(0)" 2>/dev/null)
[ -z "${restarts:-}" ] && restarts=0

need_restart=0; reason=""
if [ "$alive" -eq 0 ]; then
  need_restart=1; reason="process_dead"
elif [ "$last" -ge 0 ] && [ "$last" -gt "$STALL_SECS" ]; then
  need_restart=1; reason="stalled_${last}s"
fi

if [ "$need_restart" -eq 1 ]; then
  if [ "$restarts" -ge "$MAX_RESTARTS" ]; then
    say "GIVING_UP restarts=$restarts reason=$reason rows=$rows"
  else
    if [ "$alive" -eq 1 ]; then
      kill -TERM "$pid" 2>/dev/null; sleep 5
      kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null
    fi
    rm -f "$PIDF"
    setsid nohup env -u PYTHONPATH "$PY" scripts/lp_rh_shadow_daemon_v1_readonly.py \
      --db "$DB" --pool 0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca \
      --pool-meta-json "$ROOT/reports/lp_rh/pool_meta.json" --samples 200 \
      --position-usd 1000 --capital-usd 10000 --horizon-hours 720 \
      --period-secs 900 --pid-file "$PIDF" >> "$LOG" 2>&1 < /dev/null &
    restarts=$((restarts + 1))
    # Verify the restart actually took.  A watchdog that logs RESTARTED
    # without checking will claim success forever while the process dies
    # on a bad argument list, which is exactly what happened here.
    sleep 6
    newpid=$(cat "$PIDF" 2>/dev/null || echo "")
    if [ -n "$newpid" ] && kill -0 "$newpid" 2>/dev/null; then
      say "RESTARTED reason=$reason rows=$rows restarts=$restarts pid=$newpid"
    else
      say "RESTART_FAILED reason=$reason rows=$rows restarts=$restarts (see $LOG)"
    fi
  fi
else
  say "OK pid=$pid rows=$rows age=${last}s restarts=$restarts"
fi

"$PY" -c "
import json
json.dump({'checked_at': '$(ts)', 'pid': '$pid', 'alive': $alive, 'rows': $rows,
           'last_sample_age_secs': $last, 'restarts': $restarts,
           'needed_restart': $need_restart, 'reason': '$reason'},
          open('$STATE', 'w'), indent=1)" 2>/dev/null
