# M0F FIX-R2 — Stage-1 proxy correlation

## Result

Proxy evidence is **VALID**. Production recommendation: `PROXY_NETCOVER`.

- same research batch: `30` rows
- fully calculable proxy/true pairs: `16` (only these participate in correlation)
- Spearman: `0.473529`; validity requires `>= 0.3` and at least `8` calculable pairs
- top-K hit: `7/10` = `0.700000`
- top-K definition: intersection(proxy descending top-K, true NetCover descending top-K) / min(K, fully calculable same-batch pairs)
- correlation retains the full in-memory selected-lead cohort; SQLite's operational unique resolved-pool key is not allowed to collapse duplicate DefiLlama leads first

## Proxy formula (zero RPC)

`income_apr = apyBase×0.65 + apyReward×REWARD_HAIRCUTS[known category]`

`cost_apr = IL(sigma, stable/same-anchor, pair quality)×(1+LVR 0.5) + annualized(2×fee_tier×50U + Base gas 0.0795U)/50U`

`proxy_netcover = income_apr / cost_apr`

Low fee tier, stable/same-anchor identity, and emission-dominant blue-chip identity are structured income/cost inputs. Only reward-dominant double-major pairs retain the full existing category haircut; other known rewards receive an extra conservative reliability discount. They are not post-hoc bonuses. The position is fixed at M1 50U and is not a ranking factor. Missing sigma/fee tier or unknown reward category makes the proxy unavailable and therefore cannot activate proxy ordering.
DefiLlama's generic sigma is a Stage-1 proxy assumption, not the terminal gate's on-chain measured pair-price sigma; weak observed correlation therefore automatically selects the original APR fallback.

## ADD-2 validation targets

**Identity limitation:** the audit target table supplies chain/project/symbol but no DefiLlama pool id. To avoid guessing identity from stale APR, each symbol label expands to every live row with the exact `Base / aerodrome-slipstream / symbol` identity. The per-symbol expansion counts are shown below.

| symbol | live status | live matches | coarse-pass | best proxy rank | in top-N | terminal rows | calculable | best true NetCover | accepted | outcomes |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |
| USDC-AVAIL | LIVE_BUT_NOT_COARSE_GATE_ELIGIBLE | 1 | 0 | — | False | 1 | 1 | 0.278670 | 0 | RESEARCH_ONLY_NOT_PROXY_TOP_N:TVL 125909 < 500000;NETCOVER_GATE_BELOW_SHADOW |
| CADC-USDC | LIVE_BUT_NOT_COARSE_GATE_ELIGIBLE | 1 | 0 | — | False | 1 | 1 | 1.357083 | 0 | RESEARCH_ONLY_NOT_PROXY_TOP_N:TVL 138832 < 500000;NETCOVER_GATE_PASS |
| MSUSD-USDC | LIVE | 2 | 1 | 4 | True | 2 | 2 | 1.073247 | 0 | ENTRY_INELIGIBLE:REWARD_PERSISTENCE_MISSING, RESEARCH_ONLY_NOT_PROXY_TOP_N:TVL 11274 < 500000;NETCOVER_GATE_BELOW_SHADOW |
| XSGD-USDC | LIVE_BUT_NOT_COARSE_GATE_ELIGIBLE | 1 | 0 | — | False | 1 | 1 | 1.653330 | 0 | RESEARCH_ONLY_NOT_PROXY_TOP_N:TVL 454687 < 500000;NETCOVER_GATE_PASS |
| VCHF-USDC | LIVE_BUT_NOT_COARSE_GATE_ELIGIBLE | 1 | 0 | — | False | 1 | 1 | 0.189685 | 0 | RESEARCH_ONLY_NOT_PROXY_TOP_N:TVL 186721 < 500000;NETCOVER_GATE_BELOW_SHADOW |
| WETH-USDC | LIVE | 7 | 2 | 25 | True | 7 | 3 | 0.320386 | 0 | PERMANENT_FAIL_CLOSED:ambiguous_multi_factory_pool, RESEARCH_ONLY_NOT_PROXY_TOP_N:TVL 12141 < 500000;NETCOVER_GATE_BELOW_SHADOW, RESEARCH_ONLY_NOT_PROXY_TOP_N:TVL 182492 < 500000;NETCOVER_GATE_BELOW_SHADOW, RESEARCH_ONLY_NOT_PROXY_TOP_N:target_expansion_only;NETCOVER_GATE_BELOW_SHADOW |
| WETH-CBBTC | LIVE | 4 | 3 | 5 | True | 4 | 1 | 0.150045 | 0 | PERMANENT_FAIL_CLOSED:ambiguous_multi_factory_pool, RESEARCH_ONLY_NOT_PROXY_TOP_N:target_expansion_only;NETCOVER_GATE_BELOW_SHADOW |
| USDC-CBBTC | LIVE | 7 | 4 | 6 | True | 7 | 3 | 0.935979 | 0 | ENTRY_INELIGIBLE:REWARD_PERSISTENCE_MISSING, PERMANENT_FAIL_CLOSED:ambiguous_multi_factory_pool, RESEARCH_ONLY_NOT_PROXY_TOP_N:target_expansion_only;NETCOVER_GATE_BELOW_SHADOW, RESEARCH_ONLY_NOT_PROXY_TOP_N:vol1d 31807 < 50000;NETCOVER_GATE_BELOW_SHADOW |

The terminal research cohort is `proxy top-N ∪ every live target-symbol row`, de-duplicated by DefiLlama pool id. Correlation uses only the same proxy-top-N subcohort so target oversampling cannot improve it. Target rows are forced into research evaluation only; no target is whitelisted, production-ranked, or directly accepted. Missing symbols are reported as NOT_IN_LIVE_UNIVERSE and never fabricated.

## RPC budget

Measured logical RPC calls: `5579`. Conservative upper bound before provider retries: `9585`.

| measured method | calls |
| --- | ---: |
| eth_blockNumber | 3 |
| eth_call | 746 |
| eth_getCode | 78 |
| eth_getLogs | 4752 |

| upper-bound component | calls |
| --- | ---: |
| batch_tip_calls | 2 |
| resolve_factory_lookup_calls | 282 |
| resolve_candidate_validation_calls | 846 |
| resolve_window_log_calls | 2068 |
| stability_window_log_calls | 6204 |
| terminal_live_state_calls | 94 |
| cross_route_fixed_batch_calls | 89 |

Budget semantics: conservative request count before provider retry attempts; cross routes are one fixed-block batch snapshot, not top_n multiplied.

## Safety

This run used public read-only RPC calls only. It did not sign, broadcast, access a wallet, change NetCover thresholds, or start a daemon.
