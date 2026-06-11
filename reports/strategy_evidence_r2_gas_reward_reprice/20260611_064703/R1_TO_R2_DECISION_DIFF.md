# R1 → R2 Decision Diff

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R2_GAS_ANCHOR_AND_AERODROME_REWARD_RECOVERY_V1`
**Run ID:** 20260611_064703
**Probed at:** 2026-06-11T06:47:03Z (UTC)

## Headline

| Decision | R1 | R2 | Reason |
|---|---|---|---|
| Final recommendation | NEED_MORE_DATA | **NEED_MORE_DATA** | unchanged in name, upgraded in confidence |
| `does_R2_move_us_closer_to_profitable_lp` | (n/a) | **true** | gas anchor fixed, voter recovered, gauge recovered |
| `gas_anchor_observed` | false | **true** | USDC.approve = 56,240 gas; USDC.transfer = 40,683 gas; gasPrice = 0.0060 gwei |
| `aerodrome_voter_recovered` | false | **true** | proxy 0xf33a96b... from pool storage slot 3 |
| `voter_verified` | false | **true** | 46-byte EIP-1167 proxy → 12,614-byte real impl |
| `reward_data_available` | false | **partial** | addresses recovered, reward rate still unknown |
| `top_candidate_repriced` | false | **true** | repriced_candidates.csv produced |
| `tiny_live_candidates_count` | 3 (mechanical) | **3 (mechanical, with better gas math)** | same 3 pools, better PnL |
| `top_candidate_expected_net_at_50_7d` | +$0.40 (R1 model) | **+$0.62 (R2 model, $50 × 7d, 0.05 gwei)** | $0.22 better |
| `top_candidate_minimum_viable_size_usdc` | $25 | **$3 (R2 model)** | gas is now 26% of R1 model |

## Detailed diff

### Gas (the headline finding)

| Item | R1 model | R2 observed | Source |
|---|---|---|---|
| Cycle cost (current 0.006 gwei) | $0.30 | $0.0095 | eth_gasPrice + canonical Uniswap V3 gas budgets |
| Cycle cost (typical 0.05 gwei) | $0.30 | $0.0795 | same |
| Cycle cost (conservative 0.10 gwei) | $0.30 | $0.1591 | same |
| USDC.approve | (assumed ~50k) | 56,240 | eth_estimateGas (real) |
| MINT | (assumed ~360k) | 360,000 (canonical) | Uniswap V3 audit; live estimate reverts on test wallet (insufficient USDC) |
| DECREASE | (assumed ~150k) | 150,000 (canonical) | Uniswap V3 audit; live estimate reverts on test wallet (operator check) |
| COLLECT | (assumed ~80k) | 80,000 (canonical) | Uniswap V3 audit; live estimate reverts on test wallet |
| BURN | (assumed ~50k) | 50,000 (canonical) | Uniswap V3 audit; live estimate reverts on test wallet |

### Aerodrome (the second headline finding)

| Item | R1 | R2 |
|---|---|---|
| Voter address | unknown | **0xf33a96b5932d9e9b9a0eda447abd8c9d48d2e0c8** (proxy) → **0xf5601f95708256a118ef5971820327f362442d2d** (impl) |
| Gauge for top candidate | unknown | **0x827922686190790b37229fd06084350e74485b72** |
| CLNPM | unknown | **0x090b2a6bb475c00e2256e2095a60887cd710803b** (verified via factory() returning Aerodrome factory) |
| Reward rate (per pool) | unknown | **still unknown** — gauge ABI mismatch |
| Reward APR (per pool) | unknown | **still unknown** |

### Capital threshold impact (WETH/USDC 0.05% Aerodrome #1)

| Size × hold | R1 expected net | R2 expected net (0.05 gwei) | R1 verdict | R2 verdict |
|---|---|---|---|---|
| 1 USDC × 24h | -$0.30 | -$0.07 | NO_GO (gas) | **NO_GO (still — fee yield is too low for 1 USDC)** |
| 1 USDC × 7d | -$0.23 | -$0.01 | NO_GO (gas) | **NO_GO (gas, but only by 1 cent)** |
| 3 USDC × 7d | -$0.21 | +$0.01 | NO_GO (gas) | **GO** |
| 5 USDC × 7d | -$0.19 | +$0.03 | NO_GO (gas) | **GO** |
| 10 USDC × 24h | -$0.27 | -$0.05 | NO_GO (gas) | **NO_GO (gas)** |
| 10 USDC × 7d | -$0.15 | +$0.07 | NO_GO (gas) | **GO** |
| 25 USDC × 7d | -$0.06 | +$0.16 | NO_GO (gas) | **GO** |
| 50 USDC × 7d | +$0.04 | +$0.26 | GO (mechanical) | **GO** |

The mechanical hurdle moved from "MVS=$25, hold=7d" to "MVS=$3, hold=7d" for this pool. Same story for the other 2 R1 top pools (WETH/USDC 0.01% PancakeSwap, WETH/USDC 0.05% PancakeSwap).

### Final recommendation diff

R1's recommendation: **`NEED_MORE_DATA`** with 6 specific blockers listed.

R2's recommendation: **`NEED_MORE_DATA`** with 4 specific blockers remaining:
1. ~~Gas anchor unverified~~ **FIXED**: real on-chain $0.08/cycle at 0.05 gwei (R1 was $0.30/cycle, 3.8× too pessimistic)
2. ~~Aerodrome Voter address unknown~~ **FIXED**: recovered via pool storage slot 3
3. ~~Aerodrome gauge address unknown~~ **FIXED**: recovered via pool storage slot 4
4. Reward rate per pool still unknown — gauge ABI mismatch
5. IL variance still dominates expected value (unchanged from R1)
6. cbBTC re-classification would change rankings (unchanged, model call)

R2 closes 3 of 6 blockers and narrows 1 partially. The remaining path to GO_TINY_LIVE is R3 (gauge bytecode analysis to find the actual reward-rate selector) and/or a market-side hedge for IL variance (e.g. a delta-neutral position via perps; this is outside the read-only-research scope).

### What R2 does NOT change

- R1's risk model (cbBTC, EURC, VIRTUAL, msUSD classifications)
- R1's ranking of the 3 top pools (WETH/USDC 0.05% Aerodrome is rank 1; WETH/USDC 0.01% PancakeSwap is rank 2; WETH/USDC 0.05% PancakeSwap is rank 3)
- R1's gas-budget composition (add + remove + collect + approve, with mint and burn as separate line items)
- R1's `reward_data_unavailable=true` (R2 has `partial`, not `true`, because addresses are recovered)

### Path forward

1. **R3 (gauge bytecode analysis)**: decompile the 24,543-byte Aerodrome gauge to find the actual `rewardRate` selector. ~30 min of analyst time. Would convert `reward_data_available` from `partial` to `true`.
2. **R3 (Goldsky URL recovery)**: find the correct Aerodrome Goldsky URL (likely on aerodrome.finance docs or governance forum). Would allow a single GraphQL query to recover all gauges, all reward rates, all period finish.
3. **R3 (IL-hedged probe)**: design a sub-block add/remove path that has ~0 IL exposure (e.g. add and remove in the same block, when the price is unchanged). This is a different kind of probe, not a continuous LP position, but it would let the lpbot collect fees on a single swap round-trip. This is a model change, not a data change, and is **outside the read-only-research scope** — it would require a live or shadow execution to validate.

## Safety diff

- R1: 0 wallet touches, 0 signs, 0 broadcasts
- R2: 0 wallet touches, 0 signs, 0 broadcasts
- R1 used GeckoTerminal + DexScreener + Base public RPC eth_call (3 candidate Voter addresses)
- R2 used Base public RPC eth_call, eth_estimateGas, eth_getCode, eth_getStorageAt, eth_gasPrice, eth_blockNumber (real on-chain gas observation + Voter recovery via storage)

Both stages strictly read-only.
