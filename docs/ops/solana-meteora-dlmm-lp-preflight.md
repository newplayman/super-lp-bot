# Solana Meteora DLMM LP preflight notes

## Scope

This note records the read-only preflight path for a Solana Meteora DLMM Tier C candidate before any live LP open.

It does not sign or broadcast transactions. A `ready=true` result only means the audited candidate, wallet funding, quote routes, price range, cost model, and exit trigger inputs are internally consistent enough to consider the next implementation step.

## Command

```bash
GOTOOLCHAIN=auto go run -tags live ./cmd/lpbot \
  --config=/opt/lpbot/lp-bot-v3/configs/config.live.toml \
  --solana-meteora-lp-preflight \
  --solana-meteora-lp-pool Cgnuirsk5dQ9Ka1Grnru7J8YW1sYncYUjiXvYxT7G4iZ \
  --solana-lp-total-usd 10 \
  --solana-meteora-lp-range-pct 2.5 \
  --solana-quote-slippage-bps 100
```

Build-readiness command:

```bash
GOTOOLCHAIN=auto go run -tags live ./cmd/lpbot \
  --config=/opt/lpbot/lp-bot-v3/configs/config.live.toml \
  --solana-meteora-lp-build-readiness \
  --solana-meteora-lp-pool Cgnuirsk5dQ9Ka1Grnru7J8YW1sYncYUjiXvYxT7G4iZ \
  --solana-lp-total-usd 10 \
  --solana-meteora-lp-range-pct 2.5 \
  --solana-quote-slippage-bps 100
```

## Current candidate

- Pool: `Cgnuirsk5dQ9Ka1Grnru7J8YW1sYncYUjiXvYxT7G4iZ`
- Protocol: `meteora-dlmm`
- Pair: `TROLL/SOL`
- Token: `5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2`
- Audit verdict: `watch`
- Risk score: `20`
- Flag: `solana_non_major_pair`

## Latest preflight result

- Ready: `true`
- Budget: `$10.00`
- Range pct: `-2.50..2.50`
- Pool price: `0.001294005367`
- Range price: `0.001261655233..0.001326355501`
- Estimated fee APR: `347.52%`
- Estimated fee/day: `$0.095211`
- Funding cost: `$0.137492`
- LP open gas estimate: `$0.043025`
- Total setup cost estimate: `$0.180517`
- Cost payback: `1.90` days
- Exit trigger: `price_outside_range_or_il_gte_1.5pct_or_exit_quote_fails`

## Funding interpretation

The preflight uses same-chain wallet assets only.

For the latest run:

- Wallet SOL raw balance: `533712699`
- Combined SOL required raw: `130034841`
- Wallet USDC raw balance: `1611041`
- Combined USDC required raw: `0`
- Estimated chain value: `$47.082722`

Leg plan:

- TROLL leg target: `45366409` raw
- TROLL prefund: `60355154` raw SOL -> `46727401` raw TROLL
- SOL leg target: `58669687` lamports

This confirms idle SOL can fund both LP legs without pulling assets from another chain.

## Quote retry lesson

Meteora preflight calls Jupiter several times:

- candidate quote audit
- USD sizing quote per leg
- funding path quote
- SOL price quote

The first implementation could falsely fail with:

- `jupiter funding quote cooldown active`
- transient `no same-chain USDC/SOL route could fund target mint`

The command now retries cooldown/rate-limit cases and retries transient generic target no-route with a fresh quote client. This prevents a temporary Jupiter quote failure from being misclassified as an LP blocker.

## Current boundary

The read-only builder/simulator now exists.

Latest build-readiness result:

- Build ready: `true`
- Simulation ready: `true`
- Position pubkey generated: `E3bisi...X78Q`
- Active bin id: `128`
- Active bin price: `1.2914225217112199411`
- Bin range: `-3343..-3316`
- Instruction count: `8`
- Serialized tx size (base64 length): `1252`
- Simulation units: `307920`
- Simulation logs captured: `55`

Current warnings:

- helper runtime emitted a `bigint` native binding fallback warning;
- Node 22 emitted a `punycode` deprecation warning.

These warnings did not block build or simulation.

The next implementation step is no longer builder creation itself. It is execution-path completion:

- sign the Meteora transaction with the real wallet key in a guarded canary path;
- broadcast and confirm the transaction;
- persist Meteora-specific position metadata for later fee/IL/exit tracking;
- add Meteora remove-liquidity / close-position read-only exit readiness.

No live TROLL/SOL LP should be opened until the guarded sign/broadcast path and the exit readiness path both exist and pass.
