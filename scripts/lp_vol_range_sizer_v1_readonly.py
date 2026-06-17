#!/usr/bin/env python3
"""
lp_vol_range_sizer_v1_readonly.py  (READ-ONLY research)

Replace "拍脑袋" LP range selection with a volatility-derived range.

Core model (driftless GBM / random walk):
  For log-price with daily vol sigma_daily, the EXPECTED time to first-touch a
  two-sided +/-L (log) band is  E[tau] = (L / sigma_daily)**2  (days).
  Invert: to target an expected rebalance interval of H days,
        L = k * sigma_daily * sqrt(H)
  k = safety multiplier (first-passage variance is large; k>1 pushes the TYPICAL
  interval longer than the mean). range_pct ~= 100 * L for small L.

Key point: sigma is measured on the POOL'S PRICE RATIO (token1/token0), not the
single asset vs USD -- correlated pairs (cbBTC/WETH) have tiny ratio-vol and
tolerate tight ranges; USD-paired majors need wide ranges or frequent rebalances.

This tool: fetch recent real swaps -> hourly closes -> realized sigma_daily ->
recommended +/-range for a grid of H targets, with expected rebalances/month and
a first-order fee-density index (fee capture ~ 1/range for fixed capital).

NO wallet / sign / broadcast / chain writes. RPC read of historical swaps only.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone

# repo-root shim so we can import sibling scripts
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Reuse the VERIFIED Tier-C RPC + decode plumbing (windowed, paced, retrying).
from scripts.lp_tier_c_exit_feasibility_v1_readonly import (  # noqa: E402
    fetch_pool_swaps,
    _rpc_with_retry,
)

BASE_BLOCK_SECS = 2.0          # Base produces ~1 block / 2s
BLOCKS_PER_HOUR = int(3600 / BASE_BLOCK_SECS)   # 1800
BLOCKS_PER_DAY = int(86400 / BASE_BLOCK_SECS)   # 43200
DEFAULT_K = 1.2                # safety multiplier on the vol band
BASELINE_RANGE_PCT = 10.0      # reference range for the fee-density index
H_GRID = [7, 14, 30, 45, 60]   # target rebalance intervals (days) to tabulate


# ---------------------------------------------------------------------------
# PURE FUNCTIONS (unit-tested, no network)
# ---------------------------------------------------------------------------
def hourly_closes(swaps, blocks_per_hour: int = BLOCKS_PER_HOUR):
    """Collapse time-ordered swaps -> one close price per hourly block-bucket.

    swaps: list of {block, price, ...} sorted by block.
    Returns list of (bucket_index, close_price) ordered by bucket.
    """
    buckets = {}
    for s in swaps:
        p = s.get("price")
        b = s.get("block")
        if p is None or b is None or p <= 0:
            continue
        idx = int(b) // blocks_per_hour
        buckets[idx] = float(p)  # last write wins == last (highest block) in bucket
    return [(i, buckets[i]) for i in sorted(buckets)]


def daily_vol_from_closes(closes, blocks_per_hour: int = BLOCKS_PER_HOUR):
    """Realized daily log-vol from hourly closes.

    closes: list of (bucket_idx, price). Uses log returns between CONSECUTIVE
    occupied buckets, normalizing each return by sqrt(hours_elapsed) so gaps
    (illiquid hours) don't inflate vol. sigma_daily = sigma_per_hour * sqrt(24).
    Returns (sigma_daily, n_returns).  None if < 2 usable points.
    """
    if len(closes) < 2:
        return None, 0
    per_hour_sq = []
    for (i0, p0), (i1, p1) in zip(closes, closes[1:]):
        if p0 <= 0 or p1 <= 0:
            continue
        dh = max(1, i1 - i0)  # hours elapsed between buckets
        r = math.log(p1 / p0)
        per_hour_sq.append((r * r) / dh)   # variance contribution per hour
    if not per_hour_sq:
        return None, 0
    var_per_hour = sum(per_hour_sq) / len(per_hour_sq)
    sigma_hour = math.sqrt(var_per_hour)
    sigma_daily = sigma_hour * math.sqrt(24.0)
    return sigma_daily, len(per_hour_sq)


def recommend_range_pct(sigma_daily: float, horizon_days: float, k: float = DEFAULT_K):
    """Vol-sized half-width in percent: 100 * k * sigma_daily * sqrt(H)."""
    return 100.0 * k * sigma_daily * math.sqrt(horizon_days)


def expected_rebalances_per_month(horizon_days: float):
    """At a range tuned for expected interval H, ~30/H rebalances per 30 days."""
    if horizon_days <= 0:
        return float("inf")
    return 30.0 / horizon_days


def fee_density_index(range_pct: float, baseline_pct: float = BASELINE_RANGE_PCT):
    """First-order fee capture for fixed capital ~ 1/range.

    Index relative to a baseline range: <1 means thinner fees than baseline,
    >1 means richer. (Ignores the offsetting gain in in-range time; this is a
    deliberately conservative 'cost of widening' lens.)
    """
    if range_pct <= 0:
        return float("inf")
    return baseline_pct / range_pct


# ---------------------------------------------------------------------------
# NETWORK
# ---------------------------------------------------------------------------
def latest_block():
    r = _rpc_with_retry("eth_blockNumber", [])
    return int(r, 16) if isinstance(r, str) else int(r)


def assess_pool(cfg, blocks_back, k):
    """Fetch swaps, measure sigma_daily, build the H-grid recommendation."""
    pool = cfg["pool"]
    dec0, dec1 = cfg["dec0"], cfg["dec1"]
    label = cfg.get("label", pool[:10])
    tip = latest_block()
    from_block = tip - int(blocks_back)
    swaps = fetch_pool_swaps(pool, from_block, tip, dec0, dec1)
    closes = hourly_closes(swaps)
    sigma_daily, n_ret = daily_vol_from_closes(closes)
    out = {
        "label": label,
        "pool": pool,
        "tier_hint": cfg.get("tier_hint", ""),
        "n_swaps": len(swaps),
        "n_hourly_closes": len(closes),
        "n_returns": n_ret,
        "window_blocks": int(blocks_back),
        "window_days": round(blocks_back / BLOCKS_PER_DAY, 2),
        "sigma_daily": sigma_daily,
        "sigma_daily_pct": (sigma_daily * 100.0) if sigma_daily else None,
        "sigma_annual_pct": (sigma_daily * math.sqrt(365) * 100.0) if sigma_daily else None,
        "grid": [],
    }
    if sigma_daily is None:
        out["status"] = "INSUFFICIENT_DATA"
        return out
    out["status"] = "OK"
    for H in H_GRID:
        rng = recommend_range_pct(sigma_daily, H, k)
        out["grid"].append({
            "H_days": H,
            "range_pct": round(rng, 2),
            "rebal_per_month": round(expected_rebalances_per_month(H), 2),
            "fee_density_index": round(fee_density_index(rng), 2),
        })
    return out


# ---------------------------------------------------------------------------
# SELF TEST (no network)
# ---------------------------------------------------------------------------
def run_self_test():
    print("=== self-test: vol-range sizer ===")
    # synthetic hourly closes: ~2%/hr moves -> sigma_hour ~0.02 -> sigma_daily ~0.098
    closes = [(i, 1.0 * math.exp(0.02 * ((-1) ** i))) for i in range(48)]
    sd, n = daily_vol_from_closes(closes)
    assert sd is not None and sd > 0, sd
    print(f"sigma_daily={sd:.4f} from {n} returns (alternating +/-2%/hr)")
    # monotonic checks
    r30 = recommend_range_pct(0.03, 30)
    r7 = recommend_range_pct(0.03, 7)
    assert r30 > r7 > 0, (r30, r7)
    print(f"sigma=3%/day -> +/-{r7:.1f}% (H=7) , +/-{r30:.1f}% (H=30)")
    assert expected_rebalances_per_month(30) < expected_rebalances_per_month(7)
    assert fee_density_index(20.0) < fee_density_index(5.0)
    # hourly_closes bucketing: two swaps same hour -> last wins
    hc = hourly_closes([
        {"block": 10, "price": 1.0},
        {"block": 11, "price": 1.5},  # same 1800-block bucket as block 10
        {"block": 2000, "price": 2.0},
    ])
    assert hc[0][1] == 1.5 and hc[-1][1] == 2.0, hc
    print("bucketing/monotonicity OK")
    print("ALL SELF-TESTS PASSED")


# ---------------------------------------------------------------------------
# RENDER
# ---------------------------------------------------------------------------
def _fmt_table(results, k, total_usd, tier_split):
    lines = []
    lines.append(f"# LP vol-range sizer  (k={k}, base capital {total_usd:.0f}U)")
    lines.append(f"_generated {datetime.now(timezone.utc).isoformat()}_\n")
    lines.append("range_pct = 100 * k * sigma_daily * sqrt(H_days). "
                 "rebal/mo ~= 30/H. fee_idx = 10%/range (fee density vs +/-10% baseline).\n")
    for r in results:
        lines.append(f"## {r['label']}  [{r.get('tier_hint','')}]")
        if r["status"] != "OK":
            lines.append(f"- status: **{r['status']}** "
                         f"(swaps={r['n_swaps']}, hourly_closes={r['n_hourly_closes']})\n")
            continue
        lines.append(f"- window {r['window_days']}d, swaps {r['n_swaps']}, "
                     f"hourly closes {r['n_hourly_closes']}, returns {r['n_returns']}")
        lines.append(f"- **sigma_daily = {r['sigma_daily_pct']:.2f}%** "
                     f"(annualized ~{r['sigma_annual_pct']:.0f}%)")
        lines.append("")
        lines.append("| H (days) | ±range | rebal/mo | fee density vs ±10% |")
        lines.append("|---|---|---|---|")
        for g in r["grid"]:
            lines.append(f"| {g['H_days']} | ±{g['range_pct']:.1f}% | "
                         f"{g['rebal_per_month']:.2f} | {g['fee_density_index']:.2f}x |")
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", help="JSON list of {pool,dec0,dec1,label,tier_hint}")
    ap.add_argument("--blocks-back", type=int, default=int(1.5 * BLOCKS_PER_DAY),
                    help="measurement window in blocks (default ~1.5 days)")
    ap.add_argument("--k", type=float, default=DEFAULT_K)
    ap.add_argument("--total-usd", type=float, default=10000.0)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.self_test:
        run_self_test()
        return

    if not args.config:
        ap.error("--config required (or --self-test)")

    with open(args.config) as f:
        cfgs = json.load(f)

    results = []
    for cfg in cfgs:
        try:
            r = assess_pool(cfg, args.blocks_back, args.k)
        except Exception as e:  # keep going on per-pool RPC failure
            r = {"label": cfg.get("label", cfg.get("pool")), "pool": cfg.get("pool"),
                 "tier_hint": cfg.get("tier_hint", ""), "status": f"ERROR: {e}",
                 "n_swaps": 0, "n_hourly_closes": 0}
        results.append(r)
        st = r.get("status")
        if st == "OK":
            g30 = next((g for g in r["grid"] if g["H_days"] == 30), r["grid"][-1])
            print(f"{r['label']}: sigma_daily {r['sigma_daily_pct']:.2f}% "
                  f"-> H=30 ±{g30['range_pct']:.1f}% (swaps {r['n_swaps']})")
        else:
            print(f"{r['label']}: {st} (swaps {r.get('n_swaps',0)})")

    md = _fmt_table(results, args.k, args.total_usd, None)
    out = args.out
    if out is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        d = os.path.join(_ROOT, "reports", "lp_vol_range_sizer", stamp)
        os.makedirs(d, exist_ok=True)
        out = os.path.join(d, "vol_range_recommendations.md")
        with open(os.path.join(d, "vol_range_recommendations.json"), "w") as f:
            json.dump(results, f, indent=2)
    with open(out, "w") as f:
        f.write(md)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
