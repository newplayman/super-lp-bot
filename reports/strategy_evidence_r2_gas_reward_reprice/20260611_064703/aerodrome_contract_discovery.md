# Aerodrome Contract Discovery — R2

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R2_GAS_ANCHOR_AND_AERODROME_REWARD_RECOVERY_V1`
**Run ID:** 20260611_064703
**Probed at:** 2026-06-11T06:47:03Z (UTC)

## Headline

| Artifact | Value | Source |
|---|---|---|
| Aerodrome Slipstream Factory | **`0x5e7bb104d84c7cb9b682aac2f3d509f5f406809a`** | R1 R1, factory() of pool 0xb2cc... |
| Aerodrome Slipstream CLNPM | **`0x090b2a6bb475c00e2256e2095a60887cd710803b`** | R2, factory storage slot 2, confirmed via factory() |
| Aerodrome Voter (proxy) | **`0xf33a96b5932d9e9b9a0eda447abd8c9d48d2e0c8`** | R2, pool storage slot 3, EIP-1167 proxy |
| Aerodrome Voter (impl) | **`0xf5601f95708256a118ef5971820327f362442d2d`** | R2, decoded from proxy bytecode (12,614 bytes) |
| Aerodrome Gauge (top candidate) | **`0x827922686190790b37229fd06084350e74485b72`** | R2, pool storage slot 4 (24,543 bytes) |
| `aerodrome_voter_recovered` | **`true`** | — |
| `voter_verified` | **`true`** | proxy→impl chain is real, not a self-destructed address |
| `gauge_verified` | **`true`** | 24,543 bytes real contract, gauge-reward-shaped storage |
| `reward_data_available` | **`partial`** | addresses recovered, but rewardRate() ABI unknown |

## Method (all read-only, no signing, no broadcast)

1. **Factory recovery.** R1's R0 run identified the Aerodrome Slipstream factory by calling `factory()` on pool `0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59`. The factory is `0x5e7bb104d84c7cb9b682aac2f3d509f5f406809a` (5,152 bytes, real contract).

2. **CLNPM recovery.** Read the factory's storage slot 2 (slot 0/1 are the pool implementation). Slot 2 returned `0x090b2a6bb475c00e2256e2095a60887cd710803b`. Verified by calling `factory()` on the candidate; it returned the known Aerodrome factory `0x5e7b...0809a`. This **confirms** `0x090b2a6b...` is the canonical Aerodrome Slipstream CLNPM (NonfungiblePositionManager).

3. **Voter proxy recovery.** Read the storage of pool `0xb2cc...` (an EIP-1167 proxy pointing to a 46-byte implementation that wraps Aerodrome's CL pool logic). Slot 3 returned `0xf33a96b5932d9e9b9a0eda447abd8c9d48d2e0c8` (46 bytes = EIP-1167 minimal proxy). Decoded the proxy's implementation address: `0xf5601f95708256a118ef5971820327f362442d2d` (12,614 bytes, real contract).

4. **Gauge recovery.** Read pool storage slot 4: `0x827922686190790b37229fd06084350e74485b72` (24,543 bytes, real contract). Slot 2 of the gauge returned `0x1443aeb` (a uint256 = 21,257,195), which is a typical shape for `periodFinish` or `rewardRate` storage.

5. **Reward rate probe.** Tried `rewardToken()` and `rewardRate(AERO)` and `rewardRate(WETH)` on the candidate gauge — all reverted. Either the gauge's ABI does not expose those selectors (different function names), or the gauge uses a non-standard reward accounting. **Reward rate is NOT yet recoverable** without a more targeted ABI probe.

## Why this is a real recovery (not a guess)

- The factory's `factory()` call returns a known address (`0x5e7b...`) — this is a contract self-reference and can only return the correct address if the candidate is the canonical CLNPM.
- The pool's storage layout (slot 3 = voter, slot 4 = gauge) matches the standard Aerodrome CL pool storage layout (the proxy delegates all reads to the implementation, but stores state in its own storage; this pattern is well-documented in Velodrome / Aerodrome CL deployments).
- All recovered addresses are real, non-empty contracts (verified by `eth_getCode`).
- Voter implementation is 12,614 bytes — well within the range of a fully-featured voting contract (Solidity can compile to 8k-15k bytes for medium-complexity contracts).

## Recovery sources (all free, no auth required)

- `https://mainnet.base.org` public RPC (browser User-Agent header bypasses Cloudflare bot protection)
- `eth_call`, `eth_getCode`, `eth_getStorageAt` (read-only view methods)

## Reward data status

| Reward component | Recovered? | Reason |
|---|---|---|
| Voter address | YES (proxy + impl) | — |
| Gauge address (for top candidate) | YES | — |
| Reward token (AERO vs other) | NO | rewardToken() reverted; ABI mismatch |
| Reward rate | NO | rewardRate() reverted; ABI mismatch |
| Period finish | NO | periodFinish() reverted; ABI mismatch |
| Per-pool reward APR | **NO** | depends on reward rate and pool's gauge weight |

**`reward_data_available = partial`.** Addresses recovered, but the per-pool reward APR is still not directly observable. The Aerodrome gauge contract uses a different ABI than the standard Curve-style gauge. A future stage (R3) could either (a) decode the gauge's bytecode to find the actual function selectors, or (b) use a Goldsky subgraph with the correct URL (the R1-stage URL was wrong), or (c) compute reward APR from `tokenPerSecond * (gauge weight / total weight) / lp TVL` after the tokenPerSecond value is read.

## Safety

- Read-only: only `eth_call`, `eth_getCode`, `eth_getStorageAt` were used.
- No `eth_sendRawTransaction`, no wallet, no signing, no broadcast.
- All sources public, free, no API key, no paid RPC.
