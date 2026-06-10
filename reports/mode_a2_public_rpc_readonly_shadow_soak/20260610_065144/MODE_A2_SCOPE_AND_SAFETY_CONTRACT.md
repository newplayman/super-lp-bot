# MODE_A2_SCOPE_AND_SAFETY_CONTRACT — P0-PG-06 Mode A2

## Scope

A bounded 30-minute shadow soak that exercises the **canonical
public RPC read-only path**. The smoke gate (P0-PG-04) bypassed
chain traffic entirely with `LPBOT_SMOKE_NO_RPC=1`. This soak
turns that bypass OFF so we observe the binary's real RPC code
paths: round-robin endpoint selection, periodic health probes,
failover, and the strategy loop's chain-read-driven evaluation.

## What this soak is

- A 30-minute bounded run of `bin/lpbot-shadow` against a fresh
  test DB.
- Shadow mode (`BuildMode == "shadow"`) only. The binary's
  broadcaster is not wired in shadow; the wallet adapter is not
  initialized; no position is ever opened.
- Public RPC read-only. The binary reads from the free public
  Base endpoints (`mainnet.base.org`, `mainnet-preconf.base.org`,
  `base.drpc.org`) and (after its first round-robin health probe)
  picks the fastest one. It does **not** write, sign, or send
  any transaction on these endpoints.

## What this soak is NOT

- **NOT** canary. No broadcaster wired.
- **NOT** live. No wallet adapter initialized. LPBOT_CONFIRM_LIVE
  not set.
- **NOT** paper trading / Mode B. No order-replay engine.
- **NOT** a probe (LP research). No candidate scoring against
  observed data.
- **NOT** a long-horizon collector run.

## Safety contract

| Constraint | How it is enforced |
|---|---|
| No wallet connection | `cmd/lpbot/mode_shadow.go` does not import the wallet adapter; shadow mode bypasses `initWallet`. Verified at startup by the `wallet adapter not initialized` log line (or by absence of `wallet adapter initialized`). |
| No signing | The signing code path is in `internal/adapters/wallet/keystore` and `internal/adapters/wallet/kms`. Neither is reachable from shadow mode. |
| No broadcast | `cmd/lpbot/mode_shadow.go:18` literally says "simulating transactions without real execution"; the broadcaster is not wired. |
| No canary / live | `BuildMode == "shadow"`; `liveSafetyGate.isExecutionMode()` returns false; `live.enabled` defaults to false. |
| No paper | Mode B is a separate code path (`mode_b`) that this binary does not enter. |
| No paid RPC | `BaseEndpoints` and `BasePublicEndpoints` are hardcoded free public endpoints (`rpc/roundrobin.go:45..55`). QuickNode discovery is gated on `rpc.ResolveQuickNodeAPIKey() != ""`; the soak unsets `QUICKNODE_API_KEY`. |
| No private RPC | The config template's `rpc_primary` is `https://mainnet.base.org` (free, public). `rpc_fallback` is `[]`. |
| No R1 / R2 reopen | R1 remains paused; R2 remains LOCKED. The binary does not touch R1 / R2 state. |
| `LPBOT_CONFIRM_LIVE` unset | The soak unsets it; `run_shadow_smoke.sh` already refuses to start if set (this soak does not use that script). |
| Logs captured | Full stdout+stderr to `SHADOW_SOAK_RUN_LOG.txt`. |

## Exit criteria

- `exit_code == 124` AND duration ≈ 1800 s — planned timeout; PASS.
- `exit_code == 0` — binary exited early; check log for cause; WARN or FAIL depending on cause.
- `exit_code != 0` AND `exit_code != 124` — abnormal exit; FAIL.
- `panic:` in log — FAIL.
- Any wallet / signing / broadcast keyword in log — FAIL.
- `smoke_no_rpc_mode=true` in log — FAIL (Mode A2 must use canonical RPC).
- `schema_guard=fail` in log — FAIL.

## What the safety check script enforces

`scripts/check_shadow_public_rpc_soak_safety.sh` runs after the
soak completes. It greps the log for:

- Forbidden: `panic:`, `^FATAL`, `fatal error`, `sendTransaction`,
  `LPBOT_CONFIRM_LIVE`, `LPBOT_CANARY`, `LPBOT_LIVE`, `CANARY_DSN`,
  `LIVE_DSN`, `QUICKNODE_API_KEY`, action verbs (mint,
  addLiquidity, removeLiquidity, approve, swap, bridge),
  wallet / signing / broadcaster keywords, `PRIVATE_KEY`,
  `MNEMONIC`, `SEED`.
- Required: `Running in shadow mode`, `metrics server started`,
  `schema_guard=ok`, `Base RPC provider initialized`, ≥1
  `health check summary` line.
- Negative: `smoke_no_rpc_mode=true` MUST NOT be present.
- It also emits panic_count / fatal_count / wallet_keyword_count /
  signing_keyword_count / broadcast_keyword_count /
  lp_action_keyword_count / rpc_health_lines for the FINAL_VERDICT.

## After this soak

The success of this soak is the gate to considering a Mode A1
(extended bounded shadow soak) or Mode A3 (dryrun replay) for
follow-up stages. It does NOT gate Mode A → canary or live; that
remains a separate decision the user must explicitly authorize in
a future stage that names the action.