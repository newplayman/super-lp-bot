#!/usr/bin/env python3
"""
lp_multiwindow_stability_v1_readonly.py  (READ-ONLY research)

Tier-B long-test readiness gap #1: a single window's sigma / fee_cover is ONE
realization. Before trusting a pool's edge for an allocation, measure it over
several ROLLING windows and report stability (mean, dispersion, fraction of
windows that would ENTER). A pool whose fee_cover is >=1 in 1 of 6 windows is a
fluke; >=1 in 6 of 6 is a durable edge.

For each pool x window: fetch real swaps -> sigma_daily -> H=14 vol-sized range
-> passive replay -> fees_quote, il_quote -> fee_cover. Aggregate per pool.

Reuses the verified sizer + replay + fee_cover. NO wallet/sign/broadcast.
RPC reads only (windowed, paced).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

BASE_BLOCKS_PER_DAY = 43200
DEFAULT_WINDOW_DAYS = 1.0
DEFAULT_N_WINDOWS = 6
STABLE_MIN_FRAC = 0.7        # >=70% of windows must ENTER to call it stable
H_NEUTRAL = 14


# ---------------------------------------------------------------------------
# PURE FUNCTIONS (unit-tested, no network)
# ---------------------------------------------------------------------------
def stability_summary(values: Sequence[Optional[float]]) -> Dict[str, Any]:
    """mean/std/cv/min/max over non-None, finite values (inf treated as large)."""
    clean = [float(v) for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    finite = [v for v in clean if not math.isinf(v)]
    n = len(clean)
    if n == 0:
        return {"n": 0, "mean": None, "std": None, "cv": None, "min": None, "max": None}
    mean = statistics.mean(finite) if finite else math.inf
    std = statistics.pstdev(finite) if len(finite) > 1 else 0.0
    cv = (std / mean) if (finite and mean not in (0, math.inf)) else None
    return {"n": n, "mean": mean, "std": std, "cv": cv,
            "min": min(clean), "max": max(clean)}


def _as_cover(v) -> float:
    if v is None:
        return 0.0
    if v == "inf":
        return math.inf
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def classify_stability(fee_covers: Sequence[Any], *, threshold: float = 1.0,
                       min_frac: float = STABLE_MIN_FRAC) -> Dict[str, Any]:
    """Fraction of windows with fee_cover >= threshold; stable if frac >= min_frac."""
    covers = [_as_cover(v) for v in fee_covers]
    n = len(covers)
    if n == 0:
        return {"n_windows": 0, "n_enter": 0, "enter_frac": 0.0, "stable": False}
    n_enter = sum(1 for c in covers if c >= threshold)
    frac = n_enter / n
    return {"n_windows": n, "n_enter": n_enter, "enter_frac": round(frac, 3),
            "stable": frac >= min_frac}


# ---------------------------------------------------------------------------
# NETWORK
# ---------------------------------------------------------------------------
def _live():
    from scripts.lp_tier_c_exit_feasibility_v1_readonly import fetch_pool_swaps, _rpc_with_retry
    from scripts.lp_vol_range_sizer_v1_readonly import (
        hourly_closes, daily_vol_from_closes, recommend_range_pct)
    from scripts.lp_tier_b_level2_replay_v1_readonly import replay
    from scripts.lp_tier_range_policy_v1_readonly import fee_cover_ratio, efficiency_ratio
    return dict(fetch_pool_swaps=fetch_pool_swaps, _rpc_with_retry=_rpc_with_retry,
                hourly_closes=hourly_closes, daily_vol_from_closes=daily_vol_from_closes,
                recommend_range_pct=recommend_range_pct, replay=replay,
                fee_cover_ratio=fee_cover_ratio, efficiency_ratio=efficiency_ratio)


def _measure_window(live, swaps, fee_tier, dec0, dec1):
    if not swaps:
        return {"n_swaps": 0, "sigma_daily": None, "er": None, "range_pct": None,
                "fees_pct": None, "il_pct": None, "fee_cover": None}
    closes = live["hourly_closes"](swaps)
    sigma_daily, _n = live["daily_vol_from_closes"](closes)
    er = live["efficiency_ratio"](closes)
    if sigma_daily is None:
        return {"n_swaps": len(swaps), "sigma_daily": None, "er": er, "range_pct": None,
                "fees_pct": None, "il_pct": None, "fee_cover": None}
    range_pct = live["recommend_range_pct"](sigma_daily, H_NEUTRAL)
    rep = live["replay"](swaps, range_pct=range_pct, fee_tier=float(fee_tier),
                         dec0=int(dec0), dec1=int(dec1), mode="passive")
    fc = live["fee_cover_ratio"](rep["fees_quote"], rep["il_quote"])
    return {"n_swaps": len(swaps), "sigma_daily": sigma_daily, "er": er,
            "range_pct": round(range_pct, 2),
            "fees_pct": rep["fees_quote"] * 100.0, "il_pct": rep["il_quote"] * 100.0,
            "fee_cover": (math.inf if fc == math.inf else fc)}


def assess_pool(live, cfg, window_days, n_windows, tip):
    pool, dec0, dec1 = cfg["pool"], int(cfg["dec0"]), int(cfg["dec1"])
    fee_tier = float(cfg["fee_tier"])
    label = cfg.get("label", pool[:10])
    wblocks = int(window_days * BASE_BLOCKS_PER_DAY)
    windows = []
    for i in range(n_windows):
        hi = tip - i * wblocks
        lo = hi - wblocks
        if lo < 0:
            break
        swaps = live["fetch_pool_swaps"](pool, lo, hi, dec0, dec1)
        m = _measure_window(live, swaps, fee_tier, dec0, dec1)
        m["window_index"] = i
        m["block_lo"], m["block_hi"] = lo, hi
        windows.append(m)
    covers = [w["fee_cover"] for w in windows]
    sigmas = [w["sigma_daily"] for w in windows]
    return {
        "label": label, "pool": pool, "tier_hint": cfg.get("tier_hint"),
        "n_windows": len(windows),
        "fee_cover_stability": classify_stability(covers),
        "fee_cover_summary": stability_summary([_as_cover(c) for c in covers]),
        "sigma_summary": stability_summary(sigmas),
        "windows": windows,
    }


# ---------------------------------------------------------------------------
# SELF TEST (no network)
# ---------------------------------------------------------------------------
def run_self_test():
    print("=== self-test: multiwindow stability ===")
    s = stability_summary([1.0, 2.0, 3.0])
    assert abs(s["mean"] - 2.0) < 1e-9 and s["n"] == 3 and s["min"] == 1.0 and s["max"] == 3.0
    s2 = stability_summary([None, 2.0, None])
    assert s2["n"] == 1 and s2["mean"] == 2.0
    s3 = stability_summary([])
    assert s3["n"] == 0 and s3["mean"] is None
    st = classify_stability([1.2, 1.5, 0.4, 2.0, 1.1, 0.9])  # 4/6 >=1
    assert st["n_enter"] == 4 and abs(st["enter_frac"] - 0.667) < 1e-2 and st["stable"] is False
    st2 = classify_stability([1.2, 1.5, 1.1, 2.0, 1.1, 1.3])  # 6/6
    assert st2["stable"] is True
    st3 = classify_stability(["inf", 2.0, 0.5])  # inf counts as enter
    assert st3["n_enter"] == 2
    assert classify_stability([])["stable"] is False
    print("ALL SELF-TESTS PASSED")


# ---------------------------------------------------------------------------
def _render(results, window_days, n_windows):
    L = [f"# Multi-window stability ({n_windows}× {window_days}d windows)",
         f"_generated {datetime.now(timezone.utc).isoformat()}_\n",
         "fee_cover >=1 = LP beats HODL-the-basket. stable = ENTER in >=70% of windows.\n",
         "| pool | tier | windows | enter_frac | stable | fee_cover mean | cv | σ_daily mean |",
         "|---|---|---|---|---|---|---|---|"]
    for r in results:
        st = r["fee_cover_stability"]; fs = r["fee_cover_summary"]; ss = r["sigma_summary"]
        fcm = "inf" if (fs["mean"] is None or math.isinf(fs["mean"])) else f"{fs['mean']:.2f}"
        cv = "-" if fs["cv"] is None else f"{fs['cv']:.2f}"
        sm = "-" if ss["mean"] is None else f"{ss['mean']*100:.2f}%"
        L.append(f"| {r['label']} | {r.get('tier_hint')} | {r['n_windows']} | {st['enter_frac']} "
                 f"| {'YES' if st['stable'] else 'no'} | {fcm} | {cv} | {sm} |")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", help="policy_config.json-style list (pool,dec0,dec1,fee_tier,label,tier_hint)")
    ap.add_argument("--window-days", type=float, default=DEFAULT_WINDOW_DAYS)
    ap.add_argument("--n-windows", type=int, default=DEFAULT_N_WINDOWS)
    ap.add_argument("--out", default=None)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        run_self_test()
        return
    if not args.config:
        ap.error("--config required (or --self-test)")

    live = _live()
    cfgs = json.load(open(args.config))
    tip = int(live["_rpc_with_retry"]("eth_blockNumber", []), 16)
    results = []
    for c in cfgs:
        try:
            r = assess_pool(live, c, args.window_days, args.n_windows, tip)
        except Exception as e:
            r = {"label": c.get("label", c.get("pool")), "pool": c.get("pool"),
                 "tier_hint": c.get("tier_hint"), "n_windows": 0,
                 "fee_cover_stability": {"enter_frac": 0.0, "stable": False},
                 "fee_cover_summary": stability_summary([]), "sigma_summary": stability_summary([]),
                 "error": str(e), "windows": []}
        results.append(r)
        st = r["fee_cover_stability"]
        print(f"{r['label']}: {r['n_windows']}w enter_frac {st['enter_frac']} "
              f"stable={st['stable']}" + (f" ERR {r.get('error')}" if r.get('error') else ""))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    d = args.out or os.path.join(_ROOT, "reports", "lp_multiwindow_stability", stamp)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "stability.md"), "w") as f:
        f.write(_render(results, args.window_days, args.n_windows))
    with open(os.path.join(d, "stability.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"wrote {d}/")


if __name__ == "__main__":
    main()
