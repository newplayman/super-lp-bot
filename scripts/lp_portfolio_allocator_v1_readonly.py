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
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.lp_netcover_engine_v1_readonly import (  # noqa: E402
    NETCOVER_SHADOW,
    absolute_profit_gate,
    position_cap_usd,
)
from scripts.lp_universe_screener_v1_readonly import reward_persistence_gate  # noqa: E402

DEFAULT_TOTAL = 10000.0
DEFAULT_TIER_WEIGHTS = {"A": 0.70, "B": 0.30, "C": 0.0}
DEFAULT_MAX_POOLS = {"A": 3, "B": 2, "C": 0}
# M1 commander's capital tier is one 50--60U position.  The lower bound is an
# output annotation threshold only; it does not bypass or weaken any runtime
# NetCover, absolute-profit, or position-cap gate.
M1_MIN_POSITION_USD = 50.0
M1_MIN_POSITION_EVIDENCE = "reports/lp_cost_sensitivity/20260808_172541"
DEFAULT_MIN_POOL_USD = M1_MIN_POSITION_USD


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
    # Defense in depth: Stage 1 normally supplies entry_eligible, but allocator
    # independently recomputes persistence from raw evidence.  Reward-bearing
    # legacy records without duration evidence fail closed; fee-only legacy
    # records remain compatible (persistence is NOT_APPLICABLE).
    if rec.get("entry_eligible") is False:
        return False
    if not reward_persistence_gate(rec)["entry_eligible"]:
        return False
    score = rec.get("composite_score")
    if score is None or float(score) <= 0.0:
        return False
    yc = rec.get("yield_cover")
    try:
        ycv = math.inf if (yc in (None, "inf") or (isinstance(yc, float) and math.isinf(yc))) else float(yc)
    except (TypeError, ValueError):
        ycv = 0.0
    if ycv < 1.0:
        return False
    # Gross/yield cover remains diagnostic.  When a full-cost NetCover value is
    # present it must independently pass the Shadow threshold.
    if rec.get("netcover") is not None:
        try:
            if float(rec["netcover"]) < NETCOVER_SHADOW:
                return False
        except (TypeError, ValueError):
            return False
    return True


def _tier_of(rec: Mapping[str, Any]) -> str:
    return str(rec.get("tier") or rec.get("tier_hint") or "").upper()


def rank_metric(rec: Mapping[str, Any]) -> float:
    """Ranking/weighting metric: reward-adjusted net APR (income - IL), UNCAPPED.

    This fixes the composite_score 100-saturation that flattened the top: among
    (already farm/wash-filtered) pools, higher real net APR ranks higher and gives
    discrimination. Falls back to composite_score if APR fields are absent.
    """
    inc = rec.get("total_income_apr")
    il = rec.get("il_apr")
    if inc is not None:
        try:
            income = float(inc)
            reward = float(rec.get("reward_apr", rec.get("apyReward", 0.0)) or 0.0)
            persistence = reward_persistence_gate(rec)
            # total_income_apr may have been computed before persistence was
            # known. Replace its reward component with the credibility-adjusted
            # current reward so a stale high APR cannot dominate allocation.
            income = income - reward + reward * float(persistence["score_factor"])
            return max(income - float(il or 0.0), 0.0)
        except (TypeError, ValueError):
            pass
    try:
        return max(float(rec.get("composite_score") or 0.0), 0.0)
    except (TypeError, ValueError):
        return 0.0


def select_per_tier(records, max_pools, *, require_stable=False):
    """Group enterable records by tier, keep top-N by rank_metric per tier."""
    by_tier: Dict[str, List[Mapping[str, Any]]] = {}
    for r in records:
        if not is_enterable(r):
            continue
        if require_stable and not r.get("stable", True):
            continue
        by_tier.setdefault(_tier_of(r), []).append(r)
    for t in by_tier:
        by_tier[t].sort(key=lambda r: -rank_metric(r))
        cap = max_pools.get(t, 0)
        by_tier[t] = by_tier[t][:cap] if cap else []
    return by_tier


def _weight_within(selected: Sequence[Mapping[str, Any]]) -> List[float]:
    scores = [rank_metric(r) for r in selected]
    s = sum(scores)
    n = len(selected)
    if n == 0:
        return []
    if s <= 0:
        return [1.0 / n] * n
    return [x / s for x in scores]


def _runtime_gate(rec: Mapping[str, Any]):
    """Return (annotated_record, rejection) for allocator's final hard gates."""
    required = {
        "pool_tvl": rec.get("tvlUsd", rec.get("pool_tvl_usd")),
        "active_liquidity_notional": rec.get("active_liquidity_notional_usd"),
        "tier_configured_max": rec.get("tier_configured_max_usd"),
        "expected_net_profit_h": rec.get("expected_net_profit_h"),
        "round_trip_cost": rec.get("round_trip_cost_usd"),
        "netcover": rec.get("netcover", rec.get("netcover_ratio")),
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        return None, {
            "symbol": rec.get("symbol"),
            "pool": rec.get("resolved_pool") or rec.get("pool"),
            "reason": "RUNTIME_GATE_INPUT_MISSING",
            "missing": missing,
        }
    try:
        cover = float(required["netcover"])
    except (TypeError, ValueError):
        cover = -math.inf
    if not math.isfinite(cover) or cover < NETCOVER_SHADOW:
        return None, {
            "symbol": rec.get("symbol"),
            "pool": rec.get("resolved_pool") or rec.get("pool"),
            "reason": "NETCOVER_BELOW_SHADOW",
            "netcover": required["netcover"],
        }
    try:
        cap = position_cap_usd(
            required["tier_configured_max"], required["pool_tvl"],
            required["active_liquidity_notional"],
        )
        profit = absolute_profit_gate(
            required["expected_net_profit_h"], required["round_trip_cost"],
        )
    except ValueError as exc:
        return None, {
            "symbol": rec.get("symbol"),
            "pool": rec.get("resolved_pool") or rec.get("pool"),
            "reason": "RUNTIME_GATE_INPUT_INVALID",
            "detail": str(exc),
        }
    if not profit.allowed:
        return None, {
            "symbol": rec.get("symbol"),
            "pool": rec.get("resolved_pool") or rec.get("pool"),
            "reason": profit.reason,
            "expected_net_profit_h": profit.expected_net_profit_usd,
            "required_profit_usd": profit.required_profit_usd,
        }
    annotated = dict(rec)
    annotated["position_cap_usd"] = cap
    annotated["absolute_profit_gate"] = {
        "allowed": True,
        "expected_net_profit_h": profit.expected_net_profit_usd,
        "required_profit_usd": profit.required_profit_usd,
    }
    return annotated, None


def allocate(records, *, total=DEFAULT_TOTAL, tier_weights=None, max_pools=None,
             min_pool_usd=DEFAULT_MIN_POOL_USD, require_stable=False,
             enforce_runtime_gates=True):
    """Allocate `total` across enterable pools by tier weight then rank_metric.

    Tier weights for tiers with NO enterable pools are redistributed pro-rata to
    the tiers that do have picks (so we don't leave the book under-deployed).
    require_stable: only include pools flagged stable (multi-window) — set when a
    stability map has been merged in via merge_stability().
    Returns {allocations:[...], by_tier_usd:{}, deployed, idle, n_pools}.
    """
    try:
        min_pool_usd = float(min_pool_usd)
    except (TypeError, ValueError) as exc:
        raise ValueError("min_pool_usd must be finite and positive") from exc
    if not math.isfinite(min_pool_usd) or min_pool_usd <= 0:
        raise ValueError("min_pool_usd must be finite and positive")
    tier_weights = dict(tier_weights or DEFAULT_TIER_WEIGHTS)
    max_pools = dict(max_pools or DEFAULT_MAX_POOLS)
    skipped: List[Dict[str, Any]] = []
    eligible = list(records)
    if enforce_runtime_gates:
        eligible = []
        for rec in records:
            annotated, rejection = _runtime_gate(rec)
            if rejection:
                skipped.append(rejection)
            else:
                eligible.append(annotated)
    by_tier = select_per_tier(eligible, max_pools, require_stable=require_stable)

    active = {t: w for t, w in tier_weights.items() if w > 0 and by_tier.get(t)}
    wsum = sum(active.values())
    if wsum <= 0:
        return {"allocations": [], "by_tier_usd": {}, "deployed": 0.0,
                "idle": total, "n_pools": 0, "skipped": skipped,
                "runtime_gates_enforced": enforce_runtime_gates,
                "config": {
                    "min_position_profile": "M1_1x50_60U",
                    "min_position_usd": min_pool_usd,
                    "min_position_evidence": M1_MIN_POSITION_EVIDENCE,
                }}
    norm = {t: w / wsum for t, w in active.items()}

    allocations: List[Dict[str, Any]] = []
    by_tier_usd: Dict[str, float] = {}
    for t, frac in norm.items():
        tier_usd = total * frac
        sel = by_tier[t]
        weights = _weight_within(sel)
        for r, w in zip(sel, weights):
            proposed_usd = tier_usd * w
            cap = r.get("position_cap_usd") if enforce_runtime_gates else None
            usd = min(proposed_usd, float(cap)) if cap is not None else proposed_usd
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
                "position_cap_usd": round(float(cap), 2) if cap is not None else None,
                "proposed_usd_before_runtime_cap": round(proposed_usd, 2),
                "absolute_profit_gate": r.get("absolute_profit_gate"),
            })
    allocations.sort(key=lambda a: (a["tier"], -a["usd"]))
    deployed = round(sum(a["usd"] for a in allocations), 2)
    # flag sub-minimum positions (capital too thin to bother / monitor)
    for a in allocations:
        a["below_min"] = a["usd"] < min_pool_usd
    by_tier_usd = {
        tier: round(sum(a["usd"] for a in allocations if a["tier"] == tier), 2)
        for tier in norm
    }
    return {"allocations": allocations, "by_tier_usd": by_tier_usd,
            "deployed": deployed, "idle": round(total - deployed, 2),
            "n_pools": len(allocations), "skipped": skipped,
            "runtime_gates_enforced": enforce_runtime_gates,
            "config": {
                "min_position_profile": "M1_1x50_60U",
                "min_position_usd": min_pool_usd,
                "min_position_evidence": M1_MIN_POSITION_EVIDENCE,
            }}


# ---------------------------------------------------------------------------
# SELF TEST (no network)
# ---------------------------------------------------------------------------
def merge_stability(records, stability_records):
    """Annotate bridge records with multi-window stability (by pool address).

    stability_records: list from lp_multiwindow_stability stability.json, each with
    'pool' and 'fee_cover_stability':{stable, enter_frac}. Adds rec['stable'] and
    rec['enter_frac']. Pools absent from the stability set get stable=False.
    """
    smap = {}
    for s in stability_records or []:
        pool = str(s.get("pool") or "").lower()
        st = s.get("fee_cover_stability") or {}
        smap[pool] = {"stable": bool(st.get("stable")), "enter_frac": st.get("enter_frac")}
    out = []
    for r in records:
        rr = dict(r)
        pool = str(rr.get("resolved_pool") or rr.get("pool") or "").lower()
        info = smap.get(pool)
        rr["stable"] = info["stable"] if info else False
        rr["enter_frac"] = info["enter_frac"] if info else None
        out.append(rr)
    return out


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
    out = allocate(recs, total=10000, enforce_runtime_gates=False)
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
    out2 = allocate(
        [r for r in recs if r["tier"] == "A"][:3], total=10000,
        enforce_runtime_gates=False,
    )
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


def _positive_usd(value):
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("must be a finite positive USD amount") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be a finite positive USD amount")
    return parsed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ranked", help="bridge resolve_and_rank.json")
    ap.add_argument("--stability", help="multiwindow stability.json (enables stability gate)")
    ap.add_argument("--require-stable", action="store_true",
                    help="only allocate to multi-window-stable pools (needs --stability)")
    ap.add_argument("--legacy-no-runtime-gates", action="store_true",
                    help="research compatibility only; bypass WP-04 hard runtime gates")
    ap.add_argument("--total", type=float, default=DEFAULT_TOTAL)
    ap.add_argument(
        "--min-position-usd", type=_positive_usd, default=M1_MIN_POSITION_USD,
        help=(
            "below-min annotation threshold (M1 default: 50U, supported by "
            "reports/lp_cost_sensitivity/20260808_172541)"
        ),
    )
    ap.add_argument("--out", default=None)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        run_self_test()
        return
    if not args.ranked:
        ap.error("--ranked required (or --self-test)")

    records = json.load(open(args.ranked))
    if args.stability:
        records = merge_stability(records, json.load(open(args.stability)))
    out = allocate(
        records, total=args.total, require_stable=args.require_stable,
        min_pool_usd=args.min_position_usd,
        enforce_runtime_gates=not args.legacy_no_runtime_gates,
    )
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
