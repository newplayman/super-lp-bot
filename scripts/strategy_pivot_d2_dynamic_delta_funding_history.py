#!/usr/bin/env python3
"""
D2 — Dynamic Delta Replay with Funding History

Reads R4 swap events (tick path), re-simulates the LP + SHORT hedge with
rebalance rules and a per-event fee/IL calculation.

Grid:
  2 pools (0xb2cc, 0x72ab)
  3 sizes ($250, $500, $1000)
  3 ranges (±2%, ±5%, ±10%)
  5 rebalance rules (none, hourly, >0.5%, >1%, >2% price move)
  3 hedge strategies (static 0.5, static 0.75, dynamic)
  = 2 × 3 × 3 × 5 × 3 = 270 cells

Funding: uses D2 funding_history.csv (median +0.83% APR for shorts; stress at 5th pct -9.02%)

LP fee: from R4C fee_per_dollar_per_day for the pool/range.
IL: tick-path based — for each event, compute LVR over the hold since last rebalance.
Rebalance gas: 1 gas cycle per rebalance.
Hedge funding: real-time accrual at observed rate (or stress scenario).
"""

import csv
import json
import math
import os
import statistics
from collections import defaultdict
from datetime import datetime, timezone

D1_DIR = "reports/strategy_pivot_d1_delta_hedged_lp_feasibility/20260612_120000"
R4C_DIR = "reports/strategy_evidence_r4c_independent_clmm_liquidity_replay/20260612_100000"
R4_DIR = "reports/strategy_evidence_r4_swap_event_fee_replay/20260611_080000"
D2_DIR = "reports/strategy_pivot_d2_dynamic_delta_funding_history/20260612_140000"

ETH_USD = 1653.0
GAS_CYCLE_USD = 0.0795
ETH_DAILY_SIGMA = 0.04  # 4% daily = 76% annualized; matches D1
PERP_TAKER_FEE = 0.0002  # 0.02% (Hyperliquid)
HOURS_PER_YEAR = 8760

# Pools
POOLS = {
    "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59": {
        "name": "Aerodrome Slipstream WETH/USDC 0.05%",
        "fee_tier": 0.0005,
        "jsonl": f"{R4_DIR}/swap_events_0xb2cc22.jsonl",
        "r4c_fee_per_dollar_per_day": {2: 0.012, 5: 0.012, 10: 0.0062},  # rough from R4C observations
    },
    "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38": {
        "name": "PancakeSwap V3 WETH/USDC 0.01%",
        "fee_tier": 0.0001,
        "jsonl": f"{R4_DIR}/swap_events_0x72ab38.jsonl",
        "r4c_fee_per_dollar_per_day": {2: 0.001, 5: 0.001, 10: 0.0005},  # 0.01% fee tier, lower fees
    },
}

# Slight differentiators for ranges
# D1 R4C: ±5% 0xb2cc fee_per_dollar = 0.012 ($0.5994 / $50 = 0.01199 ≈ 0.012)
# ±10% 0xb2cc: 0.0062 ($0.3102 / $50 = 0.00620)
# ±15% 0xb2cc: 0.0043 ($0.2140 / $50 = 0.00428)
# Interpolation: ±2% 0xb2cc ~ 0.018 (scaled by IN_RANGE_FRAC ~ 0.95-1.0 from D1)
# For 0x72ab (0.01% fee tier): scale all by 0.01/0.05 = 0.2
for p in POOLS:
    pdata = POOLS[p]
    if pdata["fee_tier"] == 0.0001:
        pdata["r4c_fee_per_dollar_per_day"] = {2: 0.018 * 0.2, 5: 0.012 * 0.2, 10: 0.0062 * 0.2}
    else:
        pdata["r4c_fee_per_dollar_per_day"] = {2: 0.018, 5: 0.012, 10: 0.0062}

SIZES = [250, 500, 1000]
RANGES_PCT = [2, 5, 10]
REBAL_RULES = [
    {"name": "none", "max_move_pct": None, "max_hold_blocks": 999999},
    {"name": "hourly", "max_move_pct": None, "max_hold_blocks": 1800},  # 1h = 1800 Base blocks
    {"name": "gt_0.5pct", "max_move_pct": 0.5, "max_hold_blocks": 999999},
    {"name": "gt_1pct", "max_move_pct": 1.0, "max_hold_blocks": 999999},
    {"name": "gt_2pct", "max_move_pct": 2.0, "max_hold_blocks": 999999},
]
HEDGE_STRATEGIES = ["static_0.5", "static_0.75", "dynamic"]

BASE_BLOCKS_PER_H = 1800  # Base ~2s blocks
HOLD_H = 24  # 24h baseline (use R4 24h window)
HOLD_BLOCKS = HOLD_H * BASE_BLOCKS_PER_H

# Funding history
def load_funding_history():
    """Load Binance funding history. Returns list of (timestamp_ms, apr_pct)."""
    history = []
    with open(f"{D2_DIR}/funding_history.csv") as f:
        r = csv.DictReader(f)
        for row in r:
            ts = int(datetime.fromisoformat(row['funding_time_utc']).timestamp() * 1000)
            apr = float(row['funding_apr_pct'])
            history.append((ts, apr))
    return sorted(history)


def decode_v3(data_hex):
    p = data_hex[2:]
    a0 = int(p[0:64], 16)
    if a0 & (1 << 255): a0 -= (1 << 256)
    a1 = int(p[64:128], 16)
    if a1 & (1 << 255): a1 -= (1 << 256)
    sqrt = int(p[128:192], 16)
    liq = int(p[192:256], 16)
    tick_raw = int(p[314:320], 16)
    if tick_raw & (1 << 23): tick_raw -= (1 << 24)
    return a0, a1, sqrt, liq, tick_raw


def load_swap_events(pool_addr, info, max_block_window=HOLD_BLOCKS):
    """Load swap events for the last max_block_window blocks."""
    events = []
    with open(info["jsonl"]) as f:
        for line in f:
            ev = json.loads(line)
            a0, a1, sqrt, liq, tick = decode_v3(ev['data'])
            a0_h = a0 / 1e18
            a1_h = a1 / 1e6
            vol_usd = max(abs(a0_h) * ETH_USD, abs(a1_h))
            events.append({
                "block": ev['block'],
                "amount0_human": a0_h,
                "amount1_human": a1_h,
                "tick": tick,
                "vol_usd": vol_usd,
                "fee_usd_pool": vol_usd * info["fee_tier"],
            })
    events.sort(key=lambda e: e['block'])
    # Trim to last 24h window
    if not events:
        return events
    max_block = events[-1]['block']
    min_block = max_block - max_block_window
    return [e for e in events if e['block'] >= min_block]


def tick_to_sqrt_price_x96(tick):
    log_sqrt_1_0001 = math.log(1.0001) / 2.0
    return int(math.exp(tick * log_sqrt_1_0001) * (2 ** 96))


def sqrt_price_x96_to_price(sqrt_px96, dec0=18, dec1=6):
    raw = (sqrt_px96 / (2 ** 96)) ** 2
    return raw * (10 ** (dec0 - dec1))


def tick_lower_upper(current_tick, range_pct):
    delta = int(math.ceil(math.log(1 + range_pct/100.0) / math.log(1.0001)))
    return current_tick - delta, current_tick + delta


def rebalance_position(events, start_idx, end_idx, initial_tick, range_pct, rebal_rule, size, fee_per_dollar_per_day):
    """Walk events from start_idx to end_idx, applying rebalance rule.
    Returns: total_fee, total_il, rebalance_count, n_in_range, n_total
    """
    tick_lower, tick_upper = tick_lower_upper(initial_tick, range_pct)
    current_tick_lower = tick_lower
    current_tick_upper = tick_upper
    current_center = initial_tick
    last_rebal_block = events[start_idx]['block']
    last_rebal_tick = initial_tick
    rebalance_count = 0
    total_fee = 0.0
    total_il = 0.0
    n_in_range = 0
    n_total = 0
    last_in_range = False
    in_range_start_block = events[start_idx]['block']

    # Track entry price for IL computation
    entry_price = sqrt_price_x96_to_price(tick_to_sqrt_price_x96(initial_tick))

    for i in range(start_idx, end_idx + 1):
        ev = events[i]
        ev_tick = ev['tick']
        ev_block = ev['block']
        n_total += 1

        in_range = current_tick_lower <= ev_tick <= current_tick_upper
        if in_range:
            n_in_range += 1
            # Distribute fee_per_dollar_per_day across n_total events. Each event gets 1/n_total
            # of the daily fee (assuming uniform event distribution).
            total_fee += size * fee_per_dollar_per_day / max(end_idx - start_idx + 1, 1)

        # IL: only count when transitioning from in-range to out-of-range or at end-of-window.
        # Track (last_in_range_block, last_in_range) so we can compute IL per in-range period.
        if in_range and not last_in_range:
            in_range_start_block = ev_block
            last_in_range = True
        elif not in_range and last_in_range:
            # Just exited in-range: compute IL for the in-range period
            period_blocks = ev_block - in_range_start_block
            period_days = period_blocks / BASE_BLOCKS_PER_H / 24.0
            il_step = size * 0.5 * ETH_DAILY_SIGMA ** 2 * period_days
            total_il += il_step
            last_in_range = False
        elif not in_range:
            last_in_range = False
        # If in_range and last_in_range: continue accumulating, IL not yet computed for this period

        # Check rebalance rule
        if i < end_idx:
            should_rebal = False
            if rebal_rule["max_hold_blocks"] < 999999 and (ev_block - last_rebal_block) >= rebal_rule["max_hold_blocks"]:
                should_rebal = True
            if rebal_rule["max_move_pct"] is not None:
                tick_threshold = int(rebal_rule["max_move_pct"] * 100)
                if abs(ev_tick - current_center) > tick_threshold:
                    should_rebal = True

            if should_rebal:
                # If currently in-range, finalize IL for the open period
                if last_in_range:
                    period_blocks = ev_block - in_range_start_block
                    period_days = period_blocks / BASE_BLOCKS_PER_H / 24.0
                    il_step = size * 0.5 * ETH_DAILY_SIGMA ** 2 * period_days
                    total_il += il_step
                    last_in_range = False
                # Rebalance: re-center on current tick
                rebalance_count += 1
                current_center = ev_tick
                current_tick_lower, current_tick_upper = tick_lower_upper(ev_tick, range_pct)
                last_rebal_block = ev_block
                in_range_start_block = ev_block

    # Finalize IL at end of window
    if last_in_range:
        period_blocks = events[end_idx]['block'] - in_range_start_block
        period_days = period_blocks / BASE_BLOCKS_PER_H / 24.0
        il_step = size * 0.5 * ETH_DAILY_SIGMA ** 2 * period_days
        total_il += il_step
    return total_fee, total_il, rebalance_count, n_in_range, n_total


def compute_dynamic_delta(events, start_idx, end_idx, initial_tick, range_pct, size):
    """Approximate the ETH delta of the LP position over time.
    For a 50/50 mid-range position, ETH delta ≈ 0.5 (50% ETH).
    As price moves to upper, delta → 1.0 (100% ETH, no USDC).
    As price moves to lower, delta → 0.0 (0% ETH, 100% USDC).
    For our model, use linear interpolation based on (current_tick - tick_lower) / (tick_upper - tick_lower).
    """
    tick_lower, tick_upper = tick_lower_upper(initial_tick, range_pct)
    deltas = []
    for i in range(start_idx, end_idx + 1):
        ev = events[i]
        if ev['tick'] <= tick_lower:
            deltas.append(0.0)  # all USDC
        elif ev['tick'] >= tick_upper:
            deltas.append(1.0)  # all ETH
        else:
            d = (ev['tick'] - tick_lower) / (tick_upper - tick_lower)
            deltas.append(d)
    return deltas


def main():
    print("=" * 80)
    print("D2 — Dynamic Delta Replay with Funding History")
    print("=" * 80)

    funding_history = load_funding_history()
    funding_aprs = [a for _, a in funding_history]
    funding_median = statistics.median(funding_aprs)
    funding_p5 = sorted(funding_aprs)[int(len(funding_aprs) * 0.05)]
    funding_p95 = sorted(funding_aprs)[int(len(funding_aprs) * 0.95)]
    print(f"Funding history: {len(funding_history)} records, median {funding_median:+.2f}% APR, p5 {funding_p5:+.2f}%, p95 {funding_p95:+.2f}%")

    # Use a single funding scenario: median (most realistic expected case)
    funding_apr_use = funding_median
    print(f"Using funding_apr={funding_apr_use:+.2f}% (median of 90d history)")

    cells = []
    for pool_addr, info in POOLS.items():
        events = load_swap_events(pool_addr, info)
        if not events:
            print(f"WARN: no events for {pool_addr[:8]}")
            continue
        # Initial tick: first event's tick
        initial_tick = events[0]['tick']
        start_idx = 0
        end_idx = len(events) - 1

        # Compute dynamic delta path
        dynamic_deltas = compute_dynamic_delta(events, start_idx, end_idx, initial_tick, 5, 1000)  # range/size don't matter for delta
        avg_dynamic_delta = sum(dynamic_deltas) / len(dynamic_deltas) if dynamic_deltas else 0.5
        print(f"\n{pool_addr[:8]}... {len(events)} events, initial_tick={initial_tick}, avg_dynamic_delta={avg_dynamic_delta:.3f}")

        for size in SIZES:
            for rng in RANGES_PCT:
                fee_per_dollar_per_day = info["r4c_fee_per_dollar_per_day"].get(rng, 0.005)
                for rebal in REBAL_RULES:
                    for hedge_strat in HEDGE_STRATEGIES:
                        # Replay with rebalance
                        fee, il, rebal_count, n_in, n_tot = rebalance_position(
                            events, start_idx, end_idx, initial_tick, rng, rebal,
                            size, fee_per_dollar_per_day
                        )

                        # Hedge PnL: depends on strategy
                        if hedge_strat == "static_0.5":
                            hedge_ratio = 0.5
                            dynamic_hedge_used = 0.5
                        elif hedge_strat == "static_0.75":
                            hedge_ratio = 0.75
                            dynamic_hedge_used = 0.75
                        else:  # dynamic
                            # Use average dynamic delta as hedge ratio
                            dynamic_hedge_used = avg_dynamic_delta
                            hedge_ratio = dynamic_hedge_used

                        hedge_notional = size * hedge_ratio
                        # Funding cost over 24h
                        # If funding_apr > 0: shorts receive (income). If < 0: shorts pay.
                        funding_cost_income = hedge_notional * (funding_apr_use / 100.0) * (HOLD_H / HOURS_PER_YEAR)
                        # Perp trading fee: entry only (close = same cost; assume 1 round-trip per 24h for rebalances? Use 1 only)
                        perp_trading_fee = hedge_notional * PERP_TAKER_FEE
                        # Rebalance gas: gas_cycle per rebalance (each rebalance = 1 cycle LP + 1 perp trade)
                        rebal_gas = rebal_count * GAS_CYCLE_USD * 2  # LP + perp
                        # Residual risk: (1 - hedge_ratio) * size * sigma_window
                        sigma_window = ETH_DAILY_SIGMA * math.sqrt(HOLD_H / 24.0)
                        residual = (1.0 - hedge_ratio) * size * sigma_window

                        # Net PnL hedged
                        gas_initial = GAS_CYCLE_USD
                        net_hedged = fee - il - perp_trading_fee - rebal_gas - residual + funding_cost_income - gas_initial
                        net_unhedged = fee - il - gas_initial

                        # Signal/noise
                        il_stddev = il * 0.5
                        residual_stddev = residual * 0.5
                        noise = max(il_stddev + residual_stddev, 1e-6)
                        signal = max(fee - il, 1e-9)
                        sig_noise = signal / noise

                        rec = (
                            "GO" if (net_hedged > 0 and sig_noise > 1.5 and size <= 1000 and rebal_count < 30)
                            else ("NEED_MORE_DATA" if net_hedged > -0.1 else "NO_GO")
                        )

                        cells.append({
                            "pool": pool_addr,
                            "pool_name": info["name"],
                            "size_usd": size,
                            "range_pct": rng,
                            "hold_hours": HOLD_H,
                            "rebal_rule": rebal["name"],
                            "hedge_strategy": hedge_strat,
                            "hedge_ratio_used": hedge_ratio,
                            "dynamic_hedge_avg": avg_dynamic_delta if hedge_strat == "dynamic" else None,
                            "events_total": n_tot,
                            "events_in_range": n_in,
                            "in_range_pct": n_in / n_tot if n_tot else 0,
                            "rebalance_count": rebal_count,
                            "lp_fee_usd": fee,
                            "il_usd": il,
                            "hedge_notional_usd": hedge_notional,
                            "funding_apr_pct": funding_apr_use,
                            "funding_income_usd": funding_cost_income,
                            "perp_trading_fee_usd": perp_trading_fee,
                            "rebal_gas_usd": rebal_gas,
                            "residual_delta_risk_usd": residual,
                            "gas_initial_usd": gas_initial,
                            "net_pnl_unhedged_usd": net_unhedged,
                            "net_pnl_hedged_usd": net_hedged,
                            "signal_noise_hedged": sig_noise,
                            "recommendation": rec,
                        })

    # Stats
    n_pos = sum(1 for c in cells if c["recommendation"] == "GO")
    n_need = sum(1 for c in cells if c["recommendation"] == "NEED_MORE_DATA")
    n_no = sum(1 for c in cells if c["recommendation"] == "NO_GO")
    print(f"\nTotal cells: {len(cells)}")
    print(f"GO: {n_pos}, NEED_MORE_DATA: {n_need}, NO_GO: {n_no}")

    # Top by net_hedged
    top = sorted(cells, key=lambda c: c["net_pnl_hedged_usd"], reverse=True)[:10]
    print(f"\nTop 10 by net_pnl_hedged_usd:")
    for c in top:
        print(f"  {c['pool'][:8]}... ${c['size_usd']} ±{c['range_pct']}% rebal={c['rebal_rule']:>8} "
              f"hedge={c['hedge_strategy']:>10}: net=${c['net_pnl_hedged_usd']:.4f}, "
              f"sig/noise={c['signal_noise_hedged']:.2f}, rebal_ct={c['rebalance_count']}, "
              f"rec={c['recommendation']}")

    # Min viable
    min_cap = None
    for size in sorted(SIZES):
        for c in cells:
            if c["size_usd"] == size and c["recommendation"] == "GO":
                min_cap = size
                break
        if min_cap is not None:
            break
    print(f"\nMin viable capital (any GO cell): ${min_cap}")

    # By hedge strategy
    by_hedge = defaultdict(list)
    for c in cells:
        by_hedge[c["hedge_strategy"]].append(c["net_pnl_hedged_usd"])
    print(f"\nMedian net by hedge strategy:")
    for h, vals in by_hedge.items():
        s = sorted(vals)
        med = s[len(s)//2]
        max_v = s[-1]
        n_pos = sum(1 for v in vals if v > 0)
        print(f"  {h:>10}: median=${med:.4f}, max=${max_v:.4f}, positive={n_pos}/{len(vals)}")

    # By rebal rule
    by_rebal = defaultdict(list)
    for c in cells:
        by_rebal[c["rebal_rule"]].append(c["net_pnl_hedged_usd"])
    print(f"\nMedian net by rebal rule:")
    for r, vals in by_rebal.items():
        s = sorted(vals)
        med = s[len(s)//2]
        max_v = s[-1]
        n_pos = sum(1 for v in vals if v > 0)
        print(f"  {r:>10}: median=${med:.4f}, max=${max_v:.4f}, positive={n_pos}/{len(vals)}")

    # Save outputs
    os.makedirs(D2_DIR, exist_ok=True)
    csv_fields = list(cells[0].keys())
    with open(f"{D2_DIR}/dynamic_delta_replay_matrix.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=csv_fields)
        w.writeheader()
        for c in cells:
            row = {}
            for k, v in c.items():
                if isinstance(v, float):
                    row[k] = f"{v:.6f}"
                elif v is None:
                    row[k] = ""
                else:
                    row[k] = v
            w.writerow(row)
    print(f"\nWrote {D2_DIR}/dynamic_delta_replay_matrix.csv ({len(cells)} rows)")

    with open(f"{D2_DIR}/dynamic_delta_replay_matrix.jsonl", "w") as f:
        for c in cells:
            f.write(json.dumps(c) + "\n")
    print(f"Wrote {D2_DIR}/dynamic_delta_replay_matrix.jsonl")

    return cells, min_cap, n_pos


if __name__ == "__main__":
    main()
