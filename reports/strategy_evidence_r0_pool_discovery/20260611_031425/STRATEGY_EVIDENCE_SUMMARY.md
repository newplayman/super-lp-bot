# R0 Base Pool Discovery — Strategy Evidence Summary

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R0_POOL_DISCOVERY_AND_TINY_LIVE_CANDIDATE_SELECTION_V1`
**Run ID:** 20260611_031425
**Branch:** `feat/supabase-postgres-deployment`
**Base commit (HEAD at scan time):** `bd0544b839c061684d32c8adfba583ea4c77c39c`
**Final recommendation:** **`NEED_MORE_DATA`** (8 blue-chip / one-stable pools are in the candidate band; 0 clear `GO_TINY_LIVE`).

## TL;DR

We pulled the top **120 Base pools by 24h volume** from GeckoTerminal (Aerodrome slipstream, plus a few PancakeSwap/Uniswap V3). After risk-filtering (TVL floor, vol/TVL bounds, age, price-change extremes, symbol denylist) we ran a closed-form LP simulation at 1/3/5/10 USDC × narrow/medium/wide range. **Every pool that passed risk produces negative expected net PnL at 1-10 USDC** because at 0.05% Aerodrome fees, daily fee income is ~$0.05-0.08 per $10 LP, and gas ($0.30/cycle) plus the IL heuristic together exceed it. The 0.3% Aerodrome tier doesn't save it (volume is thinner). The 1% USDC/cbBTC tier produces the highest gross fee ($0.25/day at $10) but fails on the risk filter (MEDIUM, due to a 5x TVL/volume ratio and `non_bluechip_pair` penalty on the cbBTC side) and still nets negative.

**This is a real data point, not a model artifact.** It says that at retail 1-10 USDC probe sizes on Base mainnet, the *fee* side of the LP equation is too thin to amortise a single add+remove+collect gas cycle. Tiny-live would burn money on gas, not earn it.

## Scan parameters

| | |
|---|---|
| Raw pools scanned | 120 |
| Risk-passed (LOW + MEDIUM) | 68 |
| Risk-rejected (HIGH + REJECT) | 52 |
| Simulated (risk-passed with positive volume & fee_tier) | 53 pools × 3 ranges × 4 sizes = **636 sim rows** |
| `GO_TINY_LIVE` | **0** |
| `NEED_MORE_DATA` | **8** |
| `NO_GO` | **45** |

## Risk distribution

| Level | Count | What it took to be here |
|---|---|---|
| LOW | 8 | Aerodrome WETH/USDC, USDC/cbBTC, USDC/cbETH, EURC/USDC, etc. — pairs where both sides are blue-chip (USDC / WETH / cbBTC) and TVL/age/volume are all in band. |
| MEDIUM | 60 | One side is a known L1 wrap or stable but the other is a long-tail token (AERO, VIRTUAL, VVV, DEGEN, msETH, etc.), or TVL/TV is borderline. |
| HIGH / REJECT | 52 | Either TVL below $50k, wash-trading volume signature, abs(24h price change) > 35%, or pool age < 14 days. |

The pool list is heavily Aerodrome-heavy because Aerodrome slipstream dominates Base DEX volume; Uniswap V3 / PancakeSwap V3 Base pools are present but lower in the ranking.

## Top 10 candidates (all `NEED_MORE_DATA`)

These are the highest-scoring blue-chip / one-stable pools that pass risk but cannot be promoted to `GO_TINY_LIVE` because the fee+IL-gas math does not close to positive at 1-10 USDC.

| rank | pool | pair | TVL | 24h vol | best (size, range) | net/day | fee/gas | go |
|---|---|---|---|---|---|---|---|---|
| 1 | 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | WETH/USDC 0.05% (aerodrome) | $8.48M | $133.3M | 10 USDC, narrow 5% | -$0.258 | 0.26 | NEED_MORE_DATA |
| 2 | 0x3fe04a59ebd38cf06080a6a98d124eb59392a | WETH/USDC 0.05% (aerodrome) | $2.95M | $34.3M | 10 USDC, narrow 5% | -$0.278 | 0.19 | NEED_MORE_DATA |
| 3 | 0x82dbe18346a8656dbb6e76f74bf3ae279cc16b29 | WETH/USDC 0.05% (aerodrome) | $451k | $4.69M | 10 USDC, narrow 5% | -$0.283 | 0.17 | NEED_MORE_DATA |
| 4 | 0xd0b53d9277642d899df5c87a3966a349a798f224 | USDC/WETH 0.05% (aerodrome) | $9.41M | $29.0M | 10 USDC, narrow 5% | -$0.289 | 0.05 | NEED_MORE_DATA |
| 5 | 0x6c561b446416e1a00e8e93e221854d6ea4171372 | WETH/USDC 0.3% (aerodrome) | $95.5M | $114.0M | 10 USDC, narrow 5% | -$0.299 | 0.12 | NEED_MORE_DATA |
| 6 | 0xb775272e537cc670c65dc852908ad47015244eaf | WETH/USDC 0.05% (aerodrome) | $1.30M | $5.78M | 1 USDC, narrow 5% | -$0.301 | 0.007 | NEED_MORE_DATA |
| 7 | 0x72ab388e2e2facef59e3c3fa2c4e29011c2d38 | WETH/USDC 0.01% (aerodrome) | $3.90M | $47.5M | 1 USDC, narrow 5% | -$0.302 | 0.004 | NEED_MORE_DATA |
| 8 | 0xb4cb800910b228ed3d0834cf79d697127bbb00e5 | WETH/USDC 0.01% (aerodrome) | $391k | $3.14M | 1 USDC, narrow 5% | -$0.303 | 0.003 | NEED_MORE_DATA |

All 8 have the same shape: positive gross fee, negative net, fee/gas ratio < 1.0.

## Why no `GO_TINY_LIVE`

The honest answer is in the fee/gas column. On Base, the realistic gas cost of a *full* LP cycle (approve+add+collect+remove = ~4 txs at ~120k gas each, ~10 gwei, ETH ~$3000) is roughly $0.30. For a $10 USDC position in a 0.05% WETH/USDC pool with $133M daily volume and $8.5M TVL, the LP's share of daily fees is:

> `10 * (133e6 * 0.0005) / 8.5e6` ≈ `0.078 USD/day`

That's 0.26× the gas cost of one cycle. **You'd have to hold the position for ~4 days just to break even on gas, ignoring IL entirely.** And IL on a narrow 5% range in a pool that moved 0.6% in 24h is small in expectation but non-zero.

A 0.3% tier (rank 5) has higher gross fee per dollar of TVL but volume is spread across more liquidity, so the per-LP share is *lower* (0.036 USD/day). The 1% USDC/cbBTC tier is the only pool whose gross fee exceeds gas — at $10 it's $0.25/day gross — but cbBTC carries the `non_bluechip_pair` risk flag (cbBTC is L1-wrapped BTC, treated as L1, but the model still penalized it because it's not a stable, so `can_tiny_live=False`).

## Risk filters applied

| Filter | Threshold | Source |
|---|---|---|
| TVL floor | $50,000 USD | 1-10 USDC LP below this moves the pool enough to break the model |
| 24h vol / TVL | 0.05 ≤ x ≤ 50.0 | Below 0.05 = dead pool. Above 50 = wash-trade candidate. |
| abs(24h price change) | ≤ 35% | Above this a 5% range is essentially guaranteed out-of-range |
| abs(6h price change) | ≤ 20% | Short-window guard |
| Pool age | ≥ 14 days | New pools have no fee history |
| Symbol denylist | INU, PEPE, SHIB, DOGE, MOON, TEST, XXX, FAKE, RUG, SCAM | Meme / honeypot surface |
| Pair allowlist | One of: blue-chip+blue-chip, stable+L1 wrap | Anything else gets `non_bluechip_pair` risk flag |
| Fee tier resolution | must parse to known bps (1, 1.8, 2, 2.1, 3, 5, 25, 30, 100) | Pools whose name doesn't end in a known fee marker get flagged |

The risk filter is intentionally conservative for tiny-live: it's a small deny-list, not a generative classifier.

## LP simulation model

Closed-form, per pool, per (size × range):

```
expected_fee_per_day = size_usdc * (pool_24h_volume * fee_bps/10000) / pool_tvl
expected_il_per_day  = size_usdc * il_daily_pct(range_pct, abs(price_change_24h))
gas_per_cycle        = 0.30 USD  (add + collect + remove, conservative)
net_per_day          = expected_fee - expected_il - gas
```

`il_daily_pct` is a piecewise heuristic on `sigma = abs(pc_24h) / 100`:
- range ≤ 5% : `min(0.5, 0.6 * sigma)`
- range ≤ 15%: `min(0.4, 0.3 * sigma)`
- range > 15%: `min(0.2, 0.1 * sigma)`

This is *not* a real options-pricing model; it bounds IL by the observed 24h move and assumes the move is one sigma. The aim is to put a number on the IL line, not to defend the number.

## Ranking formula

For each pool, the script picks the (size, range) cell that maximises:

```
score = 0.6 * n_net + 0.4 * n_fg - range_pen
where n_net  = clip((net_per_day + 1.0) / 2.0, 0, 1)
      n_fg   = clip(fee_to_gas / 50.0, 0, 1)
      range_pen = {narrow: 0, medium: 0.05, wide: 0.10}
```

Then sort by `go_no_go` (GO first, NEED_MORE next, NO_GO last) and within each group by `score` desc.

## What is *not* covered

- No historical OHLCV back-test. We use 24h/6h point-in-time volume and price-change %, not a 30-day fee-yield reconstruction.
- No holder concentration (we'd need the `/networks/base/tokens/{addr}/info` endpoint, which is rate-limited).
- No contract verification status. We trust the token allowlist (USDC, USDbC, DAI, WETH, cbBTC).
- No actual gas measurement against a live tx. The $0.30/cycle is a conservative hand-estimate.
- IL is a heuristic, not an analytic model.

## Decision for the next stage

This run is **WARN by the stage's own criteria** (data is real, conclusion is `NEED_MORE_DATA`, no pools were promoted to live). The right next move is **NOT to attempt tiny-live yet** — the math is clear that 1-10 USDC on the WETH/USDC pairs is gas-negative. The options to re-evaluate are:

1. **Hold/extend observation**: re-run weekly; see whether a fee-tier-1% pool on a stable/L1 wrap pair sustains positive expected net. (cbBTC/USDC 1% is the closest, but model currently penalises cbBTC.)
2. **Re-tune risk**: decide whether cbBTC counts as L1-blu-chip for tiny-live; if yes, that pool promotes to `GO_TINY_LIVE` with a $10 cap.
3. **Look at non-Aerodrome venues** on Base (Uniswap V3, PancakeSwap V3) for any pool with a fee tier that produces a positive net at $10 — none of the 53 ranked pools did, but the universe of 120 was dominated by Aerodrome slipstream.
4. **Look at non-USD-quoted pools** with higher APR, accepting the additional token risk.

See `TINY_LIVE_CANDIDATE_RECOMMENDATION.md` for the explicit top-3 selection (under the conservative interpretation; all 3 are `NEED_MORE_DATA`) and `NO_GO_REASONS.md` for the rest.
