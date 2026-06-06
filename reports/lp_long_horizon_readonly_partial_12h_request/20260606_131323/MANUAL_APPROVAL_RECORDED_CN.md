# Manual Approval Recorded

- stage: `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_PARTIAL_REAL_UNIVERSE_REQUEST_V1`
- section: manual_approval_recorded
- run_id: `20260606_131323`
- branch: `feat/supabase-postgres-deployment`
- approved_at_utc: `2026-06-06T13:17:00Z`

## 0. 总结

✅ **审批短语已记录**. 用户显式批准 partial 12h observation (Solana + BSC only), 不包括 Base. `auto_advance_allowed=false`, **不** 自动进入 24h.

## 1. 审批短语

```
APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=12h mode=readonly no_probe=true scope=partial_solana_bsc
```

## 2. 关键字段

| 字段 | 值 |
|---|---|
| `user_approval_text` | `APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=12h mode=readonly no_probe=true scope=partial_solana_bsc` |
| `approved_stage` | **12h** |
| `scope` | **partial_solana_bsc** |
| `coverage_scope` | **partial_solana_bsc_real_universe** |
| `mode` | **readonly** |
| `no_probe` | **true** |
| `auto_advance_allowed` | **false** |
| `approved_next_stages` | `[]` (空 — 不允许自动到下一 stage) |
| `denied_next_stages` | `["24h", "48h", "72h", "7d", "any auto_advance", "any live/canary/paper/probe/send_tx"]` |
| `selected_pool_count` | **53** (49 Solana + 4 BSC V3) |
| `expected_end_time_utc` | **`2026-06-07T01:17:00Z`** (12h 后) |
| `expected_runtime_minutes` | **720** (12h) |
| `expected_runtime_tolerance_min` | **60** (1h tolerance) |
| `long_run_started` | **false** (启动时变 true) |
| `can_run_probe_now` | **false** (LOCKED) |
| `tiny_canary_allowed` | `"no"` (LOCKED) |
| `wallet_or_tx_touched` | **false** (LOCKED) |
| `transaction_sent` | **false** (LOCKED) |

## 3. 12h 时间表

| 阶段 | 时间 (UTC) |
|---|---|
| 启动 | 2026-06-06 13:17:00 |
| 第 1 checkpoint | 2026-06-06 14:17:00 (1h 后) |
| 第 6 checkpoint (中点) | 2026-06-06 19:17:00 (6h 后) |
| 第 12 checkpoint (完成) | 2026-06-07 01:17:00 (12h 后) |
| 失败 fallback deadline | 2026-06-07 02:17:00 (12h + 1h tolerance) |

## 4. 锁定字段 (5 项全 false/no + 8 additional)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `long_run_started` | `false` (启动时变 true) |
| `auto_advance_allowed` | `false` |
| `auto_advance_to_24h_disabled` | `true` |
| `do_not_treat_as_full_universe` | `true` |
| `no_collector_started_yet` | `true` |
| `no_12h_retry_started_yet` | `true` |
| `no_paid_rpc_key_committed` | `true` |
| `no_real_secret_committed` | `true` |
| `send_hard_disable_still_active` | `true` |

## 5. 严禁 (本轮全部不触发, 启动后仍不触发)

- ❌ 不启动 24h / 48h / 72h / 7d
- ❌ 不启动并行 collector
- ❌ 不启用 cron / systemd / daemon
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / seed / keypair / signer
- ❌ 不发送 transaction / approve / mint / swap / bridge
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 原始表
- ❌ 不接 paid RPC / paid indexer
- ❌ **不** 写真实 RPC key / private_key / mnemonic / seed
- ❌ **不** 自动 advance 到 24h (auto_advance_allowed=false)
- ❌ **不** 启动 12h retry 在 Base 链 (Base RPC 不可达)
- ❌ **不**修改 12h data_dir (84 文件, 0 修改)
- ❌ **不**修改 6h data_dir (42 文件, 0 修改)
- ❌ **不**修改 v2 12h FINAL_VERDICT / v2 6h FINAL_VERDICT / corrected verdicts / 12h node report
- ❌ **不**修改 supervisor stage runner
- ❌ **不**修改 collector

## 6. 下游

进入 Stage E (12h partial run config) → F (safety check) → G (launch).
