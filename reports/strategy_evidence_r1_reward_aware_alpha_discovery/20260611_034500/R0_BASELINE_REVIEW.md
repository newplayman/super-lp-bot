# R0 Baseline Review

**Reviewed:** `reports/strategy_evidence_r0_pool_discovery/20260611_031425/`
**Reviewed at:** 2026-06-11T03:50:00Z
**Reviewing run:** `20260611_034500` (R1)

## R0 status

- **Final recommendation:** `NEED_MORE_DATA`
- **Status:** WARN
- **pushed:** true (commits `0e219ec`, `78f33bd`, `137402a`, `f633df0`, `1c9cea1` on `feat/supabase-postgres-deployment`)
- **Key finding:** Every risk-passed pool produces negative expected net PnL at 1-10 USDC × 24h. At the deepest Aerodrome WETH/USDC pool (0xb2cc...), expected gross fee is $0.078/day per $10 LP, gas cost is $0.30/cycle.

## What R0 got right

1. Honest reporting: the report explicitly says "no pool is `GO_TINY_LIVE`", and the per-row `reason` field is informative ("bluechip_or_onestable, near_breakeven net=-0.2576").
2. Clean separation of `raw`, `risk_filtered`, `lp_simulation`, `ranked` artefacts.
3. Symbol coverage was 100% on the ranked CSV despite the GeckoTerminal `/tokens/multi` 429.
4. Fee/gas ratio is the binding constraint and is correctly identified.

## What R0 was missing (R1 fills these)

| Gap in R0 | R1 fix |
|---|---|
| Capital grid stops at $10 USDC; no answer to "what size *would* work?" | Capital grid extended to 1/3/5/10/25/**50** USDC. |
| No horizon dimension (only daily net). | Horizons 1h/6h/24h/72h/**7d**; 7d is the smallest that crosses zero for the top 3. |
| No on-chain gas measurement; $0.30/cycle is a hand-estimate. | Still a hand-estimate (we did not call the gas estimator), but the *per-pool minimum-viable-size* table is a direct output. |
| No DexScreener; GeckoTerminal-only means many small PancakeSwap V3 / Uniswap V3 Base pools were missed. | DexScreener search adds 102 unique pools. |
| Reward APR not modelled; AERO/USDC and AERO/WETH had no special treatment. | AERO-paired pools are tagged `is_aero_paired=true`; reward APR is `null` and `reward_data_unavailable=true` is documented; a small `reward_unquantified=+0.10` bonus is added to the score (and explained). |

## What R0 *did not* say that R1 now says

- "The 1-10 USDC band is gas-negative; the 25-50 USDC × 7d band crosses zero on three pools" is the new headline.
- "Three GO_TINY_LIVE candidates exist *if* we accept $50 USDC × 7d as the probe size; at $10 USDC the answer remains NEED_MORE_DATA."

## R0 → R1 data flow

| | R0 | R1 |
|---|---|---|
| Raw pool count | 120 | 202 |
| Risk-passed | 68 | 115 |
| Simulated (LOW/MEDIUM only) | 53 | 49 (tighter: must have parseable fee_tier + positive volume) |
| Top rank pool | WETH/USDC 0.05% aerodrome $8.48M TVL | same pool, $8.74M TVL (+3% — same pool, different day) |
| WETH/USDC 0.05% expected net @ $10 USDC × 24h | -$0.258 | (now) -$0.222 with refreshed data |
| WETH/USDC 0.05% expected net @ $50 USDC × 7d | not computed | **+$0.40** |

The WETH/USDC 0.05% pool is the *same pool* (0xb2cc...) but the data is now slightly more favorable because the snapshot is fresher (R1 ran ~1h after R0).
