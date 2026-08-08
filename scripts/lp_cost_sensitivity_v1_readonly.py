#!/usr/bin/env python3
"""WP-04 Cost Sensitivity for a traceable historical Base vetted pool.

Pure/read-only analysis: no network, wallet, signing, approval, or transaction
code.  The default parameters are loaded from committed historical research
artifacts so every number has an evidence path rather than an invented pool.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.lp_netcover_engine_v1_readonly import (  # noqa: E402
    REWARD_HAIRCUTS,
    absolute_profit_gate,
    evaluate_netcover,
    position_cap_usd,
)
from scripts.lp_swap_cost_model_v1_readonly import (  # noqa: E402
    exit_conversion_cost_usd,
)


SIZES_USD = (25, 50, 75, 100, 200, 500)
DEFAULT_POOL_ADDRESS = "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59"
DEFAULT_HOLDING_HOURS = 30.0 * 24.0  # PASSIVE_CL calibration horizon
HOURS_PER_YEAR = 365.0 * 24.0

QUALITY_SOURCE = "reports/lp_pool_resolve_and_rank/run_qualityA/resolve_and_rank.json"
DEPTH_SOURCE = "reports/lp_quote_depth_curve_fix/20260601_091739/quote_depth_curve_v2_results.csv"
REPLAY_SOURCE = "reports/strategy_evidence_r4b_active_liquidity_corrected_replay/20260612_090000/active_liquidity_corrected_replay_matrix.jsonl"
SWAP_SOURCE = "reports/strategy_evidence_r4_swap_event_fee_replay/20260611_080000/swap_events_decoded.csv"


def price_from_sqrt_x96(sqrt_price_x96: int, *, dec0: int, dec1: int) -> float:
    """Convert a V3 Swap event sqrtPriceX96 to human token1/token0 price."""
    value = int(sqrt_price_x96)
    if value <= 0:
        raise ValueError("sqrt_price_x96 must be positive")
    return (value / 2**96) ** 2 * 10 ** (dec0 - dec1)


@dataclass(frozen=True)
class BasePoolParameters:
    chain: str
    symbol: str
    address: str
    project: str
    pool_tvl_usd: float
    active_liquidity_notional_usd: float
    l_active_raw_historical: int
    price_usd: float
    fee_tier: float
    dec0: int
    dec1: int
    conservative_fee_apr_pct: float
    reward_apr_pct: float
    expected_il_apr_pct: float
    lvr_coefficient_model: float
    reward_haircut: float
    reward_conversion_apr_pct_model: float
    exit_latency_loss_apr_pct_model: float
    gas_usd_historical: float
    tier_configured_max_usd: float
    holding_horizon_hours: float
    source_paths: tuple[str, ...]
    source_kind: str = "historical_real_base_vetted_pool"

def _load_jsonl_first_matching(path: Path, address: str) -> dict[str, Any]:
    with path.open() as handle:
        for line in handle:
            row = json.loads(line)
            if str(row.get("pool", "")).lower() == address.lower():
                return row
    raise ValueError(f"pool {address} absent from {path}")


def default_base_vetted_pool(repo_root: Path | str = _ROOT) -> BasePoolParameters:
    """Load the same real Base vetted pool across three committed artifacts."""
    root = Path(repo_root)
    quality = json.loads((root / QUALITY_SOURCE).read_text())
    qrow = next(
        row for row in quality
        if str(row.get("resolved_pool", row.get("pool", ""))).lower() == DEFAULT_POOL_ADDRESS
    )
    with (root / DEPTH_SOURCE).open(newline="") as handle:
        depth_rows = list(csv.DictReader(handle))
    drow = next(
        row for row in depth_rows
        if row["pool_id"].lower() == DEFAULT_POOL_ADDRESS and float(row["virtual_notional_usd"]) == 100.0
    )
    replay = _load_jsonl_first_matching(root / REPLAY_SOURCE, DEFAULT_POOL_ADDRESS)
    with (root / SWAP_SOURCE).open(newline="") as handle:
        swap_rows = list(csv.DictReader(handle))
    swap = next(row for row in swap_rows if row["pool"].lower() == DEFAULT_POOL_ADDRESS)
    dec0, dec1 = int(qrow["dec0"]), int(qrow["dec1"])

    # PRD v2.1: min(APR24h, APR7d) × 0.65.  The historical artifacts have an
    # on-chain annualized fee estimate and DefiLlama base APR; use the smaller.
    conservative_fee_apr = min(float(qrow["apyBase"]), float(qrow["fee_apr_onchain"])) * 0.65
    return BasePoolParameters(
        chain="base",
        symbol=str(qrow["symbol"]),
        address=DEFAULT_POOL_ADDRESS,
        project=str(qrow["project"]),
        pool_tvl_usd=float(qrow["tvlUsd"]),
        active_liquidity_notional_usd=float(drow["reserve_liquidity_usd"]),
        l_active_raw_historical=int(swap["liquidity"]),
        price_usd=price_from_sqrt_x96(
            int(swap["sqrtPriceX96"]), dec0=dec0, dec1=dec1,
        ),
        fee_tier=float(qrow["fee_tier"]),
        dec0=dec0,
        dec1=dec1,
        conservative_fee_apr_pct=conservative_fee_apr,
        reward_apr_pct=float(qrow.get("reward_apr") or 0.0),
        expected_il_apr_pct=float(qrow["il_apr"]),
        lvr_coefficient_model=0.50,
        reward_haircut=REWARD_HAIRCUTS["protocol"],
        # Explicit initial model estimates; Shadow data must calibrate them.
        reward_conversion_apr_pct_model=0.10,
        exit_latency_loss_apr_pct_model=0.50,
        gas_usd_historical=float(replay["gas_usd"]),
        tier_configured_max_usd=500.0,
        holding_horizon_hours=DEFAULT_HOLDING_HOURS,
        source_paths=(QUALITY_SOURCE, DEPTH_SOURCE, REPLAY_SOURCE, SWAP_SOURCE),
    )


def _swap_components(size_usd: float, pool: BasePoolParameters) -> dict[str, float]:
    entry_total = exit_conversion_cost_usd(
        size_usd, pool.l_active_raw_historical, pool.price_usd, pool.fee_tier,
        pool.dec0, pool.dec1, "buy_base",
    )
    exit_total = exit_conversion_cost_usd(
        size_usd, pool.l_active_raw_historical, pool.price_usd, pool.fee_tier,
        pool.dec0, pool.dec1, "sell_base",
    )
    entry_fee = size_usd * pool.fee_tier
    exit_fee = size_usd * pool.fee_tier
    slippage = max(entry_total + exit_total - entry_fee - exit_fee, 0.0)
    return {
        "entry_cost_usd": entry_fee,
        "exit_cost_usd": exit_fee,
        "slippage_usd": slippage,
        "round_trip_cost_usd": entry_total + exit_total,
    }


def _annual_rates(pool: BasePoolParameters) -> tuple[float, float]:
    income_rate = (
        pool.conservative_fee_apr_pct
        + pool.reward_apr_pct * pool.reward_haircut
    ) / 100.0
    risk_rate = (
        pool.expected_il_apr_pct * (1.0 + pool.lvr_coefficient_model)
        + pool.reward_conversion_apr_pct_model
        + pool.exit_latency_loss_apr_pct_model
    ) / 100.0
    return income_rate, risk_rate


def _economics_at_size(size_usd: float, pool: BasePoolParameters) -> dict[str, float | bool]:
    swaps = _swap_components(size_usd, pool)
    income_rate, risk_rate = _annual_rates(pool)
    horizon_fraction = pool.holding_horizon_hours / HOURS_PER_YEAR
    fee_ev = size_usd * pool.conservative_fee_apr_pct / 100.0 * horizon_fraction
    reward_ev = size_usd * pool.reward_apr_pct / 100.0 * horizon_fraction
    il_ev = size_usd * pool.expected_il_apr_pct / 100.0 * horizon_fraction
    reward_conversion = (
        size_usd * pool.reward_conversion_apr_pct_model / 100.0 * horizon_fraction
    )
    exit_latency = (
        size_usd * pool.exit_latency_loss_apr_pct_model / 100.0 * horizon_fraction
    )
    estimate = evaluate_netcover(
        fee_ev=fee_ev,
        reward_ev=reward_ev,
        reward_haircut=pool.reward_haircut,
        expected_il=il_ev,
        lvr_coefficient=pool.lvr_coefficient_model,
        entry_cost=swaps["entry_cost_usd"],
        exit_cost=swaps["exit_cost_usd"],
        gas=pool.gas_usd_historical,
        slippage=swaps["slippage_usd"],
        reward_conversion_cost=reward_conversion,
        exit_latency_loss=exit_latency,
    )
    expected_net = estimate.adjusted_income_ev - estimate.expected_risk_cost
    profit_gate = absolute_profit_gate(expected_net, swaps["round_trip_cost_usd"])
    fixed_cost = swaps["round_trip_cost_usd"] + pool.gas_usd_historical
    annual_net_dollars = size_usd * (income_rate - risk_rate)
    break_even_hours = fixed_cost / annual_net_dollars * HOURS_PER_YEAR
    return {
        **swaps,
        "fixed_cost_usd": fixed_cost,
        "adjusted_income_rate_per_year": income_rate,
        "risk_rate_per_year": risk_rate,
        "break_even_holding_hours": break_even_hours,
        "netcover_30d": estimate.netcover,
        "expected_net_profit_h_usd": expected_net,
        "absolute_profit_required_usd": profit_gate.required_profit_usd,
        "absolute_profit_gate_pass": profit_gate.allowed,
    }


def min_economic_position_usd(pool: BasePoolParameters) -> float:
    """Numerically find the smallest size passing INV-COST-01 at the horizon."""
    low, high = 0.01, 1.0
    while high < 1_000_000 and not _economics_at_size(high, pool)["absolute_profit_gate_pass"]:
        high *= 2.0
    if high >= 1_000_000 and not _economics_at_size(high, pool)["absolute_profit_gate_pass"]:
        raise ValueError("no economic position below $1,000,000 under current assumptions")
    for _ in range(80):
        mid = (low + high) / 2.0
        if _economics_at_size(mid, pool)["absolute_profit_gate_pass"]:
            high = mid
        else:
            low = mid
    return high


def analyse_sizes(
    pool: BasePoolParameters,
    sizes: Sequence[float] = SIZES_USD,
) -> list[dict[str, Any]]:
    minimum = min_economic_position_usd(pool)
    cap = position_cap_usd(
        pool.tier_configured_max_usd, pool.pool_tvl_usd,
        pool.active_liquidity_notional_usd,
    )
    rows = []
    for size in sizes:
        economics = _economics_at_size(float(size), pool)
        rows.append({
            "size_usd": int(size) if float(size).is_integer() else float(size),
            **economics,
            "min_economic_position_usd": minimum,
            "position_cap_usd": cap,
            "within_runtime_cap": float(size) <= cap,
            "source_kind": pool.source_kind,
        })
    return rows


def render_report(pool: BasePoolParameters, rows: Sequence[dict[str, Any]], as_of: str) -> str:
    lines = [
        "# LP Cost Sensitivity — Base vetted pool",
        "",
        f"As of analysis: `{as_of}` (historical inputs; no live/network calls)",
        f"Pool: `{pool.address}` · {pool.project} {pool.symbol}",
        f"Horizon for MinEconomicPosition: {pool.holding_horizon_hours:.0f}h; "
        f"conservative fee APR {pool.conservative_fee_apr_pct:.4f}%; "
        f"reward APR {pool.reward_apr_pct:.4f}% × haircut {pool.reward_haircut:.2f}.",
        "",
        "LVR and exit-latency are model estimates. Position cap uses a historical "
        "active-notional depth proxy; swap math uses price and raw active liquidity "
        "decoded from a real Swap event; gas is a historical replay observation.",
        "",
        "| size U | round-trip U | fixed cost U | break-even h | MinEconomicPosition U | NetCover 30d | abs-profit gate | runtime cap U |",
        "|---:|---:|---:|---:|---:|---:|:---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['size_usd']} | {row['round_trip_cost_usd']:.6f} | "
            f"{row['fixed_cost_usd']:.6f} | {row['break_even_holding_hours']:.2f} | "
            f"{row['min_economic_position_usd']:.2f} | {row['netcover_30d']:.3f} | "
            f"{'PASS' if row['absolute_profit_gate_pass'] else 'SKIP'} | "
            f"{row['position_cap_usd']:.2f} |"
        )
    lines.extend(["", "Sources:"] + [f"- `{path}`" for path in pool.source_paths])
    lines.append("")
    return "\n".join(lines)


def write_report(
    out_dir: Path | str,
    pool: BasePoolParameters,
    rows: Sequence[dict[str, Any]],
    *,
    as_of: str | None = None,
) -> Path:
    destination = Path(out_dir)
    destination.mkdir(parents=True, exist_ok=True)
    timestamp = as_of or datetime.now(timezone.utc).isoformat()
    payload = {
        "as_of": timestamp,
        "pool": asdict(pool),
        "semantics": {
            "expected_lvr": "model_estimate: expected_il * lvr_coefficient_model",
            "exit_latency_loss": "model_estimate: free-RPC full-path latency annualized loss",
            "gross_fee_cover": "diagnostic_only; NetCover is the gate",
        },
        "rows": list(rows),
    }
    (destination / "cost_sensitivity.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )
    (destination / "cost_sensitivity.md").write_text(render_report(pool, rows, timestamp))
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="WP-04 Base LP cost sensitivity (read-only)")
    parser.add_argument("--out", help="output directory; default reports/lp_cost_sensitivity/<stamp>")
    args = parser.parse_args()
    pool = default_base_vetted_pool()
    rows = analyse_sizes(pool)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = Path(args.out) if args.out else _ROOT / "reports" / "lp_cost_sensitivity" / stamp
    write_report(out, pool, rows)
    print(f"wrote {len(rows)} rows to {out}")


if __name__ == "__main__":
    main()
