# Orca Whirlpool Read-Only Connector V1 — One-Page Summary

- stage: `LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1`
- run_id: `20260604_025414`
- branch: `feat/supabase-postgres-deployment`
- head_before: `22d2941`

## 关键结果

```text
status                              = WARN
candidate_raw_count                 = 15002   (14983 Orca official + 19 DexScreener)
selected_for_chain_verify_count     = 75
verified_pool_count                 = 75      (100% verify; data_len 653 each)
sdk_decode_success_count            = 75      (100% via @orca-so/whirlpools 8.0.0)
tick_array_ready_pool_count         = 4       (LAZY init by Orca 8.0 program)
quote_ready_pool_count              = 10      (limited by public RPC 429)
survival_ev_model_ran               = True
row_count                           = 1680
positive_zero_il_lvr_count          = 29
positive_optimistic_count           = 0
positive_realistic_count            = 0
positive_conservative_count         = 0
near_break_even_count               = 928
high_fee_quote_ready_count          = 20
best_pool                           = C9U2Ksk6 (SOL/Fartcoin, 16bps)
best_pair                           = SOL/Fartcoin
best_notional                       = 2000
best_hold_window                    = 7d
best_scenario                       = zero_il_lvr
best_net_ev_proxy_usd               = +0.106
best_net_ev_proxy_pct               = +0.0053%
can_run_probe_now                   = False
solana_wallet_or_keypair_touched    = False
transaction_sent                    = False
edge_proven                         = no
tiny_canary_allowed                 = no
recommended_next_stage              = LP_RAYDIUM_CLMM_READONLY_CONNECTOR_V1
v2_line_count                       = 992 (unchanged)
```

## 关键 finding (V1 真实)

1. **Orca 8.0 SDK 走通**: `fetchConcentratedLiquidityPool` + `swapInstructions` (quote-only) 完整 read-only 路径可用, public RPC 上 100% verify success。
2. **Tick array 是 LAZY init**: Orca 8.0 program 用 dynamic tick array, 只有跨过 tick range 的 swap 才会初始化。225 个 PDA 派生, 仅 4 个 on-chain 存在 (1.8%)。池-level `liquidity` (Stage G) 是唯一直接 active 信号 (72/75 池 > 0)。
3. **best cell +$0.106 in zero_il_lvr only**: 任何 IL/LVR 假设 → 全负。Best 池 C9U2Ksk6 (SOL/Fartcoin, 16bps fee) margin 比 Meteora V8 (0.544) 小 5×。
4. **V3 CL AMM 累计 reject 2/3**: Meteora DLMM (V8) + Orca Whirlpools (V1) 都验证 negative 在零售 10-20U 2000 USD 范围。Raydium CLMM 是 3rd 独立测试。

## V1 / V8 对比

| 维度 | Meteora V8 | Orca V1 |
|---|---|---|
| 候选源 | GeckoTerminal + DexScreener | **Orca 官方 API (14983)** + DexScreener |
| Verify | 56/60 (93%) | **75/75 (100%)** |
| Decode | 56/56 | **75/75** |
| Quote-ready | 27/56 (48%) | 10/75 (受 429, 实际 ~30) |
| Best cell | +$0.544 | +$0.106 |
| positive_realistic | 0 | 0 |
| Fee 范围 | 0.01%–1% | 0.01%–2% |
| Tick array 模型 | always init | **LAZY init (Orca 8.0)** |

## 决定

recommended_next_stage = `LP_RAYDIUM_CLMM_READONLY_CONNECTOR_V1`

理由:
- Meteora DLMM + Orca Whirlpools 两个 V3 CL AMM 零售 10-20U 2000 USD 已被验证 negative
- Orca V1 SDK read-only path 走通, 池子 fee data 真实 (1-200bps)
- best 0.106 USD margin (zero_il_lvr only) 远低于 practical LP 操作成本
- Raydium CLMM 是 3rd V3 CL AMM, 应作独立验证
- 3rd 独立 AMM negative 后可稳定结论"零售 LP 在 Solana 不可行", 而非"某个协议失败"

## 不做什么 (硬边界)

- ❌ 不 instantiate Keypair
- ❌ 不构造 transaction
- ❌ 不 swap / open_position / close_position / increaseLiquidity / decreaseLiquidity
- ❌ 不 collectFees / collectReward
- ❌ 不 paid RPC (public RPC 够用)
- ❌ 不接 wallet
- ❌ 不 modify EVM executor v2
- ❌ 不 set can_run_probe_now = true
- ❌ 不 set tiny_canary_allowed = yes
- ❌ 不进 10/20U probe preflight (positive_realistic=0)
