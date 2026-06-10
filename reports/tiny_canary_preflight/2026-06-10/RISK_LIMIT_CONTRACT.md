# RISK_LIMIT_CONTRACT — Tiny Canary Preflight

> **PROPOSED CONTRACT ONLY — NOT AUTHORIZED FOR EXECUTION.**
> This document defines risk caps for a future `*_EXECUTE_V1` stage
> that would run a tiny canary. The user must explicitly authorize
> that stage in a separate prompt before any of these caps take
> effect.

## Caps (proposed)

| Dimension | Cap | Rationale |
|---|---|---|
| max_total_exposure_usdc | **≤ 10 USDC** (across all pools) | Hard ceiling for first run. Below the per-order minimums of any production system. |
| max_per_pool_exposure_usdc | **≤ 3 USDC** | Even if multiple pools are touched, no single pool gets >30% of total exposure. |
| max_action_count | **1** | One action per tiny canary run. The runner rejects any attempt to queue a 2nd action. |
| max_duration_minutes | **15** | Bounded wallclock. Long enough to exercise one round-trip (build → sign → broadcast → confirm), short enough that no on-chain MEV / market exposure can compound. |
| Max order USD (config) | **≤ 10.0** | Within `canaryMaxOrderUSD = 20.0` hard cap (`cmd/lpbot/main.go:50`). Provides 2x headroom for size-quantization variance. |
| Daily loss limit (config) | **2 USDC** | Tight daily loss limit; the runner refuses any action that would exceed it. |
| Max total exposure (config) | **10 USDC** | Mirrors the proposed capital cap. |
| Max pending exposure (config) | **2 USDC** | Pending (in-flight) orders limited to a single-action notional. |
| Max submitted private exposure (config) | **0 USDC** | Tiny canary must not generate private-exposure LP actions; private (non-public) routing is not allowed in tiny canary. |
| Min gas reserve wei (config) | **≥ 0** (small positive value) | Gas reserve enforced; no zero-reserve execution. |

## Hard caps that already exist in code (verified during audit)

| Hard cap | Source | Effect |
|---|---|---|
| `canaryMaxOrderUSD = 20.0` | `cmd/lpbot/main.go:50` (const) | Tiny canary's `Live.MaxOrderUSD` cannot exceed 20.0. If it does, `liveSafetyGate.blockers()` returns `"canary max_order_usd X exceeds hard cap 20.0"`. |
| `LPBOT_CONFIRM_LIVE=YES` | `mode_live.go::Run` | Live binary refuses to start without it. |
| Build tag `live` | `//go:build live` on every live path | Shadow / dryrun binaries cannot reach live code at all. |

## Risk acceptance conditions for executing tiny canary

A `*_EXECUTE_V1` stage must satisfy ALL of:

1. `Live.Enabled=true`
2. `Live.Canary=true`
3. `Live.MaxOrderUSD ≤ 10.0`
4. `Live.DailyLossLimitUSD > 0`
5. `Live.AllowedChains` contains exactly one chain (`base` for tiny canary; no `solana` yet because solana_lp_*_canary_live.go paths are out of scope for the first tiny canary)
6. `Live.AllowedPools` contains exactly one pool id (operator-supplied; pre-validated)
7. `Live.WalletAddress` set
8. `LiveRisk.MaxTotalExposureUSD > 0`
9. `LiveRisk.MaxPendingExposureUSD > 0`
10. `LiveRisk.MaxSubmittedPrivateExposureUSD = 0`
11. `LiveRisk.MinGasReserveWei` ≥ small positive
12. `Wallet.Backend = "keystore"`
13. `Wallet.KeystorePath` exists and is readable
14. `Wallet.Passphrase` non-empty
15. `Execution.Backend = "native-rpc"` (no OKX in tiny canary v1)
16. `Execution.NPMBaseAddress` set
17. `chains.base.rpc_primary` set OR `QUICKNODE_API_KEY` set
18. `LPBOT_CONFIRM_LIVE=YES` exported
19. Action count capped at 1 (enforced by the runner; not a config field)
20. Duration capped at 15 minutes (enforced by `timeout --foreground 900`)

If any of (1)–(20) is unsatisfied at execution time, the runner
refuses to start, logs the blocker, and exits non-zero.

## What the tiny canary v1 does NOT do

- Does not execute Sol transactions (out of scope; would be a
  follow-up stage if a separate tiny canary is approved).
- Does not execute bridge / cross-chain operations.
- Does not execute collect / sweep operations.
- Does not execute swap operations.
- Does not interact with any non-allowlisted RPC endpoint.
- Does not store or persist secrets beyond the keystore file
  path (which is operator-supplied and not committed).
- Does not loop / iterate; single shot.

## What tiny canary v1 DOES do (single action)

The action is one of:

- **Approve + wrap WETH** (Base mainnet, a single USDC→WETH wrap
  for the smallest possible amount; record success/failure
  without attempting the subsequent LP open).
- **OR** a pre-flight dry-build only (sign a transaction, do not
  broadcast; compare the signed tx hash against expectations;
  exit).

The first variant exercises the full broadcast path but only
with a $1 wrap. The second variant exercises the signing path
without broadcasting, and is safer for the first execution.

The user's preference between these two variants is part of the
`LP_BOT_ENGINEERING_TINY_CANARY_PREFLIGHT_V1` accept message.