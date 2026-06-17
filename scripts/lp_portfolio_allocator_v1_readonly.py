#!/usr/bin/env python3
"""
lp_portfolio_allocator_v1_readonly.py  (READ-ONLY research)

STAGE 3-lite: turn the ranked, on-chain-validated pool list (output of the
Stage 1->2 bridge `lp_pool_resolve_and_rank`) into a concrete capital allocation
for a fixed budget (default 10000U), per the operator's Tier A/B design:
  - Tier A 70%, Tier B 30% (Tier C 0 by default — too rug-prone for the base book)
  - cap pools per tier (A<=3, B<=2) -> ~5 pools total
  - within a tier, weight by composite_score, with a per-pool minimum
  - only ENTERABLE pools: status OK, resolved, not wash, yield_cover>=1, score>0

Pure / no network: consumes the bridge's resolve_and_rank.json.
NO wallet/sign/broadcast. This produces a PAPER allocation plan only (freeze intact).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Sequence

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

DEFAULT_TOTAL = 10000.0
DEFAULT_TIER_WEIGHTS = {"A": 0.70, "B": 0.30, "C": 0.0}
DEFAULT_MAX_POOLS = {"A": 3, "B": 2, "C": 0}
DEFAULT_MIN_POOL_USD = 1000.0


# ---------------------------------------------------------------------------
# PURE FUNCTIONS (unit-tested, no network)
# ---------------------------------------------------------------------------
def is_enterable(rec: Mapping[str, Any]) -> bool:
    if rec.get("status") not in (None, "OK"):
        return False
    if rec.get("resolve_status") not in (None, "OK"):
        return False
    if rec.get("wash_flag"):
        return False
    score = rec.get("composite_score")
    if score is None or float(score) <= 0.0:
        return False
    yc = rec.get("yield_cover")
    try:
        ycv = math.inf if (yc in (None, "inf") or (isinstance(yc, float) and math.isinf(yc))) else float(yc)
    except (TypeError, ValueError):
        ycv = 0.0
    return ycv >= 1.0


def _tier_of(rec: Mapping[str, Any]) -> str:
    return str(rec.get("tier") or rec.get("tier_hint") or "").upper()


def select_per_tier(records: Sequence[Mapping[str, Any]], max_pools: Mapping[str, int]):
    """Group enterable records by tier, keep top-N by composite_score per tier."""
    by_tier: Dict[str, List[Mapping[str, Any]]] = {}
    for r in records:
        if not is_enterable(r):
            continue
        by_tier.setdefault(_tier_of(r), []).append(r)
    for t in by_tier:
        by_tier[t].sort(key=lambda r: -float(r.get("composite_score") or 0.0))
        cap = max_pools.get(t, 0)
        by_tier[t] = by_tier[t][:cap] if cap else []
    return by_tier


def _weight_within(selected: Sequence[Mapping[str, Any]]) -> List[float]:
    scores = [max(float(r.get("composite_score") or 0.0), 0.0) for r in selected]
    s = sum(scores)
    n = len(selected)
    if n == 0:
        return []
    if s <= 0:
        return [1.0 / n] * n
    return [x / s for x in scores]


def allocate(records, *, total=DEFAULT_TOTAL, tier_weights=None, max_pools=None,
             min_pool_usd=DEFAULT_MIN_POOL_USD):
    """Allocate `total` across enterable pools by tier weight then score weight.

    Tier weights for tiers with NO enterable pools are redistributed pro-rata to
    the tiers that do have picks (so we don't leave the book under-deployed).
    Returns {allocations:[...], by_tier_usd:{}, deployed, idle, n_pools}.
    """
    tier_weights = dict(tier_weights or DEFAULT_TIER_WEIGHTS)
    max_pools = dict(max_pools or DEFAULT_MAX_POOLS)
    by_tier = select_per_tier(records, max_pools)

    active = {t: w for t, w in tier_weights.items() if w > 0 and by_tier.get(t)}
    wsum = sum(active.values())
    if wsum <= 0:
        return {"allocations": [], "by_tier_usd": {}, "deployed": 0.0,
                "idle": total, "n_pools": 0}
    norm = {t: w / wsum for t, w in active.items()}

    allocations: List[Dict[str, Any]] = []
    by_tier_usd: Dict[str, float] = {}
    for t, frac in norm.items():
        tier_usd = total * frac
        by_tier_usd[t] = round(tier_usd, 2)
        sel = by_tier[t]
        weights = _weight_within(sel)
        for r, w in zip(sel, weights):
            usd = tier_usd * w
            allocations.append({
                "tier": t,
                "symbol": r.get("symbol"),
                "project": r.get("project"),
                "pool": r.get("resolved_pool") or r.get("pool"),
                "dec0": r.get("dec0"), "dec1": r.get("dec1"),
                "fee_tier": r.get("fee_tier"),
                "range_pct": r.get("range_pct"),
                "composite_score": r.get("composite_score"),
                "yield_cover": r.get("yield_cover"),
                "fee_apr_onchain": r.get("fee_apr_onchain"),
                "reward_apr": r.get("reward_apr"),
                "usd": round(usd, 2),
                "weight_in_tier": round(w, 4),
            })
    allocations.sort(key=lambda a: (a["tier"], -a["usd"]))
    deployed = round(sum(a["usd"] for a in allocations), 2)
    # flag sub-minimum positions (capital too thin to bother / monitor)
    for a in allocations:
        a["below_min"] = a["usd"] < min_pool_usd
    return {"allocations": allocations, "by_tier_usd": by_tier_usd,
            "deployed": deployed, "idle": round(total - deployed, 2),
            "n_pools": len(allocations)}


# ---------------------------------------------------------------------------
# SELF TEST (no network)
# ---------------------------------------------------------------------------
def run_self_test():
    print("=== self-test: portfolio allocator ===")
    recs = [
        {"symbol": "A1", "tier": "A", "status": "OK", "resolve_status": "OK",
         "composite_score": 100, "yield_cover": 10, "range_pct": 12, "wash_flag": False},
        {"symbol": "A2", "tier": "A", "status": "OK", "resolve_status": "OK",
         "composite_score": 50, "yield_cover": 5, "range_pct": 10, "wash_flag": False},
        {"symbol": "A3", "tier": "A", "status": "OK", "resolve_status": "OK",
         "composite_score": 25, "yield_cover": 2, "range_pct": 8, "wash_flag": False},
        {"symbol": "A4", "tier": "A", "status": "OK", "resolve_status": "OK",
         "composite_score": 10, "yield_cover": 2, "range_pct": 8, "wash_flag": False},
        {"symbol": "B1", "tier": "B", "status": "OK", "resolve_status": "OK",
         "composite_score": 40, "yield_cover": 3, "range_pct": 20, "wash_flag": False},
        {"symbol": "WASH", "tier": "B", "status": "OK", "resolve_status": "OK",
         "composite_score": 999, "yield_cover": 50, "wash_flag": True},
        {"symbol": "WEAK", "tier": "B", "status": "OK", "resolve_status": "OK",
         "composite_score": 5, "yield_cover": 0.5, "wash_flag": False},
    ]
    out = allocate(recs, total=10000)
    syms = [a["symbol"] for a in out["allocations"]]
    assert "WASH" not in syms and "WEAK" not in syms, syms      # gated out
    assert "A4" not in syms, "tier A capped at 3"               # A capped
    a_usd = sum(a["usd"] for a in out["allocations"] if a["tier"] == "A")
    b_usd = sum(a["usd"] for a in out["allocations"] if a["tier"] == "B")
    assert abs(a_usd - 7000) < 1 and abs(b_usd - 3000) < 1, (a_usd, b_usd)
    # higher score gets more within tier
    aa = {a["symbol"]: a["usd"] for a in out["allocations"]}
    assert aa["A1"] > aa["A2"] > aa["A3"]
    assert abs(out["deployed"] - 10000) < 1 and out["n_pools"] == 4
    # redistribution: no B picks -> A gets everything
    out2 = allocate([r for r in recs if r["tier"] == "A"][:3], total=10000)
    assert abs(sum(a["usd"] for a in out2["allocations"]) - 10000) < 1
    print("ALL SELF-TESTS PASSED")


# ---------------------------------------------------------------------------
# RENDER
# ---------------------------------------------------------------------------
def render_md(out, total):
    L = [f"# LP portfolio allocation (paper, base {total:.0f}U)",
         f"_generated {datetime.now(timezone.utc).isoformat()}_\n",
         f"deployed {out['deployed']:.0f}U / idle {out['idle']:.0f}U across {out['n_pools']} pools; "
         f"by tier {out['by_tier_usd']}\n",
         "| tier | symbol | project | pool | ±range | USD | yield_cover | fee_apr | reward_apr | score | flags |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for a in out["allocations"]:
        rng = f"±{a['range_pct']:.1f}%" if a.get("range_pct") else "?"
        yc = a.get("yield_cover")
        ycs = "inf" if yc in (None, "inf") else (f"{float(yc):.1f}" if isinstance(yc, (int, float)) else str(yc))
        flags = "⚠below-min" if a.get("below_min") else ""
        L.append(f"| {a['tier']} | {a.get('symbol')} | {(a.get('project') or '')[:10]} | "
                 f"`{(a.get('pool') or '')[:10]}…` | {rng} | {a['usd']:.0f} | {ycs} | "
                 f"{_f(a.get('fee_apr_onchain'))} | {_f(a.get('reward_apr'))} | {_f(a.get('composite_score'))} | {flags} |")
    return "\n".join(L) + "\n"


def _f(v):
    return "-" if v is None else (f"{v:.1f}" if isinstance(v, (int, float)) else str(v))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ranked", help="bridge resolve_and_rank.json")
    ap.add_argument("--total", type=float, default=DEFAULT_TOTAL)
    ap.add_argument("--out", default=None)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        run_self_test()
        return
    if not args.ranked:
        ap.error("--ranked required (or --self-test)")

    records = json.load(open(args.ranked))
    out = allocate(records, total=args.total)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    d = args.out or os.path.join(_ROOT, "reports", "lp_portfolio_allocator", stamp)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "allocation.md"), "w") as f:
        f.write(render_md(out, args.total))
    with open(os.path.join(d, "allocation.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"deployed {out['deployed']:.0f}/{args.total:.0f} across {out['n_pools']} pools; by tier {out['by_tier_usd']}")
    for a in out["allocations"]:
        print(f"  [{a['tier']}] {a.get('symbol'):16s} {a['usd']:7.0f}U  ±{a.get('range_pct')}%  score {a.get('composite_score')}")
    print(f"wrote {d}/")


if __name__ == "__main__":
    main()
