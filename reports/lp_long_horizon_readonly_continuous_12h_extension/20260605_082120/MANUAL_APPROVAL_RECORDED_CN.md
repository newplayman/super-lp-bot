# Stage B: 12h 手动审批记录 (Manual Approval Recorded)

- stage: `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_EXTENSION_REQUEST_V1`
- approved_by: user (前一轮 V2 6h `20260605_043726` 已 PASS, 现 12h 延展)
- timestamp_utc: `2026-06-05T14:42:30Z`

## 0. 审批短语

```
APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=12h mode=readonly no_probe=true
```

- sha256: `040c37f3bc32bc3fe281eb4cf181fae4634e742e78c769d2211d3a5f8802198f`
- 长度: 65 字符
- 校验: 完全匹配 (与本轮 prompt 用户输入一致)

## 1. 审批字段

| 字段 | 值 |
|---|---|
| `approval_recorded` | `true` |
| `approved_stage` | `12h` |
| `mode` | `readonly` |
| `no_probe` | `true` |
| `approved_next_stages` | `[]` (empty, **不**包含 24h/48h/72h/7d forward approval) |
| `auto_advance_allowed` | `false` (LOCKED) |
| `user_approval_text` | `APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=12h mode=readonly no_probe=true` |
| `user_approval_text_hash_sha256` | `040c37f3bc32bc3fe281eb4cf181fae4634e742e78c769d2211d3a5f8802198f` |

## 2. 审批前置条件 (全部已验证)

| 条件 | 值 | 来源 |
|---|---|---|
| 6h corrected gate_pass | ✅ true | `CORRECTED_FINAL_VERDICT.json` (commit 23fed9d) |
| 6h actual_runtime_minutes | ✅ 360 | supervisor log + corrected verdict |
| 6h short_mode_used | ✅ false | LOCKED |
| 6h checkpoint_count | ✅ 6 | data_dir (6 ckpts × 7 文件 = 42) |
| 6h full node report | ✅ exists | `reports/lp_long_horizon_node_reports/20260605_043726/6h/` |
| 6h data 完整保留 | ✅ untouched | 0 修改 |
| 真实 pool universe 可用 | ✅ available | orca 75 + raydium_clmm 80 + raydium_cpmm 120 candidates |
| 12h 必须用真实池 | ✅ enforced | 不得继续 placeholder |
| 24h/48h/72h/7d forward approval | ❌ empty | approved_next_stages=[] |
| auto_advance_allowed | ❌ false | LOCKED |
| can_run_probe_now | ❌ false | LOCKED |
| tiny_canary_allowed | `"no"` | LOCKED |
| edge_proven | `"no"` | LOCKED |
| LP strategy research freeze | ACTIVE | per `docs/LPBOT_RESEARCH_STATUS_CN.md` |

## 3. V2 supervisor preflight 校验 (12h supervisor 必须)

12h supervisor `scripts/run_lp_long_horizon_readonly_stage_once.sh` 在 preflight 阶段:

1. 读取 `MANUAL_APPROVAL_RECORDED.json`
2. 校验 `user_approval_text == "APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=12h mode=readonly no_probe=true"`
3. 校验 `user_approval_text_hash_sha256 == "040c37f3bc32bc3fe281eb4cf181fae4634e742e78c769d2211d3a5f8802198f"`
4. 校验 `approved_next_stages == []` (无 forward approval)
5. 校验 `auto_advance_allowed == false`
6. 校验 `approved_stage == "12h"`
7. 校验 `no_probe == true`

任何不匹配 → exit 11 (REFUSED).

## 4. 之前 (6h) 审批记录

6h 审批短语: `APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=6h mode=readonly no_probe=true` (sha256: `1dd950db...`, 已记录在 `MANUAL_APPROVAL_RECORDED.json` per V2 启动).

12h 复用同一审批短语结构, 但 stage=12h, 重新计算 sha256.

## 5. 不得自动进入 24h

本审批仅 12h 阶段, **不**包含 24h/48h/72h/7d 任何 forward approval. 12h 完成后:

- 12h gate PASS → `recommended_next_stage = LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1` (但**仍需新 manual approval**)
- 12h gate FAIL → `recommended_next_stage = LP_LONG_HORIZON_12H_NODE_REPORT_FIX_REPEAT` 或 `LP_LONG_HORIZON_12H_COLLECTOR_FIX_REPEAT`

`auto_advance_to_24h = false` 锁死, 12h supervisor 不会自动启动 24h.

## 6. can_run_probe_now / tiny_canary_allowed / edge_proven 保持

| 字段 | 值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` (R0 read-only) |
| `transaction_sent` | `false` (R0 read-only) |
| `send_hard_disable_still_active` | `true` |

12h 不会启动 probe / canary / live / paper.

## 7. 12h supervisor scope (本轮新设计)

| 字段 | 值 |
|---|---|
| `stage` | `12h` |
| `mode` | `readonly` |
| `duration_hours` | `12` |
| `duration_minutes` | `720` |
| `expected_min_runtime_minutes` | `660` (12h - 1h tolerance) |
| `loop_count` | `12` (12 hours × 1 ckpt/hour) |
| `sleep_seconds_per_iteration` | `3600` (1h) |
| `heartbeat_interval_minutes` | `15` |
| `checkpoint_interval_minutes` | `60` |
| `data_dir` | `data/lp_long_horizon/20260605_082120/` |
| `report_dir` | `reports/lp_long_horizon_readonly_continuous_12h_extension/20260605_082120/` |
| `node_report_dir` | `reports/lp_long_horizon_node_reports/20260605_082120/12h/` |
| `tmux_session_name` | `lp_long_horizon_12h_20260605_082120` |
| `real_pool_universe_path` | `reports/lp_long_horizon_readonly_continuous_12h_extension/20260605_082120/real_pool_universe_for_12h.json` |

## 8. 结论

12h 审批短语 + sha256 已记录. 12h supervisor preflight 校验将通过. 12h 启动就绪.

**Stage B PASS** → 进入 Stage C (真实 pool universe for 12h).
