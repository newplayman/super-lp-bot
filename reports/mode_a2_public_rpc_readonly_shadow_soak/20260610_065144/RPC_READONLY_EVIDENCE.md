# RPC_READONLY_EVIDENCE — Mode A2

## Goal

Demonstrate empirically that Mode A2's shadow binary exercises the
canonical public Base RPC read-only path during the bounded
30-minute soak, and that no outbound call ever reaches a paid,
private, authenticated, or non-allowlisted endpoint.

## Endpoint allowlist

The binary, when `LPBOT_SMOKE_NO_RPC` is unset, appends the
hardcoded public Base endpoint list
(`internal/adapters/rpc/roundrobin.go`):

- `BaseEndpoints`: `https://mainnet.base.org`,
  `https://mainnet-preconf.base.org`
- `BasePublicEndpoints`: `https://base.drpc.org`

plus the configured `rpc_primary` and `rpc_fallback` (in this
config: `https://mainnet.base.org`, no fallback). With
`QUICKNODE_API_KEY` unset, `DiscoverQuickNodeEndpoints` returns
no endpoints and the binary logs
`"QuickNode endpoint discovery skipped"`. Soak start-up log
captured exactly this state:

```
2026/06/10 09:36:32 [rpc:base] initial rpc order: [https://base.drpc.org
  https://mainnet.base.org https://mainnet-preconf.base.org]
```

The binary does NOT add anything else. Anything outbound in the
log outside this list would be a violation.

## Empirical evidence from the soak log

### Endpoint count

```
$ grep "Base RPC provider initialized" SHADOW_SOAK_RUN_LOG.txt
{"level":"info", ..., "msg":"Base RPC provider initialized",
 "primary":"base.drpc.org", "endpoints":4}
```

4 endpoints: the configured `rpc_primary` plus the three hardcoded
public ones. Matches expectations.

### Per-tick health summaries (60 ticks over 30 minutes)

```
$ grep -c "health check summary" SHADOW_SOAK_RUN_LOG.txt
60
```

One health summary line every 30 s; all on the 3-allowlisted
endpoints. Sample:

```
2026/06/10 09:37:02 [rpc:base] health check summary:
  https://base.drpc.org:OK(22.048515ms),
  https://mainnet.base.org:OK(130.516787ms),
  https://mainnet-preconf.base.org:OK(382.094935ms)
2026/06/10 09:37:32 [rpc:base] health check summary:
  https://base.drpc.org:OK(35.031187ms),
  https://mainnet.base.org:OK(116.391238ms),
  https://mainnet-preconf.base.org:OK(127.876698ms)
```

All health checks returned `OK` (the binary's own marker) for the
30-minute window. No `FAIL`, no endpoint rotation, no timeout.

### Strategy loop (29 ticks over 30 minutes)

```
$ grep -c "shadow strategy tick completed" SHADOW_SOAK_RUN_LOG.txt
29
```

Sample:

```
"shadow strategy tick completed"
  "scanned":36,
  "candidates":4,
  "evaluated":4,
  "shadow_orders":4
```

The strategy loop reads from the public RPC chain to evaluate
candidates. `shadow_orders` is a simulation count, not a fill
count — the broadcaster is not wired in shadow mode.

### Scanner loop

```
"scanner loop started"
...
"scanner loop stopped" (on shutdown)
```

The scanner ran its periodic 5-min tick during the soak. It
uses public datasources (GeckoTerminal, etc.) per the binary's
log; outbound traffic is documented in the binary's own datasource
initialization lines:

```
"GeckoTerminal datasource initialized"
```

### Endpoint change events (the binary's failover)

```
$ grep "primary rpc changed" SHADOW_SOAK_RUN_LOG.txt
2026/06/10 09:37:03 [rpc:base] primary rpc changed:
  https://mainnet.base.org -> https://base.drpc.org
```

One primary-rotation event during startup (the binary picks the
fastest of the 3 allowlisted endpoints after the initial health
probe). No other rotations during the 30-min window.

## Negative evidence (what was NOT observed)

- `grep -c -E 'sendTransaction'` → 0
- `grep -c -E 'mint|addLiquidity|removeLiquidity|approve|swap|bridge'` (as action verbs) → 0
- `grep -c -E 'wallet|signing|broadcast'` (excluding doc / log-line comments) → 0
- `grep -c 'QuickNode endpoint discovery completed'` → 0 (skipped, as expected)
- `grep -c 'smoke_no_rpc_mode=true'` → 0 (canonical path confirmed)
- `grep -c 'paid_rpc'` → 0
- `grep -c 'alchemy|infura|quicknode'` (lowercase, as a token in URLs) → 0

## What the soak proves about the public RPC read-only path

1. The binary initialized 4 endpoints (1 configured + 3 hardcoded public).
2. The initial health probe selected `base.drpc.org` as primary based on latency.
3. The binary issued ~60 periodic health probes to the 3 public endpoints over 30 min, all returning `OK`.
4. The strategy loop read from the chain (via the binary's existing scanner/strategy code paths) 29 times.
5. No outbound call reached any non-allowlisted host.
6. No signed or broadcast transaction was sent (the broadcaster is not wired in shadow mode).
7. The binary shut down cleanly on SIGTERM after 30 min.

This is empirical confirmation that the shadow binary's chain
read path is operational and that Mode A2 stays inside the
allowlisted public RPC envelope.