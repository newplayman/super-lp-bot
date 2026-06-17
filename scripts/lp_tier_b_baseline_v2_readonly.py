#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from statistics import median
from typing import Any, Dict, List

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.lp_tier_b_baseline_v1_readonly import (  # noqa: E402
    fee_apr_pct,
    classify_tier,
    realized_24h_net,
)

DEFAULT_INPUT = (
    "reports/strategy_evidence_r0_pool_discovery/"
    "20260611_031425/candidate_pools_raw.jsonl"
)


def apr_from_window(fee_tier_bps, volume_window, hours_in_window, tvl_usd) -> float:
    try:
        fee_tier_bps_f = float(fee_tier_bps)
        volume_window_f = float(volume_window)
        hours_in_window_f = float(hours_in_window)
        tvl_usd_f = float(tvl_usd)
    except (TypeError, ValueError):
        return 0.0

    if tvl_usd_f <= 0 or hours_in_window_f <= 0:
        return 0.0
    return (fee_tier_bps_f / 10000.0) * volume_window_f * (8760.0 / hours_in_window_f) / tvl_usd_f * 100.0


def fee_apr_multi(fee_tier_bps, vol_h1, vol_h6, vol_h24, tvl_usd) -> dict:
    return {
        "apr_h1": apr_from_window(fee_tier_bps, vol_h1, 1.0, tvl_usd),
        "apr_h6": apr_from_window(fee_tier_bps, vol_h6, 6.0, tvl_usd),
        "apr_h24": apr_from_window(fee_tier_bps, vol_h24, 24.0, tvl_usd),
    }


def is_sustained(apr_h1, apr_h6, apr_h24, max_ratio=3.0) -> bool:
    vals = [a for a in (apr_h1, apr_h6, apr_h24) if a > 0]
    if len(vals) < 2:
        return False
    try:
        max_ratio_f = float(max_ratio)
    except (TypeError, ValueError):
        return False
    lo = min(vals)
    hi = max(vals)
    if lo <= 0:
        return False
    return (hi / lo) <= max_ratio_f


def age_days(pool_created_iso, fetched_at_iso) -> float:
    try:
        if not pool_created_iso or not fetched_at_iso:
            return -1.0
        created = datetime.fromisoformat(str(pool_created_iso).replace("Z", "+00:00"))
        fetched = datetime.fromisoformat(str(fetched_at_iso).replace("Z", "+00:00"))
        delta_days = (fetched - created).total_seconds() / 86400.0
        return max(delta_days, 0.0)
    except Exception:
        return -1.0


def passes_tier_b_refined(
    fee_apr_24h,
    tvl_usd,
    age_d,
    abs_move_pct,
    sustained,
    *,
    tvl_min,
    age_min_days,
    move_max_pct,
) -> bool:
    return (
        80.0 <= fee_apr_24h < 800.0
        and tvl_usd >= tvl_min
        and age_d >= age_min_days
        and abs_move_pct <= move_max_pct
        and sustained
    )


def _to_float(v, default=0.0) -> float:
    try:
        if v is None:
            return float(default)
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def _parse_ranges(raw: str) -> List[float]:
    if not raw:
        return [5, 10, 20]
    vals: List[float] = []
    for part in raw.split(","):
        p = part.strip()
        if not p:
            continue
        f = float(p)
        if f <= 0:
            continue
        vals.append(float(f))
    if not vals:
        return [5, 10, 20]
    return vals


def _median(values: List[float]):
    if not values:
        return None
    return median(values)


def _to_payload(raw_result: Any, fee_apr_24h: float) -> Dict[str, Any]:
    net = None
    gross = _to_float(fee_apr_24h, 0.0)
    il = None

    if isinstance(raw_result, dict):
        for k in ("net_apr_pct", "net_apr", "realized_net_apr_pct", "net"):
            if k in raw_result:
                net = _to_float(raw_result[k], None)
                break
        for k in ("gross_fee_apr_24h", "gross_apr_pct", "gross", "gross_apr"):
            if k in raw_result:
                gross = _to_float(raw_result[k], gross)
                break
        for k in ("il_usd", "impermanent_loss_usd", "il"):
            if k in raw_result:
                il = _to_float(raw_result[k], None)
                break
    elif isinstance(raw_result, (list, tuple)):
        if len(raw_result) >= 3:
            net = _to_float(raw_result[0], None)
            gross = _to_float(raw_result[1], gross)
            il = _to_float(raw_result[2], None)
        elif len(raw_result) == 2:
            net = _to_float(raw_result[0], None)
            il = _to_float(raw_result[1], None)
        elif len(raw_result) == 1:
            net = _to_float(raw_result[0], None)
    else:
        try:
            if raw_result is not None:
                net = float(raw_result)
        except (TypeError, ValueError):
            net = None

    if net is None:
        return {
            "net_apr_pct": None,
            "gross_fee_apr_24h": _to_float(fee_apr_24h, None),
            "il_usd": None,
            "raw": raw_result,
        }
    return {
        "net_apr_pct": net,
        "gross_fee_apr_24h": gross,
        "il_usd": il,
        "raw": raw_result,
    }


def _default_output_path() -> str:
    utc = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return os.path.join("reports", "lp_tier_b_baseline_v2", utc, "lp_tier_b_baseline_v2_readonly.json")


def run(
    input_path: str,
    ranges: List[float],
    tvl_min: float,
    age_min_days: float,
    move_max_pct: float,
    max_ratio: float,
    size: int,
    out_path: str,
):
    raw_tier_histogram: Dict[str, int] = defaultdict(int)
    drop_breakdown = {
        "low_tvl": 0,
        "too_young": 0,
        "too_volatile": 0,
        "not_sustained": 0,
    }

    refined_b_pools: List[Dict[str, Any]] = []
    per_range_stats = {
        str(r): {"gross": [], "net": [], "il": [], "positive_net_share_count": 0}
        for r in ranges
    }
    total_rows = 0

    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            total_rows += 1
            fee_tier_bps = _to_float(rec.get("fee_tier_bps"), 0.0)
            tvl_usd = _to_float(rec.get("tvl_usd"), 0.0)
            v1 = _to_float(rec.get("volume_usd_h1"), 0.0)
            v6 = _to_float(rec.get("volume_usd_h6"), 0.0)
            v24 = _to_float(rec.get("volume_usd_h24"), 0.0)

            fee_apr_24h = _to_float(fee_apr_pct(fee_tier_bps, v24, tvl_usd), 0.0)
            tier = classify_tier(fee_apr_24h)
            raw_tier_histogram[str(tier)] += 1

            if tier != "B":
                continue

            aprs = fee_apr_multi(fee_tier_bps, v1, v6, v24, tvl_usd)
            age_d = age_days(rec.get("pool_created"), rec.get("fetched_at"))
            abs_move_pct = abs(_to_float(rec.get("price_change_pct_h24"), 0.0))
            sustained = is_sustained(aprs["apr_h1"], aprs["apr_h6"], aprs["apr_h24"], max_ratio=max_ratio)

            if tvl_usd < tvl_min:
                drop_breakdown["low_tvl"] += 1
            if age_d < age_min_days or age_d < 0:
                drop_breakdown["too_young"] += 1
            if abs_move_pct > move_max_pct:
                drop_breakdown["too_volatile"] += 1
            if not sustained:
                drop_breakdown["not_sustained"] += 1

            if not passes_tier_b_refined(
                fee_apr_24h,
                tvl_usd,
                age_d,
                abs_move_pct,
                sustained,
                tvl_min=tvl_min,
                age_min_days=age_min_days,
                move_max_pct=move_max_pct,
            ):
                continue

            range_results: Dict[str, Dict[str, Any]] = {}
            for rng in ranges:
                try:
                    raw_net = realized_24h_net(size, rng, fee_apr_24h, abs_move_pct)
                except Exception:
                    raw_net = None

                payload = _to_payload(raw_net, fee_apr_24h)
                range_key = str(rng)
                range_results[range_key] = {
                    "net_apr_pct": payload["net_apr_pct"],
                    "gross_fee_apr_24h": payload["gross_fee_apr_24h"],
                    "il_usd": payload["il_usd"],
                }

                net_apr = payload["net_apr_pct"]
                if net_apr is not None:
                    per_range_stats[range_key]["net"].append(float(net_apr))
                    if net_apr > 0:
                        per_range_stats[range_key]["positive_net_share_count"] += 1
                gross = payload["gross_fee_apr_24h"]
                if gross is not None:
                    per_range_stats[range_key]["gross"].append(float(gross))
                il = payload["il_usd"]
                if il is not None:
                    per_range_stats[range_key]["il"].append(float(il))

            refined_b_pools.append(
                {
                    "name": rec.get("name", ""),
                    "pool_address": rec.get("pool_address", ""),
                    "dex_id": rec.get("dex_id", ""),
                    "token0_symbol": rec.get("token0_symbol", ""),
                    "token1_symbol": rec.get("token1_symbol", ""),
                    "fee_tier_bps": fee_tier_bps,
                    "tvl_usd": tvl_usd,
                    "apr_h1": aprs["apr_h1"],
                    "apr_h6": aprs["apr_h6"],
                    "apr_h24": aprs["apr_h24"],
                    "age_days": age_d,
                    "abs_price_change_pct_h24": abs_move_pct,
                    "sustained": sustained,
                    "size": size,
                    "range_results": range_results,
                    "pool_created": rec.get("pool_created"),
                    "fetched_at": rec.get("fetched_at"),
                }
            )

    aggregates: Dict[str, Any] = {}
    for r in ranges:
        key = str(r)
        gross_vals = per_range_stats[key]["gross"]
        net_vals = per_range_stats[key]["net"]
        il_vals = per_range_stats[key]["il"]
        n = len(net_vals)
        pos = per_range_stats[key]["positive_net_share_count"]
        aggregates[key] = {
            "n": n,
            "median_gross_fee_apr_24h": _median(gross_vals),
            "median_net_apr_pct": _median(net_vals),
            "median_il_usd": _median(il_vals),
            "positive_net_share": (pos / n) if n else 0.0,
        }

    out = {
        "raw_tier_histogram": dict(raw_tier_histogram),
        "raw_b_count": int(raw_tier_histogram.get("B", 0)),
        "drop_breakdown": drop_breakdown,
        "refined_b_count": len(refined_b_pools),
        "ranges": ranges,
        "refined_b_pools": refined_b_pools,
        "aggregates": aggregates,
        "meta": {
            "input_path": input_path,
            "size": size,
            "tvl_min": tvl_min,
            "age_min_days": age_min_days,
            "move_max_pct": move_max_pct,
            "max_ratio": max_ratio,
            "total_rows": total_rows,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as out_f:
        json.dump(out, out_f, indent=2)

    print(f"raw B count: {out['raw_b_count']}")
    print(f"drop breakdown: {out['drop_breakdown']}")
    print(f"refined B count: {out['refined_b_count']}")
    if out["refined_b_count"] == 0:
        print("no refined Tier-B pools")
    else:
        for r in ranges:
            k = str(r)
            agg = aggregates[k]
            med_gross = agg["median_gross_fee_apr_24h"]
            med_net = agg["median_net_apr_pct"]
            med_il = agg["median_il_usd"]
            print(
                f"range={k}: "
                f"n={agg['n']}, "
                f"median_gross_fee_apr_24h={med_gross}, "
                f"median_net_apr_pct={med_net}, "
                f"median_il_usd={med_il}, "
                f"positive_net_share={agg['positive_net_share']:.2%}"
            )

    return out


def parse_args():
    p = argparse.ArgumentParser(description="Refined Tier-B baseline (readonly, no RPC).")
    p.add_argument("--tvl-min", type=float, default=100000)
    p.add_argument("--age-min-days", type=float, default=7.0)
    p.add_argument("--move-max-pct", type=float, default=25.0)
    p.add_argument("--max-ratio", type=float, default=3.0)
    p.add_argument("--size", type=float, default=200.0)
    p.add_argument("--ranges", type=str, default="5,10,20")
    p.add_argument("--input", type=str, default=DEFAULT_INPUT)
    p.add_argument("--out", type=str, default=None)
    return p.parse_args()


def main():
    args = parse_args()
    ranges = _parse_ranges(args.ranges)
    out = args.out if args.out else _default_output_path()
    run(
        input_path=args.input,
        ranges=ranges,
        tvl_min=args.tvl_min,
        age_min_days=args.age_min_days,
        move_max_pct=args.move_max_pct,
        max_ratio=args.max_ratio,
        size=args.size,
        out_path=out,
    )


if __name__ == "__main__":
    main()
