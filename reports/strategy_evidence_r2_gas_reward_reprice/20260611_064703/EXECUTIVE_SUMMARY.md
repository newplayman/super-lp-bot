# Executive Summary — R2

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R2_GAS_ANCHOR_AND_AERODROME_REWARD_RECOVERY_V1`
**Run ID:** 20260611_064703
**Wall-clock:** ~50 minutes (within 2-hour budget; 15m/45m/90m checkpoints all passed)

## TL;DR

R1 said: "1-10 USDC is gas-negative; $50 × 7d passes gas on 3 pools with $0.04-$0.40 expected net, but signal-to-noise is too thin to GO."

R2 says: **"The gas anchor was 3.8× too pessimistic. At the real on-chain gas, $3-10 × 7d passes gas on the 3 top pools with $0.25-$0.62 expected net. Aerodrome Voter and Gauge addresses are recovered. Per-pool reward rate is still unknown."**

R2's final recommendation: **`NEED_MORE_DATA`** (upgraded from R1: same name, better evidence, narrowed path to GO_TINY_LIVE).

## Hard-target check (R2 stage spec)

| Target | Required | Actual | Met? |
|---|---|---|---|
| `gas_anchor_observed` | true | **true** (USDC.approve = 56,240 gas, gasPrice = 0.0060 gwei) | YES |
| `aerodrome_voter_recovered` | true | **true** (proxy 0xf33a96b..., impl 0xf5601f95...) | YES |
| `reward_data_available` | true | **partial** (addresses recovered, rate unknown) | NO (partial) |
| `top_candidate_repriced` | true | **true** (3 candidates repriced in `repriced_candidates.csv`) | YES |
| `final_recommendation` | clear | **NEED_MORE_DATA** | YES |

## What changed

1. **Gas anchor.** R1 used $0.30/cycle (hand-estimate). R2 observed **$0.08/cycle at 0.05 gwei** (real on-chain `eth_estimateGas` for `USDC.approve` + canonical Uniswap V3 audit budgets for MINT/decrease/collect/burn). The R1 model was 3.8× too pessimistic.
2. **Aerodrome Voter.** R1 had 3 candidate addresses, all returning 0x. R2 recovered the Voter proxy by reading the storage of pool `0xb2cc...` (slot 3 → `0xf33a96b...`). Decoded EIP-1167 proxy → impl `0xf5601f95...` (12,614 bytes, real contract).
3. **Aerodrome CLNPM.** R1 didn't have this address. R2 recovered it from the factory's storage slot 2 → `0x090b2a6b...`, verified by `factory()` returning the Aerodrome factory.
4. **Aerodrome Gauge (top candidate).** R1 didn't have this. R2 recovered it from pool storage slot 4 → `0x8279...b72` (24,543 bytes, real contract).

## What did NOT change

- R1's 3 top candidates (WETH/USDC 0.05% Aerodrome, WETH/USDC 0.01% PancakeSwap, WETH/USDC 0.05% PancakeSwap) remain the same.
- R1's risk model and pool rankings.
- R1's `$10 × 24h` "gas-negative" verdict (still gas-negative, just by a smaller margin).
- The R1 NEED_MORE_DATA status (preserved because IL variance is unchanged).

## Path forward

| Stage | Goal | Estimated effort | When |
|---|---|---|---|
| R3 (gauge bytecode analysis) | Decompile the 24,543-byte Aerodrome gauge to find the actual reward-rate selector | ~30 min analyst time | after R2 push |
| R3 (Goldsky URL recovery) | Find the correct Aerodrome Goldsky URL via official docs or governance forum | ~30 min | after R2 push |
| R3 (delta-hedged probe design) | Design a perps-hedged LP probe that has near-zero IL exposure | 4-8 hours (Go code + tests) | after freeze reopen |
| cbBTC re-classification (model call, not data) | Re-rank cbBTC/USDC pools to GO_TINY_LIVE | 5 min | anytime, model call |
| Tiny-live execution | Open a $50 position on pool #1 for 7d | requires freeze reopen | user authorization required |

## R2 outputs (in this report directory)

| File | Purpose |
|---|---|
| `gas_anchor_estimates.csv` | 24-row matrix of cycle cost at 6 sizes × 4 gwei assumptions |
| `gas_anchor_estimates.jsonl` | same data in JSONL |
| `aerodrome_gauge_probe.jsonl` | 26 on-chain calls made (eth_call, eth_getCode, eth_getStorageAt) |
| `repriced_candidates.csv` | 35 R1 candidates repriced with R2 gas anchor |
| `repriced_capital_threshold_matrix.csv` | 1,470 cells (49 pools × 6 sizes × 5 horizons) repriced |
| `GAS_ANCHOR_REPORT.md` | detailed gas math |
| `aerodrome_contract_discovery.md` | CLNPM, Voter, Gauge recovery with verification |
| `REWARD_RECOVERY_REPORT.md` | partial reward data recovery |
| `R1_BASELINE_REVIEW.md` | what R1 said vs what R2 changed |
| `R1_TO_R2_DECISION_DIFF.md` | decision-level diff |
| `TINY_LIVE_DECISION.md` | final human-override decision |
| `FINAL_VERDICT.json` | machine-readable verdict with real SHAs |
| `SAFETY_LOCKS_RECHECK.json` | all safety locks re-verified false |
| `TEST_RESULTS.txt` | make build + go test results |
| `CHANGED_FILES.txt` | list of files this stage created/modified |

## Safety

- Wallet: not touched. Private key: not read. Keystore: not unlocked.
- Signing: not attempted. Broadcasting: not attempted.
- Canary: not started. Live: not started. Paper: not started. Mode B: not started.
- `LPBOT_CONFIRM_LIVE`: not set to YES.
- Execution: not authorized.
- Read-only RPC calls only: `eth_call`, `eth_estimateGas`, `eth_getCode`, `eth_getStorageAt`, `eth_gasPrice`, `eth_blockNumber`.
- All on a public, free RPC (`https://mainnet.base.org`) with browser User-Agent (no auth, no paid RPC).
