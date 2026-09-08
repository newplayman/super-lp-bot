#!/usr/bin/env bash
# One-glance status of the RH forward observation. Read-only; safe to run anytime.
set -u
ROOT=/opt/lpbot/lp-bot-v3-origin-check
PY=/root/lp-bot/.venv/bin/python
cd "$ROOT" || exit 1
"$PY" - <<'PY'
import sqlite3, datetime, json, os, subprocess
DB = "reports/lp_rh/scanner.db"
now = datetime.datetime.now(datetime.timezone.utc)
c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
n = c.execute("select count(*) from rh_market_states").fetchone()[0]
first, last = c.execute("select min(sample_time), max(sample_time) from rh_market_states").fetchone()
fd = datetime.datetime.fromisoformat(first.replace("Z", "+00:00"))
ld = datetime.datetime.fromisoformat(last.replace("Z", "+00:00"))
span_h = (ld - fd).total_seconds() / 3600
age = int((now - ld).total_seconds())
prices = [float(r[0]) for r in c.execute(
    "select reference_mid from rh_market_states where reference_mid is not null") if r[0]]
health = dict(c.execute("select state, count(*) from rh_rpc_health group by state").fetchall())
snaps = c.execute("select count(*) from rh_source_snapshots").fetchone()[0]
size_mb = os.path.getsize(DB) / 1024 / 1024
try:
    pid = open("reports/lp_rh/collector.pid").read().strip()
    alive = subprocess.run(["kill", "-0", pid], capture_output=True).returncode == 0
except Exception:
    pid, alive = "?", False
try:
    wd = json.load(open("reports/lp_rh/watchdog_state.json"))
except Exception:
    wd = {}
print("=" * 62)
print(" RH 正向观测状态 (PRD 21.1 Stage A 需 >= 72h)")
print("=" * 62)
print(f" 采集器 PID    : {pid}  {'运行中' if alive else '**已停止**'}")
print(f" 看门狗        : cron */5min  最近检查 {wd.get('checked_at','?')}  重启次数 {wd.get('restarts','?')}")
print(f" 样本数        : {n:,}")
print(f" 观测起点      : {first}")
print(f" 最新样本      : {last}  ({age}s 前)")
print(f" 已覆盖        : {span_h:.2f} h / 72 h   ({span_h/72*100:.1f}%)")
print(f" 剩余          : {max(0, 72-span_h):.2f} h")
if prices:
    print(f" 价格 WETH/USDG: 当前 {prices[-1]:,.2f}  区间 {min(prices):,.2f} ~ {max(prices):,.2f}")
print(f" RPC 健康      : {health}")
print(f" 快照去重后    : {snaps:,} 条 (样本 {n:,})")
print(f" 库大小        : {size_mb:.1f} MB / 2048 MB 软预算 ({size_mb/2048*100:.2f}%)")
print("=" * 62)
PY
