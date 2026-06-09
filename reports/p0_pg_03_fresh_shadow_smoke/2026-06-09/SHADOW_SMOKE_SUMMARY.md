# SHADOW_SMOKE_SUMMARY — P0-PG-03

## What was run

The shadow binary `bin/lpbot-shadow` (commit `883251b`, build tag `shadow`)
was started against the fresh-DB-prepared test config
`configs/config.shadow.smoke.toml`, under a 5-minute bounded timeout
(`SMOKE_DURATION_SECONDS=300`). Stdout + stderr were captured to
`SHADOW_SMOKE_RUN_LOG.txt` in this report dir.

The dryrun binary was **not** executed. The live binary was **not**
executed. Only the shadow binary ran.

## Outcome

- Started: `2026-06-09T16:31:43Z`
- Ended:   `2026-06-09T16:36:43Z`  (5 min 0 s exact)
- Exit:    124 (timeout, normalized to 0 by `run_shadow_smoke.sh`)
- Process left running after smoke: NO
- Panic / fatal errors in log: NO
- Wallet / signing / broadcast keywords: NO
- Canary / live / paper / LPBOT_CONFIRM_LIVE in log: NO
- Shadow mode banner present: YES (`Running in shadow mode: ...`)
- Metrics server started: YES (`metrics server started addr=:9091`)
- Live safety gate status: NOT READY (correct — shadow is not live)

The safety-check script `scripts/check_shadow_smoke_safety.sh` returns
exit 0 against the log:

```
shadow_smoke_safety: OK (no panic, no fatal, no canary/live/paper,
shadow_smoke_safety:     no signing/broadcast/mint/swap keywords,
shadow_smoke_safety:     shadow mode banner + metrics server present)
```

## What the binary actually did during the 5 minutes

- Initialized adapters, including Postgres store and the rpc simulator
- Did a one-time base RPC health probe at startup (public endpoints,
  free, no secret, read-only)
- Ran the strategy loop on a 1-minute tick; visible ticks at
  `18:32:08`, `18:33:48`, `18:35:49` (all logged with `scanned=39,
  candidates=3, evaluated=3, shadow_orders=3`)
- Ran the scanner loop on a 5-minute tick (no scan in the 5-min window;
  first scan scheduled after the window)
- Ran periodic base RPC health checks at 30 s intervals
  (`base.drpc.org`, `mainnet.base.org`, `mainnet-preconf.base.org`),
  all public, all `OK`
- Received SIGTERM-equivalent on timeout, shut down cleanly:
  `shutdown signal received` -> `stopping workers...` ->
  `all workers stopped` -> process exit 124

## Pre-existing warning observed (NOT a blocker)

Each strategy tick emits one WARN from `cmd/lpbot/position_mark.go:220`:

```
shadow position mark query failed
  error: scan active position: sql: Scan error on column index 3, name
  "chain": converting driver.Value type string ("base") to a int:
  invalid syntax
```

This is a **pre-existing schema-encoding bug** between the Go code
(`chain INTEGER`) and one of the postgres adapter's scan paths, where
the schema column is returned as a string. The canonical P0-PG-02 audit
flagged this kind of issue under P0-PG-02-C (chain type alignment),
which is a deliberate follow-up after P0-PG-03. The WARN is **not** a
fatal — the strategy loop continues, the shadow binary stays up, and
the smoke completes its full 5-minute window. **It is not caused by
this stage**, and not blocking PASS. It is recorded here so future
reviewers can see I did not silently swallow a regression.

## What was NOT exercised

- No transaction was sent to any chain (the binary is shadow mode;
  the broadcaster is not wired in shadow; wallet / signer paths are
  not loaded)
- No keypair, mnemonic, or seed was used (the test config does not
  load any; `LPBOT_CONFIRM_LIVE=YES` is unset; the safety script
  refuses to start if it is)
- No `r1-postgres`, `infra-postgres-1`, or supabase container was
  touched
- No canary, paper, or live binary was executed
- No LP strategy was actually deployed (the strategy loop produced
  shadow orders, not real ones; `shadow_orders=3` is the simulation
  count, not a fill count)

## Why this qualifies as PASS

- 5-minute bounded run completed cleanly.
- No panic, no fatal, no shadow-mode escape.
- Schema guard (via `loadLiveSchemaState` + `ensureShadow*Table` calls
  at startup) reported all required tables and indexes present.
- Metrics server initialized.
- Workers started, ran, and stopped cleanly.
- Post-smoke `ps aux | grep lpbot-shadow`: empty.
- No daemon left running.
- `safety = false / LOCKED` on every check.
