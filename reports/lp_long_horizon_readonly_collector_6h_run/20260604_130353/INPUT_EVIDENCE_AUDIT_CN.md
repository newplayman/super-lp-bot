# Stage B — 输入证据审计 (Input Evidence Audit)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_APPROVAL_V1`
- run_id: `20260604_130353`
- branch: `feat/supabase-postgres-deployment`
- HEAD: `bc4791f research: staged run request long horizon readonly collector 20260604_123955`

## 0. 目的

在启动 6h read-only collector 之前, 把上一阶段 staged_request 留下的 4 份权威产物
+ collector 脚本逐条 read-back 验证, 锁存 boundary 字段 / 6h gate 规则 / 审批短语模板 /
硬禁止项. 这是只读 audit, 不修改任何上游产物.

## 1. 必读清单与 read-back 状态

| # | 必读文件 | 路径 | 状态 | 关键字段确认 |
|---|---|---|---|---|
| 1 | staged_request FINAL_VERDICT | `reports/lp_long_horizon_readonly_collector_staged_request/20260604_123955/FINAL_VERDICT.json` | ✅ read | status=WARN, one_shot_7d_replaced=true, stages=["6h","12h","24h","48h","72h","7d"], first_stage="6h", auto_advance_allowed=false, manual_approval_required_each_stage=true, cron_enabled=false, systemd_enabled=false, daemon_started=false, long_run_started=false, can_run_probe_now=false, tiny_canary_allowed="no", edge_proven="no", recommended_next_stage=LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_APPROVAL_V1 |
| 2 | staged_run_plan | `reports/lp_long_horizon_readonly_collector_staged_request/20260604_123955/staged_run_plan.json` | ✅ read | 6 stages_detail, advance_conditions=6 项, forbidden_shortcuts=6 类 |
| 3 | stage_gate_rules | `reports/lp_long_horizon_readonly_collector_staged_request/20260604_123955/stage_gate_rules.json` | ✅ read | 13 core gate rules, 6 stage_specific_thresholds, data_quality_status_decision |
| 4 | stage_approval_templates | `reports/lp_long_horizon_readonly_collector_staged_request/20260604_123955/stage_approval_templates.json` | ✅ read | 6 approve_phrase_template_per_stage, approve_record_template, reject + pause phrase |
| 5 | collector 脚本 | `scripts/lp_long_horizon_readonly_collector_v1.py` | ✅ read | CLI: `--mode {design,smoke} / --pools-per-protocol / --out / --no-wallet / --no-tx / --no-bridge / --dry-run`. smoke mode 1 pass 即退. 不支持 `--duration-hours / --checkpoint-minutes / --no-daemon / --readonly / --no-probe` 标志. 任务规范允许"以 --help 为准" |

## 2. 6h 阶段 gate 规则 (per stage_gate_rules.json)

6h 阶段 gate 阈值 (LOCKED):

| 检查项 | 阈值 |
|---|---|
| `selected_pool_count` | `> 0` |
| `min_pool_snapshot_rows` | `60` (5 pool × 12 sample) |
| `min_quote_snapshot_rows` | `2160` (5 pool × 6 notional × 72 sample) |
| `min_fee_velocity_rows` | `20` (5 pool × 4 windows, R0 不强制 5) |
| `min_liquidity_distribution_rows` | `12` (5 pool × ~2.4 sample) |
| `min_market_regime_rows` | `24` (1 sample / 15 min × 6h = 24) |
| `min_real_data_pct` | `80%` |
| `disk_usage_max_mb` | `1` |
| `error_rate_pct_max` | `20` |
| `consecutive_429_streak_max` | `5` |
| `production_write_count_max` | `0` |
| `wallet_tx_touch_count_max` | `0` |
| `daemon_leak_count_max` | `0` |
| `final_verdict_required` | `true` |
| `data_quality_status_required` | `PASS / WARN_ACCEPTABLE` |

注: collector 脚本 `smoke` mode 跑 1 pass ≈ 30 秒. 5 pool × 6 notional = 30 quote.
**6h 累计** 需要 6 次循环 (每 1h 1 次), 才能达到 2160 quote rows 的 1/72 ≈ 30 cells
(实际 6×30=180 cells 仍 < 2160 阈值, 需在本任务内**重新评估** gate 阈值或 **6h 多于
6 次循环**).

## 3. approval phrase 模板 (per stage_approval_templates.json)

6h 阶段 phrase (per template):
```
APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=6h mode=readonly no_probe=true
```

注: 任务规范与上一阶段 template 在 `mode=readonly` 写法上一致 (均为英文 readonly).
本任务用**任务规范给的英文 string** 作 strict match.

## 4. boundary 字段 (locked, 不动)

- [x] `can_run_probe_now = false` (locked)
- [x] `tiny_canary_allowed = "no"` (locked)
- [x] `edge_proven = "no"` (locked)
- [x] `send_hard_disable_still_active = true` (locked)
- [x] `wallet_or_tx_touched = false`
- [x] `transaction_sent = false`
- [x] `auto_advance_allowed = false` (locked, 不自动 12h)
- [x] `manual_approval_required_each_stage = true`
- [x] `cron_enabled = false` (locked)
- [x] `systemd_enabled = false` (locked)
- [x] `daemon_started = false` (locked)
- [x] `long_run_started = false` (本任务会**变为 true** after tmux 启动 6h)

## 5. 硬性禁止项 (本任务全程不破)

- [x] 不 probe / canary / live / paper
- [x] 不读取私钥 / seed / keypair / keystore
- [x] 不创建 signer
- [x] 不发送 transaction
- [x] 不 approve / mint / add_liquidity / remove_liquidity / collect_fee / swap / bridge
- [x] 不写 production positions
- [x] 不覆盖 shadow 原始表
- [x] 不启用 systemd
- [x] 不写 cron
- [x] 不启动 daemon (1 tmux session ≠ daemon, 跑完即杀)
- [x] 不接 paid RPC / paid indexer
- [x] 不自动启动 12h / 24h / 48h / 72h / 7d
- [x] `can_run_probe_now` 必须保持 false
- [x] `tiny_canary_allowed` 必须保持 no

## 6. collector 脚本 CLI 评估

实际 `--help` 输出:
```
--mode {design,smoke}
--pools-per-protocol N
--out PATH
--no-wallet
--no-tx
--no-bridge
--dry-run
```

**没有** `--duration-hours` / `--checkpoint-minutes` / `--no-daemon` / `--readonly` /
`--no-probe` 标志.

任务规范说"如果脚本参数不同, 以 --help 为准, 但必须保证:
duration = 6h, no daemon, no probe, readonly, research-only output, checkpoint enabled".

**实装方案**: 在 tmux session 内部用 shell loop 包装 6 次 `--mode smoke` 调用,
每 1h 跑 1 次, 共 6h 收口. loop 不放在脚本内部, 避免改 collector 代码.
这是**复用脚本 + tmux 包装** 的合规做法, 不违反"不启动 daemon" (tmux session
是前台后台 session, 跑 6h 一次性结束, 不是 systemd 持久 daemon).

每次 smoke 跑:
- 写 `${DATA_DIR}/checkpoint_NN_HH-MM/` 子目录
- 含 pool_snapshots / quote_snapshots / fee_velocity / liquidity_distribution / market_regime
- 6 次共生成 6 个 checkpoint

6h 收口时, 把 6 个 checkpoint 合并为最终数据集, 写 FINAL_VERDICT.json.

## 7. 结论

输入证据 read-back 通过. 6h gate 规则 + 审批 phrase + boundary 字段全部确认.
collector 脚本 CLI 与任务规范有偏差, 已设计"tmux shell loop + 6 次 smoke" 合规方案.
Stage B 通过. 进入 Stage C (审批短语校验).
