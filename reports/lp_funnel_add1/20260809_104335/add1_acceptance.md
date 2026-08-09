# M0F ADD-1 — range-aware FeeEV and drag-aware H

## Result

The post-fix live run is **732 → 10 → 10 → 10 → 0 accepted**. Exactly **4/10**
score records are fully calculable. `accepted=0` is reported as observed; ADD-1
does not require a positive acceptance count.

`reports/lp_funnel_add1/20260809_103217/` is an invalidated pre-fix diagnostic.
Only this `20260809_104335` directory is final ADD-1 live evidence.

## Task A — range-aware FeeEV

Fee APR is anchored to its fixed seven-day evidence window. The target H does
not linearly multiply FeeEV. Instead, final code computes
`recommend_range_pct(sigma_pair, H/24)`, derives canonical raw position
liquidity with `lp_v3_fee_share.position_liquidity_raw` (including the
`10^((dec0+dec1)/2)` decimal scale), and applies the target/reference share
ratio. Missing pair sigma, valid `<100%` range, internally proven price/L, or
decimals makes `fee_ev_usd=None`.

Final formula:

```text
FeeEV(H) = 50U × min(APR_24h, APR_7d) × haircut × (168/8760)
           × share(range(H)) / share(range(168h))
share(r) = L_pos(50U, price, r, dec0, dec1) / (L_active + L_pos)
```

The fixed 168h anchor is deliberate: `fee_apr_7d` is annualized seven-day
evidence, and retaining a target-H multiplier would leave a free `sqrt(H)`
score lever.

Real-pool self-check uses raw R1b fixed evidence at
`2026-08-09T10:06:43.620485+00:00` and final ADD-1 code:

| pool | H7 range | H30 range | H7 FeeEV | H30 FeeEV | H30/H7 |
| --- | ---: | ---: | ---: | ---: | ---: |
| USDC-CBMEGA | 9.741627% | 20.167084% | 0.191802762 | 0.094188404 | 0.491069 |
| O-USDC | 5.634036% | 11.663563% | 0.133234816 | 0.065117587 | 0.488743 |
| WETH-MORPHO | 6.310430% | 13.063831% | 0.141732318 | 0.069334115 | 0.489191 |

All ratios are close to `sqrt(7/30)=0.483046`; none is the superseded linear
`30/7=4.285714` multiplier.

## Task B — fixed-drag-aware H

`DRAG_APR_MAX=15%` is an explicit **H-selection model constant**, not an entry
gate and not a change to any existing threshold. Drag uses fee tier as a
fraction:

```text
drag_apr = (2 × fee_tier + gas_usd / 50U) / (H / 8760) × 100
```

Starting from the measured ER-policy candidate, code moves only upward through
the profile's frozen discrete set and chooses the smallest satisfying H. If the
maximum still exceeds 15%, it sets `high_drag_flag=true` and continues to the
normal NetCover evaluation; it does not reject.

## USDC-VVV three-basis comparison

Source record:
`reports/lp_netcover_inputs/20260809_final_default/scanner.db`, as-of
`2026-08-09T08:19:38.034782+00:00`.

| basis | H | H source | FeeEV | NetCover | expected net yield |
| --- | ---: | --- | ---: | ---: | ---: |
| pre-ADD-1 | 168h | historical ER policy | 0.061290082 | 0.040912955 | -1.436770420 |
| Task A only | 168h | `ER_policy` | 0.061290082 | 0.040912955 | -1.436770420 |
| Task A+B | 720h | `drag_adjusted(from=168)` | 0.029880723 | 0.005780933 | -5.138960317 |

Task A intentionally leaves the H7 evidence anchor unchanged. Task B lowers
fixed drag to 9.2345%, but the synchronously wider range reduces FeeEV while
IL/latency retain their horizon exposure; NetCover therefore falls honestly.

## Final live evidence

| symbol | H | source | drag APR | FeeEV | NetCover | result |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| O-USDC | 720h | `ER_policy` | 9.2345% | 0.067957063 | 0.260563740 | below shadow |
| USDC-CBMEGA | 720h | `drag_adjusted(from=168)` | 9.2345% | 0.076842889 | 0.192247674 | below shadow |
| WETH-MORPHO | 720h | `drag_adjusted(from=168)` | 8.5921% | 0.071120887 | 0.334936046 | below shadow |
| WETH-USOL | 720h | `ER_policy` | 5.5845% | 0.038537608 | 0.026537884 | below shadow |
| RECALL-USDC | — | — | — | — | — | permanent: ambiguous multi-factory pool |
| WETH-VVV | — | — | — | — | — | permanent: ambiguous multi-factory pool |
| AERO-CBBTC | — | — | — | — | — | permanent: ambiguous multi-factory pool |
| WETH-AERO | — | — | — | — | — | permanent: ambiguous multi-factory pool |
| WETH-USDC | — | — | — | — | — | permanent: ambiguous multi-factory pool |
| MSUSD-MSETH | — | — | — | — | — | permanent: ambiguous multi-factory pool |

Command:

```text
CALL_PACE_SECS=0 python3 scripts/lp_scanner_daemon_v1_readonly.py --once --db reports/lp_funnel_add1/20260809_104335/scanner.db --top 10 --window-blocks 86400 --window-days 1 --n-windows 6 --vetted-menu-out reports/lp_funnel_add1/20260809_104335/vetted_menu.json
```

No daemon or long-running process was started.

## Safety and verification

- Funnel assembly clears every candidate-prefilled H/drag alias before reading
  internally measured sigma/ER; missing or cross-profile policy evidence leaves
  H absent and fails closed.
- Fee density rejects generic DefiLlama `sigma`; it accepts only pair-price
  `sigma_pair`/`sigma_daily` and internally proven decoded-swap or live pool
  price/liquidity provenance.
- Caller-prefilled FeeEV, fee-capture metadata, H, direct price/L, and generic
  sigma attack cases are covered by tests and cannot reopen the evidence path.
- Protected files `lp_netcover_engine_v1_readonly.py`,
  `lp_tier_range_policy_v1_readonly.py`, and
  `lp_multiwindow_stability_v1_readonly.py` have zero diff from ADD-1 baseline.
- Targeted verification: **62 passed in 6.74s**.
