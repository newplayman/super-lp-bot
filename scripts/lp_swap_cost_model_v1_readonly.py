"""
lp_swap_cost_model_v1_readonly.py
----------------------------------
READ-ONLY, PURE-MATH module.  No network, no wallet, no side-effects.

Provides depth-aware cost math for a Uniswap V3-style concentrated-liquidity
pool: local price-impact of a swap, effective fee-share dilution, and
roundtrip conversion cost for a position exit.

DECIMAL CONVENTION (CRITICAL – a past bug lived here)
------------------------------------------------------
On-chain V3 liquidity L is in RAW token units: L = sqrt(x_raw * y_raw).
The human<->raw liquidity scale is 10**((dec0+dec1)/2), NOT 10**(dec0-dec1).
See scripts/lp_v3_fee_share.py:position_liquidity_raw for the canonical note.

    human_L = l_raw / 10**((dec0+dec1)/2)

Price P is HUMAN price = token1 per token0 (quote per base).
In human units with human liquidity L_h and human price P:
    x_h = L_h / sqrt(P)       (token0 / base amount)
    y_h = L_h * sqrt(P)       (token1 / quote amount)

V3 LOCAL PRICE-IMPACT MATH (constant-L within the active tick range)
---------------------------------------------------------------------
buy_base  (spending quote to get base / token0) -> RAISES sqrt(P):
    sqrt(P') = sqrt(P) + N_q / L_h

sell_base (selling base / token0 for quote)    -> LOWERS sqrt(P):
    sqrt(P') = sqrt(P) - N_q / L_h

delta_P/P  = (sqrt(P') / sqrt(P))**2 - 1
exec_price = N_q / dx_h   where  dx_h = L_h * (1/sqrt(P) - 1/sqrt(P'))  [abs]
slippage_bps = |P - exec_price| / P * 1e4
"""

import math
import os
import sys
import argparse

# Ensure repo root is on sys.path so `scripts.*` imports resolve correctly
# regardless of how this script is invoked.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ---------------------------------------------------------------------------
# Decimal / human-liquidity helpers
# ---------------------------------------------------------------------------

def human_liquidity(l_raw: float, dec0: int, dec1: int) -> float:
    """Convert raw on-chain liquidity to human-unit liquidity.

    L_human = l_raw / 10**((dec0+dec1)/2)

    This is the CORRECT scale (sqrt(x_raw*y_raw) -> sqrt(x_h*y_h)).
    """
    if l_raw <= 0:
        return 0.0
    return l_raw / (10 ** ((dec0 + dec1) / 2))


# ---------------------------------------------------------------------------
# V3 local price-impact functions
# ---------------------------------------------------------------------------

def swap_new_sqrt_price(
    notional_quote: float,
    l_raw: float,
    price: float,
    dec0: int,
    dec1: int,
    side: str,
) -> float:
    """Return sqrt(P') after a swap of quote-notional *notional_quote*.

    side in {"buy_base", "sell_base"}.
    Raises ValueError for unknown side.
    Clamps result so sqrt(P') > 0.
    """
    if side not in ("buy_base", "sell_base"):
        raise ValueError(f"Unknown side {side!r}; must be 'buy_base' or 'sell_base'")

    if notional_quote <= 0 or l_raw <= 0 or price <= 0:
        return math.sqrt(max(price, 0.0)) if price >= 0 else 0.0

    l_h = human_liquidity(l_raw, dec0, dec1)
    sqrt_p = math.sqrt(price)

    if side == "buy_base":
        sqrt_p_new = sqrt_p + notional_quote / l_h
    else:  # sell_base
        sqrt_p_new = sqrt_p - notional_quote / l_h

    # clamp to a tiny positive value – can't have negative sqrt price
    return max(sqrt_p_new, 1e-30)


def price_impact_frac(
    notional_quote: float,
    l_raw: float,
    price: float,
    dec0: int,
    dec1: int,
    side: str,
) -> float:
    """Return |delta_P/P| as a fraction (0 = zero impact)."""
    if notional_quote <= 0 or l_raw <= 0 or price <= 0:
        return 0.0

    sqrt_p = math.sqrt(price)
    sqrt_p_new = swap_new_sqrt_price(notional_quote, l_raw, price, dec0, dec1, side)
    ratio = sqrt_p_new / sqrt_p
    return abs(ratio ** 2 - 1)


def slippage_bps_for_swap(
    notional_quote: float,
    l_raw: float,
    price: float,
    dec0: int,
    dec1: int,
    side: str,
) -> float:
    """Return slippage in basis-points (>=0) for a swap of *notional_quote* USD.

    Effective average execution price  = N_q / dx_h
        where  dx_h = L_h * |1/sqrt(P) - 1/sqrt(P')|

    slippage_bps = |P - exec_price| / P * 1e4
    """
    if notional_quote <= 0 or l_raw <= 0 or price <= 0:
        return 0.0

    l_h = human_liquidity(l_raw, dec0, dec1)
    sqrt_p = math.sqrt(price)
    sqrt_p_new = swap_new_sqrt_price(notional_quote, l_raw, price, dec0, dec1, side)

    inv_p_diff = abs(1.0 / sqrt_p - 1.0 / sqrt_p_new)
    if inv_p_diff == 0:
        return 0.0

    dx_h = l_h * inv_p_diff
    if dx_h <= 0:
        return 0.0

    exec_price = notional_quote / dx_h
    return abs(price - exec_price) / price * 1e4


# ---------------------------------------------------------------------------
# Fee-share dilution
# ---------------------------------------------------------------------------

def effective_fee_share(
    size_usd: float,
    l_active_raw: float,
    entry_price: float,
    range_pct: float,
    dec0: int,
    dec1: int,
) -> float:
    """Return the position's share of fees in [0, 1).

    Uses scripts.lp_v3_fee_share.position_liquidity_raw to compute l_pos_raw,
    then share = l_pos_raw / (l_active_raw + l_pos_raw).

    At tiny size << pool this approximates the linear size=1 normalisation;
    it saturates correctly as size grows.
    """
    if size_usd <= 0 or l_active_raw <= 0 or entry_price <= 0:
        return 0.0

    from scripts.lp_v3_fee_share import position_liquidity_raw
    l_pos_raw = position_liquidity_raw(size_usd, entry_price, range_pct, dec0, dec1)
    if l_pos_raw <= 0:
        return 0.0

    return l_pos_raw / (l_active_raw + l_pos_raw)


# ---------------------------------------------------------------------------
# Exit conversion cost
# ---------------------------------------------------------------------------

def exit_conversion_cost_usd(
    value_usd: float,
    l_active_raw: float,
    price: float,
    fee_tier: float,
    dec0: int,
    dec1: int,
    side: str = "sell_base",
) -> float:
    """Cost (USD) of converting a whole position *value_usd* back to base in one swap.

    cost = swap_fee + slippage
         = value_usd * fee_tier  +  value_usd * (slippage_bps / 1e4)

    Returns 0.0 for value_usd<=0.
    """
    if value_usd <= 0 or l_active_raw <= 0 or price <= 0:
        return 0.0

    slip_bps = slippage_bps_for_swap(value_usd, l_active_raw, price, dec0, dec1, side)
    return value_usd * fee_tier + value_usd * (slip_bps / 1e4)


def roundtrip_cost_usd(
    size_usd: float,
    l_active_raw: float,
    price: float,
    fee_tier: float,
    dec0: int,
    dec1: int,
) -> float:
    """Entry (buy_base) + exit (sell_base) conversion cost for *size_usd*.

    Returns 0.0 for size_usd<=0.
    """
    if size_usd <= 0 or l_active_raw <= 0 or price <= 0:
        return 0.0

    entry = exit_conversion_cost_usd(size_usd, l_active_raw, price, fee_tier, dec0, dec1, "buy_base")
    exit_ = exit_conversion_cost_usd(size_usd, l_active_raw, price, fee_tier, dec0, dec1, "sell_base")
    return entry + exit_


# ---------------------------------------------------------------------------
# Self-test / CLI
# ---------------------------------------------------------------------------

def run_self_test():
    """Print a tiny cost table and assert monotonicity."""
    # Use WETH/USDC-like params: dec0=18, dec1=6, price~3000, fee_tier=0.0005
    dec0, dec1 = 18, 6
    price = 3000.0
    fee_tier = 0.0005
    range_pct = 5.0

    # Approximate pool liquidity: for a balanced pool near price P,
    # total_usd ~ 2 * L_h * sqrt(P)  =>  L_h ~ total_usd / (2*sqrt(P))
    l_scale = 10 ** ((dec0 + dec1) / 2)

    def pool_l_raw(pool_usd):
        l_h = pool_usd / (2 * math.sqrt(price))
        return l_h * l_scale

    sizes = [100, 1_000, 10_000]
    pools = [("$1M", pool_l_raw(1_000_000)), ("$10M", pool_l_raw(10_000_000))]

    header = f"{'size_usd':>10}  {'pool':>6}  {'slip_bps':>10}  {'roundtrip_usd':>14}  {'fee_share':>10}"
    print(header)
    print("-" * len(header))

    for pool_label, l_raw in pools:
        prev = None
        for sz in sizes:
            slip = slippage_bps_for_swap(sz, l_raw, price, dec0, dec1, "sell_base")
            rt = roundtrip_cost_usd(sz, l_raw, price, fee_tier, dec0, dec1)
            fs = effective_fee_share(sz, l_raw, price, range_pct, dec0, dec1)
            print(f"{sz:>10}  {pool_label:>6}  {slip:>10.4f}  {rt:>14.4f}  {fs:>10.6f}")
            if prev is not None:
                assert slip > prev[0], (
                    f"slippage must increase with size: {prev[0]} >= {slip}"
                )
                assert rt > prev[1], (
                    f"roundtrip must increase with size: {prev[1]} >= {rt}"
                )
                assert fs > prev[2], (
                    f"fee_share must increase with size: {prev[2]} >= {fs}"
                )
            prev = (slip, rt, fs)

    # Larger pool -> less slippage for same size
    for sz in sizes:
        slip_small = slippage_bps_for_swap(sz, pools[0][1], price, dec0, dec1, "sell_base")
        slip_large = slippage_bps_for_swap(sz, pools[1][1], price, dec0, dec1, "sell_base")
        assert slip_large < slip_small, (
            f"deeper pool must have less slippage: {slip_large} >= {slip_small} at size {sz}"
        )

    print("\nAll monotonicity assertions passed.")


def main():
    parser = argparse.ArgumentParser(description="LP swap cost model v1 (read-only)")
    parser.add_argument("--self-test", action="store_true", help="Run built-in self-test and exit")
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        sys.exit(0)
    parser.print_help()


if __name__ == "__main__":
    main()
