#!/usr/bin/env python3
"""
D1 — Delta-Hedged LP Feasibility Model

Static delta-hedged EV model for the same high-volume Base LP pools.
Scales R4C's correct per-size fee into a 5×5×5×2×5×3 grid per pool.

Grid:
  3 pools (0xb2cc, 0x72ab, 0xb775)
  5 sizes ($50, $100, $250, $500, $1000)
  5 ranges (±1%, ±2%, ±5%, ±10%, ±15%)
  5 horizons (1h, 6h, 24h, 72h, 7d)
  2 hedge ratios (50%, 75% of notional)
  5 funding scenarios (-20%, -5%, 0%, +5%, +20% APR)
  3 perp trading fees (0.02%, 0.05%, 0.10%)
  = 3 × 5 × 5 × 5 × 2 × 5 × 3 = 11,250 cells

Fee scaling: R4C fee ∝ size for fixed pool/range. Base R4C fee is computed
from the 24h hold; for 72h/7d, the 24h fee is multiplied by (hold_h / 24)
with no compounding and no decay model (conservative linear).

IL: σ²/R² formula, scaled linearly with size and time. σ assumed 2%/hour for ETH.

Hedge cost: hedge_notional × (funding_apr/100) × (hold_h / 8760).
Hedge trading fee: hedge_notional × perp_fee (entry, no exit assumed).
Rebalance cost: 1 gas cycle per 24h of holding.
Residual delta: (1 - hedge_ratio) × σ × size × √(hold_h / 24) × 1.0 (1σ move).

Net PnL hedged = lp_fee - IL - hedge_funding - hedge_trading_fee - gas - rebalance - residual_risk
Net PnL unhedged = lp_fee - IL - gas

Output: delta_hedged_ev_matrix.csv, delta_hedged_ev_matrix.jsonl
"""

import csv
import json
import math
import os
from collections import defaultdict

R4C_DIR = "reports/strategy_evidence_r4c_independent_clmm_liquidity_replay/20260612_100000"
D1_DIR = "reports/strategy_pivot_d1_delta_hedged_lp_feasibility/20260612_120000"
R2_DIR = "reports/strategy_evidence_r2_gas_reward_reprice/20260611_064703"

ETH_USD = 1653.0  # matches R4C and R4
HOURS_PER_YEAR = 8760
GAS_CYCLE_USD = 0.0795  # R2 typical 0.05 gwei anchor

# Pools
POOLS = {
    "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59": {
        "name": "Aerodrome Slipstream WETH/USDC 0.05%",
        "fee_tier": 0.0005,
    },
    "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38": {
        "name": "PancakeSwap V3 WETH/USDC 0.01%",
        "fee_tier": 0.0001,
    },
    "0xb775272e537cc670c65dc852908ad47015244eaf": {
        "name": "PancakeSwap V3 WETH/USDC 0.05%",
        "fee_tier": 0.0005,
    },
}

SIZES = [50, 100, 250, 500, 1000]
RANGES_PCT = [1, 2, 5, 10, 15]
HORIZONS_H = [1, 6, 24, 72, 168]  # 168h = 7d
HEDGE_RATIOS = [0.5, 0.75]
FUNDING_APRS = [-20, -5, 0, 5, 20]
PERP_FEES = [0.0002, 0.0005, 0.001]  # 0.02%, 0.05%, 0.10%

# In-range fraction for ranges R4C didn't compute.
# R4C showed 100% in-range for ±5/10/15% on 24h for these pools (tick movement <5%).
# For ±1% and ±2%, more conservative. ETH/USDC tick stddev over 24h is ~50-100 ticks
# (0.5-1% price). ±1% range = ~100 ticks half-width; ±2% = ~200 ticks.
# P(tick in range) for symmetric normal: Φ(R/σ_tick) for one side, squared for two-sided.
# 24h σ_tick ~100, 1h σ_tick ~20. Conservative: 70% for ±1%, 95% for ±2%.
# Use 24h averages; for shorter holds assume 100% in-range.
IN_RANGE_FRAC = {1: 0.70, 2: 0.95, 5: 1.0, 10: 1.0, 15: 1.0}

# Volatility assumptions (ETH hourly σ, conservative; ETH has been 50-100% annualized)
ETH_HOURLY_SIGMA = 0.02  # 2% per hour; ~50% annualized
# IL formula from R4C: il = size * (sigma_pct / 100)^2 / (R^2) * 0.5 * hold_days
# Note: R4C used sigma_pct=2.0 in /100 form = 0.02 absolute
# But that's 2% (per hour, 2% volatility/hour), so daily σ ~9.4% if sqrt(24)*2% scaling
# R4C's IL formula: il = size * (sigma / 100)² / R² * 0.5 * hold_days  (in days, not hours)
# where sigma_pct = 2.0 means 2% per √day, which is 2% daily vol
# This is unrealistically low (2% daily vol = 38% annualized)
# Use 2x R4C's sigma for 4% daily vol, 76% annualized (more realistic for ETH)
SIGMA_DAILY_PCT = 4.0  # 4% daily vol, ~76% annualized


def load_r4c_base_fees():
    """Load R4C fees at $10, $25, $50 base sizes, for each (pool, range, 24h).
    Returns dict: (pool, range_pct) -> fee_per_dollar_per_day.
    For ±1% and ±2% (R4C didn't compute), use the ±5% rate scaled by IN_RANGE_FRAC.
    """
    base = {}
    with open(f"{R4C_DIR}/independent_clmm_fee_replay_matrix.csv") as f:
        r = csv.DictReader(f)
        for row in r:
            pool = row['pool']
            rng = int(row['range_pct'])
            size = float(row['size_usd'])
            hold = float(row['hold_hours'])
            if hold != 24.0 or size not in (10, 25, 50):
                continue
            fee = float(row['fee_usd_r4c'])
            fee_per_dollar = fee / size
            key = (pool, rng)
            if key not in base:
                base[key] = []
            base[key].append((size, fee_per_dollar))
    # Average the per-dollar rates across $10, $25, $50
    avg = {}
    for key, vals in base.items():
        per_dollar_avg = sum(v[1] for v in vals) / len(vals)
        avg[key] = per_dollar_avg

    # Add ±1% and ±2% extrapolations from ±5% base, scaled by IN_RANGE_FRAC
    for pool_addr in POOLS:
        if (pool_addr, 5) in avg:
            base_5 = avg[(pool_addr, 5)]
            for rng in (1, 2):
                if (pool_addr, rng) not in avg:
                    # Scale by in-range fraction relative to ±5%
                    avg[(pool_addr, rng)] = base_5 * (IN_RANGE_FRAC[rng] / IN_RANGE_FRAC[5])
    return avg


def compute_il(size, range_pct, hold_h, sigma_daily_pct=SIGMA_DAILY_PCT):
    """IL estimate using a realistic LVR-based formula.

    R4C's formula (size * σ² / R² * 0.5 * hold_days) was wildly overstated for tight ranges
    (e.g. $400/day IL on a $50 ±1% position). Use a more realistic estimate:
      LVR_daily = 0.5 * (σ_daily)²
      For R4C's σ_daily = 4%, LVR_daily = 0.5 * 0.0016 = 0.08% of size per day
      Range amplification: tight ranges amplify LVR by a factor of ~1/(2R) for very tight ranges
        (and don't amplify for loose ranges)
      Cap: at 5% per day to prevent runaway values for ultra-tight ranges
    """
    R = range_pct / 100.0
    hold_days = hold_h / 24.0
    sigma = sigma_daily_pct / 100.0
    lvr_daily = 0.5 * sigma ** 2  # ~0.08% per day for σ=4%
    # Range amplification: 1x for loose, up to 1/(2R) for very tight
    if R >= 0.10:  # ±10% or wider
        range_mult = 1.0
    elif R >= 0.02:  # ±2-10%
        range_mult = 1.0 + (0.10 - R) * 5  # linear ramp
    else:  # ±1% or tighter
        range_mult = 1.0 + (0.10 - 0.02) * 5 + (0.02 - R) * 50  # steep ramp
        range_mult = min(range_mult, 100.0)  # cap
    il_daily = lvr_daily * range_mult
    il_daily = min(il_daily, 0.05)  # 5% per day cap
    return size * il_daily * hold_days


def compute_residual_delta(size, hedge_ratio, hold_h, sigma_daily_pct=SIGMA_DAILY_PCT):
    """Residual delta risk: 1-σ move over the holding window, on the unhedge-portion.
    σ_window = σ_daily * √(hold_days).
    residual_risk = (1 - hedge_ratio) * size * σ_window.
    """
    R = 1.0 - hedge_ratio
    hold_days = hold_h / 24.0
    sigma_window = (sigma_daily_pct / 100.0) * math.sqrt(max(hold_days, 1.0 / 24.0))
    return R * size * sigma_window


def rebalance_gas_cost(hold_h):
    """Approximate rebalance cost: 1 gas cycle per 24h of holding.
    R4C used 0 rebalances; in practice a tight range rebalances more often.
    Assume 1 rebalance per 24h ceiling.
    """
    return GAS_CYCLE_USD * math.ceil(hold_h / 24.0)


def main():
    print("=" * 80)
    print("D1 — Delta-Hedged LP Feasibility Model")
    print("=" * 80)

    base = load_r4c_base_fees()
    print(f"Loaded {len(base)} (pool, range) base rate keys from R4C")

    cells = []
    n_positive_hedged = 0
    best_cell = None
    best_net = None

    for pool_addr, info in POOLS.items():
        for size in SIZES:
            for rng in RANGES_PCT:
                key = (pool_addr, rng)
                if key not in base:
                    print(f"WARN: no R4C base for {pool_addr[:8]} ±{rng}%")
                    continue
                fee_per_dollar_per_day_24h = base[key]
                for hold_h in HORIZONS_H:
                    # In-range fraction for short holds: assume 100% for hold ≤ 6h on these tight ranges
                    # For 24h, use IN_RANGE_FRAC. For longer holds (72h, 7d), apply sqrt decay.
                    if hold_h <= 6:
                        in_range_frac = 1.0
                    else:
                        in_range_frac = IN_RANGE_FRAC.get(rng, 1.0)
                        if hold_h > 24:
                            # Decay for longer holds: sqrt(24/hold) factor
                            in_range_frac *= math.sqrt(24.0 / hold_h)
                            in_range_frac = max(in_range_frac, 0.05)  # floor at 5%
                    fee_per_dollar_per_day = fee_per_dollar_per_day_24h * in_range_frac / IN_RANGE_FRAC.get(rng, 1.0)
                    # LP fee at this size and hold
                    hold_days = hold_h / 24.0
                    lp_fee = fee_per_dollar_per_day * size * hold_days
                    # IL at this size and hold
                    il = compute_il(size, rng, hold_h)
                    # Unhedged net (no hedge cost, no rebalance assumed for unhedged)
                    unhedged_net = lp_fee - il - GAS_CYCLE_USD

                    for hedge_ratio in HEDGE_RATIOS:
                        hedge_notional = size * hedge_ratio
                        for funding_apr in FUNDING_APRS:
                            # Funding cost over the hold (for SHORT: pay if rate>0, receive if rate<0)
                            # funding_apr is in % (e.g. 5 = 5% APR)
                            # funding_cost_per_year = hedge_notional * (funding_apr / 100)
                            # funding_cost = funding_cost_per_year * (hold_h / HOURS_PER_YEAR)
                            # If funding_apr > 0, shorts receive; if < 0, shorts pay
                            # In our model, hedge funding "income" is positive when rate>0
                            funding_cost = -hedge_notional * (funding_apr / 100.0) * (hold_h / HOURS_PER_YEAR)
                            for perp_fee in PERP_FEES:
                                hedge_trading_fee = hedge_notional * perp_fee  # entry only
                                reb_gas = rebalance_gas_cost(hold_h)
                                residual = compute_residual_delta(size, hedge_ratio, hold_h)

                                net_hedged = (
                                    lp_fee
                                    - il
                                    - hedge_trading_fee
                                    - funding_cost  # negative funding_cost = +funding income
                                    - GAS_CYCLE_USD
                                    - reb_gas
                                    - residual
                                )
                                # Signal/noise: signal = lp_fee - il, noise = (IL_stddev + residual_stddev)
                                il_stddev = il * 0.5
                                residual_stddev = residual * 0.5
                                noise = max(il_stddev + residual_stddev, 1e-6)
                                signal = max(lp_fee - il, 1e-9)
                                sig_noise_hedged = signal / noise
                                sig_noise_unhedged = (lp_fee - il) / max(il_stddev, 1e-6) if il_stddev > 0 else 0

                                rec = (
                                    "GO" if (net_hedged > 0 and sig_noise_hedged > 1.0 and size <= 1000)
                                    else ("NEED_MORE_DATA" if net_hedged > -0.1 else "NO_GO")
                                )

                                cell = {
                                    "pool": pool_addr,
                                    "pool_name": info["name"],
                                    "size_usd": size,
                                    "range_pct": rng,
                                    "hold_hours": hold_h,
                                    "hedge_ratio": hedge_ratio,
                                    "funding_apr_pct": funding_apr,
                                    "perp_fee_pct": perp_fee * 100,
                                    "fee_per_dollar_per_day": fee_per_dollar_per_day,
                                    "lp_fee_usd": lp_fee,
                                    "il_estimate_usd": il,
                                    "hedge_notional_usd": hedge_notional,
                                    "hedge_funding_cost_usd": funding_cost,  # positive=income
                                    "hedge_trading_fee_usd": hedge_trading_fee,
                                    "residual_delta_risk_usd": residual,
                                    "gas_cycle_usd": GAS_CYCLE_USD,
                                    "rebalance_cost_usd": reb_gas,
                                    "net_pnl_unhedged_usd": unhedged_net,
                                    "net_pnl_hedged_usd": net_hedged,
                                    "signal_noise_unhedged": sig_noise_unhedged,
                                    "signal_noise_hedged": sig_noise_hedged,
                                    "recommendation": rec,
                                }
                                cells.append(cell)
                                if rec == "GO":
                                    n_positive_hedged += 1
                                if best_net is None or net_hedged > best_net:
                                    best_net = net_hedged
                                    best_cell = cell

    print(f"\nTotal cells: {len(cells)}")
    print(f"GO cells (hedged positive): {n_positive_hedged}")
    print(f"Best cell: {best_cell['pool'][:8]}... ${best_cell['size_usd']} ±{best_cell['range_pct']}% "
          f"{best_cell['hold_hours']}h hedge={best_cell['hedge_ratio']} "
          f"funding={best_cell['funding_apr_pct']}% perp={best_cell['perp_fee_pct']:.2f}%: "
          f"net_hedged=${best_cell['net_pnl_hedged_usd']:.4f}, signal/noise={best_cell['signal_noise_hedged']:.2f}, "
          f"rec={best_cell['recommendation']}")

    # Recommendation distribution
    rec_counts = defaultdict(int)
    for c in cells:
        rec_counts[c["recommendation"]] += 1
    print(f"Recommendation distribution: {dict(rec_counts)}")

    # Group by funding_apr to see how funding affects edge
    by_funding = defaultdict(list)
    for c in cells:
        by_funding[c["funding_apr_pct"]].append(c["net_pnl_hedged_usd"])
    print(f"\nMedian net_pnl_hedged by funding_apr:")
    for fapr, vals in sorted(by_funding.items()):
        s = sorted(vals)
        med = s[len(s) // 2]
        max_v = s[-1]
        n_pos = sum(1 for v in vals if v > 0)
        print(f"  funding={fapr:+3d}%: median=${med:.4f}, max=${max_v:.4f}, positive={n_pos}/{len(vals)}")

    # Min viable capital: smallest size with at least 1 GO cell
    min_capital = None
    for size in sorted(SIZES):
        for c in cells:
            if c["size_usd"] == size and c["recommendation"] == "GO":
                min_capital = size
                break
        if min_capital is not None:
            break
    print(f"\nMin viable capital (any GO cell): ${min_capital}")

    # Save matrix CSV
    os.makedirs(D1_DIR, exist_ok=True)
    csv_fields = list(cells[0].keys())
    with open(f"{D1_DIR}/delta_hedged_ev_matrix.csv", "w", newline="") as f:
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
    print(f"Wrote {D1_DIR}/delta_hedged_ev_matrix.csv ({len(cells)} rows)")

    with open(f"{D1_DIR}/delta_hedged_ev_matrix.jsonl", "w") as f:
        for c in cells:
            f.write(json.dumps(c) + "\n")
    print(f"Wrote {D1_DIR}/delta_hedged_ev_matrix.jsonl")

    return cells, best_cell, min_capital, n_positive_hedged


if __name__ == "__main__":
    main()
