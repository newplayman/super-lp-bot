# SHADOW_SOAK_SUMMARY — Mode A2

## What was run

The shadow binary `bin/lpbot-shadow` (commit `856ea6e`, build tag
`shadow`) was started against the Mode A2 test config
`configs/config.shadow.a2-public-rpc.toml` (materialized from the
example template at runtime; the live copy is NOT in VCS), under a
30-minute bounded timeout (`timeout --foreground 1800`).

`LPBOT_SMOKE_NO_RPC`, `LPBOT_CONFIRM_LIVE`, `LPBOT_CANARY`,
`LPBOT_LIVE`, `CANARY_DSN`, `LIVE_DSN`, `QUICKNODE_API_KEY`,
`BASE_RPC_PRIMARY`, `SOL_RPC_PRIMARY`, `WALLET_KEYSTORE_PATH`,
`WALLET_PASSPHRASE` were all explicitly unset before the run.

Stdout+stderr captured to `SHADOW_SOAK_RUN_LOG.txt` (33234 bytes).

## Outcome

- Started: 2026-06-10T07:35:49Z (binary first log line)
- Ended:   2026-06-10T08:06:29Z (binary last log line)
- Duration: 1832 s (≈30.5 min; planned timeout = 1800 s, planned end normalized to 0)
- Exit:    124 (timeout, normalized to 0)
- Process left running after soak: NO (`ps aux | grep lpbot-shadow` empty)
- Panic / fatal errors in log: 0
- Wallet / signing / broadcast keywords: 0
- Canary / live / paper keywords: 0
- LP action keywords (mint / addLiquidity / removeLiquidity / approve / swap / bridge): 0
- Smoke-no-rpc mode in log: 0 (canonical RPC path confirmed)

The safety check `scripts/check_shadow_public_rpc_soak_safety.sh`
returns exit 0:

```
shadow_soak_safety: forbidden_pattern_violations=0
shadow_soak_safety: rpc_health_lines=60
shadow_soak_safety: panic_count=0
shadow_soak_safety: fatal_count=0
shadow_soak_safety: lp_action_keyword_count=0
shadow_soak_safety: OK
```

## What the binary actually did during the 30 minutes

- Initialized adapters, including:
  - Base RPC provider with 4 endpoints (1 configured `rpc_primary`
    + 3 hardcoded public).
  - Postgres store (no Redis — `redis.url` empty, binary logs
    `Redis runtime disabled`).
  - Metrics server on `:9092` (distinct from the smoke `:9091`).
  - Schema guard: `schema_guard=ok backend=postgres
    checked_relations=9`.
- Did a one-time base RPC health probe at startup (3 public
  endpoints, all `OK`, latency 1.2–1.5 s each).
- Selected `base.drpc.org` as primary after the initial probe.
- Ran the strategy loop on a 1-minute tick (29 ticks visible in
  the log; expected ~30 over 30 min — the missing tick is
  startup vs steady-state boundary).
- Ran the scanner loop on a 5-minute tick (started at boot,
  stopped cleanly on SIGTERM).
- Ran periodic base RPC health checks at 30 s intervals (60
  total: 1 initial + 59 periodic), all on the 3 allowlisted
  endpoints, all `OK`, latency 30–200 ms typical.
- One primary-rotation event at startup (`mainnet.base.org -> base.drpc.org`).
  No other rotations during the soak.
- Received SIGTERM-equivalent on timeout, shut down cleanly:
  `shutdown signal received` → `stopping workers...` →
  `strategy loop stopped` → `scanner loop stopped` →
  `all workers stopped` → process exit 124.

## Pre-existing warning observed (NOT a blocker)

Each strategy tick emits one WARN from `cmd/lpbot/position_mark.go:220`:

```
shadow position mark query failed
  error: scan active position: sql: Scan error on column index 3,
  name "chain": converting driver.Value type string ("base") to a
  int: invalid syntax
```

This is the same pre-existing chain-type mismatch tracked under
audit P0-PG-02-C and observed in every prior canonical stage
(P0-PG-03, P0-PG-03B, P0-PG-04, P0-PG-06). 29 instances over 30
minutes (one per strategy tick). The WARN is contained to the
shadow strategy tick; the strategy loop continues; the binary
stays up; the soak completes its full 30-min window. Not blocking
PASS.

## Why this qualifies as PASS

- 30-minute bounded run completed cleanly (planned timeout).
- No panic, no fatal, no shadow-mode escape.
- Schema guard OK.
- Metrics server initialized on :9092.
- Base RPC provider initialized with 4 endpoints.
- 60 RPC health ticks, all on the 3 allowlisted public endpoints,
  all OK.
- 29 strategy ticks, 1 scanner loop, both clean.
- Pre-existing chain-type WARN present 29 times but does not
  expand or block.
- No signing, broadcasting, mint, addLiquidity, removeLiquidity,
  approve, swap, or bridge keywords.
- No live / canary / paper / wallet / private / paid / QuickNode
  references.
- Safety check script exit 0.
- Post-soak: `ps aux | grep lpbot-shadow` empty; no daemon left.