#!/usr/bin/env bash
# 夜间采数 scanner 自愈看门狗（2026-08-09 夜，Claude 启动）
# 只做一件事：scanner 死了就拉起来。只读采数，不碰钱包/不广播。
# 停止方法：kill 本脚本的 PID（见 reports/lp_shadow_launch/watchdog.pid），再 kill scanner。
set -u
cd /opt/lpbot/lp-bot-v3-origin-check || exit 1

PIDFILE="reports/lp_scanner/scanner.pid"
LOG="reports/lp_shadow_launch/scanner-collection.log"
WDLOG="reports/lp_shadow_launch/watchdog.log"
MAX_RESTARTS=20
restarts=0

echo "$$" > reports/lp_shadow_launch/watchdog.pid

start_scanner() {
  setsid nohup python3 -u scripts/lp_scanner_daemon_v1_readonly.py \
    --chain Base --projects aerodrome-slipstream uniswap-v3 --top 30 \
    --db reports/lp_scanner/scanner.db \
    --pid-file "$PIDFILE" \
    --coarse-interval-secs 900 --top-interval-secs 60 \
    --window-blocks 86400 --window-days 1 --n-windows 6 \
    --vetted-menu-out reports/lp_scanner/vetted_menu.json \
    >> "$LOG" 2>&1 < /dev/null &
}

while true; do
  sleep 120
  pid="$(cat "$PIDFILE" 2>/dev/null || echo '')"
  if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
    if [ "$restarts" -ge "$MAX_RESTARTS" ]; then
      echo "$(date -u +%FT%TZ) 达到重启上限 $MAX_RESTARTS，停止自愈并退出（需人工介入）" >> "$WDLOG"
      exit 1
    fi
    restarts=$((restarts + 1))
    echo "$(date -u +%FT%TZ) scanner 不在（pid='$pid'），第 $restarts 次拉起" >> "$WDLOG"
    start_scanner
  fi
done
