# V2 6h Approval Recorded (手动审批记录)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCK_FIX_REPEAT_V2`
- run_id: `20260605_043726`
- approved_by: user (前一轮 V1 `20260604_134918` 已 fail, 现 V2 启动)
- timestamp_utc: `2026-06-05T04:48:30Z`

## 0. 审批短语

```
APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=6h mode=readonly no_probe=true
```

- sha256: `1dd950db67e3bad450d4d319c3c5e8ec3a57eb1cdb6d75027cdab307f4681b3e`
- 长度: 67 字符
- 校验: 完全匹配

## 1. 审批字段

| 字段 | 值 |
|---|---|
| `approved_stage` | `6h` |
| `mode` | `readonly` |
| `no_probe` | `true` |
| `approval_recorded` | `true` |
| `approved_next_stages` | `[]` (empty, no forward approval) |
| `auto_advance_allowed` | `false` |
| `user_approval_text` | `APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=6h mode=readonly no_probe=true` |
| `user_approval_text_hash_sha256` | `1dd950db67e3bad450d4d319c3c5e8ec3a57eb1cdb6d75027cdab307f4681b3e` |

## 2. V2 supervisor preflight 校验

V2 supervisor `scripts/run_lp_long_horizon_readonly_6h_once.sh` 在 preflight 阶段:
1. 读取 `MANUAL_APPROVAL_RECORDED.json` (在 `reports/lp_long_horizon_readonly_collector_6h_fix/20260605_043726/` 或 `reports/lp_long_horizon_readonly_collector_6h_run/20260605_043726/`)
2. 校验 `user_approval_text` == `APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=6h mode=readonly no_probe=true`
3. 校验 `approved_next_stages == []` (no forward approval to 12h/24h/48h/72h/7d)
4. 校验 `auto_advance_allowed == false`

任何不匹配 → exit 11 (REFUSED).

## 3. 之前 (V1) 审批记录

V1 (`20260604_134918`) 已记录相同审批短语 (sha256 一致 `1dd950db...`), 详见 `reports/lp_long_horizon_readonly_collector_6h_fix/20260604_134918/MANUAL_APPROVAL_RECORDED.json`.

V2 复用同一审批短语, 因为:
- V1 失败原因已分析 (supervisor 双 bug, 不是审批问题)
- V1 修复 = 修 supervisor + 重跑, 不需要新审批
- 审批语义保持一致: 6h, readonly, no_probe

## 4. 不得自动进入 12h

本审批仅 6h 阶段, **不**包含 12h/24h/48h/72h/7d 任何 forward approval. 6h 完成后:
- 6h gate PASS → `recommended_next_stage = LP_LONG_HORIZON_READONLY_COLLECTOR_12H_RUN_APPROVAL_V1` (但**仍需新 manual approval**)
- 6h gate FAIL → `recommended_next_stage = LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCK_FIX_REPEAT` (FIX_REPEAT)

`auto_advance_to_12h = false` 锁死, V2 supervisor 不会自动启动 12h.

## 5. can_run_probe_now / tiny_canary_allowed 保持

| 字段 | 值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `send_hard_disable_still_active` | `true` |

V2 不会启动 probe / canary / live / paper.

## 6. 结论

V2 审批短语 + sha256 已记录, V2 supervisor preflight 将校验通过. V2 启动就绪.
