# Raydium CPMM Read-Only Connector V1 — One-Page Summary

- stage: `LP_RAYDIUM_CPMM_READONLY_CONNECTOR_V1`
- run_id: `20260604_040952`
- branch: `feat/supabase-postgres-deployment`
- head_before: `b4327d4`

## 关键结果

```text
status                              = WARN
program_verified                    = True (Raydium AMM v4, 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8)
candidate_raw_count                 = 127
selected_for_chain_verify_count     = 120
verified_pool_count                 = 81      (100% on selected; 39 owner_mismatch filtered; data_len 752)
sdk_decode_success_count            = 81      (via @raydium-io/raydium-sdk-v2 0.2.50-alpha)
quote_ready_pool_count              = 73      (constant product formula)
survival_ev_model_ran               = True
row_count                           = 12264   (73 × 6 × 7 × 4)
positive_zero_il_lvr_count          = 1344
positive_optimistic_count           = 0
positive_realistic_count            = 0
positive_conservative_count         = 0
near_break_even_count               = 1344
high_fee_quote_ready_count          = 0        (all AMM v4 fees = 25bps)
stable_quote_ready_count            = 24
best_pool                           = vs6XUbGcVWG75Gv81qvDMBxkQ67Kr2eLrFNDTrCxxwk (YZai/SOL)
best_pair                           = YZai/SOL
best_notional                       = 2000
best_hold_window                    = 7d
best_scenario                       = zero_il_lvr
best_net_ev_proxy_usd               = +0.172
best_net_ev_proxy_pct               = +0.0086%
can_run_probe_now                   = False
solana_wallet_or_keypair_touched    = False
transaction_sent                    = False
edge_proven                         = no
tiny_canary_allowed                 = no
recommended_next_stage              = LP_SOLANA_STABLE_POOL_RESEARCH_V1
v2_line_count                       = 992 (unchanged)
```

## 关键 finding (V1 真实)

1. **AMM v4 (CPMM) 是 mainnet 唯一 deployed Raydium constant-product program**。source-declared `CPMMoo8L...` (new cp-swap) NOT on mainnet; `DRaycpLY18...` (devnet) NOT on mainnet. v2 SDK wires `DRaycpLY18` as `CREATE_CPMM_POOL_PROGRAM` 但只用于 devnet testing.
2. **AMM v4 SDK decode 走通**: `liquidityStateV4Layout` (v2 SDK) 在 public RPC 上 100% 成功, 81/81 池全部 read 完整 state.
3. **Quote 73/81 quote-ready via constant product formula**: 292 quote rows, 243/292 low slippage (<5% impact). All fees 25bps (AMM v4 standard).
4. **best cell +$0.172 in zero_il_lvr only**: 任何 IL/LVR 假设 → 全负. YZai/SOL (25bps fee) 2000/7d.
5. **4/4 Solana AMM 累计 reject 验证逻辑完成**:
   - Meteora DLMM V8: +$0.544 (zero_il_lvr), 0 realistic
   - Orca Whirlpools V1: +$0.106 (zero_il_lvr), 0 realistic
   - Raydium CLMM V1: +$0.167 (zero_il_lvr), 0 realistic
   - **Raydium CPMM V1 (AMM v4): +$0.172 (zero_il_lvr), 0 realistic**
6. **Per spec rule_2 + user instruction**: 切到 LP_SOLANA_STABLE_POOL_RESEARCH_V1 (test stable-stable AMM, e.g. Curve-style on Solana). 如果 Solana 无 active stable pool → STOP_LP_RESEARCH_NOW.

## 4 AMM 累计对比

| 协议 | 类型 | best cell | positive_realistic | 备注 |
|---|---|---|---|---|
| Meteora DLMM V8 | DLMM (V3) | +$0.544 | 0 | dynamic fee, IL binary |
| Orca Whirlpools V1 | V3 CL | +$0.106 | 0 | 16bps fee, lazy tick array |
| Raydium CLMM V1 | V3 CL | +$0.167 | 0 | 25bps fee, lazy tick array |
| **Raydium CPMM V1 (AMM v4)** | **constant product** | **+$0.172** | **0** | 25bps fee, 100% IL |

## 决定

recommended_next_stage = `LP_SOLANA_STABLE_POOL_RESEARCH_V1`

理由:
- 4/4 AMM 都 reject retail 10-20U 2000 USD LP (强烈稳定结论)
- AMM v4 24 stable pairs 全是 USDC/SOL 或 USDC/USDT (不是 stable-stable)
- stable-stable (Curve-style) 是唯一 IL ≈ 0 的 AMM class
- Solana 上 stable pool 候选: Saber, Orca Whirlpool stable, Mercurial (大多过时)
- 如果 Solana 无 active stable-stable → STOP_LP_RESEARCH_NOW 是合理 stable 结论

## 不做什么 (硬边界)

- ❌ 不 instantiate Keypair
- ❌ 不构造 transaction
- ❌ 不 swap / addLiquidity / removeLiquidity / open LP / close LP
- ❌ 不 collectFee / collectReward
- ❌ 不 paid RPC (public RPC 够用)
- ❌ 不接 wallet
- ❌ 不 modify EVM executor v2
- ❌ 不 set can_run_probe_now = true
- ❌ 不 set tiny_canary_allowed = yes
- ❌ 不进 10/20U probe preflight (positive_realistic=0)
