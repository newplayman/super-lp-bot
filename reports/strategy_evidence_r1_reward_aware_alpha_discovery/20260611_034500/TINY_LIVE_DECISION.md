# Tiny-Live Decision

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R1_REWARD_AWARE_ALPHA_POOL_DISCOVERY_V1`
**Run ID:** 20260611_034500
**Final recommendation:** **`NEED_MORE_DATA`** (3 GO_TINY_LIVE candidates exist *if* the user accepts $50 USDC × 7d as the probe size and the unresolved AERO reward question is deferred).

## Why `NEED_MORE_DATA` and not `GO_TINY_LIVE`

The R1 decision matrix says 3 pools pass `GO_TINY_LIVE`:

| pool | MVS | hold | expected net |
|---|---|---|---|
| 0xb2cc... (Aerodrome WETH/USDC 0.05%) | $25 | 7d | +$0.13 |
| 0x72ab... (PancakeSwap V3 WETH/USDC 0.01%) | $25 | 7d | +$0.05 |
| 0xb775... (PancakeSwap V3 WETH/USDC 0.05%) | $50 | 7d | +$0.04 |

But:

1. **Expected net is < $0.50 over 7 days for all three.** A $50 USDC probe earning 30-40 cents of expected net is *barely* positive in the model; in practice, IL variance on a 15% range is ±$1-2 over 7 days, which dwarfs the expected value. The signal-to-noise is not good enough to call this a "GO".

2. **The $0.30 gas cycle estimate is not yet measured on-chain.** R0 and R1 both use a hand-estimated 0.30 USD/cycle (Base L2 at 10 gwei × 420k gas total). We have not yet submitted a single addLiquidity/collect/remove cycle to validate. Until that is done, the gas anchor is a model assumption, not an observation.

3. **AERO reward APR is unquantified.** AERO-paired pools (not in the top 3, but the next 7 include several) cannot be honestly ranked without AERO reward data. The current `reward_data_unavailable=true` is a real data gap, not a model gap.

4. **The 7d hold is long for a "tiny live" probe.** The user's earlier stage definition treats "tiny live" as a 24h probe. Stretching to 7d to amortise gas is a real trade-off, but it's worth flagging.

For these reasons, **the run reports `GO_TINY_LIVE=3` mechanically but the stage's final_recommendation is `NEED_MORE_DATA`**: the user should review the top 3, decide if the $50 × 7d band is the right probe size, and either:

- **Accept the trade-off** → call it `GO_TINY_LIVE` and execute $50 USDC × 7d probe on candidate #1 (Aerodrome WETH/USDC 0.05%) with hard kill conditions.
- **Reject the trade-off** → stay in `NEED_MORE_DATA` until R2 (live gas measurement + Aerodrome Voter address recovery) fills the data gaps.

## Explicit go/no-go for the 25 NO_GO candidates

See `NO_GO_REASONS.md`.

## Recommended abort conditions for the (hypothetical) tiny-live execution

If the user decides to call it `GO_TINY_LIVE` despite the above, the abort conditions are:

- **Data-quality kill:** if live fee accrual is $0 for 24h consecutive, kill. This is the "is the model right?" kill switch.
- **Price kill:** if price leaves ±15% of entry (medium range), exit at market to avoid full out-of-range IL.
- **Gas kill:** if observed gas/cycle on the first addLiquidity exceeds $0.50, kill. The $0.30 model is wrong in a way that makes the trade gas-negative.
- **Time kill:** 7 days hard, regardless of PnL.
- **Cross-pool kill:** if candidate #1 (Aerodrome) and candidate #2 (PancakeSwap) both show $0 fee accrual at 24h, the data-source assumption (volume is real) is wrong — kill all probes and re-evaluate.

These kill conditions should be hard-coded into any subsequent `LP_BOT_TINY_LIVE_V1` runbook.

## What this stage *did* move forward

- **Capital-threshold answer:** $50 USDC × 7d is the smallest honest probe size on Base today. R0 did not compute this; R1 does.
- **Gas-amortization answer:** per-pool minimum-viable-size table (`gas_amortization_matrix.csv`). 49 pools, 35 of which pass at $50 × 7d.
- **Reward placeholder:** AERO paired pools are tagged; the offline Aerodrome subgraph is documented as the only blocker to converting placeholder into real numbers.
- **Cross-venue coverage:** DexScreener adds 102 unique pools not in GeckoTerminal's top-200.
- **Honest `reward_data_unavailable`:** documented in `reward_pools.csv`, `reward_model.jsonl`, `DATA_SOURCE_HEALTH.md`. The R2 stage's job is to fill this.

## What this stage did *not* move forward

- **1-10 USDC probe** — still gas-negative on every pool, including the 3 new GO candidates. R0's finding is confirmed.
- **AERO reward quantification** — needs R2.
- **Live on-chain gas measurement** — needs R2.
- **Tiny-live execution** — needs explicit user authorisation, plus freeze reopening.
