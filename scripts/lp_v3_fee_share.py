import math

def position_liquidity_raw(size_usd, entry_price, range_pct, dec0=18, dec1=6):
    if entry_price <= 0 or size_usd <= 0:
        return 0.0
    p_lo = entry_price * (1 - range_pct / 100)
    p_hi = entry_price * (1 + range_pct / 100)
    sqrt_p = math.sqrt(entry_price)
    vraw = 2 * sqrt_p - math.sqrt(p_lo) - entry_price / math.sqrt(p_hi)
    if vraw <= 0:
        return 0.0
    return (size_usd / vraw) * 10 ** (dec0 - dec1)


def swap_notional_usd(amount1_raw, dec1=6):
    return abs(amount1_raw) / (10 ** dec1)


def fee_for_swap_usd(l_pos_raw, l_active_raw, amount1_raw, fee_tier=0.0005, dec1=6):
    notional = swap_notional_usd(amount1_raw, dec1)
    denom = l_active_raw + l_pos_raw
    if denom <= 0 or l_pos_raw <= 0:
        return 0.0
    share = l_pos_raw / denom
    return fee_tier * notional * share
