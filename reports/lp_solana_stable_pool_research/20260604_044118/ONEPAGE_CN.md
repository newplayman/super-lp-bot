# Stable Pool Research — One-Page Summary (LP Research 收口)

- stage: `LP_SOLANA_STABLE_POOL_RESEARCH_V1`
- run_id: `20260604_044118`
- branch: `feat/supabase-postgres-deployment`
- head_before: `8b2562a`

## 关键结果 (LP research 收口)

```text
status                              = WARN
program_verified                    = True (4 stable AMM candidates verified on mainnet)
verified_program_count              = 4
verified_pool_count                 = 25
sdk_decode_success_count            = 25
quote_ready_pool_count              = 10
survival_ev_model_ran               = True
row_count                           = 1680
positive_zero_il_lvr_count          = 30
positive_optimistic_count           = 0
positive_realistic_count            = 0
positive_conservative_count         = 0
near_break_even_count               = 1067
high_fee_quote_ready_count          = 3
stable_quote_ready_count            = 10
best_pool                           = AiMZS5U3JMvpdvsr1KeaMiS354Z1DeSg5XjA4yYRxtFf (mSOL/USDC)
best_pair                           = mSOL/USDC
best_notional                       = 2000
best_hold_window                    = 7d
best_scenario                       = zero_il_lvr
best_net_ev_proxy_usd               = +0.204
best_net_ev_proxy_pct               = +0.0102%
can_run_probe_now                   = False
solana_wallet_or_keypair_touched    = False
transaction_sent                    = False
edge_proven                         = no
tiny_canary_allowed                 = no
recommended_next_stage              = STOP_LP_RESEARCH_NOW
v2_line_count                       = 992 (unchanged)
```

## 关键 finding (LP research 收口阶段)

1. **4 mainnet stable AMM programs verified**: Meteora Stable Swap (ex-Saber) `SSwpkEEcbUqx4vtoEByFjSkhKdCT862DNVb52nZg1UZ`, Meteora DAMM v2 `cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG`, Orca Whirlpool `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc`, Raydium AMM v4 `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8`.
2. **Meteora DAMM v2 API mislabels**: 50 "USDC-USDT" candidates returned by API actually belong to Orca (owner=`Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB`), not Meteora DAMM v2. After chain verify, 0 DAMM v2 stable pools.
3. **Saber rebrand as Meteora Stable Swap but no active pools on mainnet** found via API or on-chain discovery.
4. **25 Orca stable pools verified** (all LST-stable: SOL/USDC, mSOL/USDC, jitoSOL/USDC, USDC/USDT 0.01%); 10/25 quote-ready, 3 high-fee (>=30bps).
5. **best cell +$0.204 in zero_il_lvr only** (mSOL/USDC, 30bps, 2000/7d); 0 in realistic/optimistic/conservative.
6. **Per spec rule_2 + 5/5 AMM reject**: **STOP_LP_RESEARCH_NOW** is the stable 结论.

## 5 AMM Protocol 累计 5/5 reject

| 协议 | 类型 | best cell | positive_realistic | 备注 |
|---|---|---|---|---|
| Meteora DLMM V8 | DLMM (V3) | +$0.544 | 0 | dynamic fee, IL binary |
| Orca Whirlpools V1 | V3 CL | +$0.106 | 0 | 16bps fee, lazy tick array |
| Raydium CLMM V1 | V3 CL | +$0.167 | 0 | 25bps fee, lazy tick array |
| Raydium CPMM V1 | constant product | +$0.172 | 0 | 25bps fee, 100% IL |
| **Orca stable (this)** | **V3 CL LST-stable** | **+$0.204** | **0** | 30bps fee, mSOL/USDC |

**5/5 Solana AMMs 全部 reject retail 10-20U 2000 USD LP** in zero_il_lvr only.

## 决定

recommended_next_stage = `STOP_LP_RESEARCH_NOW`

理由 (5/5 reject 累计):
1. **Meteora DLMM V8**: best +$0.544, 0 realistic
2. **Orca Whirlpools V1**: best +$0.106, 0 realistic
3. **Raydium CLMM V1**: best +$0.167, 0 realistic
4. **Raydium CPMM V1**: best +$0.172, 0 realistic
5. **Orca stable (this)**: best +$0.204, 0 realistic

**All best cells only in zero_il_lvr scenario, all under $0.55 even at 7d 2000 USD notional**.
**结论**: 在 Solana 生态, retail 10-20U 2000 USD LP 在所有已知 AMM protocols (V3 CL, constant product, LST-stable) 都无法获得 realistic positive EV. LP research 该阶段完成.

## 不做什么 (硬边界)

- ❌ 不 instantiate Keypair
- ❌ 不构造 transaction
- ❌ 不 swap / openPosition / closePosition / addLiquidity / removeLiquidity
- ❌ 不 collectFees / collectReward
- ❌ 不 paid RPC (public RPC 够用)
- ❌ 不接 wallet
- ❌ 不 modify EVM executor v2
- ❌ 不 set can_run_probe_now = true
- ❌ 不 set tiny_canary_allowed = yes
- ❌ 不进 10/20U probe preflight (positive_realistic=0)
- ❌ 不再继续 LP research (STOP_LP_RESEARCH_NOW 是收口)

## STOP_LP_RESEARCH_NOW 含义 (per spec)

按 spec 列表:
- `LP_STABLE_POOL_10_20U_PROBE_PREFLIGHT_DESIGN_V1` (本轮 reject)
- `LP_STABLE_POOL_KNOWN_POOL_FEED_EXPANSION_REPEAT` (本轮 reject)
- `LP_SOLANA_PAID_RPC_SETUP_REQUIRED` (本轮 reject)
- **`STOP_LP_RESEARCH_NOW` (本轮 selected)**

STOP 意味着:
- 累计 5 AMM protocols 验证 negative
- Solana 生态对 retail 10-20U 2000 USD LP 不可行
- LP research 该阶段完成
- 任何后续 LP 决策必须基于 manual operator 决策 (not auto)
- hard-disable 仍 active, can_run_probe_now=false, tiny_canary_allowed=no (不变)
