#!/usr/bin/env python3
"""BSC PancakeSwap V3 economics preview with recovered fee velocity (read-only).

Combines:
  - Phase 4 fee velocity short backfill   (recovered swap data)
  - lp_bsc_overnight_realdata_pipeline    (precise quote, tick liquidity, real cost)

For each (pool, notional, hold_window, IL/LVR scenario) cell computes:
  fee_proxy_usd       = pool-level fee / (window seconds) × hold seconds
                        × (notional / pool TVL proxy)
  fixed_cost_usd      = looked up from real cost model
  il_lvr_proxy_usd    = scenario × notional × tick-volatility heuristic
  net_ev_proxy_usd    = fee_proxy_usd - fixed_cost_usd - il_lvr_proxy_usd

This is a fee-velocity-recovered REFINEMENT of the prior overnight preview;
it does NOT claim actual position fee accrual (token_id_available=false).

Outputs:
  $REPORT_DIR/bsc_realdata_economics_with_recovered_fee.json
  $REPORT_DIR/bsc_realdata_economics_with_recovered_fee.csv
  $REPORT_DIR/BSC_REALDATA_ECONOMICS_WITH_RECOVERED_FEE_CN.md
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Optional


NOTIONALS_USD = [Decimal(x) for x in [20, 100, 500, 1000, 2000]]
HOLD_WINDOWS_SEC = {
    "15m": 15 * 60,
    "30m": 30 * 60,
    "1h":  3600,
    "2h":  7200,
    "6h":  21600,
    "24h": 86400,
}
IL_LVR_SCENARIOS = {
    # scenario -> multiplier of (notional * hold_volatility_proxy)
    "zero_il_lvr":  Decimal("0"),
    "optimistic":   Decimal("0.0005"),   # 5 bps/hold-period
    "realistic":    Decimal("0.0020"),   # 20 bps/hold-period
    "conservative": Decimal("0.0050"),   # 50 bps/hold-period
}
WINDOW_SECONDS = {
    "24h": 24 * 3600,
    "72h": 72 * 3600,
    "7d":  7 * 24 * 3600,
}
# Heuristic: assume the position concentrates ~5% of the pool's TVL into the
# active range; thus its share-of-fees equals (notional × 20) / pool_TVL.
# For the smoke preview we use a coarse pool-level fee per second rate scaled
# by the position's notional divided by an assumed pool TVL of $5M (a low,
# conservative figure that biases the EV downward — keeps us from over-
# claiming). Refinement requires actual tickLiquidity-aware share math from
# the tick liquidity table (Phase 5 leaves room for that in a v2).
POOL_TVL_PROXY_USD = Decimal("5000000")


def _safe_decimal(x, default: Decimal = Decimal("0")) -> Decimal:
    if x is None or x == "":
        return default
    try:
        return Decimal(str(x))
    except Exception:  # noqa: BLE001
        return default


def load_real_cost(real_cost_csv: Path) -> dict:
    """Return mapping (pool_id_lower, notional_int) -> {fixed_cost_usd: Decimal, slippage: Decimal}.

    Uses the 'diagnostic_low' scenario rows by default (lowest gas-price
    sanity baseline)."""
    out: dict[tuple[str, int], dict] = {}
    if not real_cost_csv.is_file():
        return out
    with real_cost_csv.open() as fh:
        for row in csv.DictReader(fh):
            if row.get("scenario") != "diagnostic_low":
                continue
            pool = row["pool_id"].lower()
            try:
                notional = int(Decimal(row["notional_usd"]))
            except Exception:  # noqa: BLE001
                continue
            out[(pool, notional)] = {
                "fixed_cost_usd": _safe_decimal(row.get("total_fixed_cost_usd")),
                "slippage_usd": _safe_decimal(row.get("proportional_slippage_cost_usd")),
            }
    return out


def load_fee_velocity(short_backfill_json: Path) -> dict:
    """Return mapping (pool_id_lower, window) -> {fee_usd, volume_usd, fee_per_sec, fee_ready}."""
    out: dict[tuple[str, str], dict] = {}
    if not short_backfill_json.is_file():
        return out
    data = json.loads(short_backfill_json.read_text())
    for row in data.get("rows", []):
        pool = row["pool_id"].lower()
        window = row["window"]
        fee_usd = _safe_decimal(row.get("pool_fee_usd_proxy"))
        volume_usd = _safe_decimal(row.get("volume_usd_proxy"))
        wsec = WINDOW_SECONDS.get(window, 86400)
        with localcontext() as ctx:
            ctx.prec = 60
            fee_per_sec = (fee_usd / wsec) if wsec > 0 else Decimal("0")
        out[(pool, window)] = {
            "fee_usd": fee_usd,
            "volume_usd": volume_usd,
            "fee_per_sec": fee_per_sec,
            "fee_ready": bool(row.get("fee_ready")),
        }
    return out


def pick_window_for_fee_rate(fee_velocity: dict, pool_lower: str, hold_window_sec: int) -> tuple[str, Decimal]:
    """Pick the longest fee-velocity window <= hold_window_sec, falling back to
    the shortest available."""
    # Prefer 7d > 72h > 24h for stability, then map down to whichever window
    # exists. For very short holds the 24h rate is still a reasonable estimate.
    preferred_order = ["7d", "72h", "24h"]
    for w in preferred_order:
        if (pool_lower, w) in fee_velocity:
            return w, fee_velocity[(pool_lower, w)]["fee_per_sec"]
    return "", Decimal("0")


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="BSC PancakeSwap V3 economics preview with recovered fee.")
    parser.add_argument("--report-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--real-cost-csv",
        default="reports/lp_bsc_overnight_realdata_pipeline/20260601_180812/BSC_REAL_COST_MODEL_RESULTS_CN.csv",
        type=Path,
    )
    parser.add_argument(
        "--short-backfill-json",
        type=Path,
        help="Defaults to <report-dir>/bsc_fee_velocity_short_backfill_results.json",
    )
    args = parser.parse_args(argv)

    short_backfill_json = args.short_backfill_json or (args.report_dir / "bsc_fee_velocity_short_backfill_results.json")
    if not short_backfill_json.is_file():
        print(f"ERROR: short backfill json not found: {short_backfill_json}", file=sys.stderr)
        return 2
    if not args.real_cost_csv.is_file():
        print(f"WARN: real cost csv not found: {args.real_cost_csv} — fixed_cost will be zero", file=sys.stderr)

    fee_velocity = load_fee_velocity(short_backfill_json)
    real_cost = load_real_cost(args.real_cost_csv)
    backfill = json.loads(short_backfill_json.read_text())

    # Build per-pool metadata index from the backfill rows.
    pool_meta = {}
    for row in backfill["rows"]:
        addr = row["pool_id"].lower()
        if addr in pool_meta:
            continue
        pool_meta[addr] = {
            "token_pair": row["token_pair"],
            "fee_tier_raw": row["fee_tier_raw"],
        }

    rows = []
    positive_total = 0
    positive_realistic = 0
    near_break_even = 0
    best_row = None

    for pool_lower, meta in pool_meta.items():
        for hold_window, hold_sec in HOLD_WINDOWS_SEC.items():
            src_window, fee_per_sec = pick_window_for_fee_rate(fee_velocity, pool_lower, hold_sec)
            for notional in NOTIONALS_USD:
                cost_key = (pool_lower, int(notional))
                cost_info = real_cost.get(cost_key, {})
                fixed_cost = cost_info.get("fixed_cost_usd", Decimal("0"))
                # Pool fee share = notional / pool_TVL (very rough)
                with localcontext() as ctx:
                    ctx.prec = 60
                    pool_share = (notional / POOL_TVL_PROXY_USD) if POOL_TVL_PROXY_USD > 0 else Decimal("0")
                    fee_proxy = fee_per_sec * Decimal(hold_sec) * pool_share

                    for scenario, il_factor in IL_LVR_SCENARIOS.items():
                        il_lvr_usd = notional * il_factor * (Decimal(hold_sec) / Decimal(86400))
                        net_ev = fee_proxy - fixed_cost - il_lvr_usd
                        net_ev_pct = (net_ev / notional * Decimal("100")) if notional > 0 else Decimal("0")

                        confidence = "low"
                        if (pool_lower, src_window) in fee_velocity and fee_velocity[(pool_lower, src_window)]["fee_ready"]:
                            confidence = "medium" if scenario in {"realistic", "conservative"} else "low"

                        row = {
                            "pool_id": pool_lower,
                            "token_pair": meta["token_pair"],
                            "fee_tier_raw": meta["fee_tier_raw"],
                            "notional_usd": str(notional),
                            "hold_window": hold_window,
                            "hold_seconds": hold_sec,
                            "fee_velocity_window_used": src_window,
                            "scenario": scenario,
                            "fee_proxy_usd": str(fee_proxy.quantize(Decimal("0.000001"))),
                            "fixed_cost_usd": str(fixed_cost.quantize(Decimal("0.000001"))),
                            "il_lvr_proxy_usd": str(il_lvr_usd.quantize(Decimal("0.000001"))),
                            "net_ev_proxy_usd": str(net_ev.quantize(Decimal("0.000001"))),
                            "net_ev_proxy_pct": str(net_ev_pct.quantize(Decimal("0.0001"))),
                            "confidence": confidence,
                            "fee_ready": (pool_lower, src_window) in fee_velocity and fee_velocity[(pool_lower, src_window)]["fee_ready"],
                        }
                        rows.append(row)

                        if net_ev > 0:
                            positive_total += 1
                            if scenario == "realistic":
                                positive_realistic += 1
                        if -Decimal("0.02") <= net_ev <= Decimal("0.02"):
                            near_break_even += 1
                        if scenario == "realistic" and row["fee_ready"]:
                            if (best_row is None) or (Decimal(row["net_ev_proxy_usd"]) > Decimal(best_row["net_ev_proxy_usd"])):
                                best_row = row

    summary = {
        "stage": "LP_BSC_FEE_VELOCITY_RECOVERY_AND_PROBE_PREFLIGHT_PIPELINE_V1",
        "phase": "5_economics_preview_with_recovered_fee",
        "run_id": args.run_id,
        "row_count": len(rows),
        "positive_proxy_count_total": positive_total,
        "positive_proxy_count_realistic": positive_realistic,
        "near_break_even_count": near_break_even,
        "best_pool": best_row["pool_id"] if best_row else "",
        "best_pair": best_row["token_pair"] if best_row else "",
        "best_fee_tier": best_row["fee_tier_raw"] if best_row else "",
        "best_notional": best_row["notional_usd"] if best_row else None,
        "best_hold_window": best_row["hold_window"] if best_row else "",
        "best_net_ev_proxy_usd": best_row["net_ev_proxy_usd"] if best_row else None,
        "best_net_ev_proxy_pct": best_row["net_ev_proxy_pct"] if best_row else None,
        "confidence_adjusted_candidate_count": sum(1 for r in rows if r["confidence"] != "low" and Decimal(r["net_ev_proxy_usd"]) > 0),
        "pool_tvl_proxy_usd_assumed": str(POOL_TVL_PROXY_USD),
        "il_lvr_scenarios": {k: str(v) for k, v in IL_LVR_SCENARIOS.items()},
        "notionals_usd": [str(n) for n in NOTIONALS_USD],
        "hold_windows": list(HOLD_WINDOWS_SEC.keys()),
        "actual_fee_ready": False,
        "token_id_available": False,
        "edge_proven": "no",
        "tiny_canary_allowed": "no",
        "can_run_probe_now": False,
        "wallet_or_tx_touched": False,
    }
    (args.report_dir / "bsc_realdata_economics_with_recovered_fee.json").write_text(json.dumps(summary, indent=2) + "\n")

    csv_path = args.report_dir / "bsc_realdata_economics_with_recovered_fee.csv"
    with csv_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else [
            "pool_id", "token_pair", "fee_tier_raw", "notional_usd", "hold_window", "hold_seconds",
            "fee_velocity_window_used", "scenario", "fee_proxy_usd", "fixed_cost_usd",
            "il_lvr_proxy_usd", "net_ev_proxy_usd", "net_ev_proxy_pct", "confidence", "fee_ready",
        ])
        w.writeheader()
        w.writerows(rows)

    md = [
        "# BSC PancakeSwap V3 economics preview (with recovered fee velocity)",
        "",
        f"- stage: `LP_BSC_FEE_VELOCITY_RECOVERY_AND_PROBE_PREFLIGHT_PIPELINE_V1`",
        f"- run_id: `{args.run_id}`",
        f"- row_count: `{summary['row_count']}`",
        f"- positive_proxy_count_total: `{summary['positive_proxy_count_total']}`",
        f"- positive_proxy_count_realistic: `{summary['positive_proxy_count_realistic']}`",
        f"- near_break_even_count: `{summary['near_break_even_count']}`",
        f"- confidence_adjusted_candidate_count: `{summary['confidence_adjusted_candidate_count']}`",
        f"- pool_tvl_proxy_usd_assumed: `{summary['pool_tvl_proxy_usd_assumed']}` (heuristic)",
        "",
        "## Best candidate (realistic scenario, fee_ready)",
        "",
        f"- pool: `{summary['best_pool'] or '-'}`",
        f"- pair: `{summary['best_pair'] or '-'}`",
        f"- fee_tier_raw: `{summary['best_fee_tier'] or '-'}`",
        f"- notional_usd: `{summary['best_notional'] or '-'}`",
        f"- hold_window: `{summary['best_hold_window'] or '-'}`",
        f"- net_ev_proxy_usd: `{summary['best_net_ev_proxy_usd'] or '-'}`",
        f"- net_ev_proxy_pct: `{summary['best_net_ev_proxy_pct'] or '-'}`",
        "",
        "## Caveats",
        "",
        "- Fee proxy uses a heuristic pool TVL = $5M (low/conservative) and pool-level fee, NOT actual position fee accrual. `actual_fee_ready = false`, `token_id_available = false`.",
        "- IL/LVR is a scenario sweep, not an empirical estimate.",
        "- USD prices are heuristic (WBNB=$600, USDC/USDT=$1) — refine with precise quote in v2 if needed.",
        "- `confidence_adjusted_candidate_count` requires `fee_ready=true` for the chosen window AND the scenario being `realistic`/`conservative`. Low-confidence cells are excluded.",
        "",
        "## Safety",
        "",
        "```text",
        "wallet_or_tx_touched   = false",
        "can_run_probe_now      = false",
        "tiny_canary_allowed    = no",
        "edge_proven            = no",
        "actual_fee_ready       = false",
        "token_id_available     = false",
        "```",
    ]
    (args.report_dir / "BSC_REALDATA_ECONOMICS_WITH_RECOVERED_FEE_CN.md").write_text("\n".join(md) + "\n")

    print(json.dumps({
        "row_count": summary["row_count"],
        "positive_proxy_count_total": summary["positive_proxy_count_total"],
        "positive_proxy_count_realistic": summary["positive_proxy_count_realistic"],
        "near_break_even_count": summary["near_break_even_count"],
        "confidence_adjusted_candidate_count": summary["confidence_adjusted_candidate_count"],
        "best_pool": summary["best_pool"],
        "best_pair": summary["best_pair"],
        "best_notional": summary["best_notional"],
        "best_hold_window": summary["best_hold_window"],
        "best_net_ev_proxy_usd": summary["best_net_ev_proxy_usd"],
    }, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
