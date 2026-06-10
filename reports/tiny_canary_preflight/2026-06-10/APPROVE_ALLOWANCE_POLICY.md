# APPROVE_ALLOWANCE_POLICY — Tiny Canary Preflight

> **PROPOSED — NOT AUTHORIZED FOR EXECUTION.**

## Goal

Define the exact approve-allowance policy for tiny canary v1,
with explicit rejection of `ApproveMax` (unlimited) and explicit
maximum per-allowance caps. The policy is enforced by the runner,
not just by the binary.

## Hard policy

### No unlimited approve

- The binary's wallet adapter exposes `ApproveExact(token,
  spender, amount)`. It does NOT expose `ApproveMax` (unlimited
  approve) in the live execution paths. Verified at audit time:
  `cmd/lpbot/live_execution_live.go` and
  `cmd/lpbot/canary_prepare.go` both call `wallet.ApproveExact`
  with explicit amounts, never `ApproveMax`.
- **Invariant #1**: the tiny canary runner MUST NOT use any approve
  call that does not have an explicit finite amount. The runner
  checks this against the canonical wallet adapter signature.
- **Invariant #2**: the tiny canary plan MUST declare the exact
  approve amount per action in advance, before the action runs.

### Per-action cap

- The approve amount must be ≤ `live.max_order_usd` (config).
- For tiny canary v1: `live.max_order_usd ≤ 10.0`.
- Therefore: **per-action approve ≤ 10 USDC**.

### Per-pool cap

- The approve is for a single spender (the pool's
  NonfungiblePositionManager or UniversalRouter). The allowlist
  of spenders is the pool id's contract address, which must be in
  `Live.AllowedPools`.
- **Invariant #3**: the approve spender must be in
  `Live.AllowedPools`. Approves for any other address are
  rejected.

### Per-token cap

- Only USDC and WETH (Base mainnet canonical LP tokens) are in
  scope for tiny canary v1.
- **Invariant #4**: the approve token must be USDC or WETH on
  Base mainnet (canonical addresses:
  `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` for USDC,
  `0x4200000000000000000000000000000000000006` for WETH).
  Approves for any other token are rejected.

### Reset policy

- After the single action completes (success OR failure), the
  runner does NOT explicitly reset the allowance to 0. The
  remaining allowance is at most `max_order_usd ≤ 10.0` USDC,
  which is the per-action cap. A subsequent run would need to
  consume the allowance before issuing a new approve; this is
  acceptable because tiny canary v1 caps at 1 action.
- A follow-up tiny canary (v2) that wants to perform multiple
  actions MUST explicitly reset the allowance between actions.
  That is a future-stage concern, not part of v1.

### Detection of `ApproveMax` at audit time

- `grep -R 'ApproveMax' cmd internal` returns no matches in
  `cmd/lpbot/live_execution_live.go` or `cmd/lpbot/canary_prepare.go`.
- `internal/adapters/wallet/keystore` exposes only `ApproveExact`.
- The tiny canary preflight safety check
  (`scripts/check_tiny_canary_preflight_safety.sh`) greps the
  plan + report for the string `ApproveMax` and fails closed on
  any occurrence.

## Per-action example (tiny canary v1)

Plan action:

- Pool: a single canonical Base aerodrome / slipstream pool,
  pre-validated and added to `Live.AllowedPools`.
- Action: `ApproveExact(USDC, <pool's UniversalRouter address>,
  1_000_000` (1 USDC, 6 decimals = 1_000_000 raw).
- After approve, the runner may attempt a `mint` or `addLiquidity`
  if the user-approved variant is the full-build variant. v1
  defaults to **sign-only, no broadcast** for the LP action; the
  approve itself is also sign-only, no broadcast, until the user
  explicitly upgrades the plan.

## Why "no unlimited approve" is non-negotiable

- Unlimited ERC20 approves are a known supply-chain risk: if a
  pool contract is later compromised, the attacker can drain up
  to the full allowance.
- Tiny canary v1 uses 1 USDC for its single action. There is no
  operational reason to approve more than that.
- The hard invariant (#1) is enforced by:
  - Wallet adapter (only `ApproveExact` available).
  - Live safety gate (`approve amount > max_order_usd → blocker`).
  - Runner (per-action pre-check).
  - Preflight safety check script (static grep over plan).

## Detection of approve in `cmd/lpbot/` audit

`grep -R 'ApproveExact\|ApproveMax' cmd/lpbot/` returns:

```
cmd/lpbot/canary_prepare.go:174:	tx, err := wallet.ApproveExact(ctx, token, spender, amount)
```

Only `ApproveExact`. No `ApproveMax` call anywhere in the
live-tagged code. This is the canonical invariant; the preflight
safety check enforces it.