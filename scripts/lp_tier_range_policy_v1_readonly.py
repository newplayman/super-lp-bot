#!/usr/bin/env python3
"""
lp_tier_range_policy_v1_readonly.py  (READ-ONLY research)

The decision layer that turns measured volatility + trend-regime into a concrete
per-pool LP range policy, and emits a replay/sim-ready config. Implements the
findings from the Tier-B Level-2 work (commits f5135d8 / 6c0e859):

  1. range_pct is VOL-SIZED: range = k*sigma_daily*sqrt(H)  (random-walk first
     passage). Wider H => fewer rebalances, lower fee density.
  2. WEEKLY-TIGHT (high capital efficiency) is gated on REGIME. In a calm /
     range-bound window, tighter range wins (2x fees > extra IL, 0 rebalances).
     In a TRENDING window, tightening backfires (IL dominates; rebalancing is
     path-dependent and hysteresis is worst). So:
        range-bound  -> weekly  (tight, H=7)   : capital efficiency
        neutral      -> H=14
        trending     -> monthly (wide,  H=30)  or AVOID for high-vol mid-caps
  3. Regime is measured by the Kaufman Efficiency Ratio (ER):
        ER = |log(p_end/p_start)| / sum|log(p_i/p_{i-1})|
     ER~1 => pure trend; ER~0 => pure chop/range-bound.

NO wallet / sign / broadcast / chain writes. RPC read of historical swaps only.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.lp_vol_range_sizer_v1_readonly import (  # noqa: E402
    BLOCKS_PER_DAY,
    DEFAULT_K,
    hourly_closes,
    daily_vol_from_closes,
    recommend_range_pct,
    expected_rebalances_per_month,
    latest_block,
)
from scripts.lp_tier_c_exit_feasibility_v1_readonly import fetch_pool_swaps  # noqa: E402
from scripts.lp_tier_b_level2_replay_v1_readonly import replay  # noqa: E402

# Regime thresholds on the efficiency ratio.
ER_RANGE_BOUND = 0.25   # ER below this => choppy / range-bound
ER_TRENDING = 0.50      # ER above this => directional / trending
# H targets (days between rebalances) per regime.
H_RANGE_BOUND = 7
H_NEUTRAL = 14
H_TRENDING = 30
# A high-vol trending mid-cap is an AVOID (IL risk swamps fees).
AVOID_SIGMA_DAILY = 0.06   # ~6%/day (annualized ~115%)
# Viability: fees must cover at least this multiple of structural IL.
FEE_COVER_MIN = 1.0
# Directional exposure (|entry->end| price move) that flags a net-long bet.
DIRECTIONAL_WARN_PCT = 15.0


# ---------------------------------------------------------------------------
# PURE FUNCTIONS (unit-tested, no network)
# ---------------------------------------------------------------------------
def efficiency_ratio(closes):
    """Kaufman Efficiency Ratio from hourly closes [(idx, price), ...].

    |net log move| / sum(|per-step log move|).  1.0 = pure trend, 0.0 = pure
    chop. None if < 2 prices or zero total path.
    """
    prices = [p for _, p in closes if p and p > 0]
    if len(prices) < 2:
        return None
    net = abs(math.log(prices[-1] / prices[0]))
    path = sum(abs(math.log(prices[i] / prices[i - 1]))
               for i in range(1, len(prices)) if prices[i] > 0 and prices[i - 1] > 0)
    if path <= 0:
        return None
    return net / path


def classify_regime(er):
    if er is None:
        return "unknown"
    if er < ER_RANGE_BOUND:
        return "range-bound"
    if er > ER_TRENDING:
        return "trending"
    return "neutral"


def choose_h(regime):
    return {"range-bound": H_RANGE_BOUND,
            "neutral": H_NEUTRAL,
            "trending": H_TRENDING}.get(regime, H_NEUTRAL)


def build_policy(sigma_daily, er, *, tier_hint="", k=DEFAULT_K):
    """Return the range policy dict for one pool.

    {regime, er, sigma_daily, H, range_pct, rebal_per_month, weekly_tight_allowed,
     action}  where action in {ENTER, ENTER_WIDE_ONLY, AVOID}.
    """
    regime = classify_regime(er)
    H = choose_h(regime)
    range_pct = recommend_range_pct(sigma_daily, H, k) if sigma_daily else None
    weekly_allowed = (regime == "range-bound")

    # Action: high-vol trending names are an AVOID (mid-cap IL trap); trending
    # otherwise -> wide-only; range-bound/neutral -> enter.
    if regime == "trending" and sigma_daily and sigma_daily >= AVOID_SIGMA_DAILY:
        action = "AVOID"
    elif regime == "trending":
        action = "ENTER_WIDE_ONLY"
    else:
        action = "ENTER"

    return {
        "regime": regime,
        "er": er,
        "sigma_daily": sigma_daily,
        "sigma_daily_pct": (sigma_daily * 100.0) if sigma_daily else None,
        "H_days": H,
        "range_pct": round(range_pct, 2) if range_pct is not None else None,
        "rebal_per_month": round(expected_rebalances_per_month(H), 2),
        "weekly_tight_allowed": weekly_allowed,
        "action": action,
    }


def fee_cover_ratio(fees_quote, il_quote):
    """fees / |structural IL|.  >=1 => fees beat IL.  inf if no IL.

    fees_quote >= 0, il_quote <= 0 (IL is a loss vs HODL). Returns None if no fee
    data. This isolates the STRUCTURAL viability of LPing (fees vs IL) from the
    DIRECTIONAL bet (holding the underlying), which is reported separately.
    """
    if fees_quote is None or il_quote is None:
        return None
    il_loss = -float(il_quote)
    if il_loss <= 0:
        return float("inf")
    return float(fees_quote) / il_loss


def finalize_action(policy, fee_cover, abs_move_pct, *, tier_hint="",
                    fee_cover_min=FEE_COVER_MIN,
                    directional_warn_pct=DIRECTIONAL_WARN_PCT):
    """Layer the viability screen on top of the ER/regime action.

    Structural gate: fees must cover IL (fee_cover >= fee_cover_min) or it's an
    AVOID regardless of regime. Directional gate: a large |move| flags a net-long
    bet — hard-AVOID for Tier A (should be ~market-neutral), a noted risk for B.
    Returns (action, reason).
    """
    base = policy["action"]
    if base.startswith("AVOID"):
        return base, "regime/vol: high-vol trend"
    if fee_cover is not None and fee_cover < fee_cover_min:
        return "AVOID_FEE<IL", f"fees cover only {fee_cover:.2f}x of IL"
    directional = abs_move_pct is not None and abs_move_pct >= directional_warn_pct
    if directional and str(tier_hint).upper().startswith("A"):
        return "AVOID_DIRECTIONAL", f"|move| {abs_move_pct:.1f}% too directional for Tier A"
    if directional:
        return base, f"OK structurally; directional risk |move| {abs_move_pct:.1f}% (Tier-B bet)"
    return base, "fees cover IL; range-appropriate"


# ---------------------------------------------------------------------------
# NETWORK
# ---------------------------------------------------------------------------
def assess_pool(cfg, blocks_back, k):
    pool = cfg["pool"]
    dec0, dec1 = int(cfg["dec0"]), int(cfg["dec1"])
    label = cfg.get("label", pool[:10])
    tip = latest_block()
    swaps = fetch_pool_swaps(pool, tip - int(blocks_back), tip, dec0, dec1)
    closes = hourly_closes(swaps)
    sigma_daily, n_ret = daily_vol_from_closes(closes)
    er = efficiency_ratio(closes)
    tier_hint = cfg.get("tier_hint", "")
    fee_tier = cfg.get("fee_tier")
    pol = build_policy(sigma_daily, er, tier_hint=tier_hint, k=k)

    # Viability screen: passive replay at the policy range over the SAME window
    # to get realized fees vs structural IL (fee_cover) and directional move.
    fees_pct = il_pct = net_pct = abs_move_pct = fee_cover = None
    window_days = round(blocks_back / BLOCKS_PER_DAY, 2)
    if pol["range_pct"] and fee_tier is not None and swaps:
        rep = replay(swaps, range_pct=pol["range_pct"], fee_tier=float(fee_tier),
                     dec0=dec0, dec1=dec1, mode="passive")
        if rep.get("net_pct") is not None:
            fees_pct = rep["fees_quote"] * 100.0
            il_pct = rep["il_quote"] * 100.0
            net_pct = rep["net_pct"]
            fee_cover = fee_cover_ratio(rep["fees_quote"], rep["il_quote"])
            ep, xp = rep["entry_price"], rep["end_price"]
            abs_move_pct = abs(xp / ep - 1.0) * 100.0 if ep else None
        # annualize realized fee yield for context
    fee_apr_pct = (fees_pct * 365.0 / window_days) if (fees_pct is not None and window_days) else None
    action, reason = finalize_action(pol, fee_cover, abs_move_pct, tier_hint=tier_hint)

    out = {
        "label": label, "pool": pool, "dec0": dec0, "dec1": dec1,
        "fee_tier": fee_tier, "tier_hint": tier_hint,
        "n_swaps": len(swaps), "n_hourly_closes": len(closes), "n_returns": n_ret,
        "window_days": window_days,
        **pol,
        "fees_pct": fees_pct, "il_pct": il_pct, "net_pct": net_pct,
        "fee_apr_pct": fee_apr_pct, "abs_move_pct": abs_move_pct,
        "fee_cover": (None if fee_cover is None else
                      (round(fee_cover, 2) if fee_cover != float("inf") else "inf")),
        "reason": reason,
    }
    out["action"] = action  # viability-refined action overrides the regime action
    return out


# ---------------------------------------------------------------------------
# SELF TEST (no network)
# ---------------------------------------------------------------------------
def run_self_test():
    print("=== self-test: tier range policy ===")
    # pure trend: monotonic up
    trend = [(i, 1.0 * (1.02 ** i)) for i in range(24)]
    er_t = efficiency_ratio(trend)
    assert er_t is not None and er_t > 0.95, er_t
    assert classify_regime(er_t) == "trending"
    # pure chop: alternate up/down, ends near start
    chop = [(i, 1.0 + (0.05 if i % 2 else -0.05)) for i in range(24)]
    er_c = efficiency_ratio(chop)
    assert er_c is not None and er_c < 0.25, er_c
    assert classify_regime(er_c) == "range-bound"
    # policy: range-bound allows weekly tight; trending high-vol avoids
    p_rb = build_policy(0.03, er_c)
    assert p_rb["weekly_tight_allowed"] and p_rb["H_days"] == H_RANGE_BOUND
    assert p_rb["action"] == "ENTER"
    p_tr = build_policy(0.08, er_t)  # high vol + trend
    assert not p_tr["weekly_tight_allowed"] and p_tr["action"] == "AVOID"
    p_tr_lo = build_policy(0.02, er_t)  # low vol + trend -> wide only
    assert p_tr_lo["action"] == "ENTER_WIDE_ONLY" and p_tr_lo["H_days"] == H_TRENDING
    # wider H => wider range
    assert recommend_range_pct(0.03, 30) > recommend_range_pct(0.03, 7)
    print(f"trend ER={er_t:.3f} -> {classify_regime(er_t)} ; chop ER={er_c:.3f} -> {classify_regime(er_c)}")
    print("ALL SELF-TESTS PASSED")


# ---------------------------------------------------------------------------
# RENDER + EMIT CONFIG
# ---------------------------------------------------------------------------
def _emit_replay_config(results):
    """Build a replay/sim-ready config from the policy (range = policy range)."""
    cfg = []
    for r in results:
        if str(r["action"]).startswith("AVOID") or r["range_pct"] is None:
            continue
        cfg.append({
            "pool": r["pool"], "dec0": r["dec0"], "dec1": r["dec1"],
            "fee_tier": r["fee_tier"], "range_pct": r["range_pct"],
            "label": f"{r['label']} [{r['regime']},H{r['H_days']}]",
            "regime": r["regime"], "action": r["action"],
            "weekly_tight_allowed": r["weekly_tight_allowed"],
        })
    return cfg


def _fmt_md(results, k):
    out = [f"# Tier range policy  (k={k})",
           f"_generated {datetime.now(timezone.utc).isoformat()}_\n",
           "range = vol-sized for regime H. ER = Kaufman efficiency ratio "
           "(1=trend, 0=chop). weekly-tight gated on range-bound regime; "
           "ENTER gated on fee_cover (fees/|IL|) >= 1.\n",
           "| pool | tier | σ_daily | ER | regime | ±range | fees% | IL% | net% | fee_cover | move% | action |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    def f2(v, suf=""):
        return "n/a" if v is None else f"{v:.2f}{suf}"
    for r in results:
        sd = f"{r['sigma_daily_pct']:.2f}%" if r.get('sigma_daily_pct') else "n/a"
        er = f"{r['er']:.2f}" if r.get('er') is not None else "n/a"
        rng = f"±{r['range_pct']:.1f}%" if r.get('range_pct') is not None else "n/a"
        out.append(f"| {r['label']} | {r['tier_hint']} | {sd} | {er} | {r['regime']} "
                   f"| {rng} | {f2(r.get('fees_pct'))} | {f2(r.get('il_pct'))} "
                   f"| {f2(r.get('net_pct'))} | {r.get('fee_cover')} | {f2(r.get('abs_move_pct'))} "
                   f"| **{r['action']}** |")
    out.append("")
    for r in results:
        out.append(f"- **{r['label']}** — {r['action']}: {r.get('reason','')}")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", help="JSON list of {pool,dec0,dec1,fee_tier,label,tier_hint}")
    ap.add_argument("--blocks-back", type=int, default=int(1.5 * BLOCKS_PER_DAY))
    ap.add_argument("--k", type=float, default=DEFAULT_K)
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
    for c in cfgs:
        try:
            r = assess_pool(c, args.blocks_back, args.k)
        except Exception as e:
            r = {"label": c.get("label", c.get("pool")), "pool": c.get("pool"),
                 "dec0": c.get("dec0"), "dec1": c.get("dec1"), "fee_tier": c.get("fee_tier"),
                 "tier_hint": c.get("tier_hint", ""), "regime": "unknown", "er": None,
                 "sigma_daily": None, "sigma_daily_pct": None, "H_days": None,
                 "range_pct": None, "rebal_per_month": None,
                 "weekly_tight_allowed": False, "action": f"ERROR: {e}", "n_swaps": 0}
        results.append(r)
        fc = r.get("fee_cover")
        print(f"{r['label']}: {r['regime']} ER={r['er'] if r['er'] is None else round(r['er'],2)} "
              f"σ={r['sigma_daily_pct'] and round(r['sigma_daily_pct'],2)}% ±{r['range_pct']}% "
              f"fees={None if r.get('fees_pct') is None else round(r['fees_pct'],2)}% "
              f"fee_cover={fc} net={None if r.get('net_pct') is None else round(r['net_pct'],2)}% "
              f"[{r['action']}]")

    replay_cfg = _emit_replay_config(results)
    out = args.out
    if out is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out = os.path.join(_ROOT, "reports", "lp_tier_range_policy", stamp)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "policy.md"), "w") as f:
        f.write(_fmt_md(results, args.k))
    with open(os.path.join(out, "policy.json"), "w") as f:
        json.dump(results, f, indent=2)
    with open(os.path.join(out, "replay_config.json"), "w") as f:
        json.dump(replay_cfg, f, indent=2)
    print(f"\nwrote {out}/  (policy.md, policy.json, replay_config.json — {len(replay_cfg)} pools enterable)")


if __name__ == "__main__":
    main()
