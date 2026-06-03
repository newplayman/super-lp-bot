# Meteora 10/20U Pre-flight Implication — Stage H

- stage: `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1`
- run_id: `20260603_153736`
- scope: **partial_pool2_only (X/USDC)**

## 0. operator 6 个问题 + 答案

### Q1: X/USDC 是否值得进入 10/20U probe preflight design？

**A: NO (honestly).**

V8 partial EV preview for X/USDC at 10/20U:
- 10U notional + zero_il_lvr scenario: net_ev ≈ -$0.187 (close to -$0.19 cost)
- 10U notional + realistic scenario: net_ev ≈ -$0.247 (cost + 0.5% IL)
- 20U notional + zero_il_lvr: net_ev ≈ -$0.184
- 20U notional + realistic: net_ev ≈ -$0.284

→ All 10/20U cells are **negative** (best -$0.184 at 20U/15m/zero_il_lvr; worst -$0.284 at 20U/15m/realistic).

### Q2: 是否需要 Solana wallet/keypair？

**A: NO (this round).**

Per spec hard rule: "不得选择 probe/live/canary/wallet/keypair". V8 is **read-only analysis only**. We do not construct any transaction or instantiate any signer. Solana wallet/keypair only needed if we **actually** probe with a 10/20U USDC position; that's a **next-stage decision** based on operator input.

### Q3: 是否需要额外 token？

**A: For probe, would need X token + USDC. For V8: NO.**

V8 only computes theoretical EV. We do **NOT** acquire any token. The "notional" column is theoretical (10U USDC input; quote to X output). To actually probe, operator would need: 10-20 USDC + 1 X (small amount) + SOL for gas.

### Q4: 是否有足够 quote/fee/cost 数据？

**A: PARTIAL. Sufficient for theoretical EV; insufficient for production probe.**

| data | status | source |
|---|---|---|
| quote (X/USDC) | ✅ ready (V6 6/6 stable; 10U=941005 raw X; 20U=1882010) | V6 |
| bin liquidity | ✅ ready (V6 231 bins with liquidity; V7 280 bins decoded) | V6+V7 |
| fee snapshot | ✅ ready (base=1.5%; max=10%; protocol=missing) | V4 |
| pool snapshot | ✅ ready (bin_step=100; active=-236; price=0.0955) | V4 |
| reserves | ✅ ready (101T X / 2.2T USDC) | V4 |
| **actual on-chain volume** | ❌ missing (heuristic used) | V8 |
| **actual realized IL/LVR** | ❌ missing (scenario-based proxy) | V8 |
| **actual priority fee** | ❌ missing (heuristic: 1k-100k microLamports) | V8 |
| **real SOL price** | ❌ missing (heuristic: $130) | V8 |
| **real rent** | ❌ missing (heuristic: 0.00089 SOL) | V8 |
| **real slippage** | ❌ missing (V6 quote has no price_impact field) | V6 |

### Q5: 是否 realistic positive EV？

**A: NO.**

Realistic scenario for 10/20U:
- 10U/realistic: net_ev = -$0.247
- 20U/realistic: net_ev = -$0.284
- 10U/realistic/15m: net_ev = -$0.247 (best)
- 20U/realistic/15m: net_ev = -$0.284 (best)

→ **All 10/20U realistic cells negative.** Best realistic cell is -$0.247.

### Q6: 是否只是 exploratory connector probe？

**A: Current state = preflight design only. V8 has done partial EV preview, NOT probe.**

If operator decides to proceed to `LP_METEORA_DLMM_10_20U_PROBE_PREFLIGHT_DESIGN_V1`, that stage would:
- Design the probe sequence (entry tx, hold window, exit tx)
- Specify required wallet setup (keypair generation, SOL funding, USDC funding, X token swap if needed)
- Define go/no-go criteria (e.g. net_ev_usd > $0 threshold)
- **NOT** execute any probe; still read-only

If `LP_METEORA_DLMM_10_20U_PROBE_PREFLIGHT_DESIGN_V1` results indicate EV would be positive, **separate stage** would actually execute the probe (with operator keypair).

## 7. 是否应优先扩 known pool feed 而不是 probe？

**A: YES (recommended).**

Reasoning:
- V8 EV preview for X/USDC at 10-2000 notionals is **all negative** even with heuristic assumptions
- Real EV may be different but not likely to be significantly positive given fixed cost structure
- **Better path**: extend known pool feed to include more Meteora DLMM pools with higher fees (e.g. some pools have max_fee=20-30% with active volume)
- Or: extend to Raydium CLMM (CAMMCzo5...) which has different fee structure
- Or: extend to Orca Whirlpools (whirLbMi...) which has different LP mechanics

→ **Recommended next_stage: `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1`** (find more pools with potentially positive EV).

## 1. Summary decision

- 10/20U X/USDC probe: **NOT worth it** (negative EV even in best case)
- 10/20U preflight design: **deferrable** (no point designing if no actual probe coming)
- Known pool feed expansion: **YES** (better ROI)
- Paid RPC for SOL/USDC: **deferrable** (would need paid RPC but X/USDC alone insufficient)
- Survival EV preview: **honest report: NEGATIVE for X/USDC at 10-2000 USD notionals**

## 2. 不在本阶段做

- ❌ 不构造任何 transaction
- ❌ 不 instantiate Keypair
- ❌ 不 import wallet adapter
- ❌ 不 probe
- ❌ 不实际 swap / open_lp / close_lp / collect_fee
- ❌ 不 paid RPC call (无 key)
- ❌ 不修改 EVM executor v2

## 3. 安全断言

```text
this_stage_only_implication_analysis = true
no_actual_probe = true
no_keypair = true
no_wallet_adapter = true
solana_wallet_or_keypair_touched = false
can_run_probe_now = false
v2_line_count_unchanged = true (992)
```

## 4. 下一阶段

进入 Stage I — next-stage decision: 选 `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1` (扩展 known pool feed 找更高 EV 池).
