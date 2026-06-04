# LP Long Horizon Read-only Collector Staged Run Request — One-Pager

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_STAGED_RUN_REQUEST_V1`
- run_id: `20260604_123955`
- branch: `feat/supabase-postgres-deployment`
- status: **WARN** (改向 one_shot_7d_replaced=true; 仅生成模板, 不启动任何 stage)

## 0. 一句话

原 `LP_LONG_HORIZON_READONLY_COLLECTOR_7D_RUN_REQUEST_V1` (一次性 7d) 改
为 `LP_LONG_HORIZON_READONLY_COLLECTOR_STAGED_RUN_REQUEST_V1` (6 阶段:
6h/12h/24h/48h/72h/7d). `auto_advance_allowed=false`, 每阶段必须独立
manual approval, 任一 FAIL 走 fix_repeat / pause / stop. 本轮**不**启动
任何 stage, **不**实装 cron / systemd / tmux session, **不**记录任何
approval 为 true.

## 1. 核心字段 (per FINAL_VERDICT.json)

| 字段 | 值 | 含义 |
|---|---|---|
| `one_shot_7d_replaced` | `true` | 原 7d 一次性改为分阶段 |
| `staged_plan_ready` | `false` | 本轮仅生成模板, 未实际进入 6h run |
| `stages` | `["6h", "12h", "24h", "48h", "72h", "7d"]` | 6 阶段顺序 |
| `first_stage` | `6h` | 默认起步, 不直接 7d |
| `auto_advance_allowed` | `false` | 每阶段必须独立审批, 不会自动晋级 |
| `manual_approval_required_each_stage` | `true` | 6 阶段都必须独立审批 |
| `stage_gate_rules_ready` | `false` | 规则已生成 (Stage D), 但本轮未实装 check_stage_gate.py |
| `tmux_template_generated` | `false` | (注: JSON 字面 false, 但模板文件已生成; 留待 6H_RUN_APPROVAL_V1 启用) |
| `cron_enabled` | `false` | 本轮不实装 |
| `systemd_enabled` | `false` | 本轮不实装 |
| `daemon_started` | `false` | 本轮不实装 |
| `long_run_started` | `false` | 本轮不启动任何 stage |
| `can_run_probe_now` | `false` | locked |
| `tiny_canary_allowed` | `no` | locked |
| `edge_proven` | `no` | locked |
| `wallet_or_tx_touched` | `false` | locked |
| `transaction_sent` | `false` | locked |
| `recommended_next_stage` | `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_APPROVAL_V1` | |

## 2. 阶段 A-H 总结

| 阶段 | 结果 |
|---|---|
| A workspace safety | PASS |
| B input evidence audit | PASS (redirect 7D → STAGED 记录) |
| C staged run plan | PASS (6 stages / first=6h / auto_advance=false) |
| D stage gate rules | PASS (13 core gate rules; PASS/WARN_ACCEPTABLE/FAIL) |
| E stage approval templates | PASS (6 APPROVE phrase + reject + pause) |
| F stage runtime budget | PASS (size + RPC + CPU + RAM 估算) |
| G stage failure & abort policy | PASS (5 abort conditions + 3 decision paths) |
| H staged tmux script template | PASS (disabled by default; 6H_RUN_APPROVAL_V1 启用) |
| I final verdict | PASS (this file) |

## 3. 6 阶段 + 阶段间晋级条件

| Stage | 时长 | 累计 | 晋级条件 |
|---|---|---|---|
| 1 | 6h | 6h | 13 gate PASS / WARN_ACCEPTABLE + final_verdict + audit + manual approval + runtime budget + failure policy |
| 2 | 12h | 18h | 同上 + 6h 跑成功 |
| 3 | 24h | 42h | 同上 + 12h 跑成功 |
| 4 | 48h | 90h | 同上 + 24h 跑成功 + paid RPC 接入 |
| 5 | 72h | 162h | 同上 + 48h 跑成功 + paid RPC 充分 |
| 6 | 7d (168h) | 330h | 同上 + 72h 跑成功 + paid RPC 充分 + disk archive plan reviewed |

## 4. 6 阶段 APPROVE phrase

```
APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=6h  mode=readonly no_probe=true
APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=12h mode=readonly no_probe=true
APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=24h mode=readonly no_probe=true
APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=48h mode=readonly no_probe=true
APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=72h mode=readonly no_probe=true
APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=7d  mode=readonly no_probe=true
```

## 5. 5 类 abort condition + 3 决策路径

abort conditions: `consecutive_429` / `error_rate` / `write_failure` /
`safety_self_check_failure` / `banned_token_detected`

决策路径: `fix_repeat` / `pause` / `stop`

## 6. tmux 模板 (disabled)

- session naming: `lp_long_horizon_<STAGE>_run_<RUN_ID>`
- max 1 concurrent session
- 默认 disabled, 实装留待 6H_RUN_APPROVAL_V1
- 不允许 cron / systemd 包装

## 7. safety 18 字段 (locked)

```json
{
  "touched_trading_path": false,
  "touched_wallet_tx_bridge_live_paper": false,
  "wallet_or_tx_touched": false,
  "solana_wallet_or_keypair_touched": false,
  "transaction_sent": false,
  "send_hard_disable_still_active": true,
  "no_paid_rpc_integration": true,
  "no_paid_indexer_integration": true,
  "no_protocol_re_run": true,
  "no_heuristic_modification": true,
  "no_long_running_daemon": true,
  "no_signer_creation": true,
  "no_7d_14d_30d_run": true,
  "no_actual_stage_run": true,
  "no_approval_recorded_true": true,
  "secret_leak_count": 0,
  "production_write_count": 0,
  "shadow_overwrite_count": 0,
  "tmux_actual_session_started": 0
}
```

## 8. 下一阶段: LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_APPROVAL_V1

任务:
1. 收到 `APPROVAL_RECORD.json` (per Stage E 模板)
2. 验证 phrase match
3. 实装 paid_rpc_indexer (9 项 readiness 第 7 项)
4. uncomment tmux 启动模板
5. 启 tmux session `lp_long_horizon_6h_run_<RUN_ID>`
6. 监控 log + abort condition
7. 6h 跑完 → 写 FINAL_VERDICT.json + 杀 session
8. 等下阶段 (12h) manual approval

## 9. 警示

- 当前不开 live / canary / paper / probe
- 当前不接 wallet / signer / keypair
- 当前不发 transaction / approve / swap / add_liquidity / remove_liquidity / collect_fee
- 当前不写 production positions / shadow 原始表
- 当前**不**启动任何 stage (6h/12h/24h/48h/72h/7d)
- 当前**不**实装 cron / systemd / tmux 实际启动
- 当前**不**记录任何 approval 为 true
- `internal/core/execution/hard-disable` 仍 active, 不释放
