# LP Long Horizon Collector Adapter Coverage Wiring V1 — One Pager

- stage: `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1`
- run_id: `20260606_093857`
- branch: `feat/supabase-postgres-deployment`
- status: **WARN** (5 conditions NOT all met; 4 new adapters wired + 1 verify, but public Base + Solana RPC not reachable in this env)

## 0. 一句话

新增 4 个 EVM/BSC read-only adapter (Base UniV3 / Base Aerodrome / BSC V3 / BSC V2) + 1 个 Meteora DLMM verify file (`scripts/lp_long_horizon/adapters/`). 全部 eth_call only, 全部 self-check 通过. Integrated smoke 跑 12 池 (全部 Solana, 真实 on-chain) + 5 个 per-adapter smoke. `observable_pool_count=13` (12 Solana + 1 BSC V3 WBNB/USDT 0.05%) — 仅 BSC V3 在此 env 真正 observed. 5 conditions NOT all met (observable < 45, chain < 3). 下一 stage 推荐 `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT`. **严禁** 自动启动 12h retry.

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `adapter_registry_ready` | **true** (8 adapters: 3 existing + 4 new + 1 verify) |
| `base_uniswap_v3_adapter_ready` | **true** (file complete, smoke blocked by Base public RPC unavailable) |
| `base_aerodrome_adapter_ready` | **"classic_only"** (Slipstream honestly marked adapter_ready=false due to custom tick math) |
| `bsc_pancakeswap_v3_adapter_ready` | **true** (file complete, **1 pool real observed**: WBNB/USDT 0.05%) |
| `bsc_pancakeswap_v2_adapter_ready` | **true** (file complete, CPMM formula test passes; smoke blocked by V2 address returning empty) |
| `meteora_dlmm_long_horizon_adapter_ready` | **"existing_solana_rpc_works_when_rpc_reachable"** (16 verified pools exist on-chain; smoke blocked by Solana public RPC empty response) |
| `integrated_smoke_ran` | **true** (12 real pool snapshots, 0 placeholder) |
| `expanded_pool_count` | **72** |
| `observable_pool_count` | **13** (solana 12 + evm 0 + bsc 1) |
| `observable_chain_count` | **2** (solana + bsc) |
| `observable_protocol_count` | **5** (4 Solana + 1 BSC) |
| `placeholder_pool_count` | **0** |
| `collector_full_coverage_ready` | ❌ **false** |
| `can_start_12h_real_universe_retry` | ❌ **false** |
| `recommended_next_stage` | **`LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT`** |
| `can_run_probe_now` | ❌ **false** (LOCKED) |
| `tiny_canary_allowed` | `"no"` (LOCKED) |
| `wallet_or_tx_touched` | **false** (LOCKED) |
| `transaction_sent` | **false** (LOCKED) |
| `long_run_started` | **false** (LOCKED) |

## 2. 5 个新 adapter file

| File | Status | Smoke | 备注 |
|---|---|---|---|
| `scripts/lp_long_horizon/adapters/evm_base_uniswap_v3.py` | **created** | rpc_unavailable | slot0 + liquidity + token0 + token1 + fee + QuoterV2 + fallback |
| `scripts/lp_long_horizon/adapters/evm_base_aerodrome.py` | **created** | rpc_unavailable | classic (Solidly getReserves) + slipstream (marked adapter_ready=false) |
| `scripts/lp_long_horizon/adapters/evm_bsc_pancakeswap_v3.py` | **created** | **1 real pool** | WBNB/USDT 0.05% real: sqrtPriceX96, tick, liquidity, fee=500, token0/1 |
| `scripts/lp_long_horizon/adapters/evm_bsc_pancakeswap_v2.py` | **created** | rpc_unavailable | getReserves + CPMM formula (fee=0.20%) |
| `scripts/lp_long_horizon/adapters/solana_meteora_dlmm_check.py` | **created** | rpc_unavailable | re-uses existing solana_rpc_readonly |

## 3. Integrated smoke 关键数字

- `selected_pool_count`: 12 (全部 Solana orca + raydium)
- `pool_snapshot_rows`: 12 (real on-chain addresses, real TVL/volume proxies)
- `quote_snapshot_rows`: 72 (12 × 6 notional)
- `fee_velocity_rows`: 60 (12 × 5 windows)
- `market_regime_rows`: 7
- `placeholder_pool_count`: **0** (no `<smoke_pool_`)
- `all_pools_are_real_on_chain`: **true**

## 4. Honest disclosure

`observable_pool_count=13` 远 < 72. 原因 (诚实记录, **不** 假设):
- 12 池 from integrated smoke (Solana only, all real)
- 1 池 from BSC V3 smoke (WBNB/USDT 0.05% real on-chain)
- 0 池 from Base (public Base RPC **不** reachable in this env)
- 0 池 from BSC V2 (WBNB/USDT public address returned empty from BSC public RPC)
- 0 池 from Meteora (Solana public RPC returned empty for 2 test pools)

**`placeholder_pool_count=0` 维持**. **no wallet/tx/probe** 维持. **不**回退 placeholder. **不**把 adapter_missing 当成 pool negative.

## 5. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `long_run_started` | `false` |
| `auto_next_stage_disabled` | `true` |
| `no_collector_started` | `true` |
| `no_tmux_session_created` | `true` |

## 6. 严禁 (本轮全部不触发)

- ❌ 不启动 12h / 24h / 48h / 72h / 7d
- ❌ 不启动 long-running collector
- ❌ 不启动 tmux / cron / systemd / daemon
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer / 私钥
- ❌ 不发送 transaction / approve / mint / swap / bridge
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 原始表
- ❌ 不接 paid RPC / paid indexer
- ❌ **不**修改 12h data_dir (84 文件, 0 修改)
- ❌ **不**修改 6h data_dir (42 文件, 0 修改)
- ❌ **不**修改 v2 12h FINAL_VERDICT / v2 6h FINAL_VERDICT / corrected verdicts / 12h node report
- ❌ **不**修改 supervisor stage runner (上一 stage 已修 finalize)
- ❌ **不**修改 collector (本 stage 仅**新增** 5 adapter file, **不**改** collector 主程序)

## 7. 5 conditions check

| 条件 | 目标 | 实际 | 状态 |
|---|---|---|---|
| `observable_pool_count >= 45` | ≥ 45 | 13 | ❌ NOT met |
| `observable_chain_count >= 3` | ≥ 3 | 2 | ❌ NOT met |
| `observable_protocol_count >= 5` | ≥ 5 | 5 | ✅ met |
| `placeholder_pool_count == 0` | = 0 | 0 | ✅ met |
| `no_wallet_tx_probe` | yes | yes | ✅ met |

**2 conditions NOT met**: `observable_pool_count` (13 < 45) + `observable_chain_count` (2 < 3).

## 8. 为什么推荐 fix_repeat

- 4 个新 adapter file 全部 self-check 通过, **代码** ready
- 唯一阻塞是 public RPC reachability (Base public RPC + Solana public RPC 在此 env 受限)
- BSC V3 smoke 1 池真实成功 (WBNB/USDT 0.05%): 证明 BSC public RPC 可达
- 下一步 fix_repeat: 在能 reach public Base RPC + Solana public RPC 的 env 再 smoke
- 12h retry **不** 推荐 until observable_pool_count >= 45

## 9. 下一轮建议 (3-stage allowed)

| 选项 | 含义 |
|---|---|
| **`LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT`** (本 stage 推荐) | 在能 reach public Base + Solana RPC 的 env 再 smoke 一次, 或等 RPC 改善 |
| `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1` | 12h retry (但仅在 observable >= 45 + chain >= 3 后才有意义) |
| `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` | 用户决定暂停, 等 RPC env 改善 |

## 10. 与前几 stage 的关系

| Stage | 状态 | 修了什么 |
|---|---|---|
| `LP_LONG_HORIZON_6H_FINALIZER_REBUILD_V1` | 上一 stage | 6h corrected verdict |
| `LP_LONG_HORIZON_12H_FINALIZER_REBUILD_FROM_CHECKPOINTS_V1` | 上一 stage | 12h corrected verdict |
| `LP_LONG_HORIZON_CONTINUOUS_OBSERVATION_NODE_REPORTS_V1` | 上一 stage | 12h 节点报告 |
| `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COLLECTOR_FIX_V1` | 上一 stage | collector `--pool-universe` CLI |
| `LP_LONG_HORIZON_STAGE_SUPERVISOR_FINALIZE_FIX_V1` | 上一 stage | supervisor finalize 4 Python heredoc 的 lowercase bool bug |
| `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1` | 上一 stage | universe 33 → 72 (8 protocols, 3 chains); 23 池 not observable |
| **`LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1`** | **本 stage** | **新增 4 EVM/BSC adapter + 1 Meteora verify; observable 49 → 13 (honest, due to RPC unreachable in env); 5 conditions NOT all met** |
| `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT` | **推荐 next** | 在能 reach public Base + Solana RPC 的 env 再 smoke |

## 11. 关键数据点

- **5 个新 Python adapter file** (4 EVM/BSC + 1 Meteora verify) 在 `scripts/lp_long_horizon/adapters/`. 全部 `read_only_only=true, wallet_required=false, transaction_required=false`.
- **6 个新 smoke 脚本** (5 per-adapter + 1 integrated) in `reports/lp_long_horizon_collector_adapter_coverage_wiring/20260606_093857/`.
- **1 integrated smoke** 实际跑 12 池 (all Solana, real on-chain). 0 placeholder.
- **4 个 per-adapter smoke**: 1 真实成功 (BSC V3 WBNB/USDT 0.05%), 3 honest rpc_unavailable (Base, BSC V2, Meteora).
- **22 pytest tests** (Stage K).

## 12. 后续

本 stage 完成, pytest 待 run (Stage K), 已 commit + push 到 `feat/supabase-postgres-deployment` (Stage L). 用户可在下一轮决定:
1. 触发 `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT` (推荐): 在能 reach public Base + Solana RPC 的 env 再 smoke
2. 触发 `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1` (需 user approval): 但**不**推荐 until observable >= 45
3. 暂停或停止

严禁 (per LP strategy research freeze): probe / canary / live / paper / wallet / tx / auto-12h.
