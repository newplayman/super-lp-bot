# 157.173.123.24 进程归属清单（停止前需用户逐条确认）

盘点时间 2026-09-07 11:02–11:20 UTC，来源 `VPS_INVENTORY_RAW.log` C 段与补充核查。判定规则：cwd 或 cmdline 落在 `/opt/lpbot/**` → LPBOT；cmdline 含 polymarket / predict / binance / chainlink / marketd / asr 或 cwd 在 `/opt/lpbot` 外 → OTHER；共用或不确定 → AMBIGUOUS。

## LPBOT（拟停止，顺序自上而下）

| 序 | 类型 | 标识 | 详情 | 停止动作 |
|---|---|---|---|---|
| 1 | cron(root) | `*/5 * * * * /opt/lpbot/d4_watchdog.sh` | 看护 6 月 D4 长测 runner；脚本自述完成后不重启 | `crontab -l` 备份到 `_migration/`，再删除该行 |
| 2 | cron(deploy) | 同上 | 同一脚本重复登记 | 同上 |
| 3 | 进程 | PID 2082408 `bash scripts/night_scanner_watchdog.sh` | 每 120s 拉起 scanner；**必须先于 scanner 停** | `kill -TERM 2082408` |
| 4 | 进程 | PID 2077656 `lp_scanner_daemon … --db reports/lp_scanner/scanner.db` | 28 天，写 2.2G 活库 | `kill -TERM`，等 WAL checkpoint 退出 |
| 5 | 进程 | PID 1749823 `lp_scanner_daemon … --db reports/lp_scanner_v2_20260823/scanner.db` | 15 天，B1 未列 | `kill -TERM` |
| 6 | 进程 | PID 1349731 `lp_portfolio_paper_runner_v1_readonly.py` | 74 天纸面 runner | `kill -TERM` |
| 7 | 进程 | PID 3913930 `python3 /opt/lpbot/tpf_disconnect_recorder.py` | 断链记录器，每 60s 写 `TPF_WATCH.jsonl`；**最后停**，停前取终轮 tick | `kill -TERM` |

systemd `lpbot-shadow / lpbot-canary / lpbot-base-m1-executor / lpbot-solana-m1-sidecar`：已 disabled + inactive，无需动作（不 enable、不删除单元文件）。

## AMBIGUOUS（默认不动，需用户裁定）

| 标识 | 说明 |
|---|---|
| `lpbot-net-guard.service`（enabled/active-exited） | iptables 把 6379 / 5432x 端口锁到 localhost；名字带 lpbot，但保护的是 Redis / Supabase，可能被其他项目依赖。**建议保留** |
| PID 236588 Claude 远程会话（cwd `/opt/lpbot`，2h+，effort xhigh） | 今天 12:00 写 B1 的会话，仍存活。停 lp-bot 进程前请确认它已无用或由你关闭；我不 kill 它 |
| 第二 worktree `/tmp/lp_tp_h_h4_29ac336` | detached、干净，属 TP-H 时期遗留；不动 |

## OTHER（绝不碰）

`md-binance-orderbook-rust`、`md-binance-transfer-rust`、`md-poly-book*`、`md-poly-l2`、`md-poly-shadow-v3`、`md-poly-twap-rust-v2`、`md-predict-*`、`poly-*`、`polycollect`、`asr.service`、`/opt/marketd/*` 全部进程、`/opt/predict-account-forward/*`、`polymarket-proxy`、`rrsync`、cron `weather_heartbeat_watchdog.sh`、cron `/root/home_watch.sh`、codex / claude broker 进程、mailpit / kong / supabase 容器。

## 停止后复核

`ps -eo pid,args` 前后快照 diff，仅允许上表 7 项消失；`systemctl list-units --state=running` 前后一致；`md-*`、`poly-*` 单元仍 active。
