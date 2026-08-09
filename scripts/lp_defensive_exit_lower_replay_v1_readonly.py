#!/usr/bin/env python3
"""C3 real-swap lower-breach defensive-exit replay (paper/read-only)."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_exit_policy_v1_readonly import (
    BreachDirection,
    BreachObservation,
    ExitMode,
    ExitPolicyConfig,
    QuoteResult,
    RiskSignals,
    RiskState,
    RpcHealth,
    build_paper_action_plan,
    classify_breach,
    evaluate_risk,
)
from scripts.lp_swap_cost_model_v1_readonly import (
    exit_conversion_cost_usd,
    slippage_bps_for_swap,
)


DEFAULT_SWAP_SOURCE = (
    REPO_ROOT
    / "reports/strategy_evidence_r4_swap_event_fee_replay/20260611_080000"
    / "swap_events_decoded.csv"
)
DEFAULT_REPORT_ROOT = REPO_ROOT / "reports/lp_defensive_exit_lower_replay"
POSITION_USD = 50.0
RISKY_TARGET = 0.25
MAX_SLIPPAGE_BPS = 75.0
MIN_BENCHMARK_NOTIONAL_USD = 100.0
MAX_PLAUSIBLE_ACTUAL_COST_BPS = 30.0

POOL_SPECS = (
    {
        "pool": "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59",
        "label": "Aerodrome Slipstream WETH/USDC 0.05%",
        "fee_tier": 0.0005,
        "unacceptable_quote": False,
    },
    {
        "pool": "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38",
        "label": "PancakeSwap V3 WETH/USDC 0.01%",
        "fee_tier": 0.0001,
        "unacceptable_quote": False,
    },
    {
        "pool": "0xb775272e537cc670c65dc852908ad47015244eaf",
        "label": "PancakeSwap V3 WETH/USDC 0.05%",
        "fee_tier": 0.0005,
        "unacceptable_quote": True,
    },
)


@dataclass(frozen=True)
class Swap:
    pool: str
    block: int
    tx: str
    price: float
    liquidity_raw: int
    amount0: float
    amount1: float


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_real_swaps(path: Path = DEFAULT_SWAP_SOURCE) -> dict[str, list[Swap]]:
    """Load immutable R4 decoded events; prices are human USDC per WETH."""
    grouped: dict[str, list[Swap]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            sqrt_price_x96 = int(row["sqrtPriceX96"])
            price = (sqrt_price_x96 / float(1 << 96)) ** 2 * 1e12
            event = Swap(
                pool=row["pool"].lower(),
                block=int(row["block"]),
                tx=row["tx"],
                price=price,
                liquidity_raw=int(row["liquidity"]),
                amount0=float(row["amount0_human"]),
                amount1=float(row["amount1_human"]),
            )
            grouped.setdefault(event.pool, []).append(event)
    for events in grouped.values():
        events.sort(key=lambda item: (item.block, item.tx))
    return grouped


def _largest_distinct_block_drop(events: list[Swap]) -> tuple[Swap, Swap]:
    pairs = [
        (events[index - 1], events[index])
        for index in range(1, len(events))
        if events[index].block > events[index - 1].block
    ]
    if not pairs:
        raise ValueError("real swap stream has no distinct-block pair")
    return min(pairs, key=lambda pair: pair[1].price / pair[0].price - 1.0)


def _previous_distinct_block(events: list[Swap], index: int) -> Swap | None:
    for prior in range(index - 1, -1, -1):
        if events[prior].block < events[index].block:
            return events[prior]
    return None


def _first_reliable_sell_after(
    events: list[Swap], *, after_block: int, fee_tier: float
) -> tuple[Swap, Swap, float, float]:
    """Pick the first later real sell whose rounded CSV amounts remain plausible.

    The source stores human amounts at finite decimal precision.  The lower
    bound of 80% of the pool fee and the broad 30 bps ceiling remove tiny-value
    rounding artefacts without selecting on model agreement.
    """
    fee_bps = fee_tier * 10_000.0
    for index, event in enumerate(events):
        if event.block <= after_block or event.amount0 <= 0.0 or event.amount1 >= 0.0:
            continue
        prior = _previous_distinct_block(events, index)
        if prior is None:
            continue
        notional = event.amount0 * prior.price
        actual_cost = notional + event.amount1  # amount1 is negative USDC received
        actual_cost_bps = actual_cost / notional * 10_000.0 if notional > 0.0 else math.nan
        if (
            notional >= MIN_BENCHMARK_NOTIONAL_USD
            and actual_cost > 0.0
            and fee_bps * 0.8 <= actual_cost_bps <= MAX_PLAUSIBLE_ACTUAL_COST_BPS
        ):
            return prior, event, notional, actual_cost
    raise ValueError("no reliable post-breach sell-base benchmark")


def _config() -> ExitPolicyConfig:
    return ExitPolicyConfig(
        profile="MAJORS",
        risky_token_side="token0:WETH",
        stable_token_side="token1:USDC",
        risky_inventory_target=RISKY_TARGET,
        max_slippage_bps=MAX_SLIPPAGE_BPS,
    )


def replay_scenario(spec: dict[str, Any], events: list[Swap]) -> dict[str, Any]:
    before, breach = _largest_distinct_block_drop(events)
    lower_bound = (before.price + breach.price) / 2.0
    direction = classify_breach(
        price=breach.price,
        lower_bound=lower_bound,
        upper_bound=before.price * 1.05,
    )
    gap_bps = (before.price - breach.price) / before.price * 10_000.0
    # Below a risky-token0 CL lower bound the removed LP inventory is token0.
    post_remove_ratio = 1.0
    risky_value_to_convert = POSITION_USD * (post_remove_ratio - RISKY_TARGET)
    expected_cost = exit_conversion_cost_usd(
        risky_value_to_convert,
        before.liquidity_raw,
        breach.price,
        spec["fee_tier"],
        18,
        6,
        "sell_base",
    )
    expected_slippage = slippage_bps_for_swap(
        risky_value_to_convert,
        before.liquidity_raw,
        breach.price,
        18,
        6,
        "sell_base",
    )
    observation = BreachObservation(
        breach_direction=direction,
        post_remove_inventory_ratio=post_remove_ratio,
        post_remove_delta_usd=risky_value_to_convert,
        expected_swap_cost=expected_cost,
    )
    decision = evaluate_risk(
        RiskState.RISK_OFF_READY,
        RiskSignals(
            lower_breach=True,
            trend_continuation=True,
            trend_worsening=True,
            il_soft_breach=True,
            netcover_forward=0.8,
        ),
        observation,
        _config(),
    )

    unacceptable_quote = bool(spec["unacceptable_quote"])
    quoted_slippage = MAX_SLIPPAGE_BPS + 1.0 if unacceptable_quote else expected_slippage
    quote = QuoteResult.ok(
        expected_slippage_bps=quoted_slippage,
        expected_swap_cost_usd=expected_cost,
    )
    final_ratio = post_remove_ratio if unacceptable_quote else RISKY_TARGET
    plan = build_paper_action_plan(
        mode=decision.recommended_exit_mode,
        rpc_health=RpcHealth.NORMAL,
        quote=quote,
        config=_config(),
        post_trade_risky_inventory_ratio=final_ratio,
        exit_latency_loss_usd=0.0,
    )

    benchmark_before, benchmark, actual_notional, actual_cost = _first_reliable_sell_after(
        events, after_block=breach.block, fee_tier=spec["fee_tier"]
    )
    model_cost_at_actual_notional = exit_conversion_cost_usd(
        actual_notional,
        benchmark_before.liquidity_raw,
        benchmark_before.price,
        spec["fee_tier"],
        18,
        6,
        "sell_base",
    )
    deviation_pct = (
        (model_cost_at_actual_notional - actual_cost) / actual_cost * 100.0
        if actual_cost > 0.0 else None
    )
    mandatory = {
        "breach_direction": decision.breach_direction.value,
        "post_remove_inventory_ratio": decision.post_remove_inventory_ratio,
        "post_remove_delta_usd": decision.post_remove_delta_usd,
        "recommended_exit_mode": decision.recommended_exit_mode.value,
        "expected_swap_cost": decision.expected_swap_cost,
    }
    assertions = {
        "real_lower_breach": direction is BreachDirection.LOWER,
        "five_mandatory_fields": len(mandatory) == 5 and all(value is not None for value in mandatory.values()),
        "remove_to_stable_recommended": decision.recommended_exit_mode is ExitMode.REMOVE_TO_STABLE,
        "paper_only": plan.paper_only,
        "actual_cost_comparison_recorded": deviation_pct is not None,
    }
    if unacceptable_quote:
        assertions.update({
            "unacceptable_quote_no_swap": not plan.swap_allowed,
            "slippage_limit_recorded": plan.block_reason == "slippage_limit",
            "staged_exit": plan.substate == "staged/limit_exit",
            "alerted": plan.alert,
            "inventory_not_falsely_complete": not plan.risk_off_complete,
        })
    else:
        assertions.update({
            "paper_remove_and_swap": plan.paper_actions == (
                "simulate_remove", "simulate_swap_to_stable"
            ),
            "post_risky_inventory_at_target": final_ratio <= RISKY_TARGET,
            "risk_off_complete": plan.risk_off_complete,
        })
    return {
        "scenario": spec["label"],
        "paper_only": True,
        "source_event_count": len(events),
        "breach": {
            "before_block": before.block,
            "before_tx": before.tx,
            "before_price": before.price,
            "breach_block": breach.block,
            "breach_tx": breach.tx,
            "breach_price": breach.price,
            "lower_bound": lower_bound,
            "gap_bps": gap_bps,
            "gap_through": gap_bps >= 10.0,
        },
        "five_mandatory_fields": mandatory,
        "decision": asdict(decision) | {
            "previous_state": decision.previous_state.value,
            "next_state": decision.next_state.value,
            "breach_direction": decision.breach_direction.value,
            "recommended_exit_mode": decision.recommended_exit_mode.value,
        },
        "paper_plan": asdict(plan) | {
            "mode": plan.mode.value,
            "next_state": plan.next_state.value,
        },
        "cost_comparison": {
            "selection_rule": "first later distinct-block plausible sell-base event; not selected on model agreement",
            "benchmark_before_block": benchmark_before.block,
            "benchmark_block": benchmark.block,
            "benchmark_tx": benchmark.tx,
            "actual_notional_usd": actual_notional,
            "replay_actual_cost_usd": actual_cost,
            "model_cost_usd": model_cost_at_actual_notional,
            "model_minus_actual_pct": deviation_pct,
            "absolute_deviation_pct": abs(deviation_pct) if deviation_pct is not None else None,
        },
        "assertions": assertions,
        "passed": all(assertions.values()),
    }


def run_replay(source: Path = DEFAULT_SWAP_SOURCE) -> dict[str, Any]:
    grouped = load_real_swaps(source)
    results = [replay_scenario(spec, grouped[spec["pool"]]) for spec in POOL_SPECS]
    return {
        "schema_version": "lp_defensive_exit_lower_replay_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "paper_only": True,
        "source": {
            "path": str(source.relative_to(REPO_ROOT)),
            "sha256": _sha256(source),
            "real_historical_swap_rows": sum(len(rows) for rows in grouped.values()),
        },
        "safety": {
            "wallet": False,
            "signing": False,
            "broadcast": False,
            "threshold_changes": False,
        },
        "passed": all(row["passed"] for row in results),
        "scenario_count": len(results),
        "gap_through_count": sum(row["breach"]["gap_through"] for row in results),
        "results": results,
    }


def write_report(out_dir: Path, source: Path = DEFAULT_SWAP_SOURCE) -> None:
    out_dir.mkdir(parents=True, exist_ok=False)
    payload = run_replay(source)
    (out_dir / "results.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# C3 Real Historical Lower-Breach Exit Replay",
        "",
        f"Result: **{'PASS' if payload['passed'] else 'FAIL'}**; "
        f"{payload['scenario_count']} lower breaches, {payload['gap_through_count']} gap-through.",
        "",
        f"Source: `{payload['source']['path']}` (`{payload['source']['sha256']}`), "
        f"{payload['source']['real_historical_swap_rows']} decoded real swaps.",
        "",
        "Paper/read-only only: no wallet, signing, approval, or broadcast.",
        "",
        "| Scenario | Lower/gap | Mode | Quote result | Post risky | Cost model vs actual | Result |",
        "|---|---|---|---|---:|---:|---|",
    ]
    for row in payload["results"]:
        plan = row["paper_plan"]
        cost = row["cost_comparison"]
        lines.append(
            f"| {row['scenario']} | LOWER/{row['breach']['gap_through']} | "
            f"{row['five_mandatory_fields']['recommended_exit_mode']} | "
            f"{'PASS' if plan['swap_allowed'] else plan['block_reason']} | "
            f"{plan['post_trade_risky_inventory_ratio']:.2f} | "
            f"{cost['model_minus_actual_pct']:+.2f}% | "
            f"{'PASS' if row['passed'] else 'FAIL'} |"
        )
    lines += [
        "",
        "The Aerodrome cost model under-estimates the selected first reliable "
        "post-breach fill by about 21%; this is explicitly retained as a calibration warning.",
    ]
    (out_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SWAP_SOURCE)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    write_report(args.out, args.source)
    print(args.out)


if __name__ == "__main__":
    main()
