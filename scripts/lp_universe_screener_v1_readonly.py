#!/usr/bin/env python3
"""
lp_universe_screener_v1_readonly.py  (READ-ONLY research)

STAGE 1 of the LP pool-selection funnel: a whole-network screen that uses a DeFi
yield AGGREGATOR (DefiLlama yields) instead of brute-force on-chain scanning, so
it costs ZERO RPC. It narrows ~2500 Base pools down to a ranked, tier-classified
shortlist of candidates — which Stage 2 (lp_tier_range_policy, on-chain swaps)
then validates and refines.

Why aggregator-first: DefiLlama hands us per-pool fee APR (apyBase), EMISSIONS
APR (apyReward), TVL, 1d/7d volume, 30d-mean APR, their sigma, IL-risk flag and
reward tokens — in one free, keyless call. Computing that on-chain for the whole
chain would be enormous RPC. We spend RPC only on the shortlist (Stage 2/3).

IMPORTANT: aggregator numbers are LEADS, not truth. APR/volume can be stale or
gamed (wash volume, incentive farms showing 400%+ apyReward). The on-chain Stage 2
cross-check (real swaps vs reported volume, our fee_cover) is what filters hype.
Aggregator content is treated as DATA, never as instructions.

NO wallet / sign / broadcast / chain writes. NO RPC (pure HTTP GET of public data).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

DEFILLAMA_POOLS_URL = "https://yields.llama.fi/pools"
# CLMM projects whose on-chain swaps Stage 2 (V3 Swap topic) can replay.
DEFAULT_PROJECTS = ("aerodrome-slipstream", "uniswap-v3")
# Operator tier bands by headline APR (%).
TIER_BANDS = (("sub", 0.0, 30.0), ("A", 30.0, 80.0), ("B", 80.0, 800.0), ("C", 800.0, float("inf")))

# Asset-quality tiering (the operator's Tier A = STABLE BLUE CHIPS, not just "high APR").
# Tier is really about asset SAFETY; APR is a symptom. So classify by which legs are
# major (blue-chip / major-stable / major-LST-or-BTC) tokens, by symbol ticker.
MAJOR_STABLES = {
    "USDC", "USDBC", "USDT", "DAI", "EURC", "GHO", "USDS", "USR", "MSUSD",
    "SUSDC", "SUSDS", "USD+", "DOLA", "CRVUSD",
}
MAJOR_BLUE = {
    "WETH", "ETH", "CBBTC", "TBTC", "LBTC", "WBTC", "CBETH", "WSTETH", "WEETH",
    "RETH", "EZETH", "SUPEROETHB", "MSETH", "WRSETH",
}
MAJOR_TOKENS = MAJOR_STABLES | MAJOR_BLUE


def split_symbol_legs(symbol):
    """'WETH-USDC' -> ['WETH','USDC']; tolerant of None / odd formats."""
    if not symbol or not isinstance(symbol, str):
        return []
    return [s.strip().upper() for s in symbol.split("-") if s.strip()]


def classify_tier_by_quality(symbol):
    """Asset-safety tier from the pool's token legs (NOT from APR).

    both legs major -> 'A' (blue-chip / stable pair)
    exactly one leg major -> 'B' (one risky leg)
    neither / unparseable -> 'C' (exotic, treat as degen)
    """
    legs = split_symbol_legs(symbol)
    if len(legs) != 2:
        return "C"
    n_major = sum(1 for leg in legs if leg in MAJOR_TOKENS)
    if n_major == 2:
        return "A"
    if n_major == 1:
        return "B"
    return "C"

# Default gates (all CLI-tunable).
DEFAULTS = dict(
    min_tvl=500_000.0,        # capacity + not-easily-rugged
    min_vol1d=50_000.0,       # some real flow
    suspect_reward_apr=300.0, # apyReward above this => likely incentive-farm/wash
    suspect_vol_tvl=20.0,     # daily volume > 20x TVL => wash-volume suspect
)

REWARD_PERSISTENCE_MIN_HOURS = 6.0
REWARD_PERSISTENCE_TRUSTED_HOURS = 24.0


# ---------------------------------------------------------------------------
# PURE FUNCTIONS (unit-tested, no network)
# ---------------------------------------------------------------------------
def parse_pool_meta(meta):
    """'CL50 - 0.05%' -> (tick_spacing=50, fee_tier=0.0005). Best-effort.

    Returns (tick_spacing|None, fee_tier|None). Handles uniswap-v3 metas like
    '0.3%' (no CL prefix) and None.
    """
    ts = fee = None
    if not meta:
        return ts, fee
    m = re.search(r"CL(\d+)", meta)
    if m:
        ts = int(m.group(1))
    m = re.search(r"([\d.]+)\s*%", meta)
    if m:
        fee = float(m.group(1)) / 100.0
    return ts, fee


def headline_apr(p):
    """Stable headline yield: prefer 30d-mean APR, else apyBase+apyReward."""
    base = p.get("apyBase") or 0.0
    rew = p.get("apyReward") or 0.0
    mean30 = p.get("apyMean30d")
    if mean30 is not None:
        return float(mean30)
    return float(base) + float(rew)


def total_apr_now(p):
    return float(p.get("apyBase") or 0.0) + float(p.get("apyReward") or 0.0)


def reward_persistence_gate(p, *, min_hours=REWARD_PERSISTENCE_MIN_HOURS,
                            trusted_hours=REWARD_PERSISTENCE_TRUSTED_HOURS):
    """Return the fail-closed RewardPersistence decision for a pool.

    `reward_high_duration` is the canonical input (hours); the explicit
    `reward_high_duration_hours` spelling is also accepted.  A reward-bearing
    pool with missing/invalid evidence is SHADOW-only and its reward gets zero
    scoring weight.  Fee-only pools remain compatible because persistence is
    not applicable.  Between 6h and 24h the reward receives a linear credibility
    haircut; at 24h it is fully trusted per PRD v1 section 16.
    """
    raw_reward = p.get("apyReward")
    if raw_reward is None:
        raw_reward = p.get("reward_apr", 0.0)
    try:
        reward_apr = float(raw_reward or 0.0)
    except (TypeError, ValueError):
        reward_apr = math.nan
    if not math.isfinite(reward_apr):
        # Corrupt explicit reward evidence is not equivalent to "no reward".
        return {
            "entry_eligible": False,
            "status": "INVALID_REWARD_FAIL_CLOSED",
            "duration_hours": None,
            "score_factor": 0.0,
            "reason": "REWARD_APR_INVALID",
        }
    if reward_apr <= 0.0:
        return {
            "entry_eligible": True,
            "status": "NOT_APPLICABLE",
            "duration_hours": None,
            "score_factor": 1.0,
            "reason": None,
        }

    raw_duration = p.get("reward_high_duration_hours")
    if raw_duration is None:
        raw_duration = p.get("reward_high_duration")
    if raw_duration is None:
        return {
            "entry_eligible": False,
            "status": "MISSING_FAIL_CLOSED",
            "duration_hours": None,
            "score_factor": 0.0,
            "reason": "REWARD_PERSISTENCE_MISSING",
        }
    try:
        duration = float(raw_duration)
    except (TypeError, ValueError):
        duration = -1.0
    if not math.isfinite(duration) or duration < 0.0:
        return {
            "entry_eligible": False,
            "status": "INVALID_FAIL_CLOSED",
            "duration_hours": None,
            "score_factor": 0.0,
            "reason": "REWARD_PERSISTENCE_INVALID",
        }
    if duration < float(min_hours):
        return {
            "entry_eligible": False,
            "status": "TOO_YOUNG_SHADOW_ONLY",
            "duration_hours": duration,
            "score_factor": 0.0,
            "reason": "REWARD_PERSISTENCE_LT_6H",
        }
    if duration < float(trusted_hours):
        return {
            "entry_eligible": True,
            "status": "MINIMUM_6H",
            "duration_hours": duration,
            "score_factor": duration / float(trusted_hours),
            "reason": None,
        }
    return {
        "entry_eligible": True,
        "status": "TRUSTED_24H",
        "duration_hours": duration,
        "score_factor": 1.0,
        "reason": None,
    }


def classify_tier_by_apr(apr):
    for name, lo, hi in TIER_BANDS:
        if lo <= apr < hi:
            return name
    return "sub"


def is_suspect(p, *, suspect_reward_apr, suspect_vol_tvl):
    """Flag likely wash-volume / incentive-farm pools (need extra on-chain scrutiny)."""
    reasons = []
    rew = p.get("apyReward") or 0.0
    if rew >= suspect_reward_apr:
        reasons.append(f"apyReward {rew:.0f}% (incentive-farm?)")
    tvl = p.get("tvlUsd") or 0.0
    vol = p.get("volumeUsd1d") or 0.0
    if tvl > 0 and vol / tvl >= suspect_vol_tvl:
        reasons.append(f"vol/TVL {vol/tvl:.0f}x (wash?)")
    if (p.get("apyBase") is None) and (p.get("apyReward") or 0) > 0:
        reasons.append("no fee APR (reward-only)")
    return reasons


def passes_gates(p, *, min_tvl, min_vol1d):
    """Coarse universe gates. Returns (ok, reason)."""
    tvl = p.get("tvlUsd") or 0.0
    if tvl < min_tvl:
        return False, f"TVL {tvl:.0f} < {min_tvl:.0f}"
    vol = p.get("volumeUsd1d")
    if vol is not None and vol < min_vol1d:
        return False, f"vol1d {vol:.0f} < {min_vol1d:.0f}"
    if total_apr_now(p) <= 0 and headline_apr(p) <= 0:
        return False, "no yield"
    return True, "ok"


def score_pool(p):
    """Provisional Stage-1 score = headline APR discounted for instability.

    Uses 30d-mean as the anchor; if the current spot APR is far above the 30d
    mean it's a spike (discount); persistence (mean near or above spot) scores
    full. This is a LEAD score; Stage 2 fee_cover is the real edge metric.
    """
    persistence_gate = reward_persistence_gate(p)
    base = float(p.get("apyBase") or 0.0)
    reward = float(p.get("apyReward") or 0.0)
    adjusted_spot = base + reward * persistence_gate["score_factor"]
    # Never let a stale 30d headline exceed what the current, persistence-
    # adjusted fee+reward observation supports.  This is the Reward Decay
    # no-extrapolation rule from PRD v2.1 section 12.4.
    h = min(headline_apr(p), adjusted_spot) if reward > 0.0 else headline_apr(p)
    spot = total_apr_now(p)
    if spot > 0:
        persistence = min(1.0, h / spot)  # mean<spot => spike => <1
    else:
        persistence = 1.0
    return h * (0.5 + 0.5 * persistence)


def assess(p, gates):
    ts, fee = parse_pool_meta(p.get("poolMeta"))
    h = headline_apr(p)
    tier = classify_tier_by_apr(h)
    ok, reason = passes_gates(p, min_tvl=gates["min_tvl"], min_vol1d=gates["min_vol1d"])
    suspect = is_suspect(p, suspect_reward_apr=gates["suspect_reward_apr"],
                         suspect_vol_tvl=gates["suspect_vol_tvl"])
    persistence = reward_persistence_gate(p)
    entry_block_reasons = []
    if not persistence["entry_eligible"]:
        entry_block_reasons.append(persistence["reason"])
    return {
        "symbol": p.get("symbol"), "project": p.get("project"),
        "llama_pool_id": p.get("pool"), "poolMeta": p.get("poolMeta"),
        "tick_spacing": ts, "fee_tier": fee,
        "underlyingTokens": p.get("underlyingTokens"),
        "rewardTokens": p.get("rewardTokens"),
        "tvlUsd": p.get("tvlUsd"),
        "apyBase": p.get("apyBase"), "apyReward": p.get("apyReward"),
        "apyMean30d": p.get("apyMean30d"), "headline_apr": round(h, 2),
        "volumeUsd1d": p.get("volumeUsd1d"), "sigma": p.get("sigma"),
        "ilRisk": p.get("ilRisk"), "stablecoin": p.get("stablecoin"),
        "tier": tier, "tier_quality": classify_tier_by_quality(p.get("symbol")),
        "score": round(score_pool(p), 2),
        "gate_ok": ok, "gate_reason": reason,
        "suspect": suspect,
        "entry_eligible": bool(ok and persistence["entry_eligible"]),
        "entry_block_reasons": entry_block_reasons,
        "reward_high_duration": persistence["duration_hours"],
        "reward_persistence_status": persistence["status"],
        "reward_persistence_score": round(float(persistence["score_factor"]), 4),
        "reward_persistence_semantics": (
            "reward-bearing missing/invalid data fail closed; <6h shadow-only; "
            "6h minimum with haircut; >=24h trusted; fee-only not applicable"
        ),
    }


# ---------------------------------------------------------------------------
# NETWORK (HTTP only)
# ---------------------------------------------------------------------------
def fetch_pools(cache_path=None, use_cache=False):
    if use_cache and cache_path and os.path.exists(cache_path):
        with open(cache_path) as f:
            return json.load(f)
    req = urllib.request.Request(
        DEFILLAMA_POOLS_URL,
        headers={"User-Agent": "lpbot-research/1.0", "accept": "application/json"})
    data = json.loads(urllib.request.urlopen(req, timeout=60).read()).get("data", [])
    if cache_path:
        with open(cache_path, "w") as f:
            json.dump(data, f)
    return data


# ---------------------------------------------------------------------------
# SELF TEST (no network)
# ---------------------------------------------------------------------------
def run_self_test():
    print("=== self-test: universe screener ===")
    assert parse_pool_meta("CL50 - 0.05%") == (50, 0.0005)
    assert parse_pool_meta("CL100 - 0.25%") == (100, 0.0025)
    assert parse_pool_meta("0.3%") == (None, 0.003)
    assert parse_pool_meta(None) == (None, None)
    assert classify_tier_by_apr(50) == "A"
    assert classify_tier_by_apr(120) == "B"
    assert classify_tier_by_apr(1500) == "C"
    assert classify_tier_by_apr(10) == "sub"
    sus = is_suspect({"apyReward": 480.0, "tvlUsd": 1e6, "volumeUsd1d": 1e5, "apyBase": 1.0},
                     suspect_reward_apr=300, suspect_vol_tvl=20)
    assert sus and "incentive" in sus[0]
    ok, _ = passes_gates({"tvlUsd": 1e6, "volumeUsd1d": 1e6, "apyBase": 30},
                         min_tvl=5e5, min_vol1d=5e4)
    assert ok
    bad, _ = passes_gates({"tvlUsd": 1e4, "volumeUsd1d": 1e6, "apyBase": 30},
                          min_tvl=5e5, min_vol1d=5e4)
    assert not bad
    # spike discounted vs persistent
    spike = score_pool({"apyBase": 100, "apyReward": 0, "apyMean30d": 20})
    persist = score_pool({"apyBase": 100, "apyReward": 0, "apyMean30d": 100})
    assert persist > spike
    print("ALL SELF-TESTS PASSED")


# ---------------------------------------------------------------------------
# RENDER
# ---------------------------------------------------------------------------
def _fmt(results, gates, n_total, n_base):
    out = [f"# LP universe screener (Stage 1, DefiLlama, 0 RPC)",
           f"_generated {datetime.now(timezone.utc).isoformat()}_\n",
           f"universe {n_total} pools; Base CLMM {n_base}; gates: "
           f"TVL>={gates['min_tvl']:.0f}, vol1d>={gates['min_vol1d']:.0f}.\n",
           "headline_apr = 30d-mean (fallback fee+reward). Stage 2 validates on-chain.\n"]
    for tier in ("A", "B", "C"):
        rows = [r for r in results if r["tier"] == tier and r["gate_ok"]]
        rows.sort(key=lambda r: -r["score"])
        out.append(f"## Tier {tier} (by APR) — {len(rows)} candidates")
        out.append("| symbol | qual | project | fee | TVL($M) | apyBase | apyReward | reward persistence | head_APR | vol1d($M) | score | flags |")
        out.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in rows[:12]:
            fee = f"{r['fee_tier']*100:.2f}%" if r['fee_tier'] else "?"
            tvl = (r['tvlUsd'] or 0)/1e6
            vol = (r['volumeUsd1d'] or 0)/1e6
            ab = "n/a" if r['apyBase'] is None else f"{r['apyBase']:.1f}"
            ar = "n/a" if r['apyReward'] is None else f"{r['apyReward']:.1f}"
            flags = "⚠" + ";".join(r["suspect"]) if r["suspect"] else ""
            if not r["entry_eligible"]:
                flags = (flags + ";" if flags else "⚠") + ";".join(r["entry_block_reasons"])
            qmark = "" if r.get("tier_quality") == tier else f"!{r.get('tier_quality')}"
            out.append(f"| {r['symbol']} | {r.get('tier_quality')}{qmark} | {r['project'][:10]} | {fee} | {tvl:.1f} | {ab} | {ar} "
                       f"| {r['reward_persistence_status']} | {r['headline_apr']:.1f} | {vol:.1f} | {r['score']:.0f} | {flags} |")
        out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--projects", nargs="*", default=list(DEFAULT_PROJECTS))
    ap.add_argument("--min-tvl", type=float, default=DEFAULTS["min_tvl"])
    ap.add_argument("--min-vol1d", type=float, default=DEFAULTS["min_vol1d"])
    ap.add_argument("--suspect-reward-apr", type=float, default=DEFAULTS["suspect_reward_apr"])
    ap.add_argument("--suspect-vol-tvl", type=float, default=DEFAULTS["suspect_vol_tvl"])
    ap.add_argument("--chain", default="Base")
    ap.add_argument("--top", type=int, default=10, help="emit top-N (across tiers) candidate list")
    ap.add_argument("--cache", default=None, help="path to cache the raw payload")
    ap.add_argument("--use-cache", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.self_test:
        run_self_test()
        return

    gates = dict(min_tvl=args.min_tvl, min_vol1d=args.min_vol1d,
                 suspect_reward_apr=args.suspect_reward_apr,
                 suspect_vol_tvl=args.suspect_vol_tvl)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = args.out or os.path.join(_ROOT, "reports", "lp_universe_screener", stamp)
    os.makedirs(out_dir, exist_ok=True)
    cache = args.cache or os.path.join(out_dir, "defillama_pools_raw.json")

    pools = fetch_pools(cache_path=cache, use_cache=args.use_cache)
    n_total = len(pools)
    base = [p for p in pools if p.get("chain") == args.chain and p.get("project") in args.projects]
    results = [assess(p, gates) for p in base]

    passed = [r for r in results if r["gate_ok"]]
    passed.sort(key=lambda r: -r["score"])
    print(f"universe {n_total}; {args.chain} CLMM {len(base)}; passed gates {len(passed)}")
    for r in passed[:args.top]:
        flags = (" ⚠" + ";".join(r["suspect"])) if r["suspect"] else ""
        print(f"  [{r['tier']}] {r['symbol']:16s} {r['project'][:18]:18s} "
              f"head_APR {r['headline_apr']:7.1f}% TVL ${ (r['tvlUsd'] or 0)/1e6:6.1f}M score {r['score']:6.1f}{flags}")

    # Young/missing reward evidence stays in screen.json for Shadow observation,
    # but it cannot silently flow into Stage 2 as an ENTER candidate.
    enterable = [r for r in passed if r["entry_eligible"]]
    ranked = sorted(enterable, key=lambda r: (bool(r["suspect"]), -r["score"]))
    candidates = ranked[:args.top]

    with open(os.path.join(out_dir, "screen.md"), "w") as f:
        f.write(_fmt(results, gates, n_total, len(base)))
    with open(os.path.join(out_dir, "screen.json"), "w") as f:
        json.dump(results, f, indent=2)
    with open(os.path.join(out_dir, "stage2_candidates.json"), "w") as f:
        json.dump(candidates, f, indent=2)
    print(f"\nwrote {out_dir}/ (screen.md, screen.json, stage2_candidates.json — {len(candidates)} candidates)")


if __name__ == "__main__":
    main()
