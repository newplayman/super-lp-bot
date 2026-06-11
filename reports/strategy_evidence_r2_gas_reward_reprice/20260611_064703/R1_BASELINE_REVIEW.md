# R1 Baseline Review — R2

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R2_GAS_ANCHOR_AND_AERODROME_REWARD_RECOVERY_V1`
**Run ID:** 20260611_064703
**Probed at:** 2026-06-11T06:47:03Z (UTC)

## R1 recap (read from `reports/strategy_evidence_r1_reward_aware_alpha_discovery/20260611_034500/`)

R1 was a reward-aware, gas-aware alpha-pool discovery run on Base mainnet. Key R1 outputs:

| Output | R1 conclusion |
|---|---|
| 202 risk-scored pools (LOW=16, MEDIUM=99, HIGH=39, REJECT=48) | — |
| 3 GO_TINY_LIVE candidates (mechanical) | 0xb2cc..., 0x72ab..., 0xb775... |
| 7 NEED_MORE_DATA candidates | 4 cbBTC pairs, EURC/USDC, VIRTUAL/WETH, msUSD/USDC |
| 25 NO_GO candidates | 5 stable-stable, 12 long-tail, 4 thin-volume, 2 unknown-fee, 2 low-TVL |
| Capital threshold matrix | 1,470 cells (49 pools × 6 sizes × 5 horizons) |
| Gas amortization matrix | 49 pools |
| Reward model | `reward_data_unavailable=true` for all 202 pools (Aerodrome subgraph offline) |
| Final recommendation | **`NEED_MORE_DATA`** |
| Reason for NEED_MORE_DATA | expected net $0.04–$0.40 vs IL variance ±$1–2, gas anchor was $0.30/cycle (R1 model) |

## R2 re-reads of R1 outputs

R2 re-uses R1's `ranked_candidates.csv`, `capital_threshold_matrix.csv`, `gas_amortization_matrix.csv` as inputs and re-prices them with the new gas anchor (R2 observed: $0.08/cycle at 0.05 gwei, vs R1 model $0.30/cycle).

R2 also re-uses R1's `reward_pools.csv` (all `reward_data_unavailable=true`) and finds that the recovery is **partial**, not full, even after R2.

## Top 3 R1 candidates — re-checked against R2 evidence

| Rank | Pool | Pair | Protocol | R1 expected net @ $50 × 7d | R2 expected net @ $50 × 7d | Change |
|---|---|---|---|---|---|---|
| 1 | 0xb2cc... | WETH/USDC 0.05% | aerodrome-slipstream | +$0.40 | +$0.40 (or higher — see note) | unchanged or better |
| 2 | 0x72ab... | WETH/USDC 0.01% | pancakeswap-v3-base | +$0.05 | +$0.05 (or higher) | unchanged or better |
| 3 | 0xb775... | WETH/USDC 0.05% | pancakeswap-v3-base | +$0.04 | +$0.04 (or higher) | unchanged or better |

**Note on R2 expected net:** R1's expected net formula was `fee_income - gas_cost`. The fee income component is unchanged (R1's TVL/volume data is from a single snapshot at 2026-06-11T03:45:00Z). The gas cost component drops from $0.30 to $0.08 (R2 observed at 0.05 gwei) — a 22-cent reduction. R2's `repriced_capital_threshold_matrix.csv` shows the full grid.

In absolute terms:
- 1 USDC × 7d: R1 net = -$0.23; R2 net = -$0.01
- 3 USDC × 7d: R1 net = -$0.21; R2 net = +$0.01
- 5 USDC × 7d: R1 net = -$0.19; R2 net = +$0.03
- 10 USDC × 7d: R1 net = -$0.15; R2 net = +$0.07
- 25 USDC × 7d: R1 net = -$0.06; R2 net = +$0.16
- 50 USDC × 7d: R1 net = +$0.04; R2 net = +$0.26

The 50 USDC × 7d case is improved by $0.22 (3.0× the R1 net). At 10 USDC × 7d, the pool now passes gas (was -$0.15, now +$0.07). This is a direct consequence of the gas anchor correction.

## Top 7 R1 NEED_MORE_DATA candidates — re-checked

All 7 R1 NEED_MORE_DATA candidates are cbBTC-paired (4), EURC-paired (1), VIRTUAL-paired (1), or msUSD-paired (1). R2's gas-anchor correction does not change their risk-based NEED_MORE_DATA classification — that was driven by cbBTC not being classified as blue-chip, by EURC being a smaller stablecoin, by VIRTUAL being long-tail, and by msUSD being newer. R2 cannot resolve any of these model calls.

The 4 cbBTC pairs would change status if cbBTC were re-classified as blue-chip (R1 documented this explicitly in `NO_GO_REASONS.md`). R2 does not re-classify cbBTC.

## What R2 changes vs R1

| Aspect | R1 | R2 | Effect on recommendation |
|---|---|---|---|
| Gas anchor (typical 0.05 gwei) | $0.30/cycle (hand-estimate) | **$0.08/cycle (real on-chain observed)** | $10 × 24h moves from gas-negative to gas-positive; $50 × 7d moves from "thin edge" to "comfortable" |
| Aerodrome Voter address | unknown | **recovered** | unblocks R3 reward-rate probing |
| Aerodrome CLNPM | unknown | **recovered** | enables direct MINT/CLNPM gas estimate (next stage) |
| Aerodrome Gauge address (top candidate) | unknown | **recovered** | unblocks R3 reward-rate probing |
| Per-pool reward rate | unknown | **still unknown** | cannot quantify AERO emissions for any pool |
| Per-pool reward APR | unknown | **still unknown** | scoring must remain `reward_unquantified=+0.10` placeholder |
| Final recommendation | NEED_MORE_DATA | **NEED_MORE_DATA** (see below) | unchanged in name, upgraded in confidence |

## Why R2 still concludes NEED_MORE_DATA (not GO_TINY_LIVE)

R1's NEED_MORE_DATA was driven by 4 concerns:
1. Reward data missing for AERO pools → **partial fix in R2** (addresses recovered, rate still unknown)
2. Gas anchor unverified → **fixed in R2** (real on-chain observed $0.08/cycle)
3. IL variance dwarfs expected net ($1–2 vs $0.04–$0.40) → **unchanged**
4. cbBTC re-classification would change rankings → **unchanged** (model call, not data)

Of the 4, R2 fixed #2 outright and partial-fixed #1. #3 and #4 remain.

The decision rule in the R2 stage spec says: `GO_TINY_LIVE` only if all of:
- top candidate expected_net_pnl_usd > 0 after observed gas → **YES for the 3 R1 top pools**
- data_quality_score >= 0.75 → **YES (R1: 0.85)**
- risk level LOW or MEDIUM → **YES (R1: LOW)**
- gas anchor observed → **YES (R2 observed)**
- reward data either observed or not required for this candidate → **PARTIAL** (R1 top-3 are non-AERO WETH/USDC, so reward data is not required for them; but the R2 stage spec says "reward data observed or not required" — and it is in fact not required for these specific candidates, so this condition is met)
- max tiny live size <= 50 USDC → **YES**
- hold <= 7d → **YES**
- clear abort conditions → **YES (R1 has these)**
- signal-to-noise better than R1 → **YES on gas; UNCHANGED on IL variance**

The signal-to-noise check is the blocker. R1's "IL variance $1-2 dwarfs expected net $0.04-0.40" is **not addressed by R2** because IL variance is a function of the price-volatility environment, not the gas anchor. The decision rule is satisfied except for this one check.

Therefore, R2's recommendation is **NEED_MORE_DATA** (upgraded from R1's "thin edge, NEED_MORE_DATA" to "gas math fixed, still need IL-variance-or-equivalent-hedge"):

- 2/5 NEED_MORE_DATA conditions fixed (gas + reward addresses)
- 1/5 still open (reward rate, partial — addresses recovered, rate unknown)
- 1/5 still open (IL variance / signal-to-noise)
- 1/5 unchanged (cbBTC re-classification, model call)

R2's path to GO_TINY_LIVE is now narrowed to: (a) read the gauge's bytecode to find the actual reward-rate selector (R3), or (b) execute the R1 top-3 candidates on a sub-second timescale basis (e.g. add → remove within 1 block, no IL exposure) using a script-only `eth_sendTransaction` (which is still prohibited by the freeze).

## What R2 does NOT do

- Does not modify the R1 reports directory.
- Does not start canary, live, paper, mode B, R1, or R2 long-horizon collector.
- Does not set `LPBOT_CONFIRM_LIVE=YES`.
- Does not connect a wallet, sign, broadcast, approve, mint, addLiquidity, removeLiquidity, collect, swap, or bridge.
- Does not use a paid RPC, private RPC, or real secret.
- Does not create CI/smoke/migration/schema-guard work.
- Does not reclassify cbBTC, EURC, or any token's risk level.
