# Polymarket 竞品采集器 — 操作手册

> 7×24 连续采集 5 个盈利账户的原始 activity 数据,用于做市/方向策略的逆向研究。
> 单轮 Python + 外部 cron 调度,与 `lp_long_horizon_*` 的"no daemon / no while-true / no sleep loop"红线一致。

## 1. 一次性环境准备(只需一次)

```bash
# 1.1 安装目录(仓外,不进 git)
sudo mkdir -p /opt/polycollect
sudo chown $USER /opt/polycollect

# 1.2 把 5 个 handle 解析后的地址写入 JSON
cat > /opt/polycollect/addresses.json <<'JSON'
{
  "schema_version": 1,
  "addresses": [
    "0xb55fa1296e6ec55d0ce53d93b9237389f11764d4",  # b55fa129
    "0x3c58ef422754ff22c7e806336feba0064d8b776b",  # antsaslyku
    "0xe0229e10a858860218b6132f4234602c47bd6603",  # jetfadil
    "0x21d0a97aac03917e752857a551bbe5103a00e8d7",  # pbot-6
    "0xb945945d5bcaf7b56834d4da8cdf8f8f94b2db68"   # l5zn1bwom8etsk
  ]
}
JSON

# 1.3 (可选) supervisor 脚本 + 调度,见第 5 节
```

## 2. 第一次跑:API 探测(必做,生成 reports/.../api_probe_summary.json)

```bash
cd /opt/lpbot/lp-bot-v3-origin-check
RUN_ID="probe_$(date -u +%Y%m%d_%H%M%S)"
python3 scripts/lp_polymarket_competitor_collector_v1_readonly.py \
  --mode probe \
  --addresses /opt/polycollect/addresses.json \
  --reports-dir reports/polymarket_competitor \
  --run-id "$RUN_ID"
# 产物:
#   reports/polymarket_competitor/$RUN_ID/ONEPAGE_CN.md
#   reports/polymarket_competitor/$RUN_ID/addresses_resolved.json
#   reports/polymarket_competitor/$RUN_ID/api_probe_summary.json
#   reports/polymarket_competitor/$RUN_ID/ARTIFACT_INDEX.md

git add reports/polymarket_competitor
git commit -m "research: polymarket_competitor probe ($RUN_ID)"
```

## 3. 烟囱测试:dryrun(拉一页,不写 DB)

```bash
python3 scripts/lp_polymarket_competitor_collector_v1_readonly.py \
  --mode dryrun \
  --addresses /opt/polycollect/addresses.json
# 期望输出: dryrun ok=True run_id=... per_address_count=5
# 不写 poly.db,不写 JSONL;只写 status.json 供 supervisor 验证存活
```

## 4. 一次完整 cycle(写真 DB + JSONL + reports)

```bash
RUN_ID="cycle_$(date -u +%Y%m%d_%H%M%S)"
python3 scripts/lp_polymarket_competitor_collector_v1_readonly.py \
  --mode cycle \
  --addresses /opt/polycollect/addresses.json \
  --db /opt/polycollect/poly.db \
  --export-dir /opt/polycollect/export \
  --status-path /opt/polycollect/status.json \
  --reports-dir reports/polymarket_competitor \
  --run-id "$RUN_ID"
# 期望: cycle ok ... inserted=N gap_addrs=0
# 产物: poly.db /opt/polycollect/export/activity_<addr>.jsonl × 5
#       status.json(心跳)
#       reports/polymarket_competitor/$RUN_ID/{ONEPAGE_CN.md, cycle_summary.json, ARTIFACT_INDEX.md}
```

## 5. 7×24 调度(放在 /opt/polycollect/,不进 git)

### 5.1 Supervisor 脚本

```bash
cat > /opt/polycollect/supervisor.sh <<'BASH'
#!/usr/bin/env bash
# /opt/polycollect/supervisor.sh
# 反复调起单轮采集器;flock 防止重叠;异常时记录到 supervisor.log
set -uo pipefail
LOCK="/var/lock/polycollect.lock"
exec 9>"$LOCK" || { echo "$(date -u +%FT%TZ) cannot open $LOCK" >&2; exit 0; }
flock -n 9 || { echo "$(date -u +%FT%TZ) previous cycle still running, skipping" >&2; exit 0; }

RUN_ID="cycle_$(date -u +%Y%m%d_%H%M%S)"
/usr/bin/python3 /opt/lpbot/lp-bot-v3-origin-check/scripts/lp_polymarket_competitor_collector_v1_readonly.py \
    --mode cycle \
    --addresses /opt/polycollect/addresses.json \
    --db /opt/polycollect/poly.db \
    --export-dir /opt/polycollect/export \
    --status-path /opt/polycollect/status.json \
    --reports-dir /opt/lpbot/lp-bot-v3-origin-check/reports/polymarket_competitor \
    --run-id "$RUN_ID" \
    >> /opt/polycollect/supervisor.log 2>&1
BASH
chmod +x /opt/polycollect/supervisor.sh
```

### 5.2 systemd 调度(每 60 秒一轮)

```bash
cat > /etc/systemd/system/polycollect.service <<'UNIT'
[Unit]
Description=Polymarket competitor single-cycle collector
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/opt/polycollect
ExecStart=/opt/polycollect/supervisor.sh
Nice=10
UNIT

cat > /etc/systemd/system/polycollect.timer <<'TIMER'
[Unit]
Description=Polymarket collector timer (every 60s)
Requires=polycollect.service

[Timer]
OnBootSec=30
OnUnitActiveSec=60
AccuracySec=5
Unit=polycollect.service
Persistent=true

[Install]
WantedBy=timers.target
TIMER

sudo systemctl daemon-reload
sudo systemctl enable --now polycollect.timer
systemctl list-timers polycollect.timer
journalctl -u polycollect.service -f   # 跟心跳
```

### 5.3 crontab 备选(无 systemd)

```bash
cat > /etc/cron.d/polycollect <<'CRON'
* * * * * root /opt/polycollect/supervisor.sh >> /var/log/polycollect.log 2>&1
CRON
```

## 6. 验收 — 7 天后跑

```bash
# 6.1 status.json 健康度
cat /opt/polycollect/status.json | python3 -c "
import json, sys, time
d = json.load(sys.stdin)
assert d['exit_status'] == 'ok', d
assert d.get('last_unresolved_gap') is None, d
print('exit_status ok; last_unresolved_gap=None')
print('rows_last_cycle_inserted:', d['totals']['rows_last_cycle_inserted'])
print('addresses:', d['addresses'])
"
# 6.2 DB 完整性
python3 - <<'PY'
import sqlite3
conn = sqlite3.connect('/opt/polycollect/poly.db')
for row in conn.execute("""
    SELECT address, COUNT(*) cnt, COUNT(DISTINCT dedup_key) uniq,
           datetime(MIN(timestamp),'unixepoch') first_ts,
           datetime(MAX(timestamp),'unixepoch') last_ts
    FROM activity GROUP BY address
"""):
    print(row)
PY
# 6.3 JSONL 文件存在 + 行数 == DB 行数
ls -la /opt/polycollect/export/
for f in /opt/polycollect/export/activity_*.jsonl; do
  echo "$f: $(wc -l < $f) lines"
done
# 6.4 抽查:任一账户最新 5 条 vs 网页 activity
python3 - <<'PY'
import json
addr = "0xb55fa1296e6ec55d0ce53d93b9237389f11764d4"
with open(f"/opt/polycollect/export/activity_{addr}.jsonl") as f:
    lines = f.readlines()
print(f"{addr} latest 5:")
for ln in lines[-5:]:
    r = json.loads(ln)
    print(" ", r.get("timestamp"), r.get("type"), r.get("side",""), r.get("slug",""))
PY
# 6.5 7 天 coverage:每账户在每个 UTC 日至少有一条
python3 - <<'PY'
import json
from datetime import datetime, timezone
expected_days = {(datetime.utcnow() - __import__("datetime").timedelta(days=d)).strftime("%Y-%m-%d") for d in range(7)}
for addr in [
    "0xb55fa1296e6ec55d0ce53d93b9237389f11764d4",
    "0x3c58ef422754ff22c7e806336feba0064d8b776b",
    "0xe0229e10a858860218b6132f4234602c47bd6603",
    "0x21d0a97aac03917e752857a551bbe5103a00e8d7",
    "0xb945945d5bcaf7b56834d4da8cdf8f8f94b2db68",
]:
    seen = set()
    with open(f"/opt/polycollect/export/activity_{addr}.jsonl") as f:
        for ln in f:
            r = json.loads(ln)
            ts = r.get("timestamp")
            if ts:
                seen.add(datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d"))
    missing = expected_days - seen
    print(addr, "missing days:", sorted(missing) or "none")
PY
```

## 7. 关键事实(实测,写在 api_probe_summary.json 之外便于人读)

- **API endpoint**:`https://data-api.polymarket.com/activity?user=<addr>&limit=<L>&offset=<O>`
- **Offset ceiling = 3000**(API 在 offset=3500 处返回 HTTP 400 + `{"error":"max historical activity offset of 3000 exceeded"}`)
- **无任何时间 / cursor 翻页参数**(`start / startTs / before / after / from / to / cursor / next` 全部被忽略)
- **字段集合**(21 个):`proxyWallet, timestamp, conditionId, type, size, usdcSize, transactionHash, price, asset, side, outcomeIndex, title, slug, icon, eventSlug, outcome, name, pseudonym, bio, profileImage, profileImageOptimized`
- **type 实测值**:`TRADE, REDEEM, TAKER_REBATE`(TRADE 主体,REDEEM 偶发,jetfadil 含 TAKER_REBATE 表明其有挂单)
- **5 个账户的 proxyWallet 全部由 5 条样本 API 校验通过**(proxyWallet 字段 == 解析地址)
- **唯一代理 l5zn 走 15m 周期**;其他 4 个走 5m 周期

## 8. 已知边界

- 公开数据**看不到对手挂单 / 撤单 / 订单簿位置**,只能看到已成交 fill + 链上活动
- 单页 500 条 + 6 页 = 3000 条 = 高频账户 ~2-3 小时窗口;`canary/shadow/live/paper` 等模式无任何触达
- 仓内 `deploy/systemd/lpbot-canary.service` 与 `lpbot-shadow.service` 显式 LOCKED,本采集器**不**与它们同目录,本 README 不提交任何 systemd unit(由操作员在 /opt/polycollect/ 自己放置)

## 9. 关联文件(全在仓库内)

- `scripts/lp_polymarket_competitor_collector_v1_readonly.py` — 采集器
- `scripts/supervisor_polymarket_competitor.sh.example` — supervisor 模板
- `tests/test_lp_polymarket_competitor_collector_v1_readonly.py` — 53 项无网络测试
- `reports/polymarket_competitor/probe_*/` — 历次 API 探测结果(提交)
- `reports/polymarket_competitor/cycle_*/` — 历次 cycle 报告(提交)
- `/opt/polycollect/{poly.db, export/, status.json, supervisor.log, supervisor.sh, addresses.json}` — 运行时数据(仓外)
