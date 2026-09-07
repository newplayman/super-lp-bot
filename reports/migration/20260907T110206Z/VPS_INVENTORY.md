# 157.173.123.24 `/opt/lpbot` 只读盘点（2026-09-07 11:02–11:20 UTC）

登录：`root@157.173.123.24`，key `~/.ssh/id_ed25519`（deploy 账号无本机公钥，root 可免密）。原始输出：`VPS_INVENTORY_RAW.log`。主机负载 28、24 个登录会话、`/` 193G 剩 58G。

## 与文档预期的差异（先报）

| # | 文档预期 | 实测 | 判定 |
|---|---|---|---|
| 1 | HEAD `1e1d9bd` | HEAD `0e2b6e6`（`1e1d9bd` 之上 1 个 commit：`docs(audit): project state and architecture snapshot 2026-09-07`，作者 `Codex Research`，12:00 CEST 提交，只加了 B1 文档） | 良性，代码未变 |
| 2 | 四个保护进程 | **五个**：多一个 `lp_scanner_daemon` 写 `reports/lp_scanner_v2_20260823/scanner.db`（PID 1749823，15 天），B1 §6.1 未列 | 需一并纳入 LPBOT 停止清单 |
| 3 | 无他人在改仓库 | 另一 Claude 远程会话 PID 236588（`/root/.claude/remote/ccd-cli`，cwd `/opt/lpbot`，已运行 2h16m，effort xhigh）仍存活；12:00 后无新写入 | 停进程前请用户确认该会话可关闭 |
| 4 | 有测试钱包 `.env` | **不存在**：`/etc/lpbot-executor/`、`/etc/lpbot-solana-executor/` 的 `keystore.json` / `password` 均 0 字节；全盘无含 PRIVATE_KEY / MNEMONIC 等键的 env 文件。仅有 `.env.d4`（`D4_BASE_RPC_URL`、`DATABASE_URL`）和封存仓库 `lp-bot-v3/.env.postgres` | 无钱包可迁；只迁 `.env.d4` |
| 5 | `inputs/` B2 在 VPS | 全盘 `find` 无 `*50_30_20*` / `*Robinhood*` | B1 已拉回并 SHA-256 校验一致；**B2 需用户提供** |
| 6 | `/opt/lpbot/lp-bot-mvp` | 不存在 | 无需处理 |

## 仓库

| 路径 | HEAD | 分支 | 脏改动 | 大小 |
|---|---|---|---|---|
| `lp-bot-v3-origin-check`（活） | `0e2b6e6` | `feat/prd-v2.1-m0-shadow` | 2 tracked（`.gitignore` +4、`scripts/lp_rpc_pool_v1_readonly.py` +5，B1 §1 已知）+ 77 untracked（reports/ 与 CODEX_*.md、CLAUDE.md、NIGHT_TASKS.md） | 5.1G（reports 4.9G，其中两个活 scanner.db 2.2G+1.6G、`polymarket_competitor` 711M；.git 40M） |
| `lp-bot-v3`（封存） | `4796ac9` | `feat/supabase-postgres-deployment` | 3 | 223M |
| 第二 worktree `/tmp/lp_tp_h_h4_29ac336` | `29ac336` detached | 0 | — |

remote 均为 `git@github.com:newplayman/super-lp-bot.git`。无 venv：守护进程用系统 `/usr/bin/python3.12`（3.12.3，107 个 dist-packages；本机同为 3.12.3）。无 `requirements.txt` / `pyproject.toml`。Go 1.22.2。

## 进程归属（PROCESS_OWNERSHIP 初稿）

**LPBOT（搬迁校验通过并经用户确认后停止）**

| PID | 运行 | 命令 | 打开文件 |
|---|---|---|---|
| 1349731 | 74d | `lp_portfolio_paper_runner_v1_readonly.py`（Base，6 池纸面） | `reports/lp_portfolio_paper_runner/launch_20260624_115413_freerpc/stdout.log` |
| 2077656 | 28d | `lp_scanner_daemon_v1_readonly.py --db reports/lp_scanner/scanner.db` | scanner.db + wal/shm，`reports/lp_shadow_launch/scanner-collection.log` |
| 2082408 | 28d | `bash scripts/night_scanner_watchdog.sh`（每 120s 拉起 2077656，最多 20 次）| — |
| 1749823 | 15d | `lp_scanner_daemon_v1_readonly.py --db reports/lp_scanner_v2_20260823/scanner.db` | 该 db + wal/shm，`reports/lp_shadow_launch_v2_20260823/scanner.log` |
| 3913930 | 27d | `python3 /opt/lpbot/tpf_disconnect_recorder.py`（每 60s 写 `TPF_WATCH.jsonl`） | `/opt/lpbot/tpf_recorder_stdout.log` |
| cron | root + deploy 各一条 | `*/5 * * * * /opt/lpbot/d4_watchdog.sh`（看护 6 月的 D4 长测 runner，注释说完成后不重启） | — |

systemd `lpbot-shadow / lpbot-canary / lpbot-base-m1-executor / lpbot-solana-m1-sidecar` 全部 disabled/inactive，不动即可。`lpbot-net-guard.service`（enabled/active，iptables 把 Redis/Supabase 端口锁 localhost）→ **AMBIGUOUS，保留不动**。

**OTHER（绝不碰）**：`md-*`（Binance / Polymarket / Predict 各采集器，Rust）、`poly-*`、`polycollect`、`asr.service`、`/opt/marketd/*`、`/opt/predict-account-forward/*`、`polymarket-proxy`、cron `weather_heartbeat_watchdog.sh`、`/root/home_watch.sh`、rrsync、codex/claude 会话、mailpit/kong/supabase 容器。

## 数据迁移评估（DATA_MIGRATION_DECISION）

- 活 SQLite 两个（2.2G + 1.6G）：用 `sqlite3.backup()` 热备到 `/opt/lpbot/_migration_<UTC>/`，B1 §10.6 称备份副本仅 50–140M（文件大部分为空闲页）。**迁备份，不迁原文件**；停进程后再做一次终轮备份取增量。
- `reports/` 其余 ~1.1G、`data/` 9.8M、`TPF_WATCH.jsonl` 27M、`/opt/lpbot/*.md`、`backups/` 5.3M、`.rollback/`：全迁。
- `reports/polymarket_competitor` 711M：在 lp-bot 仓库内，随仓库迁；若本机空间紧再议。
- 封存 `lp-bot-v3` 223M：`tar czf` 归档迁到 `/root/lp-bot/_archive/`。
- 不迁：`__pycache__`、`.pytest_cache`、`*.db-wal/-shm`、`/opt/lpbot/codex_*.log`（7 个共 ~20M 历史派工日志——一并 tar 进归档）。
- 本机：2 核 / 3G 内存 / 32G 可用。够搬迁与跑测试；**不适合同时复活两个 scanner**。
