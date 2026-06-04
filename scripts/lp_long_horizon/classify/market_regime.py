"""Market regime classifier (7 regimes + priority order).

Implements the spec from `MARKET_REGIME_CLASSIFIER_SPEC_CN.md` (R0 阶段).
Used by the real-data smoke runner to classify each pool's regime from
the (placeholder / proxy) inputs it has.

The classifier is a pure function: given numeric inputs and a couple of booleans,
it returns one of 7 regime names. It does NOT fetch any external data; callers
are responsible for feeding it real measurements (or honest placeholders).

Priority order (matches spec section 1):
1. low_volatility_stable     (vol_7d < 1%)
2. incentive_period          (LM active OR bribe active; overrides trend)
3. high_volatility_trend     (vol_7d >= 10%)
4. high_volume_sideways      (sideways + vol_tvl_30d >= 1%)
5. uptrend                   (px_change_7d > +5%)
6. downtrend                 (px_change_7d < -5%)
7. sideways                  (default fallback)
"""
from __future__ import annotations

from typing import Final


# Constants per spec section 1
VOL_7D_LOW_THRESHOLD_PCT: Final[float] = 1.0
VOL_7D_HIGH_THRESHOLD_PCT: Final[float] = 10.0
PX_CHANGE_7D_UPTREND_THRESHOLD_PCT: Final[float] = 5.0
PX_CHANGE_7D_DOWNTREND_THRESHOLD_PCT: Final[float] = -5.0
VOL_TVL_30D_HIGH_VOLUME_THRESHOLD_PCT: Final[float] = 1.0


REGIME_LOW_VOLATILITY_STABLE: Final[str] = "low_volatility_stable"
REGIME_INCENTIVE_PERIOD: Final[str] = "incentive_period"
REGIME_HIGH_VOLATILITY_TREND: Final[str] = "high_volatility_trend"
REGIME_HIGH_VOLUME_SIDEWAYS: Final[str] = "high_volume_sideways"
REGIME_UPTREND: Final[str] = "uptrend"
REGIME_DOWNTREND: Final[str] = "downtrend"
REGIME_SIDEWAYS: Final[str] = "sideways"
REGIME_UNKNOWN: Final[str] = "unknown"


PRIORITY_ORDER: Final[tuple[str, ...]] = (
    REGIME_LOW_VOLATILITY_STABLE,
    REGIME_INCENTIVE_PERIOD,
    REGIME_HIGH_VOLATILITY_TREND,
    REGIME_HIGH_VOLUME_SIDEWAYS,
    REGIME_UPTREND,
    REGIME_DOWNTREND,
    REGIME_SIDEWAYS,
)


VALID_REGIMES: Final[frozenset[str]] = frozenset(PRIORITY_ORDER)


def classify_regime(*, realized_vol_7d_pct: float,
                    price_change_7d_pct: float,
                    volume_to_tvl_30d_pct: float,
                    lm_active: bool = False,
                    bribe_active: bool = False) -> str:
    """Classify a market regime per spec.

    Returns one of 7 regime names. Order of checks follows the priority order.

    Parameters
    ----------
    realized_vol_7d_pct:
        7-day realized volatility as a percentage (e.g. 12.3 means 12.3%).
    price_change_7d_pct:
        7-day price change as a percentage (e.g. -8.5 means -8.5%).
    volume_to_tvl_30d_pct:
        30-day volume / TVL ratio as a percentage (e.g. 1.5 means 1.5%).
    lm_active:
        True if the pool's protocol farm program is active.
    bribe_active:
        True if any bribe marketplace for this pool is active.

    Returns
    -------
    str
        One of REGIME_* constants (always).
    """
    # Priority 1: low volatility stable
    if realized_vol_7d_pct < VOL_7D_LOW_THRESHOLD_PCT:
        return REGIME_LOW_VOLATILITY_STABLE

    # Priority 2: incentive period (overrides trend)
    if lm_active or bribe_active:
        return REGIME_INCENTIVE_PERIOD

    # Priority 3: high volatility trend
    if realized_vol_7d_pct >= VOL_7D_HIGH_THRESHOLD_PCT:
        return REGIME_HIGH_VOLATILITY_TREND

    # Priority 4-6: trend buckets
    if price_change_7d_pct > PX_CHANGE_7D_UPTREND_THRESHOLD_PCT:
        return REGIME_UPTREND
    if price_change_7d_pct < PX_CHANGE_7D_DOWNTREND_THRESHOLD_PCT:
        return REGIME_DOWNTREND

    # Priority 7-8: sideways vs high_volume_sideways
    if volume_to_tvl_30d_pct >= VOL_TVL_30D_HIGH_VOLUME_THRESHOLD_PCT:
        return REGIME_HIGH_VOLUME_SIDEWAYS
    return REGIME_SIDEWAYS


def is_valid_regime(name: str) -> bool:
    return name in VALID_REGIMES


def regime_priority_index(name: str) -> int:
    """Return the priority index of a regime (lower = higher priority).

    Returns ``len(PRIORITY_ORDER)`` if the regime name is unknown.
    """
    try:
        return PRIORITY_ORDER.index(name)
    except ValueError:
        return len(PRIORITY_ORDER)


def build_market_regime_row(*, regime: str, lookback_days: int = 7,
                            price_change_pct: float = 0.0,
                            realized_vol_pct: float = 0.0,
                            volume_to_tvl_pct: float = 0.0,
                            incentive_active: bool = False,
                            regime_at: str = "",
                            real_data: bool = True,
                            data_source: str = "real_classifier") -> dict:
    """Build a market_regime record (R0 schema) from a real classifier result."""
    return {
        "regime": regime,
        "lookback_days": lookback_days,
        "price_change_pct": price_change_pct,
        "realized_vol_pct": realized_vol_pct,
        "volume_to_tvl_pct": volume_to_tvl_pct,
        "incentive_active": incentive_active,
        "regime_at": regime_at,
        "real_data": real_data,
        "data_source": data_source,
    }
