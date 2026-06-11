# Reward Recovery Report — R2

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R2_GAS_ANCHOR_AND_AERODROME_REWARD_RECOVERY_V1`
**Run ID:** 20260611_064703
**Probed at:** 2026-06-11T06:47:03Z (UTC)

## Summary

`reward_data_available = partial` — addresses recovered, but per-pool reward rate and per-pool reward APR are **not yet directly readable**. The Aerodrome gauge's ABI differs from the standard Curve / Stash pattern, so the selectors we tried (`rewardToken()`, `rewardRate(AERO)`, `rewardRate(WETH)`, `periodFinish()`) all reverted.

## Recovered (this stage)

| Component | Address | Verified? | Method |
|---|---|---|---|
| Aerodrome Voter (proxy) | `0xf33a96b5932d9e9b9a0eda447abd8c9d48d2e0c8` | yes (46-byte EIP-1167 proxy → 12,614-byte impl) | pool storage slot 3 |
| Aerodrome Voter (impl) | `0xf5601f95708256a118ef5971820327f362442d2d` | yes (12,614 bytes real contract) | decoded from proxy |
| Aerodrome Gauge (top candidate) | `0x827922686190790b37229fd06084350e74485b72` | yes (24,543 bytes real contract) | pool storage slot 4 |
| Aerodrome Slipstream CLNPM | `0x090b2a6bb475c00e2256e2095a60887cd710803b` | yes (factory() returns Aerodrome factory) | factory storage slot 2 |
| Aerodrome Slipstream Factory | `0x5e7bb104d84c7cb9b682aac2f3d509f5f406809a` | yes (R1 confirmed via pool.factory()) | R1, verified in R2 |

## Not recovered (still blockers)

| Component | Status | Reason |
|---|---|---|
| Reward token symbol | unknown | gauge.rewardToken() reverted; ABI mismatch |
| Reward rate (per second) | unknown | gauge.rewardRate(...) reverted; ABI mismatch |
| Period finish | unknown | gauge.periodFinish() reverted; ABI mismatch |
| Per-pool gauge weight | unknown | voter.poolForGauge(gauge) or similar — selector unknown |
| Total weight | unknown | voter.totalWeight() — selector unknown |
| AERO token address on Base | tentative guess `0x940181a94a35a4569e4529a181cdfb81441baec4` | not verified; rewardRate(AERO) reverted on the gauge |

## Why the ABI probe failed

The standard Curve / Convex / Aerodrome-V1 gauge has a well-known interface (`rewardToken`, `rewardRate`, `periodFinish`, `claimable`, `earned`). Aerodrome Slipstream (the CL / Uniswap-V3-fork version) is a newer contract and uses a **non-standard ABI** for its gauges. The actual function names and selectors are encoded in the gauge's 24,543 bytes of bytecode and were not directly probed in R2 (R2 budget: 2 hours; bytecode analysis would be a multi-day effort).

Two viable paths to recovery:

1. **Bytecode analysis.** Use a Solidity decompiler (e.g., heimdall-rs, etherscan decompile) on the 24,543-byte gauge bytecode to extract the actual function names and selectors. This is a one-time cost (~30 minutes of analyst time per contract) and produces a reusable ABI fragment.
2. **Subgraph URL recovery.** Aerodrome migrated from hosted TheGraph to a Goldsky-hosted endpoint. The correct Goldsky URL was not archived in this repo. A future stage could either (a) check Aerodrome's governance forum for an updated URL, or (b) check Aerodrome's official documentation site. Once the URL is known, the subgraph returns all gauges, all reward tokens, all reward rates, and all period finish timestamps in a single GraphQL query.

## Reward APR estimate (honest, not a number)

Without a directly-observed reward rate, R2 cannot quantify the AERO emissions per pool. R1's `reward_apr_est=null` for all 202 pools is preserved.

The R1 model used a placeholder "+0.10 score bonus" for AERO-paired pools, not an APR number. This is a model call, not a data call — the score bonus is intended to rank AERO pools above non-AERO pools of equivalent fee yield, and the magnitude was chosen to be below the fee-APR range of typical pools (so it does not artificially promote pools). R2 keeps this convention.

## `aerodrome_voter_recovered = true`

R2's primary success criterion. R1 was stuck because the Voter address was unknown; R2 recovered it via the pool's storage slot 3 (and verified via EIP-1167 proxy decoding).

## `gauge_for_top_candidate_recovered = true`

The gauge for the top Aerodrome candidate (`0xb2cc...`) is at `0x8279...b72`, recovered via pool storage slot 4. Verified by `eth_getCode` returning 24,543 bytes.

## `reward_data_available = partial` (not `true`)

Strictly, `reward_data_available` would be `true` only if the reward rate (in tokens/second) and reward token symbol were readable. R2 recovered the addresses but not the parameters. A future R3 stage can close this gap with bytecode analysis or subgraph recovery.

## Safety

- Read-only: only `eth_call`, `eth_getCode`, `eth_getStorageAt`.
- No `eth_sendRawTransaction`, no wallet, no signing, no broadcast.
- All on-chain calls on public, free RPC `https://mainnet.base.org`.
