# Solana PancakeSwap CLMM LP exit lessons

Date: 2026-05-25

## Incident

A 10 USD SOL/USDC PancakeSwap V3 Solana LP position could be removed from the PancakeSwap UI up to wallet signing, but the bot close preflight blocked on invalid reward accounts and then close-position simulation failure.

Position NFT:

`2GrEPwBXCtyL9K5RHWehUd1ScYYhvZ7v9vTMmpozNSw4`

Pool:

`DJNtGuBGEQiUCWE8F981M2C3ZghZt2XLD8f2sQdZ6rsZ`

## Root cause

The bot copied an incompatible Pancake/Raydium CLMM interpretation:

- Pool `rewardInfos` start offset was wrong: `392`.
- Pancake frontend SDK layout shows `rewardInfos` starts after `status` plus 7 bytes padding, offset `397`.
- The wrong offset decoded fake reward mint/vault addresses, causing `InvalidRewardInputAccountNumber` style failures.
- The close-position discriminator was also wrong for Pancake Solana CLMM.

Correct constants now fixed in code:

- `rewardInfosOffset = 397`
- `pancakeClosePositionDiscriminator = [123, 134, 81, 0, 49, 68, 98, 98]`
- `pancakeDecreaseLiquidityV2Discriminator = [58, 127, 188, 62, 79, 82, 196, 96]`

## Permanent rule

For PancakeSwap V3 Solana CLMM:

- Do not reuse Raydium pool layout offsets without checking Pancake frontend SDK or actual account bytes.
- If Pancake UI can construct a wallet transaction but bot cannot build/simulate, treat bot instruction/account layout as suspect before labeling the pool toxic.
- For full exit, use ordered steps:
  - `decrease_liquidity`
  - wait for confirmation
  - rebuild/read state
  - `close_position`
- If `liquidity_raw == 0`, skip duplicate decrease and close the position NFT directly.

## Confirmed live transactions

Decrease liquidity:

`V7AZSLNo74aQ6xhYQzV5FHBRhdiANtmrAbuZNvJJZwFvjV6SYRjbnYYZ7eYbbYokBczAjfAg96pfk25oXpuvCmW`

Close position:

`3oDTMenzAmRc2ZRpJ3hm4iWvRcaWoFbJXXAkHMbcqi2vLdkDSD9swfC5dnNwezERjH46saVNDqrFSFw4g1iHaAa2`

## Regression coverage

Regression tests added:

- `TestPancakeSolanaPoolRewardInfoLayoutMatchesFrontendSDK`
- `TestPancakeSolanaClosePositionDiscriminatorMatchesFrontendSDK`

Test file:

`cmd/lpbot/solana_pancake_layout_test.go`

## PnL audit status after this incident

The bot currently has enough audit trail to prove execution path:

- open transaction hash
- decrease transaction hash
- close transaction hash
- DB position status transition to `closed`
- canary event log for signed/broadcast/complete stages
- wallet same-chain balance snapshot after close

It is not yet sufficient for final accurate Solana realized PnL attribution because exit token deltas, per-leg fees, priority fees, rent returned, and realized IL are not yet persisted as a normalized close ledger.

Required next improvement:

- parse confirmed Solana transaction meta for pre/post token balances and SOL lamport delta
- persist realized exit amounts and network cost
- compute realized PnL from open token amounts, exit token amounts, funding swaps, rent/gas/priority fees, and price marks
- write one immutable audit row per LP lifecycle
