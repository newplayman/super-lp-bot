# Data Source Health

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R1_REWARD_AWARE_ALPHA_POOL_DISCOVERY_V1`
**Run ID:** 20260611_034500
**Probed at:** 2026-06-11T03:45:00Z (UTC)

## Summary

| Source | URL | HTTP | Latency | Used? | Reason |
|---|---|---|---|---|---|
| GeckoTerminal API v2 | `https://api.geckoterminal.com/api/v2/networks/base/pools?page={N}&sort=h24_volume_usd_desc` | 200 | ~0.4s | ✓ | 100 pools across 5 pages |
| GeckoTerminal `/networks/base/pools/{addr}` | same base | 200 | ~0.4s | ✓ (background) | spot-checked, no APR/reward fields |
| DexScreener `/latest/dex/search` | `https://api.dexscreener.com/latest/dex/search?q=...` | 200 | ~0.4s | ✓ | 135 unique Base pairs across 14 queries |
| DexScreener `/latest/dex/pairs/base/{addr}` | `https://api.dexscreener.com/latest/dex/pairs/base/{addr}` | 200 | ~0.4s | ✓ (background) | no APR/reward fields |
| Base public RPC | `https://mainnet.base.org` | 200 (eth_blockNumber, eth_call) | ~0.5s | ✓ (background) | used for Voter probe only; results = null/0x |
| Aerodrome hosted subgraph (legacy) | `https://api.thegraph.com/subgraphs/name/aerodrome-finance/aerodrome` | 301 → error.thegraph.com | — | ✗ | **service is offline** |
| Aerodrome goldsky subgraph | `https://api.goldsky.com/api/public/project_clvh9byacv8nc31pvhv7hpgq/subgraphs/aerodrome-base/v1.0.0/graphql` | 404 | — | ✗ | URL is wrong; correct URL unknown without registration |
| Aerodrome public API | `https://aerodrome.finance/api/v1/pools` | 200 (HTML, not JSON) | — | ✗ | returns landing page, not a JSON API |
| Aerodrome Voter contract (multiple candidates) | on-chain `gauges(address)` selector `0x4d24804c` | 200 (0x) | — | ✗ | all candidate addresses returned empty/0x — Voter address is not in this repo's source |

## Failure modes and fallbacks

### Aerodrome subgraph / voter → reward data unavailable

The Aerodrome finance team migrated from the hosted TheGraph to a Goldsky-hosted endpoint, but the endpoint URL was not archived in this repo. The 14 candidate addresses we tried for the Voter contract all returned `0x` (no contract at that address or no `gauges()` mapping populated for the queried pool).

Result: **`reward_data_unavailable=true`** for all 202 pools in the dataset. The run still records the AERO token pair membership in `reward_pools.csv` (column `reward_token=AERO` for AERO-paired pools), so a future stage that *does* recover the Voter address can re-emit the reward APR with no data-shape change.

### GeckoTerminal /tokens/multi → name-parse fallback

Same as R0. When the multi-token endpoint returns 429 (rate-limited), the script falls back to parsing `attributes.name` (e.g. "WETH / USDC 0.05%") for symbol resolution. Symbol coverage: 100% on the 202-pool raw dataset.

### DexScreener fee_tier

DexScreener's pair payload includes `feeBps` only on some responses; for the rest we parse the fee tier from the pool's name. Coverage of `fee_tier_bps > 0` on the merged dataset: 49/202 (24% — the 24% that survive risk-filtering with positive volume).

## Outbound connections actually made

- `api.geckoterminal.com` over HTTPS (GET, paginated, with 0.4s cushion)
- `api.dexscreener.com` over HTTPS (GET, 14 queries, with 0.5s cushion)
- `mainnet.base.org` over HTTPS (POST eth_call × 3, background only)
- No other host. No auth header. No persistent connection.

## Wall-clock breakdown

| Step | Wall-clock |
|---|---|
| GeckoTerminal pull (5 pages × 0.4s + cushion) | 2.4s |
| DexScreener pull (14 queries × 0.5s + cushion) | 7.5s |
| Risk scoring + matrix (in-process Python, stdlib) | < 1s |
| Aerodrome Voter probe (3 eth_call) | 0.5s |
| CSV / JSONL write | < 0.5s |
| **Total scan** | **15.8s** |
