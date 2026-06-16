import math


def _range_bounds(entry_price, range_pct):
    return (entry_price * (1 - range_pct / 100), entry_price * (1 + range_pct / 100))


def lp_position_value_usd(size_usd, entry_price, range_pct, current_price):
    if entry_price <= 0 or size_usd <= 0:
        return 0.0
    p_lo, p_hi = _range_bounds(entry_price, range_pct)
    sqrt_lo = math.sqrt(p_lo)
    sqrt_hi = math.sqrt(p_hi)
    sqrt_entry = math.sqrt(entry_price)
    vraw_entry = 2 * sqrt_entry - sqrt_lo - entry_price / sqrt_hi
    k = size_usd / vraw_entry

    if current_price <= p_lo:
        return k * (1 / sqrt_lo - 1 / sqrt_hi) * current_price
    elif current_price >= p_hi:
        return k * (sqrt_hi - sqrt_lo)
    else:
        sqrt_cur = math.sqrt(current_price)
        return k * (2 * sqrt_cur - sqrt_lo - current_price / sqrt_hi)


def lp_hodl_value_usd(size_usd, entry_price, current_price):
    if entry_price <= 0 or size_usd <= 0:
        return 0.0
    return size_usd / 2 + (size_usd / 2) * (current_price / entry_price)


def lp_impermanent_loss_usd(size_usd, entry_price, range_pct, current_price):
    return lp_position_value_usd(size_usd, entry_price, range_pct, current_price) - lp_hodl_value_usd(
        size_usd, entry_price, current_price
    )


def lp_mtm_usd(size_usd, entry_price, range_pct, current_price):
    return lp_position_value_usd(size_usd, entry_price, range_pct, current_price) - size_usd


def lp_weth_amount_eth(size_usd, entry_price, range_pct, current_price):
    """Position's CURRENT WETH holding in ETH units (the LP delta to hedge)."""
    if entry_price <= 0 or size_usd <= 0:
        return 0.0
    p_lo = entry_price * (1 - range_pct / 100)
    p_hi = entry_price * (1 + range_pct / 100)
    vraw = 2 * math.sqrt(entry_price) - math.sqrt(p_lo) - entry_price / math.sqrt(p_hi)
    if vraw <= 0:
        return 0.0
    k = size_usd / vraw
    if current_price <= p_lo:
        return k * (1 / math.sqrt(p_lo) - 1 / math.sqrt(p_hi))
    elif current_price >= p_hi:
        return 0.0
    else:
        return k * (1 / math.sqrt(current_price) - 1 / math.sqrt(p_hi))
