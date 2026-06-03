# Input Evidence Audit — LP_MULTICHAIN_DEX_LP_DISCOVERY_AND_SURVIVAL_EV_V1

- stage: `LP_MULTICHAIN_DEX_LP_DISCOVERY_AND_SURVIVAL_EV_V1`
- run_id: `20260603_051605`
- branch: `feat/supabase-postgres-deployment`
- head before: `9c3af43` (research: finalize base 10u probe monitor go nogo 20260603_040018)

## 1. 上游 inputs 一览

| 路径 | 关键字段 | 状态 |
|---|---|---|
| `reports/lp_base_10u_probe_monitor_finalize/20260603_040018/FINAL_VERDICT.json` | `go_nogo=NO_GO`, `latest_tick_drift=-722`, `recommended_next_stage=LP_BASE_10U_PROBE_MARKET_UNSAFE_WAIT_V1` | OK |
| `reports/lp_base_10u_probe_monitor_finalize/20260603_040018/BASE_10U_PROBE_GO_NOGO_REVIEW_CN.md` | 3 GO fail, 3 NO-GO trigger, monotonic worsening | OK |
| `reports/lp_base_10u_probe_monitor_finalize/20260603_040018/base_10u_probe_go_nogo_review.json` | `go_fail_count=3`, `no_go_trigger_count=3`, `drift_trajectory=monotonically_worsening_after_iter_18` | OK |
| `reports/lp_evm_wallet_crosschain_dry_run_router/20260602_105654/FINAL_VERDICT.json` | `wallet_address_bound=true`, `wallet_loaded=false`, `base_total_usd_proxy=26.84`, `bsc_total_usd_proxy=0.00`, `likely_funded_chain=base`, `base_candidate_count=5` | OK |
| `reports/lp_bsc_fee_velocity_recovery_probe_preflight/20260602_060633/FINAL_VERDICT.json` | `bsc_included=true`, `fee_ready_pool_count=7`, `best_pool=0x172fcd41... (USDT/WBNB 100)`, `best_net_ev_proxy_usd=-0.015560` (slightly negative) | OK |
| `reports/lp_universe_scope_audit/20260601_154136/FINAL_VERDICT.json` | `unique_pool_count=94`, `chain_count=2`, `protocol_count=12`, `pool_level_positive_proxy_count=0`, `universe_likely_too_narrow=true`, `recommended_next_stage=LP_EVM_UNIVERSE_EXPANSION_DESIGN_V1` | OK |
| `reports/lp_evm_standard_v3_discovery/20260602_000000/FINAL_VERDICT.json` | `chain_count_rpc_ready=2`, `protocol_count_attempted=2`, `discovered_pool_count=8`, `metadata_valid_pool_count=8` | OK |
| `docs/LPBOT_RESEARCH_STATUS_CN.md` | `current_full_strategy=FAIL`, `tiny_canary_allowed=no`, `edge_proven=no`, `next recommended action=STOP_LP_RESEARCH_NOW`; 但本任务是 read-only discovery, **not** live execution | OK |
| `docs/LPBOT_RESEARCH_ARTIFACT_INDEX_CN.md` | 索引 | OK |

## 2. 关键事实（自上游）

```text
Base 10U probe              = NO_GO  (47/47 unsafe; drift -722; monotonic worsening)
BSC fee velocity            = working; best pool USDT/WBNB 0.01% has near-zero EV ($-0.0156)
Wallet funding              = Base only ($26.84 = ETH 0.0905 + WETH 0.00247 + USDC 21.77)
                              BSC $0.00
Current universe            = 2 chains (Base + BSC) × 12 protocols × 94 pools
                              positive_realistic_count = 0 across current universe
Uniswap V3 single-chain discovery  = 8 pools found, all metadata/quote/tick ready
Likely funded chain         = base
Wallet holds tokens         = ETH, WETH, USDC on Base
Wallet allowance on NPM     = ApproveExact-style partial allowance (WETH 0.00247, USDC 5 USDC)
freeze status               = LP strategy research FROZEN; current_full_strategy=FAIL
                              but read-only research pipelines (this task) ARE allowed
```

## 3. 关键矛盾 / 偏移

1. **钱包仅在 Base** — 但 spec 要求**多链**。任何非 Base 候选都需要用户先准备资金；本阶段只能识别，**不**自动 bridge / swap。
2. **当前 universe 仅 2 chain** — spec 要求**6+ EVM chains + Solana**。本阶段需要新建多链 RPC / factory / quote 路径。
3. **当前 positive_realistic_count = 0** — 这是本轮要解决的核心矛盾；不是因为 0 个池子，而是因为 IL / LVR / cost 太高，10U 不经济。需要扩到 100/500/1000/2000U 才有正 EV。
4. **fees 没准备好** (`actual_fee_ready = false` across all stages) — 任何 EV 推算都基于 proxy；spec 明确说"按 proxy 推算"。
5. **BSC best_net_ev_proxy_usd = -0.0156** 是 BSC 唯一有 dry-run-ready 池子的 proxy，已经**负 EV**。说明 fixed-horizon + simple short-hold 路线在 BSC 10/20U 也不成立。

## 4. 本轮目标（来自 operator prompt）

1. **不**局限 Base / BSC / 当前钱包资金链；扩展到 6+ EVM chains + Solana 设计。
2. **不**仅看 single-pool 状态；要看 LP **survival horizon** + **EV** 在不同 notional / hold window 下的覆盖。
3. **不**仅看 10/20U；要外推 100/500/1000/2000U。
4. **不**仅 V3；要覆盖：
   - P0: Uniswap V3 + PancakeSwap V3
   - P1: Aerodrome / Velodrome / Curve / Balancer / PCS V2
   - P2: Solana Meteora / Orca / Raydium
5. **不**执行任何链上交易；**不**自动 bridge / swap / mint；**不**释放 hard-disable。

## 5. 决定

继续 Stage C — 多链 DEX universe 规划。

## 6. 安全不变式（来自上游）

```text
can_run_probe_now                = false
execution_allowed_now            = false
tiny_canary_allowed              = "no"
edge_proven                      = "no"
actual_fee_ready                 = false
token_id_available               = false
wallet_or_tx_touched             = false
manual_approval_required         = true
send_hard_disable_still_active   = true
```

本阶段**不**改任何上述值。
