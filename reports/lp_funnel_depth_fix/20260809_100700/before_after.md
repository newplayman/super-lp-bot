# M0F FIX-R1b — final depth evidence

## Result

Final-code live scan: **733 → 10 → 10 → 10 → 0 accepted**. Fully calculable NetCover records improved from the R1a/M0P live baseline **1/10** to the current live cohort **4/10**. The free DefiLlama top-10 changed, so this is a live capability comparison, not a paired claim over identical ten rows.

| symbol | result | NetCover | final reason |
| --- | --- | ---: | --- |
| USDC-CBMEGA | fully calculable | 0.422059 | BELOW_SHADOW |
| O-USDC | fully calculable | 0.311985 | BELOW_SHADOW |
| WETH-MORPHO | fully calculable | 0.438460 | BELOW_SHADOW |
| WETH-VVV | permanent fail-closed | — | ambiguous_multi_factory_pool |
| WETH-USDC | permanent fail-closed before replay | — | ambiguous_multi_factory_pool |
| WETH-AERO | permanent fail-closed | — | ambiguous_multi_factory_pool |
| AERO-CBBTC (3707…) | permanent fail-closed | — | ambiguous_multi_factory_pool |
| MSUSD-MSETH | permanent fail-closed | — | ambiguous_multi_factory_pool |
| AERO-CBBTC (53b7…) | permanent fail-closed | — | ambiguous_multi_factory_pool |
| WETH-USOL | fully calculable | 0.070430 | BELOW_SHADOW |

## Safety evidence

- Aerodrome resolution exhausts all three official factories in both token orders, de-duplicates canonical addresses, and validates bytecode, token0/token1, decimals and exact tick spacing. Partial RPC evidence cannot prove uniqueness.
- Range `==100`, `>100` and non-finite values are rejected before replay, with measured sigma/H/range/entry/lower-bound retained. This live WETH-USDC row closed earlier because three distinct validated factory pools existed.
- Non-stable cost math converts `size_usd / token1_usd` into quote units, applies the existing pair-price/liquidity impact math, then multiplies costs by `token1_usd`. Pair price is never labelled USD.
- At fixed block `49740557`, all ten score records contain exactly two zero-liquidity watchlist routes with `executable=false`. The four L>0 Initial routes form the frozen executable AERO allowlist and use the highest same-notional measured conversion cost. A watchlist read failure or transition to executable makes the whole evidence package fail closed pending review.
- Caller-supplied cross-route fields are stripped before scanner-internal evidence is constructed; route and provenance evidence remains in `score_json`.
- The three protected threshold files have no diff from R1a.

Controlled reassembly of old R1a rows completes the nine input fields for WETH-CBBTC, WETH-MORPHO, AERO-CBBTC, WETH-AERO and WETH-USOL. This is component evidence only, not an 8/10 same-cohort full-funnel result, because the exhaustive resolver independently closes multi-factory ambiguity.

## Verification

```text
pytest -q tests/test_lp_pool_resolve_and_rank_v1_readonly.py tests/test_lp_netcover_inputs_v1_readonly.py tests/test_lp_scanner_daemon_v1_readonly.py
60 passed in 13.63s
```

```text
CALL_PACE_SECS=0 python3 scripts/lp_scanner_daemon_v1_readonly.py --once --db reports/lp_funnel_depth_fix/20260809_100700/scanner.db --top 10 --window-blocks 86400 --window-days 1 --n-windows 6 --vetted-menu-out reports/lp_funnel_depth_fix/20260809_100700/vetted_menu.json
[scanner] as_of=2026-08-09T10:06:43.620485+00:00 screened=733 top=10 resolved=10 scored=10 accepted=0 sessions=0
[tg-fallback] event=rpc_degraded text=[LPBOT][WARNING][rpc_degraded] scanner RPC health changed UNKNOWN -> DEGRADED; new entries blocked
[scanner] vetted_menu exported=0 invalid=0 out=reports/lp_funnel_depth_fix/20260809_100700/vetted_menu.json
```

No daemon or long-running shadow process was started.
