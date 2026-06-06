# ARTIFACT INDEX — Collector Adapter Coverage Wiring V1

- stage: `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1`
- run_id: `20260606_093857`
- branch: `feat/supabase-postgres-deployment`
- status: **WARN** (5 conditions NOT all met; 4 new adapters wired + 1 verify, but public Base + Solana RPC not reachable in this env)
- generated_at_utc: `2026-06-06T09:51:00Z`

## 1. Output files (in `reports/lp_long_horizon_collector_adapter_coverage_wiring/20260606_093857/`)

| # | 文件 | 描述 |
|---|---|---|
| 1 | `INPUT_EVIDENCE_AUDIT_CN.md` | 输入证据审计 (CN) |
| 2 | `input_evidence_audit.json` | 输入证据审计 (JSON) |
| 3 | `ADAPTER_REGISTRY_DESIGN_CN.md` | Adapter registry 设计 (CN) — 8 adapters |
| 4 | `adapter_registry_design.json` | Adapter registry 设计 (JSON) |
| 5 | `BASE_UNISWAP_V3_ADAPTER_WIRING_CN.md` | Base UniV3 wiring (CN) |
| 6 | `base_uniswap_v3_adapter_wiring.json` | Base UniV3 wiring (JSON) |
| 7 | `BASE_AERODROME_ADAPTER_WIRING_CN.md` | Base Aerodrome wiring (CN) |
| 8 | `base_aerodrome_adapter_wiring.json` | Base Aerodrome wiring (JSON) |
| 9 | `BSC_PANCAKESWAP_V3_ADAPTER_WIRING_CN.md` | BSC V3 wiring (CN) |
| 10 | `bsc_pancakeswap_v3_adapter_wiring.json` | BSC V3 wiring (JSON) — 1 real pool observed |
| 11 | `BSC_PANCAKESWAP_V2_ADAPTER_WIRING_CN.md` | BSC V2 wiring (CN) |
| 12 | `bsc_pancakeswap_v2_adapter_wiring.json` | BSC V2 wiring (JSON) |
| 13 | `METEORA_DLMM_LONG_HORIZON_ADAPTER_CHECK_CN.md` | Meteora DLMM check (CN) |
| 14 | `meteora_dlmm_long_horizon_adapter_check.json` | Meteora DLMM check (JSON) |
| 15 | `INTEGRATED_ADAPTER_WIRING_SMOKE_CN.md` | Integrated smoke (CN) |
| 16 | `integrated_adapter_wiring_smoke.json` | Integrated smoke (JSON) |
| 17 | `COVERAGE_READINESS_DECISION_CN.md` | Coverage readiness decision (CN) |
| 18 | `coverage_readiness_decision.json` | Coverage readiness decision (JSON) |
| 19 | `FINAL_VERDICT.json` | Final verdict (含 spec-required 完整字段) |
| 20 | `ONEPAGE_CN.md` | One-pager 总结 (CN) |
| 21 | `ARTIFACT_INDEX.md` | 本文件 |
| 22 | `smoke_*.py` (5 files) | Smoke scripts (read-only, generates the wiring JSONs) |
| 23 | `build_integrated_smoke.py` | Build integrated smoke report |
| 24 | `build_coverage_readiness_decision.py` | Build coverage readiness decision |

## 2. New adapter files (in `scripts/lp_long_horizon/adapters/`)

| File | Status | Public RPC reachable in this env | 备注 |
|---|---|---|---|
| `evm_base_uniswap_v3.py` | new | ❌ (Base public RPC) | slot0 + liquidity + token0 + token1 + fee + QuoterV2 + fallback |
| `evm_base_aerodrome.py` | new | ❌ (Base public RPC) | classic (Solidly getReserves) + slipstream (marked adapter_ready=false) |
| `evm_bsc_pancakeswap_v3.py` | new | ✅ (BSC public RPC) | 1 real WBNB/USDT 0.05% observed |
| `evm_bsc_pancakeswap_v2.py` | new | ✅ (BSC public RPC, but WBNB/USDT address returned empty) | getReserves + CPMM formula |
| `solana_meteora_dlmm_check.py` | new (verify) | ❌ (Solana public RPC empty response) | re-uses existing solana_rpc_readonly |

## 3. Integrated smoke (12 real pools)

- `selected_pool_count`: 12 (all Solana, all real on-chain)
- `pool_snapshot_rows`: 12
- `quote_snapshot_rows`: 72 (12 × 6 notional)
- `fee_velocity_rows`: 60 (12 × 5 windows)
- `market_regime_rows`: 7
- `placeholder_pool_count`: **0**
- `all_pools_are_real_on_chain`: **true**

## 4. 锁定字段 (5 项全 false/no)

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

## 5. 严禁 (本轮全部不触发)

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

## 6. 输入证据 (本轮**只**读)

- `reports/lp_long_horizon_real_pool_universe_coverage_expand/20260606_091120/FINAL_VERDICT.json` (prior stage)
- `reports/lp_long_horizon_real_pool_universe_coverage_expand/20260606_091120/expanded_real_pool_universe_for_12h_retry.json` (current 72-pool universe)
- `reports/lp_long_horizon_real_pool_universe_collector_fix/20260605_083000/FINAL_VERDICT.json` (prior-2 stage)
- `scripts/lp_long_horizon_readonly_collector_v1.py` (collector, 801 lines)
- `scripts/run_lp_long_horizon_readonly_stage_once.sh` (stage runner, 518 lines)
- `scripts/lp_long_horizon/adapters/{solana_rpc_readonly,public_api_coingecko,local_artifact_replay}.py` (3 existing)
- `reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/meteora_pool_chain_verification.json` (16 verified Meteora pools)
- `reports/lp_bsc_pancakeswap_v3_precise_quote/20260602_235959/bsc_quote_target_candidates.csv` (8 BSC V3 pool addresses)

## 7. 3-stage allowed next stages

- **`LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT`** (本 stage 推荐) — 在能 reach public Base + Solana RPC 的 env 再 smoke
- `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1` — 12h retry (需 user approval + observable >= 45)
- `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` — 用户决定暂停

## 8. Recommended next stage

**`LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT`**

理由: 5 conditions NOT all met. 4 个新 adapter file + 1 verify file 全部 self-check 通过, 代码 ready. 唯一阻塞是 public RPC reachability (Base public RPC + Solana public RPC 在此 env 受限, BSC V3 1 池真实成功证明 BSC public RPC 可达). 下一 stage 在能 reach public Base RPC + Solana public RPC 的 env 再 smoke 一次, 让 observable_pool_count 升到 >= 45. 12h retry **不**推荐 until all 5 conditions met.

## 9. 5 conditions

| 条件 | 实际 | 状态 |
|---|---|---|
| `observable_pool_count >= 45` | 13 | ❌ NOT met |
| `observable_chain_count >= 3` | 2 (solana + bsc) | ❌ NOT met |
| `observable_protocol_count >= 5` | 5 (4 Solana + 1 BSC) | ✅ met |
| `placeholder_pool_count == 0` | 0 | ✅ met |
| `no_wallet_tx_probe` | yes | ✅ met |

**2 conditions NOT met**: `observable_pool_count` (13 < 45) + `observable_chain_count` (2 < 3).
