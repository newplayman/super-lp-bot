#!/usr/bin/env python3
"""Offline, read-only IL/inventory replay for WP-02.

The computed side calls the production Python engine.  The reference side is
implemented independently below from the canonical V3 amount equations and
does not call the engine's inventory, NAV, baseline, or IL helpers.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Callable, Iterable

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.lp_il_inventory_engine_v1_readonly import (  # noqa: E402
    current_inventory,
    hodl_nav,
    il_usd,
    paper_entry_baseline,
    position_state_from_capital,
)


DEFAULT_REAL_SWAP_SOURCE = str(
    _REPO_ROOT
    / "reports/strategy_evidence_r4_swap_event_fee_replay/20260611_080000"
    / "swap_events_0xb2cc22.jsonl"
)
SCENARIO_TYPES = (
    "inside",
    "upper_breach",
    "lower_breach",
    "gap_through",
    "v_shape",
    "sustained_trend",
)
INVENTORY_ERROR_LIMIT_PCT = 0.1
IL_ERROR_LIMIT_BPS_OF_NAV = 5.0


@dataclass(frozen=True)
class Trajectory:
    trajectory_id: str
    scenario_type: str
    provenance: str
    prices: tuple[float, ...]
    range_pct: float = 10.0
    capital_quote: float = 1_000.0
    source_note: str = "deterministic artificial V3 price path"


def _decode_sqrt_price_x96(data_hex: str) -> int:
    """Decode word 3 of a standard V3/Slipstream Swap event payload."""

    payload = data_hex[2:] if data_hex.startswith("0x") else data_hex
    if len(payload) < 192:
        raise ValueError("Swap data is shorter than three ABI words")
    sqrt_price_x96 = int(payload[128:192], 16)
    if sqrt_price_x96 <= 0:
        raise ValueError("decoded sqrtPriceX96 is not positive")
    return sqrt_price_x96


def load_real_swap_prices(source: str | Path, *, limit: int = 128) -> list[float]:
    """Stream a deterministic prefix of tracked Base WETH/USDC Swap events.

    Pool token decimals are token0 WETH=18 and token1 USDC=6.  The returned
    human price is token1 per token0 (USDC per WETH).  No RPC/network is used.
    """

    if limit <= 0:
        raise ValueError("limit must be positive")
    path = Path(source)
    prices: list[float] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if len(prices) >= limit:
                break
            try:
                event = json.loads(line)
                sqrt_price_x96 = _decode_sqrt_price_x96(event["data"])
                raw_ratio = (sqrt_price_x96 / (2**96)) ** 2
                price = raw_ratio * 10 ** (18 - 6)
                if not math.isfinite(price) or price <= 0:
                    raise ValueError("decoded price is not positive and finite")
                prices.append(price)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid V3 swap record at {path}:{line_number}: {exc}") from exc
    if len(prices) < limit:
        raise ValueError(f"source contains only {len(prices)} decodable swaps; need {limit}")
    return prices


def _real_inside_trajectories(real_prices: list[float]) -> list[Trajectory]:
    if len(real_prices) < 48:
        raise ValueError("at least 48 real swap prices are required")
    trajectories = []
    source_note = (
        "real historical Base Swap flow; Aerodrome Slipstream WETH/USDC pool "
        "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59; tracked raw artifact"
    )
    for index in range(6):
        window = tuple(real_prices[index * 8 : (index + 1) * 8])
        entry = window[0]
        max_deviation_pct = max(abs(price / entry - 1.0) * 100.0 for price in window)
        # The source remains an unmodified real price window.  Only the paper
        # range is sized around it so the scenario truthfully remains inside.
        range_pct = min(95.0, max(2.0, max_deviation_pct + 0.5))
        trajectories.append(
            Trajectory(
                trajectory_id=f"real-inside-{index + 1:02d}",
                scenario_type="inside",
                provenance="real_historical_swap",
                prices=window,
                range_pct=range_pct,
                source_note=source_note,
            )
        )
    return trajectories


def _scaled(pattern: Iterable[float], scale: float) -> tuple[float, ...]:
    return tuple(float(value) * scale for value in pattern)


def _synthetic_trajectory(scenario: str, index: int) -> Trajectory:
    scale = 1.0 + index * 0.015
    if scenario == "inside":
        pattern = (100, 102, 99, 104, 97, 101, 103, 100)
    elif scenario == "upper_breach":
        pattern = (100, 103, 108, 111, 120, 130, 145, 160)
    elif scenario == "lower_breach":
        pattern = (100, 97, 92, 89, 80, 70, 60, 50)
    elif scenario == "gap_through":
        pattern = (100, 103, 128, 132, 82, 78, 96, 105)
    elif scenario == "v_shape":
        pattern = (100, 94, 87, 78, 84, 92, 101, 112)
    elif scenario == "sustained_trend":
        pattern = (100, 105, 112, 121, 132, 145, 160, 178)
        if index % 2:
            pattern = tuple(10_000 / value for value in pattern)
    else:
        raise ValueError(f"unknown scenario: {scenario}")
    return Trajectory(
        trajectory_id=f"synthetic-{scenario}-{index + 1:02d}",
        scenario_type=scenario,
        provenance="synthetic",
        prices=_scaled(pattern, scale),
    )


def build_trajectories(real_prices: list[float]) -> list[Trajectory]:
    """Build 60 deterministic trajectories: 10 per required scenario type."""

    trajectories = _real_inside_trajectories(real_prices)
    trajectories.extend(_synthetic_trajectory("inside", index) for index in range(4))
    for scenario in SCENARIO_TYPES[1:]:
        trajectories.extend(_synthetic_trajectory(scenario, index) for index in range(10))
    return trajectories


# -------------------------------------------------------------------------
# Independent V3 reference math.  Keep separate from the production engine.
# -------------------------------------------------------------------------

def _reference_entry(entry_price: float, capital: float, range_pct: float) -> dict[str, float]:
    lower = entry_price * (1.0 - range_pct / 100.0)
    upper = entry_price * (1.0 + range_pct / 100.0)
    sqrt_p, sqrt_a, sqrt_b = math.sqrt(entry_price), math.sqrt(lower), math.sqrt(upper)
    q0_per_l = (sqrt_b - sqrt_p) / (sqrt_p * sqrt_b)
    q1_per_l = sqrt_p - sqrt_a
    liquidity = capital / (q0_per_l * entry_price + q1_per_l)
    return {
        "lower": lower,
        "upper": upper,
        "liquidity": liquidity,
        "q0_entry": liquidity * q0_per_l,
        "q1_entry": liquidity * q1_per_l,
    }


def _reference_inventory(reference: dict[str, float], price: float) -> tuple[float, float]:
    lower, upper, liquidity = reference["lower"], reference["upper"], reference["liquidity"]
    sqrt_a, sqrt_b = math.sqrt(lower), math.sqrt(upper)
    if price <= lower:
        return liquidity * (sqrt_b - sqrt_a) / (sqrt_a * sqrt_b), 0.0
    if price >= upper:
        return 0.0, liquidity * (sqrt_b - sqrt_a)
    sqrt_p = math.sqrt(price)
    q0 = liquidity * (sqrt_b - sqrt_p) / (sqrt_p * sqrt_b)
    q1 = liquidity * (sqrt_p - sqrt_a)
    return q0, q1


def _evaluate_trajectory(trajectory: Trajectory) -> dict:
    entry_price = trajectory.prices[0]
    computed_state = position_state_from_capital(
        entry_price, trajectory.capital_quote, trajectory.range_pct
    )
    computed_baseline = paper_entry_baseline(
        entry_price, trajectory.capital_quote, trajectory.range_pct
    )
    reference = _reference_entry(entry_price, trajectory.capital_quote, trajectory.range_pct)
    observations = []
    max_inventory_error = 0.0
    max_il_error = 0.0
    for tick_index, price in enumerate(trajectory.prices):
        computed_inventory = current_inventory(computed_state, price)
        computed_hodl = hodl_nav(computed_baseline, price, 1.0)
        computed_il = il_usd(computed_inventory.nav_quote, computed_hodl)

        ref_q0, ref_q1 = _reference_inventory(reference, price)
        ref_lp_nav = ref_q0 * price + ref_q1
        ref_hodl = reference["q0_entry"] * price + reference["q1_entry"]
        ref_il = ref_lp_nav - ref_hodl

        q0_scale = max(abs(reference["q0_entry"]), abs(ref_q0), 1e-30)
        q1_scale = max(abs(reference["q1_entry"]), abs(ref_q1), 1e-30)
        inventory_error_pct = 100.0 * max(
            abs(computed_inventory.q0 - ref_q0) / q0_scale,
            abs(computed_inventory.q1 - ref_q1) / q1_scale,
        )
        il_error_bps = 10_000.0 * abs(computed_il - ref_il) / max(abs(ref_hodl), 1e-30)
        max_inventory_error = max(max_inventory_error, inventory_error_pct)
        max_il_error = max(max_il_error, il_error_bps)
        observations.append(
            {
                "tick_index": tick_index,
                "price_token1_per_token0": price,
                "computed_q0": computed_inventory.q0,
                "reference_q0": ref_q0,
                "computed_q1": computed_inventory.q1,
                "reference_q1": ref_q1,
                "computed_il_quote": computed_il,
                "reference_il_quote": ref_il,
                "inventory_error_pct": inventory_error_pct,
                "il_error_bps_of_nav": il_error_bps,
            }
        )
    passed = (
        max_inventory_error <= INVENTORY_ERROR_LIMIT_PCT
        and max_il_error <= IL_ERROR_LIMIT_BPS_OF_NAV
    )
    return {
        "trajectory_id": trajectory.trajectory_id,
        "scenario_type": trajectory.scenario_type,
        "provenance": trajectory.provenance,
        "source_note": trajectory.source_note,
        "price_convention": "human token1 per token0; NAV in token1 quote units",
        "tick_count": len(trajectory.prices),
        "range_pct": trajectory.range_pct,
        "capital_quote": trajectory.capital_quote,
        "max_inventory_error_pct": max_inventory_error,
        "max_il_error_bps_of_nav": max_il_error,
        "passed": passed,
        "observations": observations,
    }


def _default_clock() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_replay(
    *,
    real_source: str | Path = DEFAULT_REAL_SWAP_SOURCE,
    output_root: str | Path | None = None,
    clock: Callable[[], str] = _default_clock,
) -> dict:
    """Run the offline replay and write summary.json/details.jsonl/summary.md."""

    source = Path(real_source).resolve()
    root = Path(output_root) if output_root is not None else _REPO_ROOT / "reports/lp_il_math_replay"
    run_dir = root / clock()
    run_dir.mkdir(parents=True, exist_ok=False)

    real_prices = load_real_swap_prices(source, limit=128)
    trajectories = build_trajectories(real_prices)
    details = [_evaluate_trajectory(trajectory) for trajectory in trajectories]
    distribution = Counter(row["scenario_type"] for row in details)
    real_count = sum(row["provenance"] == "real_historical_swap" for row in details)
    synthetic_count = sum(row["provenance"] == "synthetic" for row in details)
    max_inventory_error = max(row["max_inventory_error_pct"] for row in details)
    max_il_error = max(row["max_il_error_bps_of_nav"] for row in details)
    status = "PASS" if all(row["passed"] for row in details) and len(details) >= 50 else "FAIL"
    summary = {
        "status": status,
        "trajectory_count": len(details),
        "real_trajectory_count": real_count,
        "synthetic_trajectory_count": synthetic_count,
        "scenario_distribution": dict(sorted(distribution.items())),
        "max_inventory_error_pct": max_inventory_error,
        "max_il_error_bps_of_nav": max_il_error,
        "inventory_error_limit_pct": INVENTORY_ERROR_LIMIT_PCT,
        "il_error_limit_bps_of_nav": IL_ERROR_LIMIT_BPS_OF_NAV,
        "real_source": str(source),
        "real_source_sha256": _sha256(source),
        "real_source_schema": "JSONL raw Base Swap logs: pool/block/tx/topics/data",
        "real_source_sampling": "streamed first 128 decoded swaps; six unmodified 8-event windows",
        "reference_math": "independent canonical V3 amount0/amount1 equations in replay module",
        "read_only": True,
    }
    with (run_dir / "details.jsonl").open("w", encoding="utf-8") as handle:
        for row in details:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (run_dir / "summary.md").write_text(
        "# WP-02 IL Math Replay\n\n"
        f"- Status: **{status}**\n"
        f"- Trajectories: {len(details)} ({real_count} real historical, {synthetic_count} synthetic)\n"
        f"- Scenario distribution: `{dict(sorted(distribution.items()))}`\n"
        f"- Max inventory error: {max_inventory_error:.12g}% (limit {INVENTORY_ERROR_LIMIT_PCT}%)\n"
        f"- Max IL error: {max_il_error:.12g} bps of HODL NAV (limit {IL_ERROR_LIMIT_BPS_OF_NAV})\n"
        f"- Real source: `{source}`\n"
        "- Sampling: streamed first 128 decoded swaps; six unmodified 8-event windows.\n"
        "- Price convention: human token1 per token0; WETH/USDC source uses token0=18, token1=6 decimals.\n"
        "- Safety: offline/read-only; no wallet, signing, broadcast, approve, or paid service.\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline read-only V3 IL math replay")
    parser.add_argument("--real-source", default=DEFAULT_REAL_SWAP_SOURCE)
    parser.add_argument("--output-root", default=str(_REPO_ROOT / "reports/lp_il_math_replay"))
    parser.add_argument("--stamp", default=None, help="deterministic output directory name")
    args = parser.parse_args()
    clock = (lambda: args.stamp) if args.stamp else _default_clock
    summary = run_replay(real_source=args.real_source, output_root=args.output_root, clock=clock)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
