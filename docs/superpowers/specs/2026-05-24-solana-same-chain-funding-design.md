# Solana Same-Chain Funding Planner Design

## Goal

Add a Solana-only funding planner that treats same-chain idle assets as usable LP capital, computes any required pre-swap path, and surfaces swap loss, gas, and slippage as mandatory readiness inputs.

## Constraints

- Funding valuation is strictly same-chain only.
- A Base opportunity must not count Ethereum mainnet assets.
- A Solana opportunity must not count Base assets.
- First implementation is scoped to the current Solana wallet asset set: `SOL` and `USDC`.
- No real swap execution is added in this step; this is read-only planning and readiness hardening.

## Design

- Add a new CLI entrypoint: `--solana-funding-plan`.
- Planner inputs:
  - wallet public key
  - target mint
  - target amount raw
  - slippage bps
  - max priority lamports
  - reserved SOL lamports for future gas
- Planner reads only Solana wallet balances and only values Solana assets.
- If the target mint balance is already enough, planner returns `ready_direct`.
- If the target mint balance is short, planner checks whether the other same-chain asset can fund the deficit via Jupiter quote search.
- Planner returns:
  - same-chain balances
  - same-chain estimated total value
  - direct balance sufficiency
  - required pre-swap direction and amount
  - expected output
  - threshold output
  - price impact
  - estimated swap loss USD
  - estimated gas USD
  - estimated max slippage USD
- `solana-swap-build-readiness` and `solana-swap-sign-readiness` must use this planner first.
  - If direct balance is enough, keep the current path.
  - If a pre-fund swap is required, print the funding plan and do not pretend the target swap is directly ready from current balances.

## Scope of This Step

- Implement the planner and readiness integration.
- Do not write ledger entries yet.
- Do not broadcast anything.
- Do not expand to non-SOL/non-USDC wallet assets yet.

## Next Step After This Change

- Reuse the same planner for Solana LP-specific two-asset funding plans.
- Then wire estimated funding costs into ledger and final LP PnL.
