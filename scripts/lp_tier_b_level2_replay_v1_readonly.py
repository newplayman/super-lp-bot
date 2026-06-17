#!/usr/bin/env python3
"""Tier-B Level-2 replay (readonly): passive vs active LP position over historical swaps."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if os.path.basename(CURRENT_DIR) == "scripts" and not os.path.exists(os.path.join(REPO_ROOT, "scripts")):
    REPO_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.lp_v3_position_value import lp_position_value_usd, lp_impermanent_loss_usd
from scripts.lp_v3_fee_share import position_liquidity_raw, fee_for_swap_usd


def price_from_sqrt_x96(sqrt_price_x96: int, dec0: int, dec1: int) -> float:
    """Convert Uniswap V3 sqrtPriceX96 to token1/token0 (decimals-adjusted) price."""
    if not sqrt_price_x96:
        return 0.0
    ratio = float(sqrt_price_x96) / (2.0 ** 96)
    return (ratio * ratio) * (10.0 ** (dec0 - dec1))


def _to_signed_256(v: int) -> int:
    v &= (1 << 256) - 1
    if v >= (1 << 255):
        v -= 1 << 256
    return v


def decode_v3_swap_data(log: Dict[str, Any]) -> Dict[str, int]:
    """Decode a Uniswap V3 Swap event log into fields."""
    data = log.get("data", "")
    if isinstance(data, str) and data.startswith("0x"):
        data = data[2:]
    if not data:
        raise ValueError("swap log missing data")
    raw = bytes.fromhex(data)

    if len(raw) < 32 * 5:
        raise ValueError("swap log data too short")

    def u256(i: int) -> int:
        off = i * 32
        return int.from_bytes(raw[off : off + 32], byteorder="big", signed=False)

    return {
        "amount0": _to_signed_256(u256(0)),
        "amount1": _to_signed_256(u256(1)),
        "sqrt_price_x96": u256(2),
        "liquidity": u256(3),
        "tick": _to_signed_256(u256(4)),
    }


V3_SWAP_TOPIC = "0xd78ad95fa46c994b6551d0da85fc275fe613ce376ca8b5ef1d2d9d89c5f0f3d16"


def _rpc_url() -> str:
    return (
        os.environ.get("D4_BASE_RPC_URL")
        or os.environ.get("BASE_RPC_URL")
        or os.environ.get("RPC_URL")
        or "https://mainnet.base.org"
    )


def _rpc_post(payload: Dict[str, Any], *, timeout: int = 30) -> Dict[str, Any]:
    response = requests.post(_rpc_url(), json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _rpc_with_retry(method: str, params: Any, *, retries: int = 5) -> Any:
    for attempt in range(retries):
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": int(time.time()),
                "method": method,
                "params": params,
            }
            out = _rpc_post(payload)
            if "error" in out:
                raise RuntimeError(f"{method} failed: {out['error']}")
            return out.get("result")
        except Exception:
            if attempt + 1 >= retries:
                raise
            sleep_s = 1.0 * (2**attempt)
            time.sleep(sleep_s)


def _to_int(v: Any) -> int:
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        return int(v, 16) if v.startswith("0x") else int(v)
    raise TypeError(f"Cannot convert block/index value: {v!r}")


def fetch_pool_swaps(pool: str, from_block: int, to_block: int, dec0: int, dec1: int) -> List[Dict[str, Any]]:
    """Fetch + decode V3 swaps for `pool` over [from_block, to_block].

    Delegates to the VERIFIED, block-windowed implementation in the Tier-C
    pipeline (correct V3 Swap topic 0xc42079f9..., signed-amount decoder, 2000-
    block windowing, env D4_BASE_RPC_URL/BASE_RPC_URL with public fallback).
    Returns dicts {block, price, liquidity, tick, amount0, amount1} sorted by block —
    exactly the shape replay() consumes.
    """
    from scripts.lp_tier_c_exit_feasibility_v1_readonly import (
        fetch_pool_swaps as _tc_fetch_pool_swaps,
    )

    return _tc_fetch_pool_swaps(pool, from_block, to_block, dec0, dec1)


def _no_data_result(mode: str) -> Dict[str, Any]:
    return {
        "mode": mode,
        "entry_price": None,
        "end_price": None,
        "n_swaps": 0,
        "fees_quote": None,
        "rebalances": None,
        "rebal_cost_quote": None,
        "lp_value_end": None,
        "il_quote": None,
        "net_quote": None,
        "net_pct": None,
        "in_range_end": None,
        "frac_swaps_in_range": None,
        "verdict": "NO_DATA",
    }


def replay(
    swaps: List[Dict[str, Any]],
    *,
    range_pct: float,
    fee_tier: float,
    dec0: int,
    dec1: int,
    mode: str,
    gas_pct: float = 0.0,
    swap_cost_bps: float = 0.0,
    hysteresis_pct: float = 0.0,
    cooldown_blocks: int = 0,
) -> Dict[str, Any]:
    """
    swaps: list of {price, liquidity(int active L), amount1(int raw), block}, time-ordered.
    size is normalized to 1.0 quote unit. entry_price = swaps[0]['price'].
    mode: 'passive' or 'active'.
    gas_pct: rebalance gas as fraction of position value per rebalance.
    swap_cost_bps: rebalance inventory cost in bps per rebalance.
    hysteresis_pct: deadband BEYOND the band edge (in %) a breach must exceed to
        justify a rebalance. 0.0 => rebalance on any exit (aggressive).
    cooldown_blocks: minimum blocks between two rebalances. 0 => no cooldown.
        Together these model the operator's Tier-A/B policy: ignore brief/shallow
        pokes outside the range, only re-center on a sustained, sizeable breach.
    Returns dict:
      {mode, entry_price, end_price, n_swaps, fees_quote, rebalances,
       rebal_cost_quote, lp_value_end, il_quote, net_quote, net_pct,
       in_range_end, frac_swaps_in_range}
    """
    if not swaps:
        return _no_data_result(mode)

    if mode not in ("passive", "active"):
        raise ValueError("mode must be 'passive' or 'active'")

    sorted_swaps = sorted(swaps, key=lambda x: (x.get("block", 0), x.get("price", 0.0)))
    entry_price = float(sorted_swaps[0]["price"])
    end_price = float(sorted_swaps[-1]["price"])
    n_swaps = len(sorted_swaps)

    anchor = entry_price
    lower = anchor * (1.0 - range_pct / 100.0)
    upper = anchor * (1.0 + range_pct / 100.0)
    in_range_count = 0

    fees_quote = 0.0
    rebalances = 0
    rebal_cost_quote = 0.0

    if mode == "passive":
        capital = 1.0
        l_pos_raw = position_liquidity_raw(capital, anchor, range_pct, dec0, dec1)

        for s in sorted_swaps:
            p = float(s["price"])
            in_range = lower <= p <= upper
            if in_range:
                in_range_count += 1
                fees_quote += fee_for_swap_usd(
                    l_pos_raw,
                    float(s.get("liquidity", 0) or 0),
                    int(s.get("amount1", 0)),
                    fee_tier,
                    dec1,
                )

        lp_value_end = lp_position_value_usd(1.0, anchor, range_pct, end_price)
        il_quote = lp_impermanent_loss_usd(1.0, entry_price, range_pct, end_price)
        net_quote = lp_value_end + fees_quote - 1.0
        net_pct = net_quote * 100.0

        return {
            "mode": mode,
            "entry_price": entry_price,
            "end_price": end_price,
            "n_swaps": n_swaps,
            "fees_quote": fees_quote,
            "rebalances": rebalances,
            "rebal_cost_quote": rebal_cost_quote,
            "lp_value_end": lp_value_end,
            "il_quote": il_quote,
            "net_quote": net_quote,
            "net_pct": net_pct,
            "in_range_end": lower <= end_price <= upper,
            "frac_swaps_in_range": in_range_count / n_swaps if n_swaps else 0.0,
        }

    # active mode
    capital = 1.0
    l_pos_raw = position_liquidity_raw(capital, anchor, range_pct, dec0, dec1)
    l_base_per_unit = position_liquidity_raw(1.0, anchor, range_pct, dec0, dec1)
    last_rebal_block = int(sorted_swaps[0].get("block", 0) or 0)

    for s in sorted_swaps:
        p = float(s["price"])
        blk = int(s.get("block", 0) or 0)
        in_range = lower <= p <= upper
        if in_range:
            in_range_count += 1
            fees_quote += capital * fee_for_swap_usd(
                l_base_per_unit,
                float(s.get("liquidity", 0) or 0),
                int(s.get("amount1", 0)),
                fee_tier,
                dec1,
            )
            continue

        # Out of range. Gate the rebalance on hysteresis (breach depth) + cooldown.
        if p > upper:
            breach_pct = (p - upper) / upper * 100.0
        else:
            breach_pct = (lower - p) / lower * 100.0
        deep_enough = breach_pct >= hysteresis_pct
        cooled_down = (blk - last_rebal_block) >= cooldown_blocks
        if not (deep_enough and cooled_down):
            # Hold out-of-range: earn no fee, do NOT churn. (transient/shallow poke)
            continue

        cur_val = capital * lp_position_value_usd(1.0, anchor, range_pct, p)
        cost = cur_val * (gas_pct + swap_cost_bps / 10000.0)
        rebal_cost_quote += cost
        capital = cur_val - cost
        rebalances += 1
        last_rebal_block = blk

        anchor = p
        lower = anchor * (1.0 - range_pct / 100.0)
        upper = anchor * (1.0 + range_pct / 100.0)
        l_pos_raw = position_liquidity_raw(capital, anchor, range_pct, dec0, dec1)
        l_base_per_unit = position_liquidity_raw(1.0, anchor, range_pct, dec0, dec1)

        in_range_count += 1
        fees_quote += capital * fee_for_swap_usd(
            l_base_per_unit,
            float(s.get("liquidity", 0) or 0),
            int(s.get("amount1", 0)),
            fee_tier,
            dec1,
        )

    capital_value_end = capital * lp_position_value_usd(1.0, anchor, range_pct, end_price)
    il_quote = lp_impermanent_loss_usd(1.0, entry_price, range_pct, end_price)
    net_quote = capital_value_end + fees_quote - 1.0
    net_pct = net_quote * 100.0

    return {
        "mode": mode,
        "entry_price": entry_price,
        "end_price": end_price,
        "n_swaps": n_swaps,
        "fees_quote": fees_quote,
        "rebalances": rebalances,
        "rebal_cost_quote": rebal_cost_quote,
        "lp_value_end": capital_value_end,
        "il_quote": il_quote,
        "net_quote": net_quote,
        "net_pct": net_pct,
        "in_range_end": lower <= end_price <= upper,
        "frac_swaps_in_range": in_range_count / n_swaps if n_swaps else 0.0,
    }


def _median(values: List[float]) -> float:
    return statistics.median(values)


def _build_parser() -> argparse.Namespace:
    default_out = os.path.join(
        "reports",
        "lp_tier_b_level2",
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
    )
    p = argparse.ArgumentParser(description="Replay real historical swaps for passive and active LP behavior.")
    p.add_argument("--config", type=str, help="Path to JSON config file")
    p.add_argument("--gas-pct", type=float, default=0.001)
    p.add_argument("--swap-cost-bps", type=float, default=5.0)
    p.add_argument("--hysteresis-pct", type=float, default=2.0,
                   help="deadband beyond band edge (%) before a rebalance is allowed (hyst mode)")
    p.add_argument("--cooldown-blocks", type=int, default=10800,
                   help="min blocks between rebalances in hyst mode (~6h on Base @2s)")
    p.add_argument("--self-test", action="store_true", help="Run synthetic self-test (no RPC)")
    p.add_argument("--out", type=str, default=default_out)
    return p.parse_args()


def _fmt_pct(v: Any) -> str:
    if v is None:
        return "N/A"
    return f"{v:.2f}%"


def _run_self_test() -> None:
    print("[self-test] Round-trip passive")
    roundtrip = [
        {"block": 1, "price": 1.0, "liquidity": 5000000, "amount1": 10**18},
        {"block": 2, "price": 1.05, "liquidity": 5000000, "amount1": 10**18},
        {"block": 3, "price": 1.0, "liquidity": 5000000, "amount1": 10**18},
    ]
    out_passive = replay(roundtrip, range_pct=10, fee_tier=0.003, dec0=18, dec1=18, mode="passive")
    print(json.dumps(out_passive, indent=2, sort_keys=True))

    print("[self-test] Trend passive vs active with rebalance")
    trend = [
        {"block": 1, "price": 1.0, "liquidity": 5000000, "amount1": 10**18},
        {"block": 2, "price": 1.12, "liquidity": 5000000, "amount1": 10**18},
        {"block": 3, "price": 1.09, "liquidity": 5000000, "amount1": 10**18},
    ]
    out_passive_trend = replay(trend, range_pct=10, fee_tier=0.003, dec0=18, dec1=18, mode="passive", gas_pct=0.001, swap_cost_bps=5)
    out_active_trend = replay(trend, range_pct=10, fee_tier=0.003, dec0=18, dec1=18, mode="active", gas_pct=0.001, swap_cost_bps=5)
    print("passive:", json.dumps(out_passive_trend, indent=2, sort_keys=True))
    print("active :", json.dumps(out_active_trend, indent=2, sort_keys=True))

    print("[self-test] In-range fee-only check")
    no_fee = [
        {"block": 1, "price": 1.0, "liquidity": 5000000, "amount1": 10**18},
        {"block": 2, "price": 1.5, "liquidity": 5000000, "amount1": 10**18},
    ]
    out_no_fee = replay(no_fee, range_pct=10, fee_tier=0.003, dec0=18, dec1=18, mode="passive")
    print(json.dumps(out_no_fee, indent=2, sort_keys=True))

    print("[self-test] NO_DATA")
    out_nodata = replay([], range_pct=10, fee_tier=0.003, dec0=18, dec1=18, mode="passive")
    print(json.dumps(out_nodata, indent=2, sort_keys=True))

    print("[self-test] Hysteresis+cooldown suppresses churn vs aggressive")
    # price pokes just past +10% band repeatedly then returns; shallow breaches.
    choppy = [
        {"block": 1, "price": 1.00, "liquidity": 5000000, "amount1": 10**18},
        {"block": 2, "price": 1.11, "liquidity": 5000000, "amount1": 10**18},  # +11% shallow poke
        {"block": 3, "price": 1.00, "liquidity": 5000000, "amount1": 10**18},
        {"block": 4, "price": 1.11, "liquidity": 5000000, "amount1": 10**18},  # poke again
        {"block": 5, "price": 1.00, "liquidity": 5000000, "amount1": 10**18},
    ]
    aggr = replay(choppy, range_pct=10, fee_tier=0.003, dec0=18, dec1=18, mode="active",
                  gas_pct=0.001, swap_cost_bps=5, hysteresis_pct=0.0, cooldown_blocks=0)
    hyst = replay(choppy, range_pct=10, fee_tier=0.003, dec0=18, dec1=18, mode="active",
                  gas_pct=0.001, swap_cost_bps=5, hysteresis_pct=5.0, cooldown_blocks=0)
    print(f"aggressive rebalances={aggr['rebalances']} net={aggr['net_pct']:.3f}% | "
          f"hyst(5% deadband) rebalances={hyst['rebalances']} net={hyst['net_pct']:.3f}%")
    assert hyst["rebalances"] < aggr["rebalances"], (hyst["rebalances"], aggr["rebalances"])
    print("OK: hysteresis suppressed shallow-poke churn")


def main() -> None:
    args = _build_parser()
    if args.self_test:
        _run_self_test()
        return

    if not args.config:
        raise SystemExit("--config is required unless --self-test is set")

    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)

    records: List[Dict[str, Any]] = []
    for item in config:
        pool = item["pool"]
        label = item.get("label", pool)
        dec0 = int(item["dec0"])
        dec1 = int(item["dec1"])
        fee_tier = float(item["fee_tier"])
        range_pct = float(item["range_pct"])
        entry_block = int(item["entry_block"])
        blocks_forward = int(item["blocks_forward"])

        from_block = entry_block
        to_block = entry_block + blocks_forward
        swaps = fetch_pool_swaps(pool, from_block, to_block, dec0, dec1)

        common = dict(range_pct=range_pct, fee_tier=fee_tier, dec0=dec0, dec1=dec1,
                      gas_pct=args.gas_pct, swap_cost_bps=args.swap_cost_bps)
        passive = replay(swaps, mode="passive", **common)
        # aggressive = rebalance on any exit (hysteresis 0, cooldown 0)
        active_aggr = replay(swaps, mode="active", hysteresis_pct=0.0, cooldown_blocks=0, **common)
        # hysteresis + cooldown (the operator's actual policy)
        active_hyst = replay(swaps, mode="active",
                             hysteresis_pct=args.hysteresis_pct,
                             cooldown_blocks=args.cooldown_blocks, **common)

        rec = {
            "label": label,
            "pool": pool,
            "passive": passive,
            "active_aggr": active_aggr,
            "active_hyst": active_hyst,
            "swaps": len(swaps),
            "entry_block": entry_block,
            "to_block": to_block,
            "range_pct": range_pct,
            "fee_tier": fee_tier,
            "dec0": dec0,
            "dec1": dec1,
            "hysteresis_pct": args.hysteresis_pct,
            "cooldown_blocks": args.cooldown_blocks,
        }
        records.append(rec)

        p_np = _fmt_pct(passive["net_pct"])
        ag_np = _fmt_pct(active_aggr["net_pct"])
        hy_np = _fmt_pct(active_hyst["net_pct"])
        ag_rb = int(active_aggr["rebalances"] or 0)
        hy_rb = int(active_hyst["rebalances"] or 0)
        nsw = int(passive["n_swaps"] or 0)
        print(f"{label} (±{range_pct:.1f}%): passive {p_np} | aggr {ag_np} (rb {ag_rb}) | "
              f"hyst {hy_np} (rb {hy_rb}) | swaps {nsw}")

    def _vals(key):
        return [r[key]["net_pct"] for r in records if r[key]["net_pct"] is not None]

    passive_vals = _vals("passive")
    aggr_vals = _vals("active_aggr")
    hyst_vals = _vals("active_hyst")

    def _share_pos(vals):
        return (sum(1 for v in vals if v > 0) / len(vals) * 100.0) if vals else 0.0

    aggregate = {
        "n_pools": len(records),
        "median_passive_net_pct": _median(passive_vals) if passive_vals else None,
        "median_active_aggr_net_pct": _median(aggr_vals) if aggr_vals else None,
        "median_active_hyst_net_pct": _median(hyst_vals) if hyst_vals else None,
        "share_passive_positive": _share_pos(passive_vals),
        "share_active_aggr_positive": _share_pos(aggr_vals),
        "share_active_hyst_positive": _share_pos(hyst_vals),
    }

    print("Aggregate")
    print(json.dumps(aggregate, indent=2, sort_keys=True))

    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, "lp_tier_b_level2_replay_v1_readonly.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"records": records, "aggregate": aggregate}, f, indent=2, sort_keys=True)
    print(f"saved: {out_path}")


if __name__ == "__main__":
    main()
