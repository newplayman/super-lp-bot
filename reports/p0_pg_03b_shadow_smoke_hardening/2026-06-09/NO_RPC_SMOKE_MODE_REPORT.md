# NO_RPC_SMOKE_MODE_REPORT — P0-PG-03B

## What was added

P0-PG-03 left an open issue: the shadow binary always appended
`rpc.BaseEndpoints` and `rpc.BasePublicEndpoints` to its endpoint list,
which meant even with empty `chains.base.rpc_primary` and
`rpc_fallback` the binary still made public-RPC health probes during
the smoke. P0-PG-03B adds an explicit, opt-in no-RPC smoke mode that
**fully suppresses** chain adapter initialization for the shadow
binary, gated by an env var and the build tag.

## Mechanism

The `cmd/lpbot/main.go` change is small and gated:

```go
noRPCSmokeMode := BuildMode == "shadow" && isSmokeNoRPCEnabled()

if noRPCSmokeMode {
    app.logger.Info("smoke_no_rpc_mode=true; base_rpc_initialization=skipped")
    // baseEndpoints stays empty
} else {
    baseEndpoints = append([]string{}, app.config.Chains.Base.RPCPrimary)
    baseEndpoints = append(baseEndpoints, app.config.Chains.Base.RPCFallback...)
    baseEndpoints = append(baseEndpoints, rpc.BasePublicEndpoints...)
    baseEndpoints = append(baseEndpoints, rpc.BaseEndpoints...)
}
```

The same gate is repeated for Solana. Both branches log a structured
line so the safety check can grep for them.

```go
func isSmokeNoRPCEnabled() bool {
    v := strings.ToLower(strings.TrimSpace(os.Getenv("LPBOT_SMOKE_NO_RPC")))
    return v == "1" || v == "true"
}
```

## Gate conditions

The mode is enabled **only** when:

1. `BuildMode == "shadow"` (set by `cmd/lpbot/mode_shadow.go` via
   `//go:build shadow`).
2. `LPBOT_SMOKE_NO_RPC` env var equals `1` or `true` (case-insensitive).

Both must hold. Any other combination (live mode, dryrun mode, missing
env var, value of `0`, value of `false`, value of `yes`, etc.) leaves
the canonical behavior in place. This means:

- **Live** binary: never affected (BuildMode != shadow).
- **Canary** (which runs the shadow binary in canary mode): never
  affected by accident — operators who want canary must NOT set
  `LPBOT_SMOKE_NO_RPC=1`.
- **Plain shadow** (without the env var): unaffected.
- **Smoke**: explicitly opt-in via the env var.

## Smoke runner wiring

`scripts/run_shadow_smoke.sh` now defaults `LPBOT_SMOKE_NO_RPC` to `1`
and exports it into the binary's environment:

```bash
export LPBOT_SMOKE_NO_RPC="${LPBOT_SMOKE_NO_RPC:-1}"
...
timeout --foreground "${DURATION_SECONDS}" \
  env LPBOT_SMOKE_NO_RPC="${LPBOT_SMOKE_NO_RPC}" \
  "${BIN}" --config="${CONFIG}" 2>&1 | tee -a "${LOG_FILE}"
```

Operators who want to disable no-RPC mode for a specific smoke run can
override the env var:

```
LPBOT_SMOKE_NO_RPC=0 scripts/run_shadow_smoke.sh ...
```

The smoke safety check still requires `smoke_no_rpc_mode=true` and
`base_rpc_initialization=skipped` to be present in the log, so a
disable override without updating the safety check will FAIL.

## Empirical evidence (5-minute hardened smoke)

The 5-minute bounded smoke captured `reports/p0_pg_03b_shadow_smoke_hardening/2026-06-09/SHADOW_SMOKE_RUN_LOG.txt`
(9939 bytes). Observed log evidence:

```
smoke_no_rpc_mode=true; base_rpc_initialization=skipped       (main.go:671)
smoke_no_rpc_mode=true; solana_rpc_initialization=skipped     (main.go:718)
schema_guard=ok backend=postgres checked_relations=9          (main.go:896)
```

**Zero chain endpoint references** in the log. Specifically:

```
$ grep -E "mainnet\.base|base\.drpc|mainnet-preconf|api\.mainnet\.solana" \
    reports/p0_pg_03b_shadow_smoke_hardening/2026-06-09/SHADOW_SMOKE_RUN_LOG.txt
(empty)
$ grep -E "QuickNode|QUICKNODE" \
    reports/p0_pg_03b_shadow_smoke_hardening/2026-06-09/SHADOW_SMOKE_RUN_LOG.txt
(empty)
```

The strategy loop tried to evaluate candidate pools and failed closed
with `reason: "no rpc provider configured for chain base"`. This is
the expected, correct behavior for a no-RPC shadow binary — the
strategy is purely an in-process simulation; it does not and cannot
read chain state.

## What was NOT changed

- The `rpc.RoundRobinProvider` itself (no behavior change for live
  builds; the smoke path bypasses the constructor entirely when
  no-RPC mode is on).
- The hardcoded `rpc.BaseEndpoints` / `rpc.BasePublicEndpoints`
  constants (still present, but unused in shadow + no-RPC mode).
- The `ensureLiveSchema` function (still gated to execution modes;
  the shadow guard is a separate `runShadowSchemaGuard` function
  that uses the same `loadLiveSchemaState` + `validateLiveSchemaState`
  helpers).
- The dryrun / live binary behavior (no-RPC gate is shadow-only).

## Safety impact

- **wallet_or_tx_touched**: unchanged from P0-PG-03.
- **signing_attempted**: unchanged.
- **broadcast_attempted**: unchanged.
- **canary_started / live_started / paper_started**: unchanged.
- **public_rpc_fallback_skipped_in_smoke**: NEW positive assertion,
  enforced by `check_shadow_smoke_safety.sh`.
- **smoke_no_rpc_mode_added**: NEW positive assertion.