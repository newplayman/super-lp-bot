# LP Long Horizon Readonly Continuous 12h Partial Real Universe Request V1 — One Pager

- stage: `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_PARTIAL_REAL_UNIVERSE_REQUEST_V1`
- run_id: `20260606_131323`
- branch: `feat/supabase-postgres-deployment`
- status: **RUNNING** (12h partial collector 启动成功, healthcheck 通过)
- launched_at_utc: `2026-06-06T13:24:00Z`
- expected_end_time_utc: `2026-06-07T01:24:45Z`

## 0. 一句话

启动一个 12h 只读 partial 观察, 范围限定为 Solana + BSC 真实池 (53 池, 5 protocols, 0 placeholder). 显式标记 `coverage_scope=partial_solana_bsc_real_universe, full_coverage_ready=false, do_not_treat_as_full_universe=true`. **不** 实盘, **不** probe, **不** live. **不** 自动 24h. Stage runner via nohup (tmux server 在本 env **不** 可访问). 启动后 2-3min healthcheck 通过 (pid 3871101 alive, checkpoint 1/12 ok, no wallet/tx/probe).

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `coverage_scope` | `partial_solana_bsc_real_universe` |
| `full_coverage_ready` | **false** |
| `do_not_treat_as_full_universe` | **true** |
| `approved_stage` | **12h** |
| `selected_pool_count` | **53** (49 Solana + 4 BSC V3) |
| `placeholder_pool_count` | **0** |
| `observable_chain_count` | **2** (solana + bsc) |
| `observable_protocol_count` | **5** (4 Solana + 1 BSC) |
| `twelve_hour_run_completed` | **false** (running) |
| `actual_runtime_minutes` | **0** (running) |
| `actual_runtime_valid_for_12h_gate` | **false** (待 12h 完成) |
| `expected_end_time_utc` | `2026-06-07T01:24:45Z` |
| `expected_checkpoint_count` | **12** |
| `current_checkpoint_index` | **1** |
| `current_checkpoint_status` | **ok** |
| `pool_snapshot_rows` | **53** (smoke 1/12) |
| `quote_snapshot_rows` | **318** (53 × 6) |
| `fee_velocity_rows` | **265** (53 × 5) |
| `liquidity_distribution_rows` | **53** |
| `market_regime_rows` | **7** |
| `gate_pass` | **false** (待 12h 完成) |
| `can_advance_to_24h` | **false** |
| `auto_advance_started` | **false** |
| `long_run_started` | **true** |
| `process_pid` | **3871101** |
| `launch_method` | **nohup** (tmux server not accessible in this env) |
| `can_run_probe_now` | **false** (LOCKED) |
| `tiny_canary_allowed` | `"no"` (LOCKED) |
| `wallet_or_tx_touched` | **false** (LOCKED) |
| `transaction_sent` | **false** (LOCKED) |
| `recommended_next_stage` (after 12h) | `LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1` |

## 2. Partial 12h 范围

| Chain | Pools | Protocols | Status |
|---|---|---|---|
| solana | 49 | orca_whirlpool (13), raydium_clmm (10), raydium_cpmm (10), meteora_dlmm (16) | ✅ observed |
| bsc | 4 | pancakeswap_v3 (4) | ✅ observed (4 V3 real on-chain via bsc-dataseed.binance.org) |
| base | 0 | — | ❌ missing (public RPC 全部 403) |

**Total**: 53 pools, 5 protocols, 2 chains (Solana + BSC only). placeholder=0.

## 3. 启动序列

```
13:17:00  Stage A-F (input evidence + scope freeze + universe build + approval + config + safety check)
13:24:00  Stage G launch via nohup (pid 3871101)
13:24:45  Checkpoint 1/12 ok (smoke: 53 pools, 318 quote, 265 fee, 53 liq, 7 regime)
13:25:00  Stage G healthcheck (this report) ✓
13:24:45  ~ 01:24:45  12h 期间 wallclock loop (12 × 1h per checkpoint)
01:24:45  Stage H finalize (auto by stage runner)
```

## 4. 锁定字段 (5 项全 false/no + 3 additional)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `long_run_started` | `true` (启动后) |
| `auto_advance_to_24h` | `false` |
| `do_not_treat_as_full_universe` | `true` |
| `no_paid_rpc_key_committed` | `true` |
| `no_real_secret_committed` | `true` |

## 5. 严禁 (启动后仍不触发)

- ❌ 不启动 24h / 48h / 72h / 7d
- ❌ 不启动并行 collector
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / seed / keypair / signer
- ❌ 不发送 transaction / approve / mint / swap / bridge
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 原始表
- ❌ 不接 paid RPC / paid indexer
- ❌ **不** 写真实 RPC key / private_key / mnemonic / seed
- ❌ **不**修改 12h data_dir (新增 12h partial 池是设计内, **不** 改 v2 12h data)
- ❌ **不**修改 6h data_dir (42 文件, 0 修改)
- ❌ **不**修改 v2 12h FINAL_VERDICT / v2 6h FINAL_VERDICT / corrected verdicts / 12h node report
- ❌ **不**修改 supervisor stage runner
- ❌ **不**修改 collector

## 6. 12h 时间表 (启动后)

| 阶段 | 时间 (UTC) | 状态 |
|---|---|---|
| Stage G launch (nohup) | 2026-06-06 13:24:00 | ✅ done |
| Stage G healthcheck | 2026-06-06 13:25:00 | ✅ done |
| Checkpoint 1/12 | 2026-06-06 13:24:45 | ✅ done |
| Checkpoint 2/12 | 2026-06-06 14:24:45 | pending |
| ... | ... | ... |
| Checkpoint 12/12 (完成) | 2026-06-07 01:24:45 | pending |
| 失败 fallback deadline | 2026-06-07 02:24:45 | pending |
| Stage H finalize (auto) | 2026-06-07 01:24:45 ~ 02:24:45 | pending |

## 7. 12h 完成后 Stage H finalize (auto by stage runner)

- `FINAL_VERDICT.json` (status=PASS/WARN/FAIL based on `actual_runtime_minutes >= 660` gate)
- `ONEPAGE_CN.md`
- `ARTIFACT_INDEX.md`
- 12h node report (基于 partial coverage, **不** 当 full coverage 用)
- coverage manifest (3 levels: chain/dex/pool, observed=false 标记 Base)
- fee estimation basis
- candidate review
- next node decision

`recommended_next_stage` 仅允许 4 个值:
- `LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1`
- `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT`
- `LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_PARTIAL_EXTENSION_REQUEST_V1`
- `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA`

**不得** 自动启动 24h.

## 8. 与前几 stage 的关系

| Stage | 状态 | 修了什么 |
|---|---|---|
| `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COLLECTOR_FIX_V1` | 早 stage | collector `--pool-universe` CLI |
| `LP_LONG_HORIZON_STAGE_SUPERVISOR_FINALIZE_FIX_V1` | 早 stage | supervisor finalize 4 Python heredoc 的 lowercase bool bug |
| `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1` | 早 stage | universe 33 → 72 (8 protocols, 3 chains); 23 池 not observable |
| `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1` | 早 stage | 新增 4 EVM/BSC adapter + 1 Meteora verify |
| `LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1` | 上一 stage | 新增 rpc_registry.py + RPC reachability matrix; BSC V3 4/4 real; observable 13 → 49; 4 conditions met, chain=2 < 3 (Base 不可达) |
| **`LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_PARTIAL_REAL_UNIVERSE_REQUEST_V1`** | **本 stage** | **启动 12h partial collector (Solana + BSC, 53 池); nohup 启动 (tmux 不可达); 2-3min healthcheck 通过; **不** 自动 24h** |
| 12h 完成后 (Stage H, auto) | 下一 stage | stage runner 自动 finalize; 推荐 LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1 |

## 9. 关键数据点

- **53 pools** (49 Solana + 4 BSC V3), 0 placeholder, all real on-chain
- **5 protocols**: solana/orca_whirlpool, solana/raydium_clmm, solana/raydium_cpmm, solana/meteora_dlmm, bsc/pancakeswap_v3
- **2 chains**: solana, bsc (base 不可达, 显式 missing)
- **Checkpoint 1/12 ok**: 53 pool_snapshots, 318 quote_snapshots, 265 fee_velocity, 53 liquidity, 7 regime
- **PID 3871101 alive** (nohup detached)
- **expected end**: 2026-06-07T01:24:45Z (12h 后)
- **22+ pytest tests** (Stage I 待 run)
- **0 forbidden process** (no canary/live/paper/sendTransaction/keypair)

## 10. 后续

12h partial collector 在 wallclock loop. 用户可在 12h 完成后决定:
1. `LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1` (推荐): review 12h node report
2. `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT`: 在能 reach Base RPC 的 env 再 smoke
3. `LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_PARTIAL_EXTENSION_REQUEST_V1`: 24h extension
4. `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA`: 暂停

严禁 (per LP strategy research freeze): probe / canary / live / paper / wallet / tx / auto-24h.
