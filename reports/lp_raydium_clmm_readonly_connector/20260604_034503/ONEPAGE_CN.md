# Raydium CLMM Read-Only Connector V1 — One-Page Summary

- stage: `LP_RAYDIUM_CLMM_READONLY_CONNECTOR_V1`
- run_id: `20260604_034503`
- branch: `feat/supabase-postgres-deployment`
- head_before: `9f0495a`

## 关键结果

```text
status                              = WARN
candidate_raw_count                 = 107
selected_for_chain_verify_count     = 80
verified_pool_count                 = 65      (100% verify; data_len 1544)
sdk_decode_success_count            = 65      (via @raydium-io/raydium-sdk 1.3.1-beta.58)
tick_array_ready_pool_count         = 2       (Raydium tick arrays lazy/active-tick only)
quote_ready_pool_count              = 50      (liquidity ratio heuristic; 53/65 have liquidity > 0)
survival_ev_model_ran               = True
row_count                           = 8400    (50 × 6 × 7 × 4)
positive_zero_il_lvr_count          = 480
positive_optimistic_count           = 0
positive_realistic_count            = 0
positive_conservative_count         = 0
near_break_even_count               = 1680
high_fee_quote_ready_count          = 50
best_pool                           = 3nMFwZXwY1s1M5s8vYAHqd4wGs4iSxXE4LRoUMMYqEgF (SOL/USDT)
best_pair                           = SOL/USDT
best_notional                       = 2000
best_hold_window                    = 7d
best_scenario                       = zero_il_lvr
best_net_ev_proxy_usd               = +0.167
best_net_ev_proxy_pct               = +0.0084%
can_run_probe_now                   = False
solana_wallet_or_keypair_touched    = False
transaction_sent                    = False
edge_proven                         = no
tiny_canary_allowed                 = no
recommended_next_stage              = LP_RAYDIUM_CPMM_READONLY_CONNECTOR_V1
v2_line_count                       = 992 (unchanged)
```

## 关键 finding (V1 真实)

1. **Raydium CLMM SDK 走通**: `PoolInfoLayout.decode` 在 public RPC 上 100% 成功, 65/65 池全部 read 完整 state (mintA/B, decimals, tickSpacing, liquidity, sqrtPriceX64, tickCurrent)。
2. **Tick array 极低 init 率**: 2/195 (1.0%) 池有 initialized tick array. Raydium tick array 只在 active tick 跨过 swap 时按需 init. Pool-level `liquidity` 是唯一可靠的 active 信号。
3. **best cell +$0.167 in zero_il_lvr only**: 任何 IL/LVR 假设 → 全负。Best 池 SOL/USDT (默认 25bps fee assumed) 2000/7d。
4. **3/3 V3 CL AMM 累计 reject 验证逻辑完成**:
   - Meteora DLMM V8: +$0.544 (zero_il_lvr), 0 realistic
   - Orca Whirlpools V1: +$0.106 (zero_il_lvr), 0 realistic
   - **Raydium CLMM V1: +$0.167 (zero_il_lvr), 0 realistic**
5. **Per user instruction**: 不再继续 V3 CL 无限扩展, 切到 Raydium CPMM / stable pool / non-CL LP。

## V3 CL AMM 累计对比

| 维度 | Meteora V8 | Orca V1 | Raydium V1 |
|---|---|---|---|
| 候选源 | GT + DS | Orca official (14983) + DS | GT raydium-clmm + DS |
| Verify | 56/60 (93%) | 75/75 (100%) | 65/80 (81%) |
| Decode | 56/56 | 75/75 | 65/65 |
| Tick array init rate | (always init) | 1.8% (LAZY) | 1.0% (LAZY) |
| Quote-ready | 27/56 (48%) | 10/75 | 50/65 (heuristic) |
| Best cell | +$0.544 | +$0.106 | +$0.167 |
| positive_realistic | 0 | 0 | 0 |
| Best fee 假设 | 100bps (memecoin) | 16bps (SOL/Fartcoin) | 25bps (default) |

**3/3 都在 zero_il_lvr 假设下才有 positive → V3 CL 协议结构的系统性问题, 不是某池的特殊情况**。

## 决定

recommended_next_stage = `LP_RAYDIUM_CPMM_READONLY_CONNECTOR_V1`

理由:
- 3/3 V3 CL AMM 累计 reject, 强烈支持切到 non-CL AMM
- Raydium CPMM (constant product) 是不同 AMM 模型, 验证 AMM class 影响
- public RPC 走通 50 quote 池 (3/3 V3 CL 中 quote-ready 最多)
- per user instruction: 不再继续 V3 CL 无限扩展

## 不做什么 (硬边界)

- ❌ 不 instantiate Keypair
- ❌ 不构造 transaction
- ❌ 不 swap / openPosition / closePosition / increaseLiquidity / decreaseLiquidity
- ❌ 不 collectFees / collectReward
- ❌ 不 paid RPC (public RPC 够用)
- ❌ 不接 wallet
- ❌ 不 modify EVM executor v2
- ❌ 不 set can_run_probe_now = true
- ❌ 不 set tiny_canary_allowed = yes
- ❌ 不进 10/20U probe preflight (positive_realistic=0)
