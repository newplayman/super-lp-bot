# TINY_CANARY_EXECUTION_PLAN_DRAFT

> **DRAFT ONLY — NOT AUTHORIZED FOR EXECUTION.**
> This plan is a draft. It does NOT authorize any execution. A
> future stage named `LP_BOT_ENGINEERING_TINY_CANARY_PREFLIGHT_EXECUTE_V1`
> (or similar) is required to authorize execution, AND that
> stage must itself be explicitly authorized by the user in a
> separate prompt. This draft is the proposal that an execute
> stage would consume.

## Scope

A single 15-minute bounded wallclock run of `bin/lpbot-live`
under the tiny canary risk contract defined in
`RISK_LIMIT_CONTRACT.md`. Single action. Tiny capital (≤10
USDC). Operator-monitored.

## Proposed run

- Binary: `bin/lpbot-live` (built from current remote HEAD with
  `-tags=live`).
- Config: a tiny canary config file (NOT in VCS) with
  `Live.Enabled=true`, `Live.Canary=true`,
  `Live.MaxOrderUSD=1.0` (NOT 10.0 — single-action sized to
  USDC), `Live.AllowedChains=[base]`,
  `Live.AllowedPools=[<one operator-supplied pool id>]`,
  `Live.WalletAddress=<operator wallet>`,
  `LiveRisk.MaxTotalExposureUSD=10`,
  `LiveRisk.MaxPendingExposureUSD=2`,
  `LiveRisk.MaxSubmittedPrivateExposureUSD=0`,
  `LiveRisk.MinGasReserveWei=<small positive>`,
  `Execution.Backend=native-rpc`,
  `Execution.NPMBaseAddress=<npm base>`,
  `chains.base.rpc_primary=https://mainnet.base.org`,
  `Wallet.Backend=keystore`,
  `Wallet.KeystorePath=<path>`,
  `Wallet.Passphrase=<from env, NOT file>`.
- Env: `LPBOT_CONFIRM_LIVE=YES`,
  `BASE_RPC_PRIMARY=https://mainnet.base.org`,
  `QUICKNODE_API_KEY` unset, `WALLET_PASSPHRASE` from env.
- Timeout: `timeout --foreground 900 ./bin/lpbot-live
  --config=tiny_canary.toml`.
- Single action: `ApproveExact(USDC, <pool router>, 1_000_000)`,
  size 1 USDC.
- The action is **sign-only, no broadcast**. The runner constructs
  the unsigned tx, signs it, and records the signed tx hash in
  the report. No broadcast call is made.

## Why sign-only for v1

The user's directive distinguishes "tiny canary" from "canary" and
from "live". v1 should exercise the full build → sign path but
should NOT exercise the broadcast path. This gives the operator:

- Confidence that wallet / signer / RPC / chain-id / gas-estimate
  paths all work end-to-end against a real keystore.
- Zero on-chain state change. No revert risk. No MEV exposure.
  No LP exposure. No token-transfer.

A v2 (separate future stage) may add the broadcast path under the
same risk contract. v3 may add the LP add/remove path. Each
stage is gated by the previous one's success.

## Operator checklist (before v1)

The operator MUST confirm each of the following in writing in the
execute stage's prompt (not in this draft):

- [ ] Wallet address is an isolated test wallet, not a
  production wallet.
- [ ] Wallet USDC balance ≥ 1.5 USDC (1 USDC for the action +
  0.5 USDC for gas + safety margin).
- [ ] Pool id is verified to be a real Base mainnet pool with
  known router address.
- [ ] Keystore passphrase is supplied via env, not committed
  anywhere.
- [ ] `LPBOT_CONFIRM_LIVE=YES` is exported in the prompt.
- [ ] Operator is monitoring the run log in real time.
- [ ] Operator has a pre-staged manual rollback plan (separate
  from the binary's kill switch).
- [ ] Operator has read and accepted the
  `TINY_CANARY_ABORT_CONDITIONS.md` and the
  `KILL_SWITCH_AND_ROLLBACK_PLAN.md`.

## Report artifacts the execute stage MUST produce

- `SHADOW_SOAK_RUN_LOG.txt` (or analogous; here the live
  equivalent): full stdout + stderr.
- `TINY_CANARY_VERDICT.json` with the live safety gate's
  blocker list, the action's pre-check results, and the
  recorded signed tx hash.
- `TINY_CANARY_SAFETY_CHECK.txt`: output of the safety
  preflight script.
- `TINY_CANARY_ABORT_REPORT.txt` (if any abort happened): the
  blocker / abort reason, the timestamp, and any partial state.
- `TINY_CANARY_FINAL_BALANCE.txt`: pre-action and post-action
  USDC balance, with delta and reason.

## Why this stage does NOT authorize execution

- This stage is `LP_BOT_ENGINEERING_TINY_CANARY_PREFLIGHT_V1`,
  not `LP_BOT_ENGINEERING_TINY_CANARY_PREFLIGHT_EXECUTE_V1`.
- The `*_EXECUTE_V1` naming convention is deliberate: the
  execution is a separate stage.
- Even within `*_EXECUTE_V1`, the operator must re-confirm the
  checklist above.

## Next recommended stage

`LP_BOT_ENGINEERING_TINY_CANARY_PREFLIGHT_EXECUTE_V1` — only
after this preflight stage's safety check passes AND the user
explicitly authorizes the execute stage in a separate prompt.

Mode A → canary / live / paper remains EXPLICITLY forbidden
without that execute stage. The user may also choose to defer
the execute stage indefinitely.