# HANDOFF 2026-09-07：lp-bot 从 157.173.123.24 搬迁到本机 + RH 增量转向起点

> 上游文档：`PROJECT_STATE_AND_ARCHITECTURE_20260907_CN.md`（B1，仓库内）、`docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md`（RH PRD v1.1）、`docs/rh_pivot/AGENT_START_AND_TASKS_CN.md`（RH-00…RH-09 任务包）。
> 本文只记录搬迁事实与当前基线；策略/资金授权状态与 B1 §11 一致：签名 0 / 广播 0 / 私钥 0 / LIVE 未授权。

## 0. 新会话对账（三样对不上先报再动手）

```bash
cd /opt/lpbot/lp-bot-v3-origin-check          # 本机真身；/root/lp-bot/lp-bot-v3-origin-check 是符号链接
git rev-parse --short HEAD                     # 搬迁基线 0e2b6e6；本文提交后为其后一个 commit
git status --short | wc -l                     # 搬迁时 79（2 tracked + 77 untracked）+ 本次新增 docs/
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider   # 3109 passed / 14 skipped
```

**157 机上 lp-bot 相关进程已于 2026-09-07 12:02 UTC 全部停止**（见 §3），`TPF_WATCH.jsonl` 不再更新；本机没有启动任何 daemon。

## 1. 本机布局

| 路径 | 内容 |
|---|---|
| `/opt/lpbot/lp-bot-v3-origin-check/` | **唯一活仓库真身**（与 VPS 路径 1:1；287 个测试硬编码此绝对路径） |
| `/root/lp-bot/lp-bot-v3-origin-check` | → 上者的符号链接 |
| `/opt/lpbot/*.md`、`TPF_WATCH.jsonl`、`backups/`、`.rollback/`、`d4_watchdog.sh`、`tpf_disconnect_recorder.py` | VPS 顶层原样复刻（记录器**未启动**） |
| `/root/lp-bot/.venv` | Python 3.12.3 venv；版本按 VPS `pip freeze` 钉死（`reports/migration/…/requirements.migrated.txt`） |
| `/root/lp-bot/_archive/` | `lp-bot-v3_sealed.tar.gz`（封存仓库，未解包）、`opt_lpbot_toplevel_docs_logs.tar.gz`、`lp-bot-v3-origin-check.bundle`（全分支 git bundle） |
| `/root/lp-bot/_migration/20260907T110206Z/` | 热快照 + 终轮快照：`*_final_compact.db`（两活库最终版）、`TPF_WATCH_final.jsonl`、`dirty.patch`、`status_short.txt`、`stop/`（停进程前后 ps / units / crontab 快照）、`SQLITE_*_BACKUPS.json` |
| `/root/lp-bot/reports/migration/20260907T110206Z/` | 盘点、rsync 日志、pytest/go 原始输出、`MIGRATION_MANIFEST.json`（126,755 个仓库文件 sha256）、`PROCESS_OWNERSHIP.md` |
| `/root/lp-bot/` 顶层 + `docs/rh_pivot/` | RH 交付包（PRD v1.1、任务书、配置契约、合成 fixture、validate_delivery.py）；`inputs/` 只有 B1，**B2 不存在**（用户确认无此文件，`validate_delivery.py` 因此 FAIL，以 PRD D01–D14 为准） |

## 2. 搬迁校验证据

| 项 | VPS | 本机 | 结果 |
|---|---|---|---|
| HEAD | `0e2b6e6`（`1e1d9bd` 之上 1 个纯文档 commit，B1 入库） | 同 | 一致 |
| 分支 | `feat/prd-v2.1-m0-shadow` | 同 | 一致 |
| 脏 diff sha256 | `77aa4c34…a516df` | 同 | 一致（`.gitignore` +4、`lp_rpc_pool_v1_readonly.py` +5，B1 §1 已知，**未提交、未丢弃**，留待用户决定） |
| `git status --short` | 79 行 | 79 行（本次工作前） | 逐行相同 |
| `reports/lp_scanner/scanner.db` | 活库 2.2G | `VACUUM INTO` 终轮压实 2.06G，integrity ok，`pool_snapshots` 2,971,610 / `opportunity_scores` 114,422 | 行数=停写后源库 |
| `reports/lp_scanner_v2_20260823/scanner.db` | 活库 1.6G | 压实 1.44G，ok，`pool_snapshots` 2,119,085 / `opportunity_scores` 80,880 | 同上 |
| `TPF_WATCH.jsonl` | 39,690 行（末 tick 12:02:39 UTC） | 同 | sha256 一致 |
| pytest | B1：3109 passed / 14 skipped | **3109 passed / 14 skipped / 0 failed**（`BASELINE_PYTEST_RAW_run4.log`） | 一致 |
| go test | B1：57 ok | **57 ok / 0 fail**（`BASELINE_GOTEST_RAW.log`，`-p 1`，4m51s） | 一致 |

首次 pytest 出现 287 个失败，全部是 `/opt/lpbot/...` 绝对路径未就位（`BASELINE_PYTEST_RAW.log` 留作证据），布局复刻后归零；**未改任何测试**。B1 §10.6 "备份副本仅 50–140M" 不成立：两库压实后仍 2.06G / 1.44G，数据是真实行。

## 3. 157 机处置记录（用户 2026-09-07 确认）

停止顺序与结果（`_migration/…/stop/`）：root 与 deploy 的 cron `*/5 * * * * /opt/lpbot/d4_watchdog.sh` 各删一行（原 crontab 已备份）→ PID 2082408 看门狗 → 2077656 scanner → 1749823 scanner-v2 → 1349731 paper runner → 3913930 断链记录器，全部 `kill -TERM` 后 2–6 秒自行退出，WAL 已 checkpoint。`ps` 前后 diff 只少了这 5 个及其 bash 包装；`systemctl --state=running` 前后**完全一致**，`md-*` / `poly-*` / `asr` 全部 active。

VPS 上**未删除**任何东西：`/opt/lpbot` 原样保留（含 6.7G `_migration_20260907T110206Z/`），`lpbot-*` systemd 单元保持 disabled，`lpbot-net-guard.service` 保留，另一 Claude 远程会话 PID 236588 未动（用户判定已无用）。VPS 上无任何测试钱包 env / keystore（均 0 字节）；只有 `.env.d4`（随仓库迁入）与封存仓库的 `.env.postgres`（在 tar 内）。

## 4. 硬边界（不变）

六常量 0.7 / 1.0 / 1.5 / 0.0005 / 0.001 / 0.50；100U / 单仓 50–60U / reserve 40U / 日亏 5U / 总回撤 10U；`LIVE_TRADING=false`；不签名不广播不生密钥；不 `git push`；不删不削弱测试；`scripts/lp_long_horizon/` 与封存仓库不动；新三桶只做 `SHADOW_SCENARIO`。

## 5. 下一步：RH-00（第一包，只读）

按 `docs/rh_pivot/AGENT_START_AND_TASKS_CN.md` 执行 RH-00。调研问题包已写在 `docs/specs/20260907_RH-00_baseline_audit_readonly.md`（Q1–Q7），用 `qwen-code -p … --disallowedTools Edit,Write` 逐题派发，产物落 `reports/rh_pivot/<UTC_RUN_ID>/RH-00/`。本机 Qwen 通道 2026-09-07 12:20 UTC 冒烟通过。

本机资源：2 核 / 3G 内存 / 22G 可用磁盘。**不要在本机同时复活两个 scanner**；RH 支线用独立 `reports/lp_rh/scanner.db`。

---

## 6. 搬迁后当日进展（2026-09-07 下午）

| commit | 内容 |
|---|---|
| `279b047` | 搬迁交接、RH 交付包入库、搬迁证据 |
| `3c0ee20` | **RH-00** 只读基线与证据链审计（`reports/rh_pivot/20260907T124500Z/RH-00/`） |
| `9b7d9bb` | **RH-00b** 修复 `RpcPool._penalize` 指数退避 float 溢出（+ 配对测试） |
| `eefcadd` | 补入被 `*.log` 规则忽略的原始测试/审查日志 |
| `0543e84` | **RH-01a** RH 资产注册表 + assets 新旧 schema 适配器（20 个配对测试） |

### RH-00 的核心结论

B1 §10.2 的 P0-1（scanner 73–80% 池永久 fail-closed，原因 `factory_registry_probe_incomplete`）**根因已定位并修复**：不是 RPC 退化、不是市场变化，而是 `scripts/lp_rpc_pool_v1_readonly.py:280` 的 `backoff = base * 2**(fails-1)` 在某端点连续失败数 ≥1025 时 float 溢出（`_fails` 只在成功时清零，28 天不重启的 daemon 必然累积到该量级）；`OverflowError` 从 `RpcPool.call` 的 except 分支穿透，被 `lp_pool_resolve_and_rank_v1_readonly.py` 记成探针错误。迁移库证据：首次出现 2026-08-31T22:02:28Z，此后**每一条**该原因的记录都带 `OverflowError`，此前一条都没有。已确定性复现（fails=1024 正常、1025 抛错）。

**因此近一周 live 漏斗的 "accepted=0" 不含任何经济信息**：最新批次 30 个候选全部是 `INPUTS_UNAVAILABLE`（24 个 OverflowError + 6 个 `NETCOVER_INPUT_MISSING`），`COMPUTED_FAIL` 为 0。阳性对照取自 2026-08-31T19:34Z（溢出前）批次：WETH-USDC NetCover 0.743、SOSO-USDC 0.300，均为真正的 `COMPUTED_FAIL: NETCOVER_BELOW_SHADOW`。

### 对 B1 的三处修正

1. B1 §6.1 列四个保护进程，实测**五个**（多一个写 `reports/lp_scanner_v2_20260823/scanner.db` 的 scanner）。
2. B1 §10.3 "两张死表 0 写入者"过时：`market_sessions` 的 writer 在 `lp_rwa_collector_daemon_v1_readonly.py:592`，`rpc_severe_incidents` 的 writer 在 `lp_shadow_gate_v1_readonly.py:293` 且已接入 daemon 主循环（:1826/:1859）；两者都是**有 writer、触发条件从未满足**，行数 0。
3. B1 §10.6 "backup 副本仅 50–140M" 不成立：`VACUUM INTO` 后仍为 2.06G / 1.44G。

A/B 档 `existing_terminal_conjunction` 无生产者（确认 NO_WRITER），RH 支线的股票终闸不得复制该模式。

### 进行中

RH-01b（`docs/specs/20260907_RH-01b_capabilities_pool_probe.md`）：链能力矩阵与 V3/V4 池探针，已派给 `qwen-task`。

### B2 设计稿已补齐（2026-09-07 16:23 UTC）

用户找到 `Robinhood_Chain_LP_Bot_50_30_20_全面转向设计文档_v1.0.md`，SHA-256 `1afc496f0a4a465a611cad6052882c14fdd0aeb92d06635fcbd4a6cea05dfd37`、45948 字节，与 `INPUT_MANIFEST.json` 逐字节吻合。已归档 `docs/rh_pivot/inputs/`，`validate_delivery.py` 现返回 **PASS**（`input_checksums_verified: true`，结果存 `docs/rh_pivot/DELIVERY_VALIDATION_LOCAL.json`）。

B2 内容与 PRD v1.1 的 D01–D14 修订一致，不改变推进路线。要点对照：B2 §55 假设 Go/Rust/PostgreSQL/NATS 技术栈（实际为 Python+SQLite，由 D01 修正）；B2 §48 的 RH-P0–P11 任务拆分被 PRD §19 的 RH-00–RH-09 取代；B2 §12 的 1%/3%/7% premium、§23 的 30/75/150 bps USDG、§26 的 2/3/5/8% 回撤门限均保留为 Shadow 初值；B2 §45 的 I-01–I-15 不变量已被 PRD §18.3 的 RH-INV-01–18 覆盖并加严；B2 §16 允许的 5% transfer tax 被 PRD §10.3 首版拒绝；B2 §21 的原子退出被 PRD §15.2 降为可选、分步退出为必须。
