# Meteora 10/20U Preflight Implication — Stage H

- stage: `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1`
- run_id: `20260603_190910`
- scope: `partial_pool2_only (X/USDC)`

## 0. 核心结论

```text
10_20U_x_usdc_probe_worth         = NO (honestly)
10_20U_preflight_design_worth    = NO (no point if no probe coming)
known_pool_feed_expansion_worth   = YES (recommended; better ROI path)
paid_rpc_for_sol_usdc             = deferrable
survival_ev_honest_report         = NEGATIVE for X/USDC at 10-2000 USD notionals
```

## 1. Operator Questions Answered

### Q1: Is X/USDC worth a 10/20U probe?

**Answer: NO (honestly).**

Best 10/20U cells under V8 EV model (Stage G):

| notional | hold | scenario | net_ev_usd | net_ev_pct |
|---|---|---|---|---|
| 10 | 15m | zero_il_lvr | -$0.156 | -1.559% |
| 10 | 15m | realistic | -$0.206 | -2.059% |
| 20 | 15m | zero_il_lvr | -$0.156 | -0.780% |
| 20 | 15m | realistic | -$0.256 | -1.279% |

All 10/20U cells are **negative in every scenario** (zero_il_lvr, optimistic, realistic, conservative). The structural issue is that gross fee capture at retail notionals (10/20 USD) is 1,000–10,000× smaller than the fixed cost (~$0.156 per position).

### Q2: Do we need a Solana wallet?

**Answer: NO (this round).**

V8 is read-only analysis only; no transaction construction; per spec "不得选择 probe/live/canary/wallet/keypair". `solana_wallet_or_keypair_touched = false`; `can_run_probe_now = false`; `tiny_canary_allowed = "no"`. Even if a future preflight-design stage were authorized, the wallet acquisition is a separate operator task and outside this stage's scope.

### Q3: Do we need extra tokens (X, USDC, SOL)?

**Answer: For probe yes (X + USDC + SOL); for V8 no.**

V8 is theoretical EV only; no token acquisition. The "notional" column is theoretical (10U USDC input → X output). Real probe would need:
- USDC: at least `notional` USDC for input
- X: at least `notional / X_price` raw X for the other side of the LP
- SOL: ~0.01 SOL for tx fees + rent

### Q4: Is the data we have sufficient?

**Answer: PARTIAL.**

**Available:**
- quote (X/USDC) — V6 6/6 stable
- bin liquidity (X/USDC) — V6 231 bins with liquidez at 5_arrays
- fee snapshot (X/USDC) — V4 1.5%/10%
- pool snapshot (X/USDC) — V4 bin_step=100, active_bin_id=-236
- reserves (X/USDC) — V4 101T X / 2.2T USDC

**Missing (heuristic-marked in model, NOT filled with 0):**
- actual on-chain trading volume
- actual realized IL/LVR
- actual realized slippage on larger notionals
- actual Solana priority fee
- actual rent amount
- real token USDC supply
- real SOL price at probe time

### Q5: Is the realistic scenario positive EV?

**Answer: NO.**

Best realistic (10 notional, 15m): **-$0.206 / -2.06%**
Worst realistic (10 notional, 7d): **-$0.256 / -2.56%**

Every realistic cell is negative. The fixed cost ($0.156) dominates the gross fee ($0.0000075) at retail notionals by 5+ orders of magnitude.

### Q6: Is this just an exploratory connector probe (no real execution)?

**Answer: V8 is preflight design only, NOT probe.**

If next stage is `LP_METEORA_DLMM_10_20U_PROBE_PREFLIGHT_DESIGN_V1`, that would **design** the probe (no execute). If EV is positive, a separate stage executes the probe (with operator keypair). V8 is the *analysis* of whether probe is worth designing.

Current state: `preflight_design` (NOT probe).

### Q7: Should we expand known pool feed instead of probing X/USDC?

**Answer: YES (recommended).**

10–20U X/USDC EV is all negative; expanding the pool feed to find higher-fee Meteora DLMM pools or other AMM protocols (Raydium CLMM, Orca Whirlpools) has better ROI. Paid RPC for SOL/USDC is deferrable until feed expansion is exhausted.

## 2. Summary Decision

| question | answer |
|---|---|
| 10_20U probe worth | **false** |
| 10_20U preflight design worth | **false** (no point if no probe coming) |
| known pool feed expansion worth | **true** |
| paid rpc for sol_usdc | deferrable |
| survival_ev honest report | NEGATIVE for X/USDC at 10–2000 USD notionals |

## 3. Key finding

10/20U X/USDC probe is **NOT worth it** under the V8 EV model (heuristic-based; missing actual volume/IL). Net EV is structurally negative at retail notionals for X/USDC given:
- low base fee (1.5%)
- low assumed volume (heuristic 0.5%)
- fixed cost (~$0.16 round-trip + setup)

Real EV could be different if:
- actual volume is 10×+ higher (e.g., if X/USDC turns out to have real organic flow)
- max_fee (10%) kicks in (Meteora dynamic volatility fee; not modeled)
- zero_il_lvr is realistic for tight notional windows (we don't know)

But under any realistic combination, the **order-of-magnitude conclusion** is the same: at retail notionals, Meteora DLMM X/USDC single-position LP cannot recover the fixed cost.

## 4. 不在本阶段做

- ❌ 不构造 transaction
- ❌ 不 instantiate Keypair
- ❌ 不 import wallet adapter
- ❌ 不 execute probe
- ❌ 不 swap / open_lp / close_lp / collect_fee
- ❌ 不 paid RPC call
- ❌ 不 modify EVM executor v2

## 5. 安全断言

```text
solana_wallet_or_keypair_touched = false
can_run_probe_now                = false
v2_line_count_unchanged          = true (992)
x_usdc_preflight_candidate       = false
```

## 6. 下一阶段

进入 Stage I — next-stage decision (recommend `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1`).
