# Data Sources Used — R0 Base Pool Discovery

**Stage:** LP_BOT_STRATEGY_EVIDENCE_R0_POOL_DISCOVERY_AND_TINY_LIVE_CANDIDATE_SELECTION_V1
**Run ID:** 20260611_031425
**Branch:** feat/supabase-postgres-deployment
**Base commit (HEAD at scan time):** bd0544b839c061684d32c8adfba583ea4c77c39c

## A.1 Sources actually used in this run

| Source | Endpoint | Auth | Used for |
|---|---|---|---|
| GeckoTerminal API v2 | `GET https://api.geckoterminal.com/api/v2/networks/base/pools?page={N}&sort=h24_volume_usd_desc` | None (public, ~30 req/min) | Pool discovery, TVL, 24h/6h/1h volume, price-change %, transaction counts, pool age. |
| GeckoTerminal API v2 | `GET https://api.geckoterminal.com/api/v2/networks/base/tokens/multi/{addrs}` | None | Token symbol + decimals (best-effort; see §A.2). |
| Pool name parsing (fallback) | Derived from `attributes.name` (e.g. "WETH / USDC 0.05%") | n/a | Token symbol + fee tier when multi-token endpoint returns 429 or skips an address. |
| Pool age computation | UTC clock vs `pool_created_at` | n/a | Risk score `young_pool` flag (< 14d). |
| Public Base chain gas heuristic | Hand-estimated (0.30 USD / add+remove+collect cycle) | n/a | LP simulation gas line. Conservative for Base public RPC; not an RPC call. |

## A.2 Failures, rate limits, fallbacks

- **Token info endpoint (`/tokens/multi/{addrs}`) returned HTTP 429** during this run because the script attempted multiple 30-address chunks in succession under GeckoTerminal's anonymous rate limit. Fallback in `normalise()` resolved all 53 ranked-pool symbol pairs by parsing the `name` field, so output symbol coverage is 100% on the ranked CSV.
- The existing Go client at `internal/adapters/datasource/geckoterminal/client.go` was **not used**. Its `PoolInfo` JSON tags do not match the live `/networks/base/pools` payload (top-level `attributes.*` vs the client's flat field expectations). Fixing that client is out of scope for R0; the Python+urllib path uses the raw response verbatim.
- DexScreener, DefiLlama, Birdeye adapters exist (`internal/adapters/datasource/{dexscreener,defillama,birdeye}`) but were **not exercised** in this run — GeckoTerminal alone was sufficient to pull the 120-pool set.

## A.3 Sources explicitly NOT used (per stage guardrails)

- No paid RPC.
- No private RPC.
- No API key.
- No QuickNode / Alchemy / Infura token.
- No wallet / signer / keypair / seed / mnemonic.
- No Base native RPC chain reads (this stage uses third-party aggregator data only).

## A.4 Outbound connections actually made

Verified by reading the script: only `api.geckoterminal.com` over HTTPS via `urllib.request`. No other host. No persistent connection, no auth header.
