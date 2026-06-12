#!/usr/bin/env python3
"""
D3 — Reward-Adjusted Delta-Hedged LP Model

Builds on D2 (dynamic delta + funding history) and adds the AERO reward APR
recovered from DefiLlama. Computes reward-adjusted net PnL across a grid.

Grid:
  2 pools (0xb2cc, 0x72ab)
  3 sizes ($250, $500, $1000)
  3 ranges (±2%, ±5%, ±10%)
  3 horizons (24h, 72h, 7d)
  2 hedge ratios (0.5, 0.75)
  5 fundings (median, p5, current, 0%, +5%)
  5 reward scenarios (0%, observed-63.52% / 2, observed 63.52%, 30%, 50%)
  = 2 × 3 × 3 × 3 × 2 × 5 × 5 = 2700 cells
"""

import csv
import json
import math
import os
import statistics
from collections import defaultdict
from datetime import datetime, timezone

D2_DIR = "reports/strategy_pivot_d2_dynamic_delta_funding_history/20260612_140000"
R4C_DIR = "reports/strategy_evidence_r4c_independent_clmm_liquidity_replay/20260612_100000"
R4_DIR = "reports/strategy_evidence_r4_swap_event_fee_replay/20260611_080000"
D3_DIR = "reports/strategy_pivot_d3_aerodrome_reward_edge/20260612_160000"

ETH_USD = 1653.0
GAS_CYCLE_USD = 0.0795
ETH_DAILY_SIGMA = 0.04
PERP_TAKER_FEE = 0.0002
HOURS_PER_YEAR = 8760
CLAIM_GAS_USD = 0.10  # 1 claim cycle ≈ $0.10

# Observed reward APR per pool (DefiLlama, 2026-06-12 snapshot)
OBSERVED_REWARD_APR = {
    "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59": 63.52,
    "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38": 0.0,  # 0x72ab is PancakeSwap; no Aerodrome rewards
}

# Use D2's best rebalance rule (gt_2pct) and D2's R4C fee per dollar
R4C_FEES = {
    "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59": {2: 0.018, 5: 0.012, 10: 0.0062},
    "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38": {2: 0.0036, 5: 0.0024, 10: 0.00124},
}

POOLS = {
    "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59": {
        "name": "Aerodrome Slipstream WETH/USDC 0.05%",
        "fee_tier": 0.0005,
        "reward_apr_pct": 63.52,
    },
    "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38": {
        "name": "PancakeSwap V3 WETH/USDC 0.01%",
        "fee_tier": 0.0001,
        "reward_apr_pct": 0.0,
    },
}

SIZES = [250, 500, 1000]
RANGES_PCT = [2, 5, 10]
HORIZONS_H = [24, 72, 168]
HEDGE_RATIOS = [0.5, 0.75]
FUNDING_APRS = ["median", "p5", "current", 0, 5]
REWARD_SCENARIOS_PCT = [0, 15, 31.76, 63.52, 100]  # 31.76 = half of observed, used as "conservative reward"


def load_funding_history():
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


def load_swap_events(pool_addr, jsonl_path, max_blocks=24*1800):
    events = []
    with open(jsonl_path) as f:
        for line in f:
            ev = json.loads(line)
            a0, a1, sqrt, liq, tick = decode_v3(ev['data'])
            a0_h = a0 / 1e18
            a1_h = a1 / 1e6
            vol_usd = max(abs(a0_h) * ETH_USD, abs(a1_h))
            events.append({
                "block": ev['block'],
                "tick": tick,
                "vol_usd": vol_usd,
            })
    events.sort(key=lambda e: e['block'])
    if not events:
        return events
    return events[-max_blocks:]


def tick_to_sqrt_price_x96(tick):
    return int(math.exp(tick * math.log(1.0001) / 2.0) * (2 ** 96))


def tick_lower_upper(current_tick, range_pct):
    delta = int(math.ceil(math.log(1 + range_pct/100.0) / math.log(1.0001)))
    return current_tick - delta, current_tick + delta


def replay_with_rebalance(events, initial_tick, range_pct, rebal_rule, size, fee_per_dollar_per_day, hold_h):
    """Walk events for the hold period, applying rebal_rule (D2 gt_2pct).
    Returns fee, il, rebal_count.
    """
    base_blocks_per_h = 1800
    target_blocks = int(hold_h * base_blocks_per_h)
    # Trim events to last hold_h
    if events:
        max_block = events[-1]['block']
        min_block = max_block - target_blocks
        events = [e for e in events if e['block'] >= min_block]
    if not events:
        return 0, 0, 0

    tick_lower, tick_upper = tick_lower_upper(initial_tick, range_pct)
    current_lower, current_upper = tick_lower, tick_upper
    current_center = initial_tick
    last_rebal_block = events[0]['block']
    rebal_count = 0
    total_fee = 0.0
    total_il = 0.0
    last_in_range = False
    in_range_start_block = events[0]['block']
    n_total = len(events)
    tick_threshold = int(rebal_rule["max_move_pct"] * 100) if rebal_rule["max_move_pct"] is not None else 999999

    for i, ev in enumerate(events):
        in_range = current_lower <= ev['tick'] <= current_upper
        if in_range:
            total_fee += size * fee_per_dollar_per_day / n_total

        if in_range and not last_in_range:
            in_range_start_block = ev['block']
            last_in_range = True
        elif not in_range and last_in_range:
            period_blocks = ev['block'] - in_range_start_block
            period_days = period_blocks / base_blocks_per_h / 24.0
            il_step = size * 0.5 * ETH_DAILY_SIGMA ** 2 * period_days
            total_il += il_step
            last_in_range = False
        elif not in_range:
            last_in_range = False

        if i < n_total - 1:
            should_rebal = False
            if rebal_rule["max_move_pct"] is not None and abs(ev['tick'] - current_center) > tick_threshold:
                should_rebal = True
            if should_rebal:
                if last_in_range:
                    period_blocks = ev['block'] - in_range_start_block
                    period_days = period_blocks / base_blocks_per_h / 24.0
                    il_step = size * 0.5 * ETH_DAILY_SIGMA ** 2 * period_days
                    total_il += il_step
                    last_in_range = False
                rebal_count += 1
                current_center = ev['tick']
                current_lower, current_upper = tick_lower_upper(ev['tick'], range_pct)
                in_range_start_block = ev['block']

    if last_in_range:
        period_blocks = events[-1]['block'] - in_range_start_block
        period_days = period_blocks / base_blocks_per_h / 24.0
        il_step = size * 0.5 * ETH_DAILY_SIGMA ** 2 * period_days
        total_il += il_step
    return total_fee, total_il, rebal_count


def main():
    print("=" * 80)
    print("D3 — Reward-Adjusted Delta-Hedged LP Model")
    print("=" * 80)

    funding_history = load_funding_history()
    funding_aprs = [a for _, a in funding_history]
    funding_median = statistics.median(funding_aprs)
    funding_p5 = sorted(funding_aprs)[int(len(funding_aprs) * 0.05)]
    funding_current = funding_aprs[-1]
    funding_map = {"median": funding_median, "p5": funding_p5, "current": funding_current, 0: 0.0, 5: 5.0}
    print(f"Funding scenarios: median={funding_median:+.2f}% p5={funding_p5:+.2f}% current={funding_current:+.2f}%")
    print(f"Reward scenarios: 0%, 15%, 31.76% (half-observed), 63.52% (observed), 100%")

    REBAL_RULE = {"name": "gt_2pct", "max_move_pct": 2.0, "max_hold_blocks": 999999}

    cells = []
    for pool_addr, info in POOLS.items():
        jsonl = f"{R4_DIR}/swap_events_0x{pool_addr[2:8]}.jsonl"
        events = load_swap_events(pool_addr, jsonl, max_blocks=24*1800)
        if not events:
            print(f"WARN: no events for {pool_addr[:8]}")
            continue
        initial_tick = events[0]['tick']

        for size in SIZES:
            for rng in RANGES_PCT:
                fee_per_dollar_per_day = R4C_FEES[pool_addr].get(rng, 0.005)
                for hold_h in HORIZONS_H:
                    fee, il, rebal_count = replay_with_rebalance(
                        events, initial_tick, rng, REBAL_RULE, size, fee_per_dollar_per_day, hold_h
                    )
                    for hedge_ratio in HEDGE_RATIOS:
                        for funding_key in FUNDING_APRS:
                            funding_apr = funding_map[funding_key]
                            for reward_apr_pct in REWARD_SCENARIOS_PCT:
                                # Reward income: linear in size, hold_years
                                hold_days = hold_h / 24.0
                                hold_years = hold_h / HOURS_PER_YEAR
                                if reward_apr_pct == 0:
                                    reward_apr = 0
                                else:
                                    reward_apr = reward_apr_pct
                                reward_income = size * (reward_apr / 100.0) * hold_years
                                # Claim gas: $0.10 per claim, 1 claim per 24h ceiling
                                claim_count = math.ceil(hold_h / 24.0)
                                claim_gas = claim_count * CLAIM_GAS_USD

                                # Funding income (same formula as D2)
                                hedge_notional = size * hedge_ratio
                                funding_income = hedge_notional * (funding_apr / 100.0) * (hold_h / HOURS_PER_YEAR)
                                # Perp trading fee: entry only at gt_2pct rebal rule ≈ 1 rebal per 24h
                                rebal_count_per_24h = max(rebal_count / max(hold_h / 24.0, 1), 0)
                                perp_fee_per_24h = (size * hedge_ratio) * PERP_TAKER_FEE * (1 + rebal_count_per_24h)
                                rebal_gas = rebal_count * GAS_CYCLE_USD * 2  # LP + perp
                                sigma_window = ETH_DAILY_SIGMA * math.sqrt(hold_days)
                                residual = (1.0 - hedge_ratio) * size * sigma_window
                                gas_initial = GAS_CYCLE_USD

                                # Net PnL hedged with reward
                                net_hedged_reward = (
                                    fee
                                    + reward_income
                                    - claim_gas
                                    - il
                                    - perp_fee_per_24h * hold_days
                                    - rebal_gas
                                    - residual
                                    + funding_income
                                    - gas_initial
                                )
                                # Net PnL fee-only (no hedge, no reward)
                                net_fee_only = fee - il - gas_initial
                                # Net PnL delta-hedged (no reward, for comparison)
                                net_hedged_only = (
                                    fee
                                    - il
                                    - perp_fee_per_24h * hold_days
                                    - rebal_gas
                                    - residual
                                    + funding_income
                                    - gas_initial
                                )

                                # Signal/noise
                                il_stddev = il * 0.5
                                residual_stddev = residual * 0.5
                                noise = max(il_stddev + residual_stddev, 1e-6)
                                signal = max(fee + reward_income - il, 1e-9)
                                sig_noise = signal / noise

                                rec = (
                                    "GO" if (net_hedged_reward > 0 and sig_noise > 1.5 and size <= 1000 and rebal_count < 30)
                                    else ("NEED_MORE_DATA" if net_hedged_reward > -0.1 else "NO_GO")
                                )

                                cells.append({
                                    "pool": pool_addr,
                                    "pool_name": info["name"],
                                    "size_usd": size,
                                    "range_pct": rng,
                                    "hold_hours": hold_h,
                                    "hedge_ratio": hedge_ratio,
                                    "funding_scenario": str(funding_key),
                                    "funding_apr_pct": funding_apr,
                                    "reward_scenario_pct": reward_apr_pct,
                                    "reward_income_usd": reward_income,
                                    "claim_gas_usd": claim_gas,
                                    "lp_fee_usd": fee,
                                    "il_usd": il,
                                    "rebalance_count_24h": rebal_count_per_24h,
                                    "perp_trading_fee_usd": perp_fee_per_24h * hold_days,
                                    "rebal_gas_usd": rebal_gas,
                                    "residual_delta_risk_usd": residual,
                                    "funding_income_usd": funding_income,
                                    "net_pnl_fee_only_usd": net_fee_only,
                                    "net_pnl_delta_hedged_usd": net_hedged_only,
                                    "net_pnl_reward_adjusted_usd": net_hedged_reward,
                                    "signal_noise_reward_adjusted": sig_noise,
                                    "recommendation": rec,
                                })

    n_pos = sum(1 for c in cells if c["recommendation"] == "GO")
    n_need = sum(1 for c in cells if c["recommendation"] == "NEED_MORE_DATA")
    n_no = sum(1 for c in cells if c["recommendation"] == "NO_GO")
    print(f"\nTotal cells: {len(cells)}")
    print(f"GO: {n_pos}, NEED_MORE_DATA: {n_need}, NO_GO: {n_no}")

    # Top 10 by net_pnl_reward_adjusted
    top = sorted(cells, key=lambda c: c["net_pnl_reward_adjusted_usd"], reverse=True)[:10]
    print(f"\nTop 10 by net_pnl_reward_adjusted_usd:")
    for c in top:
        print(f"  {c['pool'][:8]}... ${c['size_usd']} ±{c['range_pct']}% {c['hold_hours']}h "
              f"hedge={c['hedge_ratio']} funding={c['funding_scenario']:>6} reward={c['reward_scenario_pct']}%: "
              f"net=${c['net_pnl_reward_adjusted_usd']:.4f} sig/noise={c['signal_noise_reward_adjusted']:.2f} "
              f"rec={c['recommendation']}")

    # Best at OBSERVED reward (63.52%) only
    obs_cells = [c for c in cells if c["reward_scenario_pct"] == 63.52]
    obs_top = sorted(obs_cells, key=lambda c: c["net_pnl_reward_adjusted_usd"], reverse=True)[:5]
    print(f"\nTop 5 at OBSERVED reward (63.52% APR):")
    for c in obs_top:
        print(f"  {c['pool'][:8]}... ${c['size_usd']} ±{c['range_pct']}% {c['hold_hours']}h "
              f"hedge={c['hedge_ratio']} funding={c['funding_scenario']:>6}: "
              f"net=${c['net_pnl_reward_adjusted_usd']:.4f} sig/noise={c['signal_noise_reward_adjusted']:.2f} "
              f"rec={c['recommendation']}")

    # Min viable at observed
    min_cap = None
    for size in sorted(SIZES):
        for c in obs_cells:
            if c["size_usd"] == size and c["recommendation"] == "GO":
                min_cap = size
                break
        if min_cap is not None:
            break
    print(f"\nMin viable capital (any GO at OBSERVED reward, any funding): ${min_cap}")

    # Min viable at observed AND median funding
    obs_med = [c for c in obs_cells if c["funding_scenario"] == "median" and c["recommendation"] == "GO"]
    min_cap_obs_med = None
    for size in sorted(SIZES):
        for c in obs_med:
            if c["size_usd"] == size:
                min_cap_obs_med = size
                break
        if min_cap_obs_med is not None:
            break
    print(f"Min viable capital (GO at observed reward AND median funding): ${min_cap_obs_med}")

    # Save outputs
    csv_fields = list(cells[0].keys())
    with open(f"{D3_DIR}/reward_adjusted_delta_matrix.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=csv_fields)
        w.writeheader()
        for c in cells:
            row = {}
            for k, v in c.items():
                if isinstance(v, float):
                    row[k] = f"{v:.6f}"
                else:
                    row[k] = v
            w.writerow(row)
    print(f"\nWrote {D3_DIR}/reward_adjusted_delta_matrix.csv ({len(cells)} rows)")

    with open(f"{D3_DIR}/reward_adjusted_delta_matrix.jsonl", "w") as f:
        for c in cells:
            f.write(json.dumps(c) + "\n")
    print(f"Wrote {D3_DIR}/reward_adjusted_delta_matrix.jsonl")

    return cells, min_cap, min_cap_obs_med, n_pos


if __name__ == "__main__":
    main()
