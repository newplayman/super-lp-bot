import argparse
import datetime
import json
import os
import statistics
import sys
from typing import Any, Dict, Iterable, List

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.lp_v3_position_value import lp_impermanent_loss_usd


def fee_apr_pct(fee_tier_bps, volume_usd_h24, tvl_usd) -> float:
    # gross fee yield on TVL, annualized from the 24h volume.
    if tvl_usd <= 0:
        return 0.0
    return (fee_tier_bps / 10000.0) * volume_usd_h24 * 365.0 / tvl_usd * 100.0


def classify_tier(apr_pct) -> str:
    # 'sub' (<30), 'A' [30,80), 'B' [80,800), 'C' (>=800)
    if apr_pct < 30:
        return 'sub'
    if apr_pct < 80:
        return 'A'
    if apr_pct < 800:
        return 'B'
    return 'C'


def realized_24h_net(size_usd, range_pct, fee_apr, price_change_pct_h24) -> dict:
    # entry normalized to 1.0; end = entry*(1+move). IL from real move via the imported fn.
    move = price_change_pct_h24 / 100.0
    entry = 1.0
    end = entry * (1.0 + move)
    il_usd = lp_impermanent_loss_usd(size_usd, entry, range_pct, end)   # <= 0
    # fee capture: pro-rata pool yield while price stays in range. If the move exceeds the
    # range, you stop earning once price exits -> approximate in-range fraction.
    # CONSERVATIVE: concentrated LP actually earns MORE than pro-rata-on-full-TVL in range,
    # so this UNDERSTATES fees (net is a lower bound).
    rfrac = abs(move) / (range_pct / 100.0) if range_pct > 0 else float('inf')
    capture = 1.0 if rfrac <= 1.0 else 1.0 / rfrac
    fee_usd = (fee_apr / 100.0 / 365.0) * size_usd * capture
    net_usd = fee_usd + il_usd
    net_apr = net_usd / size_usd * 365.0 * 100.0 if size_usd > 0 else 0.0
    return {'il_usd': il_usd, 'fee_usd': fee_usd, 'capture': capture,
            'net_usd_24h': net_usd, 'net_apr_pct': net_apr}


def _parse_ranges(raw_ranges: str) -> List[float]:
    if raw_ranges is None:
        return []
    parts = [item.strip() for item in raw_ranges.split(",")]
    return [float(item) for item in parts if item]


def _load_rows(input_path: str) -> Iterable[Dict[str, Any]]:
    with open(input_path, "r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _coerce_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_median(values: List[float]) -> float:
    return statistics.median(values) if values else 0.0


def build_payload(input_path: str, size: float, ranges: List[float]) -> Dict[str, Any]:
    tier_histogram = {'sub': 0, 'A': 0, 'B': 0, 'C': 0}
    tier_b_pools: List[Dict[str, Any]] = []

    agg_bucket = {}
    for range_pct in ranges:
        agg_bucket[range_pct] = {
            "gross_fee_apr_values": [],
            "net_apr_values": [],
            "il_values": [],
            "positive_net_count": 0,
            "n": 0,
        }

    for row in _load_rows(input_path):
        fee_tier_bps = int(row.get("fee_tier_bps", 0) or 0)
        tvl_usd = _coerce_float(row.get("tvl_usd"), 0.0)
        volume_usd_h24 = _coerce_float(row.get("volume_usd_h24"), 0.0)
        price_change_pct_h24 = _coerce_float(row.get("price_change_pct_h24"), 0.0)

        fee_apr = fee_apr_pct(fee_tier_bps, volume_usd_h24, tvl_usd)
        tier = classify_tier(fee_apr)
        tier_histogram[tier] += 1

        if tier != "B":
            continue

        range_rows: List[Dict[str, float]] = []
        for range_pct in ranges:
            realized = realized_24h_net(size, range_pct, fee_apr, price_change_pct_h24)
            range_rows.append({
                "range_pct": range_pct,
                "net_apr_pct": realized["net_apr_pct"],
                "fee_usd": realized["fee_usd"],
                "il_usd": realized["il_usd"],
            })

            bucket = agg_bucket[range_pct]
            bucket["gross_fee_apr_values"].append(fee_apr)
            bucket["net_apr_values"].append(realized["net_apr_pct"])
            bucket["il_values"].append(realized["il_usd"])
            bucket["n"] += 1
            if realized["net_usd_24h"] > 0:
                bucket["positive_net_count"] += 1

        tier_b_pools.append({
            "pool_address": row.get("pool_address"),
            "name": row.get("name"),
            "dex_id": row.get("dex_id"),
            "fee_tier_bps": fee_tier_bps,
            "tvl_usd": tvl_usd,
            "volume_usd_h24": volume_usd_h24,
            "fee_apr_pct": fee_apr,
            "price_change_pct_h24": price_change_pct_h24,
            "ranges": range_rows,
            "token0_symbol": row.get("token0_symbol"),
            "token1_symbol": row.get("token1_symbol"),
        })

    aggregates: Dict[str, Dict[str, Any]] = {}
    for range_pct, bucket in agg_bucket.items():
        n = bucket["n"]
        positive_share = bucket["positive_net_count"] / n if n else 0.0
        aggregates[str(range_pct)] = {
            "n": n,
            "median_gross_fee_apr_pct": _safe_median(bucket["gross_fee_apr_values"]),
            "median_net_apr_pct": _safe_median(bucket["net_apr_values"]),
            "median_il_usd": _safe_median(bucket["il_values"]),
            "positive_net_share": positive_share,
        }

    return {
        "tier_histogram": tier_histogram,
        "ranges": ranges,
        "tier_b_pools": tier_b_pools,
        "aggregates": aggregates,
        "meta": {
            "input": input_path,
            "size": size,
            "generated_note": "Read-only snapshot-based Tier-B baseline computation.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only Tier-B baseline from an existing Base pool snapshot JSONL."
    )
    parser.add_argument(
        "--input",
        default="reports/strategy_evidence_r0_pool_discovery/20260611_031425/candidate_pools_raw.jsonl",
    )
    parser.add_argument("--size", type=float, default=200, help="Position size in USD")
    parser.add_argument(
        "--ranges",
        default="5,10,20",
        help="Comma-separated range widths in percent",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Output JSON path. Defaults to reports/lp_tier_b_baseline/<UTC stamp>/tier_b_baseline.json",
    )
    args = parser.parse_args()

    ranges = _parse_ranges(args.ranges)
    payload = build_payload(args.input, args.size, ranges)

    if args.out:
        out_path = args.out
    else:
        utc_stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(
            "reports",
            "lp_tier_b_baseline",
            utc_stamp,
            "tier_b_baseline.json",
        )

    out_dir = os.path.dirname(out_path) or "."
    os.makedirs(out_dir, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)

    print("tier_histogram=", json.dumps(payload["tier_histogram"], sort_keys=True))

    if payload["tier_histogram"].get("B", 0) == 0:
        print("no Tier-B pools")
    else:
        for range_pct in ranges:
            agg = payload["aggregates"][str(range_pct)]
            print(
                "range={:.2f}% n={} median_gross_fee_apr_pct={:.6f} "
                "median_net_apr_pct={:.6f} share_positive={:.6f}".format(
                    range_pct,
                    agg["n"],
                    agg["median_gross_fee_apr_pct"],
                    agg["median_net_apr_pct"],
                    agg["positive_net_share"],
                )
            )

    print("wrote:", out_path)


if __name__ == "__main__":
    main()
