# R1 Reward-Aware Alpha Pool Discovery — Executive Summary

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R1_REWARD_AWARE_ALPHA_POOL_DISCOVERY_V1`
**Run ID:** 20260611_034500
**Branch:** `feat/supabase-postgres-deployment`
**Base commit:** `1c9cea12b7c9afab96d525cb06d06f3642a9fc6d`
**Final recommendation:** **`NEED_MORE_DATA`** (3 blue-chip pools are now technically `GO_TINY_LIVE` only at $50 USDC × 7d hold; $10 USDC remains gas-negative as R0 found).

## TL;DR

We pulled **202 Base pools** (GeckoTerminal + DexScreener union, de-duplicated by pool address) and ran the *capital-threshold* and *gas-amortization* matrices that R0 was missing. The headline answer to the user's question:

> **At $10 USDC, gas dominates. At $50 USDC × 7-day hold, three blue-chip pools cross the gas-amortization line with $0.04–$0.40 expected net (after fee + IL − gas).** AERO reward emissions exist for AERO-paired pools but the public reward data source (Aerodrome hosted subgraph) is offline; `reward_data_unavailable=true` for the whole run.

## Scan parameters

| | |
|---|---|
| Raw pools scanned | 202 (100 GeckoTerminal + 135 DexScreener, 33 overlap) |
| Risk-passed (LOW + MEDIUM) | 115 |
| Risk-rejected (HIGH + REJECT) | 87 |
| Simulated cells (size × horizon × pool) | 1,470 (49 pools × 6 sizes × 5 horizons) |
| `GO_TINY_LIVE` | **3** (only at $50 USDC × 7d) |
| `NEED_MORE_DATA` | 7 |
| `NO_GO` | 25 |
| `reward_data_unavailable` | **true** (Aerodrome subgraph is offline) |

## Top 3 by score (all `GO_TINY_LIVE`)

| rank | pool | pair | TVL | 24h vol | MVS | hold | expected_net | gas/24h | pass @ 10usdc-24h | pass @ 50usdc-7d | risk | dq |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | WETH/USDC 0.05% aerodrome-slipstream | $8.74M | $134.7M | $25 | 7d | $0.40 | $0.30 | False | **True** | LOW | 0.85 |
| 2 | 0x72ab388e2e2facef59e3c3fa2c4e29011c2d38 | WETH/USDC 0.01% pancakeswap-v3-base | $3.93M | $48.6M | $25 | 7d | $0.05 | $0.30 | False | **True** | LOW | 0.85 |
| 3 | 0xb775272e537cc670c65dc852908ad47015244eaf | WETH/USDC 0.05% pancakeswap-v3-base | $1.31M | $5.84M | $50 | 7d | $0.04 | $0.30 | False | **True** | LOW | 0.85 |

`MVS` = minimum viable size (smallest position size × horizon that produces net ≥ 0).
All three pass the gas-amortization check at $50 USDC × 7d but fail at $10 USDC × 24h.

## What changed vs R0

| | R0 | R1 |
|---|---|---|
| Sources | GeckoTerminal only | GeckoTerminal + DexScreener |
| Raw pool count | 120 | 202 |
| Capital grid | 1/3/5/10 USDC | 1/3/5/10/25/50 USDC |
| Horizon grid | (n/a, daily only) | 1h / 6h / 24h / 72h / 7d |
| Gas-amortization answer | not computed | **computed per-pool** (gas_amortization_matrix.csv) |
| Reward APR | not modelled | placeholder `reward_data_unavailable=true` |
| Decision | NEED_MORE_DATA, no GO | **3 GO_TINY_LIVE only at $50 USDC × 7d**, 7 NEED_MORE_DATA |

## What R1 *did not* move forward

- **AERO reward APR** is structurally missing from public free data sources. The Aerodrome hosted subgraph (`api.thegraph.com/subgraphs/name/aerodrome-finance/aerodrome`) is 301-redirected to `error.thegraph.com` — this run could not connect. AERO/USDC and AERO/WETH pools are present in the candidate set but their reward component is unquantified; the run adds a small `reward_unquantified=+0.10` bonus to the score for AERO-paired pools, **not** an APR number.
- **1-10 USDC × ≤ 24h** still produces negative net on every pool. R0's conclusion holds.
- **Holder concentration, contract verification, bribe data** are still not in scope. The risk filter is the same allow-by-symbol heuristic as R0.

## Decision for the next stage

This run produces a *real* minimum-viable-size answer: **$25-50 USDC × 7-day hold** is the smallest honest entry point on Base today for fee-only LP economics. The natural next stages are:

1. **R2a_gas_aware_$50_tiny_live_dryrun** — actually validate the gas-anchor assumption by submitting one addLiquidity/collect/remove cycle against a Base RPC *read-only simulation*. This is a dryrun / shadow test; no signing, no real tx, but uses the existing `lp_base_unsigned_tx_package_builder_v1_readonly.py` + `lp_base_gas_estimate_feasibility_v1_readonly.py` paths.
2. **R2b_aerodrome_voter_recovery** — recover the canonical Aerodrome Voter address (a single contract lookup against `0xAero` style source-code trace, or reading the latest AERO emissions whitepaper / governance forum) so that on-chain `gauges()` reads work. This is the *only* way to convert the `reward_data_unavailable=true` placeholder into real numbers and is the prerequisite for a true `GO_TINY_LIVE`.
3. **STOP** — accept the conclusion that on Base mainnet at retail sizes, fee-only LP does not amortise a single cycle of gas; redirect to a different venue (Uniswap V3 mainnet? a different chain?) or a different strategy (rewards farming, delta-neutral).

## Wall-clock budget

- 15m checkpoint: passed (data sources probed, 2/4 healthy).
- 45m checkpoint: passed (script built and ran; raw 202 pools).
- 90m checkpoint: passed (35 ranked, 3 GO, real capital matrix).
- Total wall-clock for scan: **16 seconds**.

No `GO_TINY_LIVE` execution was performed. No wallet, signer, or live env was touched.
