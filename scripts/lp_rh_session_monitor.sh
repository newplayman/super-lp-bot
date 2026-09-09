#!/usr/bin/env bash
# RH 会话监护（Session monitor）
#
# 本脚本由 Claude 主脑通过 Monitor 工具常驻运行，每行 stdout 即一条通知。
# 它是**会话级**的：会话结束即终止，下一任会话必须重新启动它。
#
# 新会话启动方式（用 Monitor 工具，persistent: true）：
#   Monitor({
#     command: "bash /opt/lpbot/lp-bot-v3-origin-check/scripts/lp_rh_session_monitor.sh",
#     description: "RH 监护：worker 完成/失败、五个录制器停滞、Stage A 里程碑、Qwen 网关、槽位空闲",
#     persistent: true, timeout_ms: 3600000 })
#
# 它监护五类事件：
#   1. WORKER_DONE        qwen worker 完成或失败（成功与失败都报）
#   2. STALLED            五个录制器任一按行增长判定停滞
#   3. STAGE_A_MILESTONE  Stage A 每跨一小时
#   4. QWEN_GATEWAY       推理网关状态变化（已去抖：连续两次同状态才报）
#   5. IDLE_SLOTS         qwen 槽位空闲超 10 分钟（仅在网关可用时才算问题）
#
# 注意：本脚本只读，不写任何库，不重启任何进程——
# 进程自愈由 cron 上的五个 lp_rh_*_watchdog.sh 负责，两者职责分开。
set -u
ROOT=/opt/lpbot/lp-bot-v3-origin-check
PY=/root/lp-bot/.venv/bin/python
LOGDIR=/root/.qwen-code/logs
KEY=/root/.secrets/vllm-qwen38-api-key
SEEN=$(mktemp)
IDLE_SINCE=0
LAST_HOUR=-1
LAST_GW=""
PREV_GW=""
for f in "$LOGDIR"/task-*.log; do
  [ -e "$f" ] || continue
  grep -qE '^\[result' "$f" 2>/dev/null && basename "$f" >> "$SEEN"
done

while true; do
  # 1) worker 完成（成功与失败都报）
  for f in "$LOGDIR"/task-*.log; do
    [ -e "$f" ] || continue
    b=$(basename "$f")
    grep -qxF "$b" "$SEEN" && continue
    line=$(grep -E '^\[result' "$f" 2>/dev/null | tail -1)
    if [ -n "$line" ]; then
      echo "$b" >> "$SEEN"
      spec=$(grep -oE 'docs/specs/[^ "]*' "$f" 2>/dev/null | head -1 | grep -oE 'RH-[0-9a-z-]+')
      echo "WORKER_DONE [${spec:-?}] $b :: $line"
    fi
  done

  # 2) 三个录制器 + 采集器：按行增长判活
  "$PY" - <<'PYEOF' 2>/dev/null
import sqlite3, datetime, os
now = datetime.datetime.now(datetime.timezone.utc)
R = "/opt/lpbot/lp-bot-v3-origin-check/reports/lp_rh"
for db, tbl, limit, label in (("scanner.db","rh_market_states",420,"采集器"),
                              ("premium.db","rh_premium_samples",600,"溢价录制器"),
                              ("organic.db","rh_organic_windows",2700,"有机录制器"),
                              ("provider_health.db","rh_provider_rollup",2700,"提供方录制器")):
    p = os.path.join(R, db)
    if not os.path.exists(p):
        continue
    try:
        c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        t = c.execute(f"select max(sample_time) from {tbl}").fetchone()[0]
        if t is None:
            continue
        age = (now - datetime.datetime.fromisoformat(t.replace("Z","+00:00"))).total_seconds()
        if age > limit:
            n = c.execute(f"select count(*) from {tbl}").fetchone()[0]
            print(f"STALLED {label} {db} 最新样本 {age:.0f}s 前 (阈值 {limit}s) rows={n}")
    except Exception as e:
        print(f"MONITOR_ERROR {label} {db}: {type(e).__name__} {e}")
PYEOF

  # 3) Stage A 每小时里程碑
  h=$("$PY" -c "
import sqlite3,datetime
try:
    c=sqlite3.connect('file:$ROOT/reports/lp_rh/scanner.db?mode=ro',uri=True)
    a,b=c.execute('select min(sample_time),max(sample_time) from rh_market_states').fetchone()
    f=lambda s: datetime.datetime.fromisoformat(s.replace('Z','+00:00'))
    print(int((f(b)-f(a)).total_seconds()//3600))
except Exception: print(-1)" 2>/dev/null)
  if [ "${h:--1}" -ge 0 ] && [ "$h" -gt "$LAST_HOUR" ]; then
    LAST_HOUR=$h
    rows=$("$PY" -c "
import sqlite3
try:
    c=sqlite3.connect('file:$ROOT/reports/lp_rh/scanner.db?mode=ro',uri=True)
    print(c.execute('select count(*) from rh_market_states').fetchone()[0])
except Exception: print('?')" 2>/dev/null)
    echo "STAGE_A_MILESTONE ${h}h / 72h  samples=${rows}"
  fi

  # 4) Qwen 推理网关：状态变化时报一次（派活的关键依赖）
  tok=$(cat "$KEY" 2>/dev/null || echo "")
  gw=$(curl -s -o /dev/null -w '%{http_code}' -m 12 \
       "https://qwen-direct.1205.date:2236/v1/models" \
       -H "Authorization: Bearer ${tok}" 2>/dev/null || echo "000")
  gw=${gw:-000}
  # Debounce: the gateway flaps every few minutes and each transition is not
  # actionable on its own.  Only report a state that has held for two checks.
  if [ "$gw" = "$PREV_GW" ] && [ "$gw" != "$LAST_GW" ]; then
    if [ "$gw" = "200" ]; then
      echo "QWEN_GATEWAY 已恢复 (HTTP 200) — 可以重新派活"
    else
      echo "QWEN_GATEWAY 不可用 (HTTP ${gw}) — 派活会失败"
    fi
    LAST_GW=$gw
  fi
  PREV_GW=$gw

  # 5) 槽位空闲（仅在网关可用时才算问题）
  # 数「顶层」qwen-task：父进程不在 qwen-task 集合内的那一个。
  # 不能用 ppid==1（nohup 从交互 shell 起的 worker 父进程不是 init，会被漏数成 0，
  # 反过来催主脑在满负荷时超额派活），也不能直接 wc -l
  # （qwen-task 是 bash 包装，一路 worker 会有 2-3 个同名进程，会数成 3 路）。
  _qw=$(ps -eo pid,ppid,cmd | grep qwen-task | grep -v grep)
  if [ -z "$_qw" ]; then
    n=0
  else
    n=$(awk 'NR==FNR{p[$1]=1;next} !($2 in p){c++} END{print c+0}' \
          <(printf '%s\n' "$_qw") <(printf '%s\n' "$_qw"))
  fi
  if [ "$n" -lt 2 ] && [ "$gw" = "200" ]; then
    [ "$IDLE_SINCE" -eq 0 ] && IDLE_SINCE=$(date +%s)
    if [ $(( $(date +%s) - IDLE_SINCE )) -ge 600 ]; then
      echo "IDLE_SLOTS qwen=${n}/2 已空闲 $(( ($(date +%s) - IDLE_SINCE) / 60 )) 分钟 — 需派新活"
      IDLE_SINCE=$(date +%s)
    fi
  else
    IDLE_SINCE=0
  fi
  sleep 60
done
