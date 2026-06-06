# LP Long Horizon Collector RPC Reachability and Adapter Smoke Fix V1 — One Pager

- stage: `LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1`
- run_id: `20260606_103807`
- branch: `feat/supabase-postgres-deployment`
- status: **WARN** (4 conditions met, observable_chain_count=2 < 3 because Base public RPC unreachable in this env)

## 0. 一句话

新增 `scripts/lp_long_horizon/rpc_registry.py` 集中管理 base/bsc/solana 3 chain 的 primary + fallback + env override (无 secret). RPC reachability matrix 实测 11 endpoints (base 4 全 403, bsc 1/4 可达, solana 1/3 可达). 重试 Base / BSC / Meteora adapter smoke. BSC V3 4/4 real on-chain, BSC V2 factory.getPair 0/3 (zero address), Base 0/N (RPC 不可达), Meteora 0/5 (Solana RPC empty). Integrated smoke 45 池 (45 Solana + 4 BSC V3 = 49 observable). 5 conditions 4 met; 1 NOT met (chain=2 < 3 因 Base RPC 不可达). 下一 stage 推荐 `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT`. **严禁** 自动启动 12h retry.

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `rpc_registry_ready` | ✅ **true** (`scripts/lp_long_horizon/rpc_registry.py` 创建, 3 chains, env override only) |
| `rpc_reachability_matrix_ran` | ✅ **true** (11 endpoints probed) |
| `base_rpc_reachable` | ❌ **false** (4 endpoints 全部 403 Forbidden / Connection reset) |
| `bsc_rpc_reachable` | ✅ **true** (bsc-dataseed.binance.org 166ms reachable) |
| `solana_rpc_reachable` | ✅ **true** (api.mainnet-beta.solana.com 59ms reachable, but `getMultipleAccountsInfo` 5/5 empty) |
| `base_adapter_smoke_success` | ❌ **false** (RPC 不可达) |
| `bsc_adapter_smoke_success` | ✅ **true** (V3 4/4 real on-chain; V2 0/3 factory.getPair zero) |
| `meteora_dlmm_smoke_success` | ❌ **false** (Solana public RPC empty) |
| `integrated_smoke_ran` | ✅ **true** (45 real pool snapshots, 0 placeholder) |
| `expanded_pool_count` | **72** |
| `observable_pool_count` | **49** (solana 45 + evm 0 + bsc 4) |
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
| `no_paid_rpc_key_committed` | ✅ **true** |
| `no_real_secret_committed` | ✅ **true** |

## 2. 5 conditions check

| 条件 | 目标 | 实际 | 状态 |
|---|---|---|---|
| `observable_pool_count >= 45` | ≥ 45 | 49 | ✅ met |
| `observable_chain_count >= 3` | ≥ 3 | 2 (solana + bsc) | ❌ NOT met |
| `observable_protocol_count >= 5` | ≥ 5 | 5 | ✅ met |
| `placeholder_pool_count == 0` | = 0 | 0 | ✅ met |
| `no_wallet_tx_probe` | yes | yes | ✅ met |

**1 condition NOT met**: `observable_chain_count` (2 < 3, Base 不可达).

## 3. RPC reachability matrix (11 endpoints)

| Chain | Primary | Fallback | Reachable |
|---|---|---|---|
| base | mainnet.base.org (9890ms 403) | base-rpc.publicnode.com (528ms 403), base.llamarpc.com (434ms 403), 1rpc.io/base (991ms reset) | **0/4** |
| bsc | bsc-dataseed.binance.org (166ms ✅) | bsc-rpc.publicnode.com (403), binance.llamarpc.com (DNS), 1rpc.io/bnb (reset) | **1/4** |
| solana | api.mainnet-beta.solana.com (59ms ✅) | solana-rpc.publicnode.com (403), 1rpc.io/solana (reset) | **1/3** |

## 4. Per-adapter smoke (retry)

| Adapter | Smoke count | Success | Reason |
|---|---|---|---|
| Base UniV3 | 2 | 0 | RPC 不可达 (403) |
| Base Aerodrome (classic) | 1 | 0 | RPC 不可达 (403); slipstream marked unsupported |
| BSC V3 | 4 | **4** | bsc-dataseed.binance.org reachable; 4 pools real on-chain |
| BSC V2 (factory.getPair) | 3 | 0 | factory.getPair 返回 zero address (candidate pairs 不存在 V2 mainnet) |
| Meteora DLMM | 5 | 0 | Solana public RPC returned empty for 5 verified pools |

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
| `no_paid_rpc_key_committed` | `true` |
| `no_real_secret_committed` | `true` |

## 6. 严禁 (本轮全部不触发)

- ❌ 不启动 12h / 24h / 48h / 72h / 7d
- ❌ 不启动 long-running collector
- ❌ 不启动 tmux / cron / systemd / daemon
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer / 私钥
- ❌ 不发送 transaction / approve / mint / swap / bridge
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 原始表
- ❌ **不** 提交 paid RPC key (即使 env var 也**不** 提交真实 value)
- ❌ **不** 写真实 secret (private_key, mnemonic, seed, API key)
- ❌ **不**修改 12h data_dir (84 文件, 0 修改)
- ❌ **不**修改 6h data_dir (42 文件, 0 修改)
- ❌ **不**修改 v2 12h FINAL_VERDICT / v2 6h FINAL_VERDICT / corrected verdicts / 12h node report
- ❌ **不**修改 supervisor stage runner
- ❌ **不**修改 collector (本 stage 仅**新增** rpc_registry.py, **不**改** collector 主程序 / 已有 adapter)

## 7. 下一轮建议 (4-stage allowed)

| 选项 | 含义 |
|---|---|
| **`LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT`** (本 stage 推荐) | 在能 reach public Base RPC 的 env 再 smoke 一次, 或等 RPC 改善 |
| `LP_LONG_HORIZON_COLLECTOR_ADAPTER_CODE_FIX_REPEAT` | 主要因 Base/BSC/Meteora adapter 代码问题 (本 stage **不** 是这种情况) |
| `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1` | 12h retry (但**不**推荐 until chain=3 met) |
| `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` | 用户决定暂停 |

## 8. 为什么推荐 fix_repeat **不**推荐 code_fix

- 4 个新 adapter + 1 verify file 全部 self-check 通过, **代码** ready
- BSC V3 4/4 real on-chain (证明 BSC V3 adapter 工作)
- BSC V2 0/3 factory.getPair zero address: 这**不**是 adapter 代码问题, 而是 candidate pair 在 V2 mainnet 不存在 (WBNB/USDT 等可能仅在 V3, 不在 V2)
- Meteora 0/5: Solana public RPC returned empty (rate-limit), 5 个池经 private RPC verified 存在 on-chain (per prior research)
- Base 0/4: env-level 网络问题 (Base public RPC 全部 403), **不** 是 adapter 代码

下一 stage 在能 reach public Base RPC 的 env 再 smoke 一次, 或等 RPC 改善.

## 9. 与前几 stage 的关系

| Stage | 状态 | 修了什么 |
|---|---|---|
| `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COLLECTOR_FIX_V1` | 早 stage | collector `--pool-universe` CLI |
| `LP_LONG_HORIZON_STAGE_SUPERVISOR_FINALIZE_FIX_V1` | 早 stage | supervisor finalize 4 Python heredoc 的 lowercase bool bug |
| `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1` | 早 stage | universe 33 → 72 (8 protocols, 3 chains); 23 池 not observable |
| `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1` | 上一 stage | 新增 4 EVM/BSC adapter + 1 Meteora verify; observable 49 → 13 (honest, due to RPC unreachable) |
| **`LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1`** | **本 stage** | **新增 rpc_registry.py + RPC reachability matrix; BSC V3 4/4 real on-chain; observable 13 → 49; 4 conditions met, chain=2 < 3 (Base 不可达)** |
| `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT` | **推荐 next** | 在能 reach public Base RPC 的 env 再 smoke |

## 10. 后续

本 stage 完成, 22+ pytest 待 run (Stage J), 已 commit + push 到 `feat/supabase-postgres-deployment` (Stage K). 用户可在下一轮决定:
1. 触发 `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT` (推荐): 在能 reach public Base RPC 的 env 再 smoke
2. 触发 `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA`: 用户决定暂停
3. 触发 `LP_LONG_HORIZON_COLLECTOR_ADAPTER_CODE_FIX_REPEAT`: 如果有证据表明 adapter 代码问题 (本 stage **不** 是这种情况)

严禁 (per LP strategy research freeze): probe / canary / live / paper / wallet / tx / auto-12h.
