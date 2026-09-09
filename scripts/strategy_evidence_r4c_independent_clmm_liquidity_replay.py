#!/usr/bin/env python3
"""
R4C — Independent CLMM Liquidity Replay

Computes L_position independently from the V3 amount0/amount1 formulas, with NO
dependency on the size/TVL * l_factor shortcut that R4 and R4B used.

Independent formulas (V3 canonical, integer-Q64.96, see Uniswap v3-core
LiquidityAmounts.sol):

  Let:
    sqrtP = sqrtPriceX96 at the current tick
    sqrtA = sqrt(1.0001 ** tickLower) in Q64.96 form
    sqrtB = sqrt(1.0001 ** tickUpper) in Q64.96 form
  Then for a position with amount0 in token0 raw units, amount1 in token1 raw units:
    L_from_amount0 = amount0 * sqrtP * sqrtB / ((sqrtB - sqrtP) * 2^96)
    L_from_amount1 = amount1 * 2^96 / (sqrtP - sqrtA)
    L_position = min(L_from_amount0, L_from_amount1)

The position is split evenly in value: amount0_human * price0 + amount1_human * price1 = size_usd.
For a position centered on the current price, amount0 and amount1 are both positive
when the range is symmetric and P is at the midpoint.

For each event:
  if event_tick in [tickLower, tickUpper]:
    fee_share = L_position / (event_liquidity + L_position)
  else:
    fee_share = 0

L_position is computed ONCE per cell (it does not vary with the event). It is
independent of L_event. The R4 / R4B shortcut was: L_pos = (size/TVL) * l_factor * L_event,
which makes L_event cancel out of the fee_share formula, leaving the same
size/TVL * l_factor that the R1/R2 proxy used.

R4C's L_position is in canonical V3 units and is comparable in scale to L_event
on a per-event basis, so the fee_share is a proper ratio of two real
liquidity values.
"""

import json
import math
import os
import sys
import csv
import time
from decimal import Decimal, localcontext

# ============================================================================
# Constants and pool metadata
# ============================================================================

ETH_USD = 1653.0
WETH_DEC = 18
USDC_DEC = 6
Q96 = 2 ** 96
Q128 = 2 ** 128
GAS_CYCLE_USD = 0.0795

R4_DIR = "reports/strategy_evidence_r4_swap_event_fee_replay/20260611_080000"
R4B_DIR = "reports/strategy_evidence_r4b_active_liquidity_corrected_replay/20260612_090000"
R4C_DIR = "reports/strategy_evidence_r4c_independent_clmm_liquidity_replay/20260612_100000"

# Per-pool metadata. token0 = WETH (18 dec), token1 = USDC (6 dec) for all 3 pools.
POOLS = {
    "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59": {
        "name": "Aerodrome Slipstream WETH/USDC 0.05%",
        "fee_tier": 0.0005,
        "tvl_usd": 8742318.4584,
        "r2_volume_24h": 134650766.605207,
        "r4_volume_24h": 91355863.95,
        "r4_fees_24h": 45677.93,
        "jsonl": f"{R4_DIR}/swap_events_0xb2cc22.jsonl",
        "abi": "v3_standard",
        "decimals0": WETH_DEC,
        "decimals1": USDC_DEC,
        "token0_symbol": "WETH",
        "token1_symbol": "USDC",
    },
    "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38": {
        "name": "PancakeSwap V3 WETH/USDC 0.01%",
        "fee_tier": 0.0001,
        "tvl_usd": 3931250.374,
        "r2_volume_24h": 48559486.4057044,
        "r4_volume_24h": 44973746.27,
        "r4_fees_24h": 4497.37,
        "jsonl": f"{R4_DIR}/swap_events_0x72ab38.jsonl",
        "abi": "algebra_v2",
        "decimals0": WETH_DEC,
        "decimals1": USDC_DEC,
        "token0_symbol": "WETH",
        "token1_symbol": "USDC",
    },
    "0xb775272e537cc670c65dc852908ad47015244eaf": {
        "name": "PancakeSwap V3 WETH/USDC 0.05%",
        "fee_tier": 0.0005,
        "tvl_usd": 1311944.4936,
        "r2_volume_24h": 5839905.92299877,
        "r4_volume_24h": 2741371.15,
        "r4_fees_24h": 1370.69,
        "jsonl": f"{R4_DIR}/swap_events_0xb77527.jsonl",
        "abi": "algebra_v2",
        "decimals0": WETH_DEC,
        "decimals1": USDC_DEC,
        "token0_symbol": "WETH",
        "token1_symbol": "USDC",
    },
}

SIZES = [10, 25, 50]
RANGES_PCT = [5, 10, 15]
HOLDS_H = [1, 6, 24]
BASE_BLOCKS_PER_H = 1800  # Base chain ~2s blocks


# ============================================================================
# Decoding helpers (mirror R4 / R4B)
# ============================================================================

def decode_v3_swap(data_hex):
    """V3 standard Swap: 5 words of 32 bytes.
    amount0 (int256), amount1 (int256), sqrtPriceX96 (uint160), liquidity (uint128), tick (int24).

    The int24 tick is RIGHT-ALIGNED in the 32-byte word (last 3 bytes), not the leftmost
    3 bytes. So we read p[314:320] (last 6 hex chars = 3 bytes) and sign-extend.
    """
    p = data_hex[2:]  # strip 0x
    a0 = int(p[0:64], 16)
    if a0 & (1 << 255):
        a0 -= (1 << 256)
    a1 = int(p[64:128], 16)
    if a1 & (1 << 255):
        a1 -= (1 << 256)
    sqrt = int(p[128:192], 16)
    liq = int(p[192:256], 16)
    # Tick word is 32 bytes, int24 is the rightmost 3 bytes
    tick_raw = int(p[314:320], 16)
    if tick_raw & (1 << 23):
        tick_raw -= (1 << 24)
    return a0, a1, sqrt, liq, tick_raw


def decode_algebra_swap(data_hex):
    """Algebra V2 Swap: 7 words of 32 bytes = 224 bytes.
    The first 5 words match V3. The last 2 are feeZto and feeOtz (uint128 each)."""
    return decode_v3_swap(data_hex)  # same first 5 words


def load_events(pool_addr, info):
    """Load and decode Swap events. Returns list of dicts with all needed fields."""
    events = []
    with open(info["jsonl"]) as f:
        for line in f:
            ev = json.loads(line)
            if info["abi"] == "v3_standard":
                a0, a1, sqrt, liq, tick = decode_v3_swap(ev["data"])
            else:
                a0, a1, sqrt, liq, tick = decode_algebra_swap(ev["data"])
            a0_h = a0 / 1e18  # WETH
            a1_h = a1 / 1e6   # USDC
            vol_weth_side = abs(a0_h) * ETH_USD
            vol_usdc_side = abs(a1_h)
            vol_usd = max(vol_weth_side, vol_usdc_side)
            events.append({
                "block": ev["block"],
                "amount0_raw": a0,
                "amount1_raw": a1,
                "amount0_human": a0_h,
                "amount1_human": a1_h,
                "sqrtPriceX96": sqrt,
                "liquidity": liq,
                "tick": tick,
                "vol_usd": vol_usd,
                "fee_usd_pool": vol_usd * info["fee_tier"],
            })
    return events


# ============================================================================
# Independent V3 liquidity math
# ============================================================================

def price_to_sqrt_price_x96(price_token1_per_token0):
    """Convert human price (token1 per token0) to sqrtPriceX96.
    For WETH/USDC: price = USDC per WETH (e.g. 1653 for $1653/ETH).
    Formula: sqrtPriceX96 = sqrt(price) * 2^96, where price is in raw units
    (token1_raw / token0_raw). For WETH/USDC the raw price already has the right
    scale, so:
        sqrt(price) * 2^96

    But wait: V3 stores price as token1_raw/token0_raw in their own decimals.
    For WETH (18) / USDC (6): 1 WETH = 1e18 wei, 1653 USDC = 1653 * 1e6 micro-USDC.
    raw_price = (1653e6) / (1e18) = 1.653e-9
    sqrtPriceX96 = sqrt(1.653e-9) * 2^96 = 4.066e-5 * 7.923e28 = 3.222e24 (matches R4)
    """
    return int(math.sqrt(price_token1_per_token0) * Q96)


def sqrt_price_x96_to_price(sqrt_px96, dec0, dec1):
    """Convert sqrtPriceX96 to human price (token1 per token0).
    raw_price = (sqrt_px96 / 2^96)^2
    human_price = raw_price * 10^(dec0 - dec1)
    """
    raw_price = (sqrt_px96 / Q96) ** 2
    return raw_price * (10 ** (dec0 - dec1))


def tick_to_sqrt_price_x96(tick):
    """Convert tick to sqrtPriceX96 in Q64.96.
    price = 1.0001 ** tick
    sqrtPriceX96 = sqrt(1.0001 ** tick) * 2^96

    V3 stores ticks as int24. The price for tick t is 1.0001^t. For typical WETH/USDC
    pools the current tick is around -200000 to +200000 (price in [0.05, 50] USDC/WETH
    for stable pairs, or wider for non-stable). Direct 1.0001^t overflows Python's
    float and is too expensive in Decimal at high precision.

    Use the log/exp decomposition with sufficient precision:
        log(sqrt(1.0001)) = log(1.0001) / 2
        sqrtPriceX96 = 2^96 * exp(tick * log(1.0001) / 2)

    In Q64.96 integer space, this gives a uint160 result.
    """
    # Use float64 for the exponent; this is exact enough for tick math purposes
    # since V3 uses 1.0001^t directly and float64 can represent 1.0001^t to ~15 digits.
    # For t in [-200000, 200000], the relative error is well below the 1-tick rounding.
    log_sqrt_1_0001 = math.log(1.0001) / 2.0
    return int(math.exp(tick * log_sqrt_1_0001) * Q96)


def tick_lower_upper_for_range(current_tick, range_pct):
    """Compute tickLower and tickUpper for a ±range_pct% range.
    In V3, a price change of (1+range_pct/100) corresponds to:
        tick_increment = log(1.0001) / log(1 + range_pct/100) ... no
        actually: ticks for R% range = (log(1+R/100) / log(1.0001))
    For a ±R% range, tickLower = current_tick - delta, tickUpper = current_tick + delta
    Round tickLower down (more conservative) and tickUpper up.
    Tick spacing on Base: Aerodrome 1, PancakeSwap 60 (typical). Use 1 for max precision
    then validate that tickLower/tickUpper are within spacing.
    """
    delta = math.log(1 + range_pct / 100.0) / math.log(1.0001)
    delta = int(math.ceil(delta))
    return current_tick - delta, current_tick + delta


def compute_l_position_independent(size_usd, current_tick, range_pct, dec0, dec1):
    """Compute L_position for a $X position with ±R% range using INDEPENDENT V3 math.

    Steps:
    1. Compute tickLower, tickUpper from current_tick and range_pct.
    2. Compute sqrtP (current), sqrtA (lower), sqrtB (upper) in Q64.96.
    3. Split notional into amount0 and amount1 such that P is at the midpoint
       and total value = size_usd.
       At midpoint: amount0_human * price = size_usd / 2  →  amount0 = (size/2) / price
                    amount1_human = size_usd / 2
       (Roughly: half in WETH, half in USDC by value.)
    4. Convert amounts to raw units: amount0_raw = amount0_human * 10^dec0,
       amount1_raw = amount1_human * 10^dec1.
    5. Compute L_from_amount0 and L_from_amount1.
    6. L_position = min(L_from_amount0, L_from_amount1).

    Note: at the midpoint, L_from_amount0 ≈ L_from_amount1 by construction.
    """
    tick_lower, tick_upper = tick_lower_upper_for_range(current_tick, range_pct)
    sqrt_p = tick_to_sqrt_price_x96(current_tick)
    sqrt_a = tick_to_sqrt_price_x96(tick_lower)
    sqrt_b = tick_to_sqrt_price_x96(tick_upper)

    # Compute human price at current tick
    price_human = sqrt_price_x96_to_price(sqrt_p, dec0, dec1)

    # Split $X into 50% WETH and 50% USDC at midpoint
    amount0_human = (size_usd / 2.0) / price_human  # WETH
    amount1_human = size_usd / 2.0                  # USDC

    # Convert to raw
    amount0_raw = int(amount0_human * (10 ** dec0))
    amount1_raw = int(amount1_human * (10 ** dec1))

    # Sanity: reconstructed value should match size_usd within rounding
    amount0_usd = (amount0_raw / (10 ** dec0)) * price_human
    amount1_usd = amount1_raw / (10 ** dec1)
    reconstructed_usd = amount0_usd + amount1_usd
    recon_error_pct = abs(reconstructed_usd - size_usd) / size_usd * 100.0

    # L_from_amount0 = amount0_raw * sqrtP * sqrtB / ((sqrtB - sqrtP) * 2^96)
    # Use Decimal for high precision.
    with localcontext() as ctx:
        ctx.prec = 80
        if sqrt_b > sqrt_p:
            L_from_amount0 = int(
                (Decimal(amount0_raw) * Decimal(sqrt_p) * Decimal(sqrt_b))
                / (Decimal(sqrt_b - sqrt_p) * Decimal(Q96))
            )
        else:
            L_from_amount0 = 0  # price at or above upper, no token0 in range

        # L_from_amount1 = amount1_raw * 2^96 / (sqrtP - sqrtA)
        if sqrt_p > sqrt_a:
            L_from_amount1 = int(
                (Decimal(amount1_raw) * Decimal(Q96))
                / Decimal(sqrt_p - sqrt_a)
            )
        else:
            L_from_amount1 = 0  # price at or below lower, no token1 in range

    L_position = min(L_from_amount0, L_from_amount1)

    return {
        "tick_lower": tick_lower,
        "tick_upper": tick_upper,
        "sqrt_p": sqrt_p,
        "sqrt_a": sqrt_a,
        "sqrt_b": sqrt_b,
        "price_human": price_human,
        "amount0_raw": amount0_raw,
        "amount1_raw": amount1_raw,
        "amount0_human": amount0_human,
        "amount1_human": amount1_human,
        "amount0_usd": amount0_usd,
        "amount1_usd": amount1_usd,
        "reconstructed_usd": reconstructed_usd,
        "recon_error_pct": recon_error_pct,
        "L_from_amount0": L_from_amount0,
        "L_from_amount1": L_from_amount1,
        "L_position": L_position,
    }


# ============================================================================
# Replay: fee computation with independent L_position
# ============================================================================

def replay_cell(pool_addr, info, size, range_pct, hold_h):
    """Replay one cell with independent L_position math."""
    events = load_events(pool_addr, info)
    if not events:
        return None

    # Filter to events in the hold window
    max_block = max(e["block"] for e in events)
    min_block = max_block - int(hold_h * BASE_BLOCKS_PER_H)
    window_events = [e for e in events if e["block"] >= min_block]
    if not window_events:
        return None

    # Use median event tick as "current" tick (proxy for the position center)
    ticks = sorted(e["tick"] for e in window_events)
    median_tick = ticks[len(ticks) // 2]

    # Independently compute L_position
    lpos = compute_l_position_independent(
        size, median_tick, range_pct, info["decimals0"], info["decimals1"]
    )
    L_position = lpos["L_position"]

    # Median L_event for the in-range events
    L_events = [e["liquidity"] for e in window_events if e["liquidity"] > 0]
    if not L_events:
        return None
    L_events_sorted = sorted(L_events)
    median_L_event = L_events_sorted[len(L_events_sorted) // 2]
    mean_L_event = sum(L_events) / len(L_events)
    L_position_over_median_L_event = L_position / median_L_event if median_L_event > 0 else None

    # R4 / R4B OLD baseline formula (still computed for comparison)
    R = range_pct / 100.0
    l_factor_old = 1.0 / (1.0 - 1.0 / math.sqrt(1.0 + R)) ** 2
    base_share_old = (size / info["tvl_usd"]) * l_factor_old

    # R4B-corrected fee_share denominator (trivial): base_share / (1 + base_share)
    fee_share_r4b_denom_corrected = base_share_old / (1.0 + base_share_old)

    # R4C independent fee share per event
    total_lp_fee_r4c = 0.0
    total_lp_fee_r4b_denom = 0.0  # for comparison
    total_lp_fee_r4_old = 0.0
    total_pool_fee = 0.0
    total_volume = 0.0
    events_in_range = 0
    share_distribution_r4c = []
    share_distribution_r4b = []
    max_share_r4c = 0.0
    aprs = []

    for ev in window_events:
        ev_tick = ev["tick"]
        in_range = (lpos["tick_lower"] <= ev_tick <= lpos["tick_upper"])
        if not in_range:
            continue
        events_in_range += 1

        L_event = ev["liquidity"]
        if L_event == 0:
            continue

        # R4C independent fee share
        fee_share_r4c = L_position / (L_event + L_position)
        share_distribution_r4c.append(fee_share_r4c)
        if fee_share_r4c > max_share_r4c:
            max_share_r4c = fee_share_r4c

        # R4B fee share (just the trivial denom correction)
        fee_share_r4b = fee_share_r4b_denom_corrected
        share_distribution_r4b.append(fee_share_r4b)

        # R4 old fee share (no denom correction)
        fee_share_r4_old = base_share_old

        lp_fee_r4c = ev["fee_usd_pool"] * fee_share_r4c
        lp_fee_r4b = ev["fee_usd_pool"] * fee_share_r4b
        lp_fee_r4_old = ev["fee_usd_pool"] * fee_share_r4_old

        total_lp_fee_r4c += lp_fee_r4c
        total_lp_fee_r4b_denom += lp_fee_r4b
        total_lp_fee_r4_old += lp_fee_r4_old
        total_pool_fee += ev["fee_usd_pool"]
        total_volume += ev["vol_usd"]

    in_range_pct = events_in_range / len(window_events) if window_events else 0.0

    # Daily APR for sanity
    hold_days = hold_h / 24.0
    apr_pct = (total_lp_fee_r4c / size) * (1.0 / hold_days) * 365 * 100.0 if hold_days > 0 else 0.0

    # Proxy fee (R2 model)
    proxy_fee = info["r2_volume_24h"] * info["fee_tier"] * (size / info["tvl_usd"]) * hold_days

    # Capture ratios
    cap_r4c = total_lp_fee_r4c / proxy_fee if proxy_fee > 0 else None
    cap_r4b = total_lp_fee_r4b_denom / proxy_fee if proxy_fee > 0 else None
    cap_r4_old = total_lp_fee_r4_old / proxy_fee if proxy_fee > 0 else None

    # IL estimate
    sigma_pct = 2.0
    R = range_pct / 100.0
    il = size * (sigma_pct / 100.0) ** 2 / (R ** 2) * 0.5 * hold_days

    # Gas
    gas = GAS_CYCLE_USD

    # Net PnL
    net_r4c = total_lp_fee_r4c - il - gas
    net_r4b = total_lp_fee_r4b_denom - il - gas
    net_r4_old = total_lp_fee_r4_old - il - gas

    # Signal/noise
    il_stddev = il * 0.5
    sig_noise_r4c = (total_lp_fee_r4c - il) / il_stddev if il_stddev > 0 else 0
    sig_noise_r4b = (total_lp_fee_r4b_denom - il) / il_stddev if il_stddev > 0 else 0

    # Suspicion flags
    daily_fee_gt_position_size = (total_lp_fee_r4c * (24.0 / hold_h)) > size
    apr_gt_1000pct = apr_pct > 1000.0
    any_share_gt_5pct = any(s > 0.05 for s in share_distribution_r4c) if share_distribution_r4c else False

    # Recommendation
    if net_r4c > 0 and sig_noise_r4c > 1.0 and not daily_fee_gt_position_size and not apr_gt_1000pct:
        rec = "GO_TINY_LIVE_PLAN_ONLY"
    elif net_r4c > 0:
        rec = "NEED_MORE_DATA"  # positive but signal noise low or suspicion flag
    else:
        rec = "NO_GO"

    return {
        "pool": pool_addr,
        "pool_name": info["name"],
        "size_usd": size,
        "range_pct": range_pct,
        "hold_hours": hold_h,
        "median_tick": median_tick,
        "tick_lower": lpos["tick_lower"],
        "tick_upper": lpos["tick_upper"],
        "price_human": lpos["price_human"],
        "amount0_raw": lpos["amount0_raw"],
        "amount1_raw": lpos["amount1_raw"],
        "amount0_usd": lpos["amount0_usd"],
        "amount1_usd": lpos["amount1_usd"],
        "reconstructed_usd": lpos["reconstructed_usd"],
        "recon_error_pct": lpos["recon_error_pct"],
        "L_from_amount0": lpos["L_from_amount0"],
        "L_from_amount1": lpos["L_from_amount1"],
        "L_position": L_position,
        "median_L_event": median_L_event,
        "mean_L_event": mean_L_event,
        "L_position_over_median_L_event": L_position_over_median_L_event,
        "events_total": len(window_events),
        "events_in_range": events_in_range,
        "in_range_pct": in_range_pct,
        "total_volume_usd": total_volume,
        "total_pool_fee_usd": total_pool_fee,
        "fee_usd_r4c": total_lp_fee_r4c,
        "fee_usd_r4b": total_lp_fee_r4b_denom,
        "fee_usd_r4_old": total_lp_fee_r4_old,
        "fee_ratio_r4c_vs_r4b": total_lp_fee_r4c / total_lp_fee_r4b_denom if total_lp_fee_r4b_denom > 0 else None,
        "fee_ratio_r4c_vs_r4_old": total_lp_fee_r4c / total_lp_fee_r4_old if total_lp_fee_r4_old > 0 else None,
        "median_share_r4c_pct": sorted(share_distribution_r4c)[len(share_distribution_r4c) // 2] if share_distribution_r4c else 0,
        "max_share_r4c_pct": max_share_r4c,
        "median_share_r4b_pct": sorted(share_distribution_r4b)[len(share_distribution_r4b) // 2] if share_distribution_r4b else 0,
        "proxy_fee_usd": proxy_fee,
        "capture_ratio_r4c": cap_r4c,
        "capture_ratio_r4b": cap_r4b,
        "capture_ratio_r4_old": cap_r4_old,
        "il_estimate_usd": il,
        "gas_usd": gas,
        "net_pnl_r4c_usd": net_r4c,
        "net_pnl_r4b_usd": net_r4b,
        "net_pnl_r4_old_usd": net_r4_old,
        "signal_noise_r4c": sig_noise_r4c,
        "signal_noise_r4b": sig_noise_r4b,
        "apr_pct": apr_pct,
        "daily_fee_gt_position_size_flag": daily_fee_gt_position_size,
        "apr_gt_1000pct_flag": apr_gt_1000pct,
        "any_share_gt_5pct_flag": any_share_gt_5pct,
        "recommendation": rec,
    }


# ============================================================================
# Validation table
# ============================================================================

def emit_validation_csv(matrix, out_path):
    """Emit the validation table for the 81 cells: prove the math is independent."""
    fields = [
        "pool", "pool_name", "size_usd", "range_pct", "hold_hours",
        "median_tick", "tick_lower", "tick_upper", "price_human",
        "amount0_raw", "amount1_raw", "amount0_usd", "amount1_usd",
        "reconstructed_usd", "recon_error_pct",
        "L_from_amount0", "L_from_amount1", "L_position",
        "median_L_event", "L_position_over_median_L_event",
        "max_share_r4c_pct", "median_share_r4c_pct", "median_share_r4b_pct",
        "validation_pass"
    ]
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(fields)
        for c in matrix:
            # Pass criteria: recon error < 1%, share never > 5%, L_pos > 0
            v_pass = (
                c["recon_error_pct"] < 1.0
                and not c["any_share_gt_5pct_flag"]
                and c["L_position"] > 0
            )
            w.writerow([
                c["pool"], c["pool_name"], c["size_usd"], c["range_pct"], c["hold_hours"],
                c["median_tick"], c["tick_lower"], c["tick_upper"], f"{c['price_human']:.4f}",
                c["amount0_raw"], c["amount1_raw"],
                f"{c['amount0_usd']:.4f}", f"{c['amount1_usd']:.4f}",
                f"{c['reconstructed_usd']:.4f}", f"{c['recon_error_pct']:.4f}",
                c["L_from_amount0"], c["L_from_amount1"], c["L_position"],
                c["median_L_event"],
                f"{c['L_position_over_median_L_event']:.6f}" if c["L_position_over_median_L_event"] is not None else "null",
                f"{c['max_share_r4c_pct']:.6f}",
                f"{c['median_share_r4c_pct']:.6f}",
                f"{c['median_share_r4b_pct']:.6f}",
                "PASS" if v_pass else "FAIL",
            ])
    return fields


# ============================================================================
# Main
# ============================================================================

def main():
    start = time.time()
    print("=" * 80)
    print("R4C — Independent CLMM Liquidity Replay")
    print("=" * 80)
    print()
    print("Inputs: R4 Swap event JSONL files")
    print("Math: V3 canonical LiquidityAmounts formulas")
    print("Outputs: independent 81-cell matrix, validation table, top-candidate diff")
    print()

    # Compute 81 cells
    matrix = []
    for pool_addr, info in POOLS.items():
        for size in SIZES:
            for rng in RANGES_PCT:
                for hold in HOLDS_H:
                    result = replay_cell(pool_addr, info, size, rng, hold)
                    if result is not None:
                        matrix.append(result)

    print(f"Computed {len(matrix)} cells in {time.time() - start:.1f}s")
    print()

    # Print top 5 by R4C net
    sorted_by_net = sorted(matrix, key=lambda c: c["net_pnl_r4c_usd"], reverse=True)
    print("### Top 5 cells by R4C independent net_pnl:")
    for c in sorted_by_net[:5]:
        ratio = c["fee_ratio_r4c_vs_r4b"]
        ratio_str = f"{ratio:.4f}" if ratio is not None else "n/a"
        print(
            f"  {c['pool'][:8]}... ${c['size_usd']} ±{c['range_pct']}% "
            f"{c['hold_hours']}h: R4C fee=${c['fee_usd_r4c']:.4f} "
            f"(R4B ${c['fee_usd_r4b']:.4f}, ratio={ratio_str}) "
            f"R4C net=${c['net_pnl_r4c_usd']:.4f} "
            f"signal/noise={c['signal_noise_r4c']:.2f} "
            f"apr={c['apr_pct']:.0f}% "
            f"rec={c['recommendation']}"
        )
    print()

    # Print top 5 by R4B net
    sorted_by_net_r4b = sorted(matrix, key=lambda c: c["net_pnl_r4b_usd"], reverse=True)
    print("### Top 5 cells by R4B baseline net_pnl (for cross-check):")
    for c in sorted_by_net_r4b[:5]:
        print(
            f"  {c['pool'][:8]}... ${c['size_usd']} ±{c['range_pct']}% "
            f"{c['hold_hours']}h: R4B fee=${c['fee_usd_r4b']:.4f} "
            f"R4C fee=${c['fee_usd_r4c']:.4f} "
            f"net_R4B=${c['net_pnl_r4b_usd']:.4f}"
        )
    print()

    # Summary stats
    ratios = [c["fee_ratio_r4c_vs_r4b"] for c in matrix if c["fee_ratio_r4c_vs_r4b"] is not None]
    if ratios:
        rs = sorted(ratios)
        print(f"### R4C/R4B fee ratio: min={rs[0]:.4f}, median={rs[len(rs)//2]:.4f}, max={rs[-1]:.4f}")
    print()

    rec_counts = {}
    for c in matrix:
        rec_counts[c["recommendation"]] = rec_counts.get(c["recommendation"], 0) + 1
    print(f"### Recommendation distribution: {rec_counts}")
    print()

    # Anomalies
    n_anomalies = sum(
        1 for c in matrix
        if c["daily_fee_gt_position_size_flag"]
        or c["apr_gt_1000pct_flag"]
        or c["recon_error_pct"] > 1.0
    )
    print(f"### Validation anomalies: {n_anomalies}/{len(matrix)} cells flagged suspicious")
    print()

    # Save outputs
    os.makedirs(R4C_DIR, exist_ok=True)

    # Replay matrix CSV
    csv_fields = [
        "pool", "pool_name", "size_usd", "range_pct", "hold_hours",
        "median_tick", "tick_lower", "tick_upper",
        "L_position", "median_L_event", "L_position_over_median_L_event",
        "events_total", "events_in_range", "in_range_pct",
        "total_volume_usd", "total_pool_fee_usd",
        "fee_usd_r4c", "fee_usd_r4b", "fee_usd_r4_old",
        "fee_ratio_r4c_vs_r4b", "fee_ratio_r4c_vs_r4_old",
        "median_share_r4c_pct", "max_share_r4c_pct", "median_share_r4b_pct",
        "proxy_fee_usd",
        "capture_ratio_r4c", "capture_ratio_r4b", "capture_ratio_r4_old",
        "il_estimate_usd", "gas_usd",
        "net_pnl_r4c_usd", "net_pnl_r4b_usd", "net_pnl_r4_old_usd",
        "signal_noise_r4c", "signal_noise_r4b",
        "apr_pct", "daily_fee_gt_position_size_flag", "apr_gt_1000pct_flag",
        "any_share_gt_5pct_flag", "recommendation",
    ]
    with open(f"{R4C_DIR}/independent_clmm_fee_replay_matrix.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(csv_fields)
        for c in matrix:
            row = []
            for fld in csv_fields:
                v = c.get(fld)
                if v is None:
                    row.append("null")
                elif isinstance(v, bool):
                    row.append("true" if v else "false")
                elif isinstance(v, float):
                    row.append(f"{v:.6f}")
                else:
                    row.append(v)
            w.writerow(row)
    print(f"Wrote {R4C_DIR}/independent_clmm_fee_replay_matrix.csv ({len(matrix)} rows)")

    # Replay matrix JSONL
    with open(f"{R4C_DIR}/independent_clmm_fee_replay_matrix.jsonl", "w") as f:
        for c in matrix:
            f.write(json.dumps(c) + "\n")
    print(f"Wrote {R4C_DIR}/independent_clmm_fee_replay_matrix.jsonl")

    # Validation CSV
    emit_validation_csv(matrix, f"{R4C_DIR}/independent_liquidity_position_validation.csv")
    print(f"Wrote {R4C_DIR}/independent_liquidity_position_validation.csv")

    return matrix


if __name__ == "__main__":
    main()
